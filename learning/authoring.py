import csv
import hashlib
import io
import json
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import Deck, Card, GenerationJob, Presentation, Attempt
from .rendering import render

SCHEMAS = {"generic": ("question", "answer", "explanation"),
           "vocabulary": ("word", "explanation", "native_language", "target_language")}
LANGUAGE_PAIRS = {("English", "Chinese"), ("English", "Spanish"), ("Spanish", "Chinese")}


def validate_source(kind, fields):
    if kind not in SCHEMAS:
        raise ValidationError("Choose Generic or Vocabulary.")
    data = {k: fields.get(k, "") for k in SCHEMAS[kind]}
    if kind == "vocabulary" and data["explanation"] is None:
        data["explanation"] = ""
    if any(not isinstance(v, str) or (not v.strip() and not (kind == "vocabulary" and key == "explanation"))
           for key, v in data.items()):
        raise ValidationError("Required source fields must contain text.")
    try:
        for value in data.values():
            value.encode("utf-8")
    except UnicodeError:
        raise ValidationError("Source fields must contain valid Unicode text.") from None
    if kind == "vocabulary" and (data["target_language"], data["native_language"]) not in LANGUAGE_PAIRS:
        raise ValidationError("Choose different supported target and native languages.")
    return data


def identity(kind, data):
    key = (render(data["question"], data["answer"], True).identity if kind == "generic" else
           [data["word"], render(data["explanation"]).identity, data["target_language"], data["native_language"]])
    return hashlib.sha256(json.dumps([kind, key], ensure_ascii=False).encode()).hexdigest()


def new_generation(card, mode="initial"):
    return GenerationJob.objects.create(card=card, source_version=card.source_version, mode=mode,
        provenance=({"enrich_source": True, "input_identity": card.identity, "input_explanation": card.explanation}
                    if mode == "initial" else {}),
        **({"token": card.rotation_token} if mode == "rotation" else {}))


def initial_inputs(deck):
    return GenerationJob.objects.filter(card__deck=deck, mode="initial", source_version=F("card__source_version"))


def definition_generated(card):
    return card.generation_jobs.filter(source_version=card.source_version, mode="initial",
                                       provenance__definition_generated=True).exists()


def duplicate(deck, kind, data):
    cards = Card.objects.filter(deck=deck, kind=kind)
    if kind == "vocabulary" and not data["explanation"].strip():
        return cards.filter(word=data["word"], target_language=data["target_language"],
                            native_language=data["native_language"]).order_by("pk").first()
    key = identity(kind, data)
    existing = cards.filter(identity=key).first()
    if not existing and kind == "vocabulary":
        job = initial_inputs(deck).filter(provenance__input_identity=key).select_related("card").first()
        existing = job.card if job else None
    return existing


def create_prepared(deck, kind, data):
    card = Card.objects.create(deck=deck, kind=kind, identity=identity(kind, data), ready=kind == "generic", **data)
    if not card.ready:
        new_generation(card)
    return card


@transaction.atomic
def create_card(deck, kind, fields):
    deck = Deck.objects.get(pk=deck.pk)
    if deck.archived:
        raise ValidationError("Restore this deck before changing its sources.")
    data = validate_source(kind, fields)
    existing = duplicate(deck, kind, data)
    return (existing, False) if existing else (create_prepared(deck, kind, data), True)


def invalidate_cards(cards):
    ids = list(cards.values_list("pk", flat=True))
    Presentation.objects.filter(card_id__in=ids).update(invalidated=True)
    Attempt.objects.filter(presentation__card_id__in=ids, state__in=["submitted", "processing", "failed"]).update(
        state="closed_unassessed", error="The source was changed or archived. This attempt cannot change progress.")
    GenerationJob.objects.filter(card_id__in=ids, state__in=["queued", "processing", "failed"]).update(state="cancelled")


@transaction.atomic
def save_card(deck, kind, fields, card=None, *, expected_identity=None):
    deck = Deck.objects.get(pk=deck.pk)
    if deck.archived:
        raise ValidationError("Restore this deck before changing its sources.")
    if card is not None:
        expected_identity = card.identity if expected_identity is None else expected_identity
        card = Card.objects.get(pk=card.pk)
        if card.archived:
            raise ValidationError("Restore this card before changing its source.")
        if card.identity != expected_identity:
            raise ValidationError("This source changed after you opened the form. Reload the page before saving.", code="stale_source")
    data = validate_source(kind, fields)
    key = identity(kind, data)
    existing = duplicate(deck, kind, data)
    if existing and card and existing.pk == card.pk:
        existing = None
    if existing:
        raise ValidationError("This source already exists in this deck, including archived cards.")
    if card is None:
        return create_prepared(deck, kind, data)
    reset = key != card.identity
    if reset:
        invalidate_cards(Card.objects.filter(pk=card.pk))
        card.source_version += 1
        card.progress_version += 1
        card.fsrs, card.review_count = {}, 0
        card.collection, card.streak, card.due = "Normal", 0, timezone.now()
        card.deferred_until = None
        card.active_pair = card.cue_pair = None
        card.cue_direction, card.direction_block, card.direction_index = "", [], 0
        card.rotation_token, card.ready = None, kind == "generic"
    for k, v in data.items():
        setattr(card, k, v)
    card.identity = key
    card.save()
    if reset and not card.ready:
        new_generation(card)
    return card


def read_csv(content, kind):
    if len(content) > 5 * 1024 * 1024:
        raise ValidationError("CSV imports are limited to 5 MB; split this file into smaller batches.")
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        headers = reader.fieldnames or []
        required = set(SCHEMAS[kind]) - ({"explanation"} if kind == "vocabulary" else set())
        if len(headers) != len(set(headers)) or not required <= set(headers) <= set(SCHEMAS[kind]):
            raise ValidationError("Use unique source headers: " + ", ".join(SCHEMAS[kind]) +
                                  (". Vocabulary explanation may be omitted." if kind == "vocabulary" else "."))
        rows = []
        for index, row in enumerate(reader, 2):
            if index > 10001:
                raise ValidationError("CSV imports are limited to 10,000 records.")
            try:
                if None in row or any(v is None for v in row.values()):
                    raise ValidationError("The record has the wrong number of fields.")
                rows.append(validate_source(kind, row))
            except ValidationError as e:
                raise ValidationError(f"CSV record {index}: {' '.join(e.messages)}") from None
        if not rows:
            raise ValidationError("The CSV contains no source records.")
        return rows
    except (UnicodeDecodeError, csv.Error):
        raise ValidationError("Use a valid UTF-8 CSV with standard quoting and complete records.") from None


def import_csv(deck, kind, content):
    prepared = [(data, identity(kind, data)) for data in read_csv(content, kind)]
    with transaction.atomic():
        deck = Deck.objects.get(pk=deck.pk)
        if deck.archived:
            raise ValidationError("Restore this deck before importing.")
        keys = set(Card.objects.filter(deck=deck).values_list("identity", flat=True))
        if kind == "vocabulary":
            keys.update(key for key in initial_inputs(deck).values_list("provenance__input_identity", flat=True) if key)
        expressions = set(Card.objects.filter(deck=deck, kind="vocabulary").values_list("word", "target_language", "native_language"))
        created, skipped = 0, 0
        for data, key in prepared:
            expression = (data.get("word"), data.get("target_language"), data.get("native_language"))
            if key in keys or (kind == "vocabulary" and not data["explanation"].strip() and expression in expressions):
                skipped += 1
                continue
            create_prepared(deck, kind, data)
            keys.add(key)
            expressions.add(expression)
            created += 1
    return created, skipped


@transaction.atomic
def archive_card(card, archived):
    if archived:
        invalidate_cards(Card.objects.filter(pk=card.pk))
    Card.objects.filter(pk=card.pk).update(archived=archived)


@transaction.atomic
def archive_deck(deck, archived):
    if archived:
        invalidate_cards(Card.objects.filter(deck=deck))
    deck.archived = archived
    deck.save(update_fields=["archived"])
