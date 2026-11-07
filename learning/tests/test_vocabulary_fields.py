import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse
from learning import api, authoring, lexical, providers, review
from learning.models import Card, Deck, ExamplePair, GenerationJob, Presentation, Attempt, ScoredReview
from learning.rendering import render


SOURCE = {"word": "absorb", "explanation": "/əbˈzɔrb/ (US; verb (transitive)):\n\n## Meaning\n\nTake in liquid.\n\nSynonyms: soak up",
          "target_language": "English", "native_language": "Chinese"}
PAIR = {"target_sentence": "The sponge <focus>absorbed</focus> the water.",
        "native_sentence": "海绵<focus>吸收</focus>了水。"}


class VocabularyFieldsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("learner")
        self.deck = Deck.objects.create(owner=self.user, name="Private")
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "fields.json"

    def legacy(self, **overrides):
        data = {**SOURCE, **overrides}
        card = Card.objects.create(deck=self.deck, kind="vocabulary", **data,
                                   identity=authoring.identity("vocabulary", data))
        pair = ExamplePair.objects.create(card=card, source_version=1,
                                          **providers.validate_pair(PAIR, "absorb", "Chinese"))
        card.active_pair = pair
        card.save(update_fields=["active_pair"])
        return card

    def export(self):
        call_command("vocabulary_fields", "export", str(self.path), stdout=io.StringIO())
        return json.loads(self.path.read_text())

    def apply(self, plan=None):
        if plan is not None:
            self.path.write_text(json.dumps(plan))
        call_command("vocabulary_fields", "apply", str(self.path), stdout=io.StringIO())

    def snapshot(self):
        return {model.__name__: list(model.objects.order_by("pk").values()) for model in
                [Card, Deck, ExamplePair, GenerationJob, Presentation, Attempt, ScoredReview]}

    def test_reviewed_backfill_is_idempotent_and_preserves_progress_and_frozen_history(self):
        card = self.legacy()
        held = review.next_question(self.user, self.deck)
        held.snapshot["explanation"] = card.explanation
        held.snapshot.pop("pronunciations"); held.snapshot.pop("synonyms")
        held.save(update_fields=["snapshot"])
        review.submit(held, "forgot")
        before = self.snapshot()
        plan = self.export()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(plan["cards"][0]["fields"], {
            "definition": "## Meaning\n\nTake in liquid.",
            "pronunciations": [{"ipa": "/əbˈzɔrb/", "variety": "US", "label": "verb (transitive)"}],
            "synonyms": ["soak up"]})
        with patch("learning.providers.request", side_effect=AssertionError("No model calls during migration")):
            self.apply()
            after = self.snapshot()
            self.apply()
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(after["Card"][0].pop("definition"), plan["cards"][0]["fields"]["definition"])
        after["Card"][0].pop("pronunciations"); after["Card"][0].pop("synonyms")
        before["Card"][0].pop("definition"); before["Card"][0].pop("pronunciations"); before["Card"][0].pop("synonyms")
        self.assertEqual(after, before)
        card.refresh_from_db()
        self.assertEqual((card.collection, card.review_count), ("Forgot", 1))
        self.assertEqual(authoring.create_card(self.deck, "vocabulary", SOURCE), (card, False))
        self.assertEqual(authoring.create_card(self.deck, "vocabulary", {**SOURCE, "explanation": ""}), (card, False))

    def test_unknown_synonyms_and_explicit_no_synonyms_remain_distinct(self):
        unknown = self.legacy(explanation="/x/: Take in liquid.")
        none = self.legacy(word="other", explanation="/x/: A different meaning. [synonyms: ]")
        self.export(); self.apply()
        unknown.refresh_from_db(); none.refresh_from_db()
        self.assertIsNone(unknown.synonyms)
        self.assertEqual(none.synonyms, [])
        self.assertEqual(lexical.missing(lexical.details(unknown)), ["synonyms"])
        self.assertEqual(lexical.missing(lexical.details(none)), [])

    def test_changed_source_rolls_back_the_whole_manifest(self):
        first = self.legacy()
        second = self.legacy(word="different")
        self.export()
        Card.objects.filter(pk=second.pk).update(explanation="A newer meaning.")
        before = self.snapshot()
        with self.assertRaisesMessage(CommandError, "source changed"):
            self.apply()
        self.assertEqual(self.snapshot(), before)
        first.refresh_from_db(); self.assertIsNone(first.definition)

    def test_already_populated_details_cannot_be_overwritten_by_an_old_plan(self):
        card = self.legacy()
        self.export()
        Card.objects.filter(pk=card.pk).update(definition="Take in liquid.", synonyms=["newer metadata"])
        before = self.snapshot()
        with self.assertRaisesMessage(CommandError, "already differ"):
            self.apply()
        self.assertEqual(self.snapshot(), before)

    def test_manifest_validation_rejects_rewrites_missing_data_and_duplicate_ids(self):
        self.legacy()
        original = self.export()
        for mutation in [
            {"definition": "An invented new sense."}, {"definition": ""},
            {"pronunciations": "not a list"}, {"synonyms": [12]}, {"synonyms": [""]},
        ]:
            plan = json.loads(json.dumps(original))
            plan["cards"][0]["fields"].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(CommandError):
                self.apply(plan)
            self.assertIsNone(Card.objects.get().definition)
        original["cards"].append(original["cards"][0])
        with self.assertRaisesMessage(CommandError, "unique integer"):
            self.apply(original)
        self.assertIsNone(Card.objects.get().definition)

    def test_export_never_overwrites_a_reviewed_manifest(self):
        self.legacy()
        self.export()
        content = self.path.read_bytes()
        with self.assertRaises(CommandError):
            self.export()
        self.assertEqual(self.path.read_bytes(), content)

    def test_completed_structured_provenance_is_used_without_reserializing_its_labels(self):
        generated = {"explanation": "Take in liquid.",
                     "pronunciations": [{"ipa": "/x/", "variety": "US", "label": "verb\n(transitive)"}],
                     "synonyms": ["soak up"]}
        card = self.legacy(explanation=lexical.combine("", generated))
        GenerationJob.objects.create(card=card, source_version=1, state="done", provenance={
            "input_explanation": "", "definition_completed": True, "definition": {"fields": generated}})
        plan = self.export()
        self.assertEqual(plan["cards"][0]["fields"], lexical.columns(generated))
        self.apply()
        card.refresh_from_db()
        self.assertEqual(card.pronunciations, generated["pronunciations"])

    def test_new_snapshots_and_api_use_structured_fields_but_held_questions_stay_frozen(self):
        card = self.legacy()
        held = review.next_question(self.user, self.deck)
        held.snapshot["explanation"] = card.explanation
        held.snapshot.pop("pronunciations"); held.snapshot.pop("synonyms")
        held.save(update_fields=["snapshot"])
        frozen = held.snapshot.copy()
        self.export(); self.apply()
        resumed = review.next_question(self.user, self.deck)
        self.assertEqual(resumed.pk, held.pk)
        self.assertEqual(resumed.snapshot, frozen)
        card.refresh_from_db()
        new = review.snapshot(card)
        self.assertEqual(new["explanation"], card.definition)
        self.assertNotIn("Synonyms:", new["explanation"])
        self.assertEqual(new["synonyms"], ["soak up"])
        self.assertEqual(new["pronunciations"], card.pronunciations)
        data = api.representation(card)
        self.assertEqual(data["definition"], card.definition)
        self.assertEqual(data["explanation"], SOURCE["explanation"])
        self.assertEqual(data["synonyms"], card.synonyms)

    def test_older_completion_without_original_input_uses_the_saved_text(self):
        card = self.legacy()
        GenerationJob.objects.create(card=card, source_version=1, state="done", provenance={
            "definition_completed": True, "definition": {"fields": {"synonyms": ["different older metadata"]}}})
        plan = self.export()
        self.assertEqual(plan["cards"][0]["fields"], lexical.columns(lexical.parts(card.explanation)))
        self.apply()
        card.refresh_from_db()
        self.assertEqual(card.synonyms, ["soak up"])

    def test_rendering_keeps_metadata_separate_and_escapes_untrusted_labels(self):
        card = self.legacy()
        self.export(); self.apply()
        Card.objects.filter(pk=card.pk).update(synonyms=['<script>alert(1)</script>'])
        self.client.force_login(self.user)
        response = self.client.get(reverse("card", args=[card.pk]))
        self.assertContains(response, "<h2>Meaning</h2>", html=True)
        self.assertContains(response, "verb (transitive)")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_legacy_parser_keeps_definition_block_indentation(self):
        for definition in ["    meaning = 'take in'", "## Meaning\n\nTake in liquid.", "> Take in liquid."]:
            for prefix in ["", "/x/ (US; verb):\n\n"]:
                for newline in ["\n", "\r\n"]:
                    with self.subTest(prefix=prefix, definition=definition, newline=newline):
                        source = (prefix + definition + "\n\nSynonyms: soak up").replace("\n", newline)
                        parts = lexical.parts(source)
                        self.assertEqual(parts["explanation"], definition.replace("\n", newline))
                        self.assertEqual(render(parts["explanation"]).html, render(definition).html)

    def test_generic_sources_are_not_split(self):
        generic = authoring.save_card(self.deck, "generic", {
            "question": "A question?", "answer": "answer", "explanation": SOURCE["explanation"]})
        before = self.snapshot()
        self.assertEqual(self.export()["cards"], [])
        self.apply()
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(generic.definition)

    def test_unchanged_edit_keeps_completed_structured_metadata(self):
        card, _ = authoring.create_card(self.deck, "vocabulary", SOURCE)
        Card.objects.filter(pk=card.pk).update(definition="## Meaning\n\nTake in liquid.\n", synonyms=["soak up."])
        card.refresh_from_db()
        before = self.snapshot()
        posted = {**SOURCE, "explanation": SOURCE["explanation"].replace("\n", "\r\n")}
        authoring.save_card(self.deck, "vocabulary", posted, card)
        self.assertEqual(self.snapshot(), before)
