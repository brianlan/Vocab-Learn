"""Reviewable, source-fenced copying of legacy teaching details; never calls a model."""
import hashlib
import json
import os
from pathlib import Path
import re
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from learning import lexical
from learning.models import Card, GenerationJob


def source_digest(card):
    source = {name: getattr(card, name) for name in ["id", "deck_id", "kind", "word", "explanation", "identity",
                                                    "source_version", "target_language", "native_language"]}
    return hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_fields(fields, card):
    original = card.explanation
    if not isinstance(fields, dict) or set(fields) != {"definition", "pronunciations", "synonyms"}:
        raise CommandError("Each record must supply exactly definition, pronunciations and synonyms.")
    if not isinstance(fields["definition"], str) or fields["definition"] not in original:
        raise CommandError("The definition must be extracted verbatim from the original source.")
    if not fields["definition"].strip() and lexical.parts(original)["explanation"].strip():
        job = card.generation_jobs.filter(mode="initial", source_version=card.source_version,
            provenance__has_key="teaching_details").order_by("-requested_at", "-pk").first()
        recorded = lexical.recovered_checkpoint(job.provenance.get("teaching_details"), original) if job else None
        if recorded is None or fields != lexical.columns(recorded):
            raise CommandError("An existing definition cannot be discarded during field migration.")
    readings = fields["pronunciations"]
    if not isinstance(readings, list) or any(
        not isinstance(item, dict) or set(item) != {"ipa", "variety", "label"} or
        any(not isinstance(value, str) for value in item.values()) or
        not re.fullmatch(r"/[^/\n]+/", item["ipa"]) for item in readings):
        raise CommandError("Pronunciations must be a list of IPA, variety and label objects.")
    synonyms = fields["synonyms"]
    if synonyms is not None and (not isinstance(synonyms, list) or any(
            not isinstance(item, str) or not item.strip() for item in synonyms)):
        raise CommandError("Synonyms must be null or a list of nonblank strings.")
    json.dumps(fields, ensure_ascii=False).encode("utf-8")


class Command(BaseCommand):
    help = "Export a private legacy-field plan for review, or apply it without changing sources or learning progress."

    def add_arguments(self, parser):
        parser.add_argument("operation", choices=["export", "apply"])
        parser.add_argument("manifest", type=Path)

    def handle(self, *args, **options):
        try:
            if options["operation"] == "export":
                self.export(options["manifest"])
            else:
                self.apply(options["manifest"])
        except (OSError, ValueError, UnicodeError, TypeError, KeyError) as error:
            raise CommandError("Field migration failed: " + str(error)) from None

    @transaction.atomic
    def export(self, path):
        completions = {job.card_id: job for job in GenerationJob.objects.filter(mode="initial").order_by("requested_at", "pk")
                       if job.provenance.get("definition_completed") or "teaching_details" in job.provenance}
        records = []
        for card in Card.objects.filter(kind="vocabulary", definition__isnull=True).order_by("pk"):
            details = lexical.parts(card.explanation)
            job = completions.get(card.pk)
            if job and job.source_version == card.source_version:
                definition = job.provenance.get("definition")
                generated = definition.get("fields") if isinstance(definition, dict) else None
                candidates = [lexical.recovered_checkpoint(job.provenance.get("teaching_details"), card.explanation),
                              lexical.recovered_details(job.provenance.get("input_explanation"), generated, card.explanation)]
                for recovered in candidates:
                    if recovered is None:
                        continue
                    try:
                        validate_fields(lexical.columns(recovered), card)
                    except (CommandError, UnicodeError):
                        pass
                    else:
                        details = recovered
                        break
            fields = lexical.columns(details)
            validate_fields(fields, card)
            records.append({"id": card.pk, "deck_id": card.deck_id, "word": card.word,
                            "source_sha256": source_digest(card), "fields": fields})
        plan = {"format": "vocabulary-fields-v1", "cards": records}
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(plan, output, ensure_ascii=False, indent=2)
            output.write("\n")
        self.stdout.write(f"Exported {len(records)} cards. Review the manifest before applying; no database rows changed.")

    @transaction.atomic
    def apply(self, path):
        plan = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(plan, dict) or plan.get("format") != "vocabulary-fields-v1" or not isinstance(plan.get("cards"), list):
            raise CommandError("Unsupported field migration manifest.")
        seen, updated, skipped = set(), 0, 0
        for record in plan["cards"]:
            if not isinstance(record, dict) or type(record.get("id")) is not int or record["id"] in seen:
                raise CommandError("Every manifest record must have a unique integer card ID.")
            seen.add(record["id"])
            card = Card.objects.filter(pk=record["id"], kind="vocabulary").first()
            if card is None or record.get("source_sha256") != source_digest(card):
                raise CommandError(f"Card {record['id']}: source changed or unavailable. Export and review a fresh plan.")
            fields = record["fields"]
            validate_fields(fields, card)
            if card.definition is not None:
                if fields != lexical.columns(lexical.details(card)):
                    raise CommandError(f"Card {card.pk}: structured details already differ. Nothing was overwritten.")
                skipped += 1
                continue
            Card.objects.filter(pk=card.pk).update(**fields)
            updated += 1
        self.stdout.write(f"Updated {updated} cards; {skipped} already matched. Sources, progress and history were preserved.")
