import io
import json
import os
from pathlib import Path
import re
import tempfile
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import Client, TestCase
from django.urls import reverse
from learning import api, authoring, lexical, providers, review, work
from learning.models import Card, Deck, ExamplePair, GenerationJob, Presentation, Attempt, ScoredReview
from learning.rendering import render


SOURCE = {"word": "absorb", "explanation": "/əbˈzɔrb/ (US; verb (transitive)):\n\n## Meaning\n\nTake in liquid.\n\nSynonyms: soak up",
          "target_language": "English", "native_language": "Chinese"}
PAIR = {"target_sentence": "The sponge <focus>absorbed</focus> the water.",
        "native_sentence": "海绵<focus>吸收</focus>了水。"}
CODE_DEFINITION = "A **thesaurus** stores words with similar meanings.\n\n```text\nEntry: car\n\nSynonyms: automobile, motorcar\n```"


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

    def test_blank_manifest_needs_a_matching_current_checkpoint_and_metadata_only_source(self):
        metadata = "/x/ (US; noun):\n\n\n\nSynonyms: first; second"
        proposed = {"definition": "", "pronunciations": [{"ipa": "/x/", "variety": "US", "label": "noun"}],
                    "synonyms": ["first", "second"]}
        for index, (name, source) in enumerate([
            ("missing", metadata), ("stale", metadata), ("different source", metadata),
            ("malformed", metadata), ("nonempty record", metadata), ("changed metadata", metadata),
            ("real meaning", "/x/ (US; noun):\n\nAn actual definition.\n\nSynonyms: first; second"),
            ("synonyms meaning with footer", "/x/ (US; noun):\n\nSynonyms: words with similar meanings.\n\nSynonyms: first; second"),
            ("literal code", CODE_DEFINITION),
            ("sole synonyms definition", "Synonyms: words or phrases with similar meanings."),
        ]):
            with self.subTest(name=name):
                self.path.unlink(missing_ok=True)
                card = self.legacy(word=f"guard {index}", explanation=source)
                if name not in {"missing", "sole synonyms definition"}:
                    checkpoint = {"source": source, "details": {"explanation": "", "pronunciations": proposed["pronunciations"],
                                                               "synonyms": proposed["synonyms"]}}
                    if name == "different source":
                        checkpoint["source"] = "An older meaning."
                    elif name == "malformed":
                        checkpoint["details"] = None
                    elif name == "nonempty record":
                        checkpoint["details"]["explanation"] = lexical.parts(source)["explanation"]
                    elif name == "changed metadata":
                        checkpoint["details"]["synonyms"] = ["first"]
                    GenerationJob.objects.create(card=card, source_version=2 if name == "stale" else 1,
                                                 provenance={"teaching_details": checkpoint})
                plan = self.export()
                record = next(row for row in plan["cards"] if row["id"] == card.pk)
                record["fields"] = proposed
                before = self.snapshot()
                with self.assertRaisesMessage(CommandError, "cannot be discarded"):
                    self.apply({"format": plan["format"], "cards": [record]})
                self.assertEqual(self.snapshot(), before)

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

    def test_vocabulary_details_and_review_back_label_the_explanation_separately(self):
        card = self.legacy(explanation="/əbˈzɔrb/: Take in **liquid**. [synonyms: soak up]")
        self.export(); self.apply()
        card.refresh_from_db()
        self.client.force_login(self.user)
        detail = self.client.get(reverse("card", args=[card.pk]))
        self.assertContains(detail, "<h2>Word details</h2>", html=True)
        held = review.next_question(self.user, self.deck)
        review.submit(held, "skip")
        frozen = held.snapshot.copy()
        back = self.client.get(reverse("status", args=[held.pk])).json()["back_html"]
        for page, html in [("detail", detail.content.decode()), ("review", back)]:
            with self.subTest(page=page):
                self.assertInHTML(
                    '<div class="teaching-explanation"><h3>Explanation</h3>'
                    '<div class="prose explanation"><p>Take in <strong>liquid</strong>.</p></div></div>', html)
                self.assertLess(html.index("<h3>Pronunciation</h3>"), html.index("<h3>Explanation</h3>"))
                self.assertLess(html.index("<h3>Explanation</h3>"), html.index("<h3>Synonyms</h3>"))
        held.refresh_from_db()
        self.assertEqual(held.snapshot, frozen)

    def test_generic_details_and_review_back_do_not_gain_duplicate_explanation_headings(self):
        card, _ = authoring.create_card(self.deck, "generic", {
            "question": "What is two plus two?", "answer": "four", "explanation": "Two pairs make four."})
        self.client.force_login(self.user)
        detail = self.client.get(reverse("card", args=[card.pk]))
        self.assertContains(detail, "<h2>Explanation</h2>", count=1, html=True)
        held = review.next_question(self.user, self.deck)
        review.submit(held, "skip")
        back = self.client.get(reverse("status", args=[held.pk])).json()["back_html"]
        for html in [detail.content.decode(), back]:
            self.assertInHTML("<p>Two pairs make four.</p>", html)
            self.assertNotIn("<h3>Explanation</h3>", html)
            self.assertNotIn("Word details", html)

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

    def test_definition_formatting_keeps_typed_metadata_and_scored_history(self):
        cases = [
            ("not a single one", ["none"], "Used to say that there are zero members left in a group.",
             "There was <focus>not a single one</focus> left.", "这里<focus>一个也没有</focus>。"),
            ("I'll pass", ["no, thank you"], "Used to refuse an offer politely.",
             "Thanks, but <focus>I'll pass</focus> on the cake.", "谢谢，不过我<focus>就算了</focus>。"),
        ]
        for word, synonyms, definition, target, native in cases:
            with self.subTest(word=word), patch.dict(os.environ, {"MINIMAX_API_KEY": "test-only"}), patch(
                    "learning.providers.request", side_effect=AssertionError("No provider requests")):
                deck = Deck.objects.create(owner=self.user, name=word)
                card, _ = authoring.create_card(deck, "vocabulary", {**SOURCE, "word": word, "explanation": ""})
                _, job_id, claim, _ = work.claim_work()
                generated = {"explanation": definition, "pronunciations": [
                    {"ipa": "/test/", "variety": "US", "label": "expression (informal)"}], "synonyms": synonyms}
                def reply(profile, system, payload):
                    return ({name: generated[name] for name in payload["requested_fields"]} if profile.task == "DEFINITION"
                            else {"target_sentence": target, "native_sentence": native})
                with patch("learning.providers.chat", side_effect=reply):
                    work.process_generation(job_id, claim)
                card.refresh_from_db()
                self.assertTrue(card.ready)
                self.assertEqual(card.synonyms, synonyms)
                review.submit(review.next_question(self.user, deck), "forgot")
                before = self.snapshot()
                browser = Client(enforce_csrf_checks=True); browser.force_login(self.user)
                url = reverse("card_edit", args=[deck.pk, card.pk])
                response = browser.get(url)
                form = response.context["form"]
                payload = {name: form[name].value() for name in authoring.SCHEMAS["vocabulary"]}
                payload["source_identity"] = form["source_identity"].value()
                payload["csrfmiddlewaretoken"] = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', response.content.decode())[1]
                payload["explanation"] = payload["explanation"].replace("Used", "**Used**", 1).replace("\n", "\r\n")
                self.assertEqual(browser.post(url, payload).status_code, 302)
                for row in before["Card"]:
                    if row["id"] == card.pk:
                        row.update(explanation=payload["explanation"], definition=definition.replace("Used", "**Used**", 1))
                self.assertEqual(self.snapshot(), before)
                card.refresh_from_db()
                self.assertEqual(api.representation(card)["synonyms"], synonyms)
                self.assertEqual(card.pronunciations, generated["pronunciations"])

    def test_explicit_metadata_edits_change_only_their_teaching_component(self):
        generated = {"explanation": "Used to refuse politely.\n",
                     "pronunciations": [{"ipa": "/x/", "variety": "US", "label": "expression"}], "synonyms": ["none"]}
        for index, (old, new, changed) in enumerate([
            ("Synonyms: none", "Synonyms: No close synonyms", {"synonyms": []}),
            ("Synonyms: none", "Synonyms: nobody", {"synonyms": ["nobody"]}),
            ("/x/ (US; expression)", "/y/ (UK; noun)", {"pronunciations": [{"ipa": "/y/", "variety": "UK", "label": "noun"}]}),
        ]):
            with self.subTest(changed=changed):
                card = self.legacy(word=f"variant {index}", explanation=lexical.combine("", generated))
                Card.objects.filter(pk=card.pk).update(**lexical.columns(generated)); card.refresh_from_db()
                source = {**SOURCE, "word": card.word, "explanation": card.explanation.replace(old, new)}
                authoring.save_card(self.deck, "vocabulary", source, card)
                card.refresh_from_db()
                self.assertEqual(lexical.details(card), {**generated, **changed})
                self.assertEqual(card.source_version, 2)

    def test_code_and_nested_examples_are_not_metadata_footers(self):
        examples = [CODE_DEFINITION, CODE_DEFINITION.replace("```", "~~~"),
                    CODE_DEFINITION.rsplit("\n```", 1)[0],
                    "A definition.\n\n    Entry: car\n\n    [synonyms: automobile, motorcar]",
                    "A definition.\n\n> [synonyms: example]", "A definition.\n\n- [synonyms: example]"]
        for definition in examples:
            for prefix in ["", "/x/ (noun):\n\n"]:
                for newline in ["\n", "\r\n"]:
                    with self.subTest(definition=definition, prefix=prefix, newline=newline):
                        text = (prefix + definition).replace("\n", newline)
                        values = lexical.parts(text)
                        self.assertEqual(values["explanation"], definition.replace("\n", newline))
                        self.assertIsNone(values["synonyms"])
                        self.assertEqual(render(values["explanation"]).html, render(definition).html)

    def test_real_footer_after_code_and_legacy_inline_footer_still_work(self):
        for definition in [CODE_DEFINITION, "A definition.\n\n    Literal code  "]:
            for footer in ["Synonyms: reference book", "[synonyms: reference book]"]:
                with self.subTest(definition=definition, footer=footer):
                    values = lexical.parts(definition + "\n\n" + footer)
                    self.assertEqual(values["explanation"], definition)
                    self.assertEqual(values["synonyms"], ["reference book"])
        self.assertEqual(lexical.parts("A definition. [synonyms: first, second]"), {
            "explanation": "A definition.", "pronunciations": [], "synonyms": ["first", "second"]})

    def test_authoring_rendering_and_judge_keep_the_whole_code_example(self):
        card, _ = authoring.create_card(self.deck, "vocabulary", {
            **SOURCE, "word": "thesaurus", "explanation": CODE_DEFINITION})
        self.assertEqual(card.definition, CODE_DEFINITION)
        self.assertIsNone(card.synonyms)
        self.client.force_login(self.user)
        response = self.client.get(reverse("card", args=[card.pk]))
        self.assertContains(response, render(CODE_DEFINITION).html, html=True)
        pair = ExamplePair.objects.create(card=card, source_version=1, **providers.validate_pair({
            "target_sentence": "Keep a <focus>thesaurus</focus> on the desk.",
            "native_sentence": "桌上放一本<focus>同义词词典</focus>。"}, "thesaurus", "Chinese"))
        card.cue_pair, card.cue_direction = pair, "recognition"
        frozen = review.snapshot(card)
        p = providers.Profile("JUDGE", "https://example.test/chat", "test-model", "test-only", 10)
        with patch("learning.providers.chat", return_value={"units": [{"id": 1, "outcome": "complete", "reason": "Test response."}]}) as chat:
            providers.assess(frozen, "同义词词典", p)
        self.assertEqual(chat.call_args.args[2]["explanation"], CODE_DEFINITION)

    def test_legacy_export_apply_preserves_code_contents_without_synonyms(self):
        card = self.legacy(word="thesaurus", explanation=CODE_DEFINITION)
        before = self.snapshot()
        plan = self.export()
        self.assertEqual(plan["cards"][0]["fields"], {
            "definition": CODE_DEFINITION, "pronunciations": [], "synonyms": None})
        with patch("learning.providers.request", side_effect=AssertionError("No model calls")):
            self.apply()
        before["Card"][0].update(plan["cards"][0]["fields"])
        self.assertEqual(self.snapshot(), before)
        card.refresh_from_db()
        self.assertEqual(api.representation(card)["definition"], CODE_DEFINITION)
        self.assertIsNone(api.representation(card)["synonyms"])
