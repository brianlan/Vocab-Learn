import io
import json
import os
from unittest import TestCase as UnitTestCase
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from learning import api_keys, authoring, lexical, providers, review, work
from learning.models import AuthoringKey, Card, Deck, GenerationJob


SOURCE = {"word": "absorb", "target_language": "English", "native_language": "Chinese", "explanation": ""}
DETAILS = {"explanation": "If something **absorbs** a liquid, the liquid goes into it and stays there.",
           "pronunciations": [{"ipa": "/əbˈzɔrb/", "variety": "US", "label": "verb"}], "synonyms": ["soak up"]}
PAIR = {"target_sentence": "The sponge <focus>absorbed</focus> the water.",
        "native_sentence": "海绵<focus>吸收</focus>了水。"}


class CompletionContractTests(UnitTestCase):
    def test_supplied_meaning_is_kept_and_only_missing_details_are_requested(self):
        original = "**Verb**\n\nTake in liquid, including water."
        p = providers.Profile("DEFINITION", "https://example.test/chat", "definition-model", "test-only", 10)
        result = {key: DETAILS[key] for key in ["pronunciations", "synonyms"]}
        with patch("learning.providers.chat", return_value=result) as chat:
            text, metadata = providers.define({**SOURCE, "explanation": original}, p)
        self.assertIn(original, text)
        self.assertEqual(chat.call_args.args[2]["requested_fields"], ["pronunciations", "synonyms"])
        self.assertEqual(metadata["model"], "definition-model")
        self.assertEqual(lexical.missing(text), [])

    def test_complete_legacy_format_skips_call_and_preserves_text(self):
        for prefix in ["/ˈɑbdʒɛkt/ (noun), /əbˈdʒɛkt/ (verb)", "/ˈprɛzənt/ (adj./n.) /prɪˈzɛnt/ (v.)"]:
            original = prefix + ": An **object** is a thing. [synonyms: ]"
            with patch("learning.providers.chat") as chat:
                text, metadata = providers.define({**SOURCE, "explanation": original})
            self.assertEqual(text, original)
            self.assertEqual(metadata["origin"], "provided")
            chat.assert_not_called()
        self.assertEqual(lexical.parts("A definition: with a meaningful colon.")["explanation"], "A definition: with a meaningful colon.")

    def test_invalid_output_and_clarification_do_not_become_a_definition(self):
        p = providers.Profile("DEFINITION", "https://example.test/chat", "definition-model", "test-only", 10)
        cases = [{"needs_clarification": "The expression appears incomplete."},
                 {**DETAILS, "extra": "unexpected"}, {**DETAILS, "pronunciations": []},
                 {**DETAILS, "pronunciations": [{"ipa": "/x/", "variety": "UK", "label": ""}]},
                 {**DETAILS, "synonyms": [3]}, {**DETAILS, "explanation": ""}]
        for result in cases:
            with self.subTest(result=result), patch("learning.providers.chat", return_value=result):
                with self.assertRaises(providers.StageError):
                    providers.define(SOURCE, p)

    def test_definition_profile_and_wire_parameters_are_independent(self):
        environment = {"MINIMAX_API_KEY": "test-only", "DEFINITION_MODEL": "definition-only"}
        with patch.dict(os.environ, environment):
            before = providers.profile("GENERATOR").metadata()
            p = providers.profile("DEFINITION")
            self.assertEqual(p.model, "definition-only")
            with patch("learning.providers.request", return_value={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(DETAILS)}}]}) as request:
                providers.define(SOURCE, p)
            self.assertEqual(set(request.call_args.kwargs["json"]), {"model", "stream", "max_completion_tokens", "messages"})
            self.assertEqual(providers.profile("GENERATOR").metadata(), before)

    def test_no_close_synonyms_is_complete_and_spanish_uses_spain(self):
        p = providers.Profile("DEFINITION", "https://example.test/chat", "definition-model", "test-only", 10)
        result = {"explanation": "Si **aprovechas** algo, lo usas para obtener algo bueno.",
                  "pronunciations": [{"ipa": "/apɾoβeˈtʃaɾ/", "variety": "Spain", "label": "verb"}], "synonyms": []}
        with patch("learning.providers.chat", return_value=result):
            text, _ = providers.define({**SOURCE, "word": "aprovechar", "target_language": "Spanish"}, p)
        self.assertIn("No close synonyms", text)
        self.assertEqual(lexical.missing(text), [])


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class VocabularyCreationTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("owner", password="test-password")
        self.other = get_user_model().objects.create_user("other")
        self.deck = Deck.objects.create(owner=self.owner, name="Private")
        self.foreign = Deck.objects.create(owner=self.other, name="Other")
        self.key, self.token = api_keys.issue(self.owner, "test client")
        self.client = Client(enforce_csrf_checks=True)
        self.headers = {"HTTP_AUTHORIZATION": "Bearer " + self.token}
        self.url = reverse("api_vocabulary_create", args=[self.deck.pk])
        self.environment = patch.dict(os.environ, {"MINIMAX_API_KEY": "test-only"})
        self.environment.start(); self.addCleanup(self.environment.stop)

    def post(self, data, url=None, **kwargs):
        return self.client.post(url or self.url, data=json.dumps(data), content_type="application/json", **self.headers, **kwargs)

    def claimed(self, source=None):
        card, created = authoring.create_card(self.deck, "vocabulary", source or SOURCE)
        self.assertTrue(created)
        _, job_id, claim, _ = work.claim_work()
        return card, GenerationJob.objects.get(pk=job_id), claim

    def test_create_is_async_and_blank_duplicates_are_scoped_to_deck_and_languages(self):
        with patch("learning.providers.define") as define, patch("learning.providers.generate") as generate:
            first = self.post(SOURCE)
            self.assertEqual(first.status_code, 201)
            self.assertFalse(first.json()["ready"])
            second = self.post({key: value for key, value in SOURCE.items() if key != "explanation"})
            self.assertEqual(second.status_code, 200)
            self.assertEqual(first.json()["id"], second.json()["id"])
            card = Card.objects.get(); card.archived = True; card.save(update_fields=["archived"])
            self.assertTrue(self.post(SOURCE).json()["archived"])
            self.assertEqual(Card.objects.count(), 1)
            self.assertEqual(GenerationJob.objects.count(), 1)
            another = Deck.objects.create(owner=self.owner, name="Independent")
            self.assertEqual(self.post(SOURCE, reverse("api_vocabulary_create", args=[another.pk])).status_code, 201)
            self.assertEqual(self.post({**SOURCE, "native_language": "Spanish"}).status_code, 201)
            self.assertEqual(self.post({**SOURCE, "explanation": "To take in information."}).status_code, 201)
            define.assert_not_called(); generate.assert_not_called()

    def test_optional_csv_schema_is_atomic_and_repeated_import_does_not_enqueue(self):
        content = b"word,target_language,native_language\nabsorb,English,Chinese\nabsorb,English,Chinese\n"
        self.assertEqual(authoring.import_csv(self.deck, "vocabulary", content), (1, 1))
        self.assertEqual(authoring.import_csv(self.deck, "vocabulary", content), (0, 2))
        bad = b"word,target_language,native_language\nnew,English,Chinese\ninvalid,Spanish,Spanish\n"
        with self.assertRaisesMessage(ValidationError, "record 3"):
            authoring.import_csv(self.deck, "vocabulary", bad)
        self.assertEqual(Card.objects.count(), 1)
        self.assertEqual(GenerationJob.objects.count(), 1)

    def test_two_stage_preparation_saves_definition_and_alias_before_examples(self):
        source = {**SOURCE, "explanation": "Take in liquid."}
        card, job, claim = self.claimed(source)
        calls = []
        def answer(p, system, payload):
            calls.append(p.task)
            if p.task == "DEFINITION":
                return {key: DETAILS[key] for key in payload["requested_fields"]}
            self.assertIn(source["explanation"], payload["explanation"])
            self.assertIn("soak up", payload["explanation"])
            return PAIR
        with patch("learning.providers.chat", side_effect=answer):
            work.process_generation(job.pk, claim)
        card.refresh_from_db();job.refresh_from_db()
        self.assertEqual(calls, ["DEFINITION", "GENERATOR"])
        self.assertTrue(card.ready)
        self.assertEqual((card.review_count, card.progress_version, card.source_version), (0, 0, 1))
        self.assertEqual(job.state, "done")
        self.assertTrue(job.provenance["definition_completed"])
        self.assertEqual(job.provenance["input_explanation"], source["explanation"])
        self.assertEqual(authoring.create_card(self.deck, "vocabulary", source), (card, False))
        self.assertEqual(self.post(SOURCE).json()["id"], card.pk)
        self.assertEqual(GenerationJob.objects.count(), 1)

    def test_example_failure_retry_preserves_completion_and_does_not_pay_twice(self):
        card, job, claim = self.claimed()
        failure = providers.StageError("GENERATOR", "Controlled outage", "transport")
        def first(p, system, payload):
            if p.task == "DEFINITION":return DETAILS
            raise failure
        with patch("learning.providers.chat", side_effect=first):
            with self.assertRaises(providers.StageError):work.process_generation(job.pk, claim)
        work.fail("generation", job.pk, claim, failure)
        card.refresh_from_db();before = card.explanation
        self.assertIn(DETAILS["explanation"], before)
        self.assertFalse(card.ready)
        self.assertFalse(review.available(self.owner).exists())
        retried = work.retry_generation(job)
        status = self.client.get(reverse("api_vocabulary", args=[card.pk]), **self.headers).json()
        self.assertEqual(status["preparation"]["phase"], "examples")
        _, _, second_claim, _ = work.claim_work()
        with patch("learning.providers.define") as define, patch("learning.providers.chat", return_value=PAIR):
            work.process_generation(retried.pk, second_claim)
        define.assert_not_called()
        card.refresh_from_db()
        self.assertTrue(card.ready)
        self.assertEqual(card.explanation, before)
        self.assertEqual(self.post(SOURCE).status_code, 200)

    def test_late_completion_cannot_overwrite_an_edited_source(self):
        card, job, claim = self.claimed()
        replacement = "/x/: A deliberately chosen meaning. [synonyms: ]"
        def complete(*args):
            authoring.save_card(self.deck, "vocabulary", {**SOURCE, "explanation": replacement}, card)
            return lexical.combine("", DETAILS), {"requested_fields": list(DETAILS)}
        with patch("learning.providers.define", side_effect=complete), patch("learning.providers.generate") as generate:
            work.process_generation(job.pk, claim)
        card.refresh_from_db(); job.refresh_from_db()
        self.assertEqual(card.explanation, replacement)
        self.assertEqual(job.state, "cancelled")
        generate.assert_not_called()

    def test_missing_definition_cannot_activate_a_pair_and_clarification_stays_unready(self):
        card, job, claim = self.claimed()
        pair = providers.validate_pair(PAIR, "absorb", "Chinese")
        self.assertIsNone(work.save_pair(job.pk, claim, pair, {}))
        failure = providers.StageError("DEFINITION", "Please clarify this expression.", "content")
        with patch("learning.providers.define", side_effect=failure):
            with self.assertRaises(providers.StageError):work.process_generation(job.pk, claim)
        work.fail("generation", job.pk, claim, failure)
        card.refresh_from_db();job.refresh_from_db()
        self.assertFalse(card.ready);self.assertEqual(card.explanation, "")
        self.assertFalse(job.retryable)
        self.assertEqual(job.provenance["failed_stage"], "DEFINITION")
        self.assertFalse(review.available(self.owner).exists())

    def test_api_authentication_ownership_and_revocation(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.url, SOURCE).status_code, 401)
        foreign = reverse("api_vocabulary_create", args=[self.foreign.pk])
        self.assertEqual(self.post(SOURCE, foreign).status_code, 404)
        self.assertEqual(self.client.get(self.url, **self.headers).status_code, 405)
        first = self.post(SOURCE).json()
        self.assertEqual(self.client.get(first["status_url"], **self.headers).status_code, 200)
        other_key, other_token = api_keys.issue(self.other)
        self.assertEqual(self.client.get(first["status_url"], HTTP_AUTHORIZATION="Bearer " + other_token).status_code, 404)
        self.key.revoked_at = timezone.now(); self.key.save(update_fields=["revoked_at"])
        self.assertEqual(self.post(SOURCE).status_code, 401)

    def test_forged_key_and_inactive_owner_cannot_authenticate(self):
        forged = self.token[:-1] + ("A" if self.token[-1] != "A" else "B")
        self.assertEqual(self.client.post(self.url, json.dumps(SOURCE), content_type="application/json",
                                         HTTP_AUTHORIZATION="Bearer " + forged).status_code, 401)
        self.owner.is_active = False;self.owner.save(update_fields=["is_active"])
        self.assertEqual(self.post(SOURCE).status_code, 401)

    def test_bad_api_inputs_never_create_cards(self):
        for data in [[], {**SOURCE, "owner_id": self.other.pk}, {**SOURCE, "word": 1},
                     {**SOURCE, "word": "\ud800"}, {**SOURCE, "target_language": "Chinese"}]:
            with self.subTest(data=data):self.assertEqual(self.post(data).status_code, 400)
        self.assertEqual(self.client.post(self.url, "{", content_type="application/json", **self.headers).status_code, 400)
        self.assertEqual(self.client.post(self.url, "x" * 65537, content_type="application/json", **self.headers).status_code, 413)
        self.assertEqual(self.client.post(self.url, SOURCE, **self.headers).status_code, 415)
        self.assertEqual(Card.objects.count(), 0)

    def test_cli_reveals_secret_once_lists_only_identifiers_and_checks_owner(self):
        output = io.StringIO()
        call_command("vocabulary_api_key", "create", self.owner.username, name="Automation", stdout=output)
        token = output.getvalue().strip().splitlines()[-1]
        key = api_keys.authenticate("Bearer " + token)
        self.assertIsNotNone(key)
        self.assertNotEqual(key.digest, token)
        listing = io.StringIO();call_command("vocabulary_api_key", "list", self.owner.username, stdout=listing)
        self.assertNotIn(token, listing.getvalue());self.assertNotIn(key.digest, listing.getvalue())
        with self.assertRaises(CommandError):
            call_command("vocabulary_api_key", "revoke", self.other.username, key_id=str(key.pk))
        call_command("vocabulary_api_key", "revoke", self.owner.username, key_id=str(key.pk), stdout=io.StringIO())
        self.assertIsNone(api_keys.authenticate("Bearer " + token))
