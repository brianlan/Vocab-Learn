import io
import json
import os
from itertools import product
from pathlib import Path
import tempfile
from unittest.mock import patch
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from learning import api, authoring, lexical, providers, review, work
from learning.models import Card, Deck, GenerationJob, ScoredReview


RIVER = "A **bank** is the ground alongside a river.\n\n```text\nThe muddy bank was steep."
READINGS = [{"ipa": "/bæŋk/", "variety": "US", "label": "noun"}]
SYNONYMS = ["riverbank", "shore"]
FOOTER = "\n\nSynonyms: riverbank; shore"
PREFIX = "/bæŋk/ (US; noun):\n\n"
RIVER_PAIR = {"target_sentence": "The muddy <focus>bank</focus> was steep.", "native_sentence": "这处泥泞的<focus>河岸</focus>很陡。"}
FINANCE_PAIR = {"target_sentence": "She went to the <focus>bank</focus> to get some money.", "native_sentence": "她去<focus>银行</focus>取钱。"}
LANGUAGES = {"target_language": "English", "native_language": "Chinese"}


class CompletionSourceTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("learner")
        self.browser = Client(enforce_csrf_checks=True)
        self.browser.force_login(self.owner)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        for mock in [patch.dict(os.environ, {"MINIMAX_API_KEY": "test-only"}),
                     patch("learning.providers.request", side_effect=AssertionError("No provider network calls"))]:
            mock.start(); self.addCleanup(mock.stop)

    def deck(self):
        return Deck.objects.create(owner=self.owner, name="Private")

    def prepare(self, card, generated, pair=RIVER_PAIR):
        _, job_id, claim, _ = work.claim_work()
        calls = {}
        def answer(profile, system, payload):
            calls[profile.task] = payload
            return {name: generated[name] for name in payload["requested_fields"]} if profile.task == "DEFINITION" else pair
        with patch("learning.providers.chat", side_effect=answer):
            work.process_generation(job_id, claim)
        card.refresh_from_db()
        self.assertTrue(card.ready)
        return calls

    def edit(self, card, explanation):
        url = reverse("card_edit", args=[card.deck_id, card.pk])
        response = self.browser.get(url)
        form = response.context["form"]
        payload = {name: form[name].value() for name in authoring.SCHEMAS["vocabulary"]}
        payload.update(explanation=explanation, source_identity=form["source_identity"].value(),
                       csrfmiddlewaretoken=self.browser.cookies["csrftoken"].value)
        self.assertEqual(self.browser.post(url, payload).status_code, 302)
        card.refresh_from_db()

    def legacy(self, original, generated, saved, typed=False):
        deck = self.deck()
        data = {**LANGUAGES, "word": "bank", "explanation": saved}
        card = Card.objects.create(deck=deck, kind="vocabulary", ready=False,
                                   identity=authoring.identity("vocabulary", data), **data)
        GenerationJob.objects.create(card=card, source_version=1, state="done", provenance={
            "input_explanation": original, "definition_completed": True, "definition": {"fields": generated}})
        if typed:
            Card.objects.filter(pk=card.pk).update(definition=RIVER, pronunciations=READINGS, synonyms=SYNONYMS)
            card.refresh_from_db()
        return card

    def manifest(self):
        path = Path(self.folder.name) / "reviewed.json"
        call_command("vocabulary_fields", "export", str(path), stdout=io.StringIO())
        plan = json.loads(path.read_text())
        call_command("vocabulary_fields", "apply", str(path), stdout=io.StringIO())
        return plan

    def test_unclosed_completion_formatting_clear_and_recompletion(self):
        for fence, newline, format_first in product(["```", "~~~"], ["\n", "\r\n"], [False, True]):
            with self.subTest(fence=fence, newline=newline, format_first=format_first):
                original = RIVER.replace("```", fence).replace("\n", newline)
                card, _ = authoring.create_card(self.deck(), "vocabulary", {**LANGUAGES, "word": "bank", "explanation": original})
                initial = {"explanation": original, "pronunciations": READINGS, "synonyms": SYNONYMS}
                self.prepare(card, initial)
                self.assertEqual(card.definition, original)
                review.submit(review.next_question(self.owner, card.deck), "forgot")
                card.refresh_from_db()
                history = list(ScoredReview.objects.filter(card=card).values())
                if format_first:
                    before = Card.objects.values().get(pk=card.pk)
                    self.edit(card, card.explanation.replace("ground", "**ground**"))
                    after = Card.objects.values().get(pk=card.pk)
                    self.assertEqual({k: v for k, v in after.items() if k not in {"explanation", "definition"}},
                                     {k: v for k, v in before.items() if k not in {"explanation", "definition"}})
                    self.assertEqual(card.definition, original.replace("ground", "**ground**"))
                self.edit(card, " \n ")
                self.assertEqual((card.definition, card.pronunciations, card.synonyms), ("", [], None))
                self.assertEqual(card.source_version, 2)
                fresh = {"explanation": "A **bank** is a business where people keep or borrow money.",
                         "pronunciations": READINGS, "synonyms": ["financial institution"]}
                calls = self.prepare(card, fresh, FINANCE_PAIR)
                self.assertEqual(calls["DEFINITION"]["requested_fields"], ["explanation", "pronunciations", "synonyms"])
                self.assertEqual(calls["GENERATOR"]["synonyms"], fresh["synonyms"])
                self.assertEqual(card.synonyms, fresh["synonyms"])
                self.assertEqual(list(ScoredReview.objects.filter(card=card).values()), history)

    def test_legacy_unclosed_export_restores_complete_components(self):
        generated = {"pronunciations": READINGS, "synonyms": SYNONYMS}
        variants = [(RIVER, generated, PREFIX + RIVER + FOOTER),
                    (RIVER, generated, PREFIX.replace(":\n\n", ": ") + RIVER + FOOTER),
                    ("/bæŋk/ : " + RIVER, {"synonyms": SYNONYMS}, "/bæŋk/ : " + RIVER + FOOTER),
                    ("", {"explanation": RIVER, **generated}, PREFIX + RIVER + FOOTER),
                    (RIVER, generated, PREFIX + RIVER)]
        cards = [self.legacy(original, fields, saved) for original, fields, saved in variants]
        before = {card.pk: Card.objects.values().get(pk=card.pk) for card in cards}
        plan = self.manifest()
        for card in cards:
            with self.subTest(card=card.pk):
                card.refresh_from_db()
                self.assertEqual(card.definition, RIVER)
                self.assertEqual(card.synonyms, SYNONYMS)
                old = before[card.pk]
                now = Card.objects.values().get(pk=card.pk)
                self.assertEqual({k: v for k, v in now.items() if k not in {"definition", "pronunciations", "synonyms"}},
                                 {k: v for k, v in old.items() if k not in {"definition", "pronunciations", "synonyms"}})
        self.assertEqual(len(plan["cards"]), 5)

    def test_legacy_synonyms_definition_exports_the_whole_batch(self):
        original = "Synonyms: words or phrases with the same or similar meanings."
        fields = {"pronunciations": READINGS, "synonyms": ["equivalent terms"]}
        old = self.legacy(original, fields, PREFIX + original + "\n\nSynonyms: equivalent terms")
        healthy = self.legacy("A useful definition.", {}, "A useful definition.")
        self.assertEqual(lexical.parts(original)["explanation"], original)
        plan = self.manifest()
        old.refresh_from_db(); healthy.refresh_from_db()
        self.assertEqual(old.definition, original)
        self.assertEqual(old.synonyms, ["equivalent terms"])
        self.assertEqual(healthy.definition, "A useful definition.")
        self.assertEqual(len(plan["cards"]), 2)

    def test_unreplayable_provenance_falls_back_to_the_saved_source(self):
        saved = "/x/: The current definition. [synonyms: current]"
        records = [({}, ""), ({"pronunciations": None}, "A supplied definition."),
                   ({"synonyms": ["stale metadata"]}, "An older definition."),
                   (None, "A supplied definition.")]
        cards = [self.legacy(original, fields, saved) for fields, original in records]
        for metadata in [None, "an older unsupported profile"]:
            card = self.legacy("A supplied definition.", {}, saved)
            job = card.generation_jobs.get()
            job.provenance["definition"] = metadata
            job.save(update_fields=["provenance"])
            cards.append(card)
        self.manifest()
        for card in cards:
            card.refresh_from_db()
            self.assertEqual(card.definition, "The current definition.")
            self.assertEqual(card.synonyms, ["current"])

    def test_checkpoint_keeps_explicit_empty_and_unserialized_metadata(self):
        cards = []
        for synonyms in [None, [], ["none"], ["no, thank you"]]:
            card = self.legacy(RIVER, {}, PREFIX + RIVER)
            details = {"explanation": RIVER, "pronunciations": READINGS, "synonyms": synonyms}
            job = card.generation_jobs.get()
            job.provenance["teaching_details"] = {"source": card.explanation, "details": details}
            job.save(update_fields=["provenance"])
            cards.append((card, details))
        self.manifest()
        for card, details in cards:
            card.refresh_from_db()
            self.assertEqual(lexical.details(card), details)

    def test_invalid_or_stale_checkpoints_fall_back_without_overriding_sources(self):
        details = {"explanation": RIVER, "pronunciations": READINGS, "synonyms": SYNONYMS}
        checkpoint = {"source": PREFIX + RIVER, "details": details}
        variants = [None, "old format", {}, {**checkpoint, "source": None},
                    {**checkpoint, "source": PREFIX + RIVER.replace("river", "lake")},
                    {**checkpoint, "details": {**details, "explanation": "Invented definition."}},
                    {**checkpoint, "details": {**details, "synonyms": 42}},
                    {**checkpoint, "details": {**details, "pronunciations": None}}]
        cards = []
        for value in variants:
            card = self.legacy(RIVER, {"pronunciations": READINGS, "synonyms": SYNONYMS}, PREFIX + RIVER)
            job = card.generation_jobs.get()
            job.provenance["teaching_details"] = value
            job.save(update_fields=["provenance"])
            cards.append(card)
        stale = self.legacy(RIVER, {}, PREFIX + RIVER)
        job = stale.generation_jobs.get()
        job.source_version = 2
        job.provenance["teaching_details"] = checkpoint
        job.save(update_fields=["source_version", "provenance"])
        self.manifest()
        for card in cards:
            card.refresh_from_db()
            self.assertEqual(lexical.details(card), details)
        stale.refresh_from_db()
        self.assertEqual(stale.definition, RIVER)
        self.assertIsNone(stale.synonyms)

    def test_legacy_unclosed_edits_keep_known_component_boundaries(self):
        variants = [("ground", "**ground**", {"explanation": RIVER.replace("ground", "**ground**")}),
                    ("Synonyms: riverbank; shore", "Synonyms: riverside", {"synonyms": ["riverside"]}),
                    ("/bæŋk/ (US; noun)", "/y/ (UK; noun)", {"pronunciations": [{"ipa": "/y/", "variety": "UK", "label": "noun"}]}),
                    (FOOTER, "", {"synonyms": None})]
        for old, new, updated in variants:
            with self.subTest(updated=updated):
                card = self.legacy(RIVER, {"pronunciations": READINGS, "synonyms": SYNONYMS}, PREFIX + RIVER + FOOTER, typed=True)
                self.edit(card, card.explanation.replace(old, new))
                self.assertEqual(lexical.details(card), {"explanation": RIVER, "pronunciations": READINGS, "synonyms": SYNONYMS, **updated})

    def test_consecutive_legacy_metadata_and_formatting_edits_keep_actual_boundaries(self):
        variants = [("Synonyms: riverside, shore", ["riverside", "shore"]),
                    ("[synonyms: riverside, shore]", ["riverside", "shore"]),
                    ("[synonyms: ]", [])]
        for (footer, synonyms), fence, newline in product(variants, ["```", "~~~"], ["\n", "\r\n"]):
            with self.subTest(footer=footer, fence=fence, newline=newline):
                original = RIVER.replace("```", fence).replace("\n", newline)
                saved = (PREFIX + RIVER + FOOTER).replace("```", fence).replace("\n", newline)
                card = self.legacy(original, {"pronunciations": READINGS, "synonyms": SYNONYMS}, saved, typed=True)
                Card.objects.filter(pk=card.pk).update(definition=original)
                card.refresh_from_db()
                self.edit(card, (PREFIX + original + "\n\n" + footer).replace("\r\n", "\n").replace("\n", newline))
                expected = {"explanation": original, "pronunciations": READINGS, "synonyms": synonyms}
                self.assertEqual(lexical.details(card), expected)
                calls = self.prepare(card, expected)
                self.assertNotIn("DEFINITION", calls)
                review.submit(review.next_question(self.owner, card.deck), "forgot")
                card.refresh_from_db()
                before = Card.objects.values().get(pk=card.pk)
                jobs = list(card.generation_jobs.values())
                history = list(ScoredReview.objects.filter(card=card).values())
                self.edit(card, card.explanation.replace("ground", "**ground**"))
                expected["explanation"] = original.replace("ground", "**ground**")
                self.assertEqual(lexical.details(card), expected)
                self.assertEqual(api.representation(card)["definition"], expected["explanation"])
                before.update(explanation=card.explanation, definition=card.definition)
                self.assertEqual(Card.objects.values().get(pk=card.pk), before)
                self.assertEqual(list(card.generation_jobs.values()), jobs)
                self.assertEqual(list(ScoredReview.objects.filter(card=card).values()), history)

    def test_ambiguous_legacy_edit_is_rejected_without_changing_data(self):
        card = self.legacy(RIVER, {"pronunciations": READINGS, "synonyms": SYNONYMS}, PREFIX + RIVER + FOOTER, typed=True)
        before = Card.objects.values().get(pk=card.pk)
        jobs = list(GenerationJob.objects.values())
        new = card.explanation.replace("ground", "land near the water").replace("riverbank; shore", "riverside")
        with self.assertRaisesMessage(ValidationError, "Markdown fence"):
            authoring.save_card(card.deck, "vocabulary", {**LANGUAGES, "word": card.word, "explanation": new}, card)
        self.assertEqual(Card.objects.values().get(pk=card.pk), before)
        self.assertEqual(list(GenerationJob.objects.values()), jobs)

    def test_serialization_does_not_append_metadata_inside_markdown(self):
        for definition in [RIVER, RIVER.replace("```", "~~~"), "A definition.\n\n<script>\nAn unfinished HTML block."]:
            for supplied in [True, False]:
                with self.subTest(definition=definition, supplied=supplied):
                    fields = {"pronunciations": READINGS, "synonyms": SYNONYMS}
                    if not supplied:
                        fields["explanation"] = definition
                    text = lexical.combine(definition if supplied else "", fields)
                    self.assertEqual(lexical.parts(text)["explanation"], definition)
                    self.assertNotIn("Synonyms: riverbank", text)


class CompletionRecoveryTests(TransactionTestCase):
    def test_each_source_revision_recovers_after_actual_schema_rollback_and_fresh_export(self):
        owner = get_user_model().objects.create_user("learner")
        target = "0010_structured_vocabulary_details"
        generated = {"explanation": RIVER, "pronunciations": READINGS, "synonyms": SYNONYMS}

        def prepare(card):
            _, job_id, claim, _ = work.claim_work()
            def answer(profile, system, payload):
                return ({name: generated[name] for name in payload["requested_fields"]}
                        if profile.task == "DEFINITION" else RIVER_PAIR)
            with patch("learning.providers.chat", side_effect=answer):
                work.process_generation(job_id, claim)
            card.refresh_from_db()
            self.assertTrue(card.ready)

        def snapshot():
            return {model.__name__: list(model.objects.order_by("pk").values())
                    for model in apps.get_app_config("learning").get_models()}

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"MINIMAX_API_KEY": "test-only"}), patch(
                "learning.providers.request", side_effect=AssertionError("No provider network calls")):
            for stage in ["queued", "ready", "formatted", "legacy"]:
                with self.subTest(stage=stage):
                    deck = Deck.objects.create(owner=owner, name=stage)
                    source = {**LANGUAGES, "word": "bank", "explanation": RIVER}
                    card, _ = authoring.create_card(deck, "vocabulary", source)
                    prepare(card)
                    self.assertNotIn("Synonyms:", card.explanation)
                    if stage == "legacy":
                        old_source = {**source, "explanation": PREFIX + RIVER + FOOTER}
                        Card.objects.filter(pk=card.pk).update(explanation=old_source["explanation"],
                            identity=authoring.identity("vocabulary", old_source))
                        card.refresh_from_db()
                    review.submit(review.next_question(owner, deck), "forgot")
                    card.refresh_from_db()
                    changed = (card.explanation.replace("riverbank; shore", "riverside, shore") if stage == "legacy"
                               else card.explanation.replace("muddy", "grassy"))
                    authoring.save_card(deck, "vocabulary", {**source, "explanation": changed}, card)
                    card.refresh_from_db()
                    self.assertEqual(card.source_version, 2)
                    if stage != "queued":
                        prepare(card)
                        review.submit(review.next_question(owner, deck), "forgot")
                        card.refresh_from_db()
                    if stage in ["formatted", "legacy"]:
                        authoring.save_card(deck, "vocabulary", {**source, "explanation": card.explanation.replace("ground", "**ground**")}, card)
                        card.refresh_from_db()
                    before = snapshot()
                    ordinary = Path(folder) / (stage + "-ordinary.json")
                    call_command("vocabulary_fields", "export", str(ordinary), stdout=io.StringIO())
                    self.assertEqual(json.loads(ordinary.read_text())["cards"], [])
                    try:
                        call_command("migrate", "learning", "0009", verbosity=0, interactive=False)
                        call_command("migrate", "learning", target, verbosity=0, interactive=False)
                        path = Path(folder) / (stage + "-fresh.json")
                        call_command("vocabulary_fields", "export", str(path), stdout=io.StringIO())
                        fields = json.loads(path.read_text())["cards"][0]["fields"]
                        self.assertEqual(fields, lexical.columns(lexical.details(card)))
                        call_command("vocabulary_fields", "apply", str(path), stdout=io.StringIO())
                        self.assertEqual(snapshot(), before)
                    finally:
                        call_command("migrate", "learning", target, verbosity=0, interactive=False)
                        deck.delete()
