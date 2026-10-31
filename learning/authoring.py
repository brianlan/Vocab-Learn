import csv
import hashlib
import io
import json
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
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
    if any(not isinstance(v, str) or not v.strip() for v in data.values()):
        raise ValidationError("Every source field is required.")
    if kind == "vocabulary" and (data["target_language"], data["native_language"]) not in LANGUAGE_PAIRS:
        raise ValidationError("Choose different supported target and native languages.")
    return data


def identity(kind, data):
    key = (render(data["question"], data["answer"], True).identity if kind == "generic" else
           [data["word"], render(data["explanation"]).identity, data["target_language"], data["native_language"]])
    return hashlib.sha256(json.dumps([kind, key], ensure_ascii=False).encode()).hexdigest()


def new_generation(card, mode="initial"):
    now = timezone.now()
    return GenerationJob.objects.create(card=card, source_version=card.source_version, mode=mode,
        **({"token": card.rotation_token} if mode == "rotation" else {}), requested_at=now,
        deadline=now + timedelta(seconds=settings.GENERATION_TIMEOUT_SECONDS))


def invalidate_cards(cards):
    ids = list(cards.values_list("pk", flat=True))
    Presentation.objects.filter(card_id__in=ids).update(invalidated=True)
    Attempt.objects.filter(presentation__card_id__in=ids, state__in=["submitted", "processing", "failed"]).update(
        state="closed_unassessed", error="The source was changed or archived. This attempt cannot change progress.")
    GenerationJob.objects.filter(card_id__in=ids, state__in=["queued", "processing", "failed"]).update(state="cancelled")


@transaction.atomic
def save_card(deck, kind, fields, card=None):
    deck = Deck.objects.get(pk=deck.pk)
    if deck.archived:
        raise ValidationError("Restore this deck before changing its sources.")
    data = validate_source(kind, fields)
    key = identity(kind, data)
    existing = Card.objects.filter(deck=deck, identity=key).exclude(pk=card.pk if card else None).first()
    if existing:
        raise ValidationError("This source already exists in this deck, including archived cards.")
    if card is None:
        card = Card.objects.create(deck=deck, kind=kind, identity=key, ready=kind == "generic", **data)
        if not card.ready:
            new_generation(card)
        return card
    card = Card.objects.get(pk=card.pk)
    if card.archived:
        raise ValidationError("Restore this card before changing its source.")
    reset = key != card.identity
    if reset:
        invalidate_cards(Card.objects.filter(pk=card.pk))
        card.source_version += 1
        card.progress_version += 1
        card.fsrs, card.review_count = {}, 0
        card.collection, card.streak, card.due = "Normal", 0, timezone.now()
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
        if len(reader.fieldnames or []) != len(SCHEMAS[kind]) or set(reader.fieldnames or []) != set(SCHEMAS[kind]):
            raise ValidationError("Use exactly these unique headers: " + ", ".join(SCHEMAS[kind]) + ".")
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
        created, skipped = 0, 0
        for data, key in prepared:
            if key in keys:
                skipped += 1
                continue
            card = Card.objects.create(deck=deck, kind=kind, identity=key, ready=kind == "generic", **data)
            if not card.ready:
                new_generation(card)
            keys.add(key)
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
