import io
import json
import os
from unittest import TestCase as UnitTestCase
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from learning import api, api_keys, authoring, lexical, providers, review, work
from learning.models import AuthoringKey, Card, Deck, GenerationJob, ScoredReview
from learning.rendering import render


SOURCE = {"word": "absorb", "target_language": "English", "native_language": "Chinese", "explanation": ""}
DETAILS = {"explanation": "If something **absorbs** a liquid, the liquid goes into it and stays there.",
           "pronunciations": [{"ipa": "/əbˈzɔrb/", "variety": "US", "label": "verb"}], "synonyms": ["soak up"]}
PAIR = {"target_sentence": "The sponge <focus>absorbed</focus> the water.",
        "native_sentence": "海绵<focus>吸收</focus>了水。"}


class CompletionContractTests(UnitTestCase):
    def test_pronunciation_labels_round_trip_through_completion(self):
        p = providers.Profile("DEFINITION", "https://example.test/chat", "definition-model", "test-only", 10)
        for label in ["", "verb (transitive)", "adjective (informal)", "verb (formal (rare))",
                      "verb (unclosed", "noun) or verb (", "noun\\usage", "verb\n(transitive)"]:
            result = {**DETAILS, "pronunciations": [{"ipa": "/əbˈzɔrb/", "variety": "US", "label": label}]}
            with self.subTest(label=label), patch("learning.providers.chat", return_value=result):
                details, metadata = providers.define(SOURCE, p)
                self.assertEqual(lexical.missing(details), [])
                self.assertEqual(details["pronunciations"][0]["label"], label)
                compatible = lexical.parts(lexical.combine("", metadata["fields"]))
                self.assertEqual(compatible["pronunciations"], details["pronunciations"])
                self.assertEqual(lexical.missing(compatible), [])
                self.assertEqual(metadata["fields"]["pronunciations"][0]["label"], label)

    def test_existing_balanced_nested_labels_are_already_complete(self):
        text = "/x/ (noun (countable)), /y/ (verb (formal (rare))): A definition. [synonyms: ]"
        with patch("learning.providers.chat") as chat:
            completed, _ = providers.define({**SOURCE, **lexical.parts(text)})
        self.assertEqual(completed, lexical.parts(text))
        self.assertEqual([p["label"] for p in lexical.parts(text)["pronunciations"]],
                         ["noun (countable)", "verb (formal (rare))"])
        chat.assert_not_called()

    def test_completion_preserves_markdown_blocks_for_supplied_and_generated_definitions(self):
        p = providers.Profile("DEFINITION", "https://example.test/chat", "definition-model", "test-only", 10)
        blocks = [("## Intended meaning\n\nTake in liquid.", "<h2>"),
                  ("- First point\n- Second point", "<li>"),
                  ("> Take in liquid.", "<blockquote>"),
                  ('    meaning = "take in"', "<pre>"),
                  ('```text\nTake in liquid.\n```', "<pre>")]
        for original, tag in blocks:
            for supplied in [True, False]:
                source_text = original if supplied else "/x/ (verb): [synonyms: ]"
                result = {k: DETAILS[k] for k in ["pronunciations", "synonyms"]} if supplied else {"explanation": original}
                with self.subTest(block=tag, supplied=supplied), patch("learning.providers.chat", return_value=result):
                    details, metadata = providers.define({**SOURCE, **lexical.parts(source_text)}, p)
                    self.assertEqual(details["explanation"], original)
                    self.assertEqual(render(details["explanation"]).html, render(original).html)
                    compatible = lexical.combine(source_text, metadata["fields"])
                    self.assertEqual(render(compatible).html.count(tag), render(original).html.count(tag))
                    self.assertEqual(lexical.missing(details), [])

    def test_supplied_meaning_is_kept_and_only_missing_details_are_requested(self):
        original = "**Verb**\n\nTake in liquid, including water."
        p = providers.Profile("DEFINITION", "https://example.test/chat", "definition-model", "test-only", 10)
        result = {key: DETAILS[key] for key in ["pronunciations", "synonyms"]}
        with patch("learning.providers.chat", return_value=result) as chat:
            details, metadata = providers.define({**SOURCE, **lexical.parts(original)}, p)
        self.assertEqual(details["explanation"], original)
        self.assertEqual(chat.call_args.args[2]["requested_fields"], ["pronunciations", "synonyms"])
        self.assertEqual(metadata["model"], "definition-model")
        self.assertEqual(lexical.missing(details), [])

    def test_complete_legacy_format_skips_call_and_preserves_text(self):
        for prefix in ["/ˈɑbdʒɛkt/ (noun), /əbˈdʒɛkt/ (verb)", "/ˈprɛzənt/ (adj./n.) /prɪˈzɛnt/ (v.)"]:
            original = prefix + ": An **object** is a thing. [synonyms: ]"
            with patch("learning.providers.chat") as chat:
                details, metadata = providers.define({**SOURCE, **lexical.parts(original)})
            self.assertEqual(details, lexical.parts(original))
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
            details, metadata = providers.define({**SOURCE, "word": "aprovechar", "target_language": "Spanish"}, p)
        self.assertEqual(details["synonyms"], [])
        self.assertIn("No close synonyms", lexical.combine("", metadata["fields"]))
        self.assertEqual(lexical.missing(details), [])


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

    def complete(self, card, job, claim):
        def reply(profile, system, payload):
            return {name: DETAILS[name] for name in payload["requested_fields"]} if profile.task == "DEFINITION" else PAIR
        with patch("learning.providers.chat", side_effect=reply):
            work.process_generation(job.pk, claim)
        card.refresh_from_db()
        self.assertTrue(card.ready)

    def edit_payload(self, client, card):
        response = client.get(reverse("card_edit", args=[card.deck_id, card.pk]))
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        fields = {name: form[name].value() for name in authoring.SCHEMAS[card.kind]}
        fields["source_identity"] = form["source_identity"].value() if "source_identity" in form.fields else card.identity
        return fields

    def stale_edit_case(self, explanation):
        source = {**SOURCE, "explanation": explanation}
        card, job, claim = self.claimed(source)
        browser = Client(); browser.force_login(self.owner)
        payload = self.edit_payload(browser, card)
        self.complete(card, job, claim)
        presentation = review.next_question(self.owner, self.deck)
        review.submit(presentation, "forgot")
        before = Card.objects.values().get(pk=card.pk)
        self.assertEqual(before["collection"], "Forgot")
        self.assertEqual(before["review_count"], 1)
        history = list(ScoredReview.objects.filter(card=card).values())
        jobs = list(card.generation_jobs.order_by("pk").values())
        response = browser.post(reverse("card_edit", args=[self.deck.pk, card.pk]), payload)
        self.assertEqual(Card.objects.values().get(pk=card.pk), before)
        self.assertEqual(list(ScoredReview.objects.filter(card=card).values()), history)
        self.assertEqual(list(card.generation_jobs.order_by("pk").values()), jobs)
        self.assertContains(response, "Reload the page")

    def test_stale_blank_edit_preserves_completed_content_and_forgot_review(self):
        self.stale_edit_case("")

    def test_stale_supplied_edit_preserves_completed_content_and_forgot_review(self):
        self.stale_edit_case("Take in liquid.")

    def test_authoring_rejects_stale_model_instances_after_completion(self):
        card, job, claim = self.claimed()
        stale = Card.objects.get(pk=card.pk)
        self.complete(card, job, claim)
        before = Card.objects.values().get(pk=card.pk)
        with self.assertRaisesMessage(ValidationError, "Reload the page"):
            authoring.save_card(self.deck, "vocabulary", SOURCE, stale)
        self.assertEqual(Card.objects.values().get(pk=card.pk), before)

    def test_fresh_edit_can_deliberately_clear_a_completed_explanation(self):
        card, job, claim = self.claimed()
        self.complete(card, job, claim)
        browser = Client(); browser.force_login(self.owner)
        payload = self.edit_payload(browser, card)
        self.assertEqual(payload["source_identity"], card.identity)
        payload["explanation"] = ""
        response = browser.post(reverse("card_edit", args=[self.deck.pk, card.pk]), payload)
        self.assertEqual(response.status_code, 302)
        card.refresh_from_db()
        self.assertEqual(card.explanation, "")
        self.assertEqual(card.source_version, 2)
        self.assertFalse(card.ready)
        self.assertEqual(card.generation_jobs.filter(state="queued", source_version=2).count(), 1)

    def test_edit_post_without_loaded_identity_is_rejected(self):
        card, job, claim = self.claimed()
        self.complete(card, job, claim)
        browser = Client(); browser.force_login(self.owner)
        before = Card.objects.values().get(pk=card.pk)
        response = browser.post(reverse("card_edit", args=[self.deck.pk, card.pk]), SOURCE)
        self.assertEqual(Card.objects.values().get(pk=card.pk), before)
        self.assertContains(response, "Reload the page")

    def streamed_request(self, body, length):
        class CountedStream(io.BytesIO):
            def __init__(self, data):
                super().__init__(data)
                self.read_sizes = []
            def read(self, size=-1):
                self.read_sizes.append(size)
                return super().read(size)
        request = RequestFactory().post(self.url, data=body, content_type="application/json", **self.headers)
        request._stream = CountedStream(body)
        if length is None:
            request.META.pop("CONTENT_LENGTH", None)
        else:
            request.META["CONTENT_LENGTH"] = length
        return request

    def test_api_rejects_declared_oversize_without_reading_stream(self):
        request = self.streamed_request(b"x" * 1048576, "1048576")
        response = api.create_vocabulary(request, deck_id=self.deck.pk)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(request._stream.read_sizes, [])
        self.assertFalse(Card.objects.exists())

    def test_api_read_is_bounded_without_a_reliable_declared_length(self):
        for length in [None, "", "1"]:
            with self.subTest(length=length):
                request = self.streamed_request(b"x" * 1048576, length)
                response = api.create_vocabulary(request, deck_id=self.deck.pk)
                self.assertEqual(response.status_code, 413)
                self.assertEqual(request._stream.tell(), 65537)
                self.assertFalse(hasattr(request, "_body"))
        self.assertFalse(Card.objects.exists())

    def test_api_accepts_exact_limit_and_rejects_one_extra_byte(self):
        source = {**SOURCE, "word": "limit-boundary"}
        source["explanation"] = "a" * (65536 - len(json.dumps(source).encode()))
        body = json.dumps(source).encode()
        self.assertEqual(len(body), 65536)
        request = self.streamed_request(body, str(len(body)))
        self.assertEqual(api.create_vocabulary(request, deck_id=self.deck.pk).status_code, 201)
        request = self.streamed_request(body + b" ", "65537")
        self.assertEqual(api.create_vocabulary(request, deck_id=self.deck.pk).status_code, 413)
        self.assertEqual(Card.objects.count(), 1)

    def test_api_rejects_invalid_declared_length_without_reading(self):
        for length in ["invalid", "-1"]:
            with self.subTest(length=length):
                request = self.streamed_request(b"{}", length)
                self.assertEqual(api.create_vocabulary(request, deck_id=self.deck.pk).status_code, 400)
                self.assertEqual(request._stream.read_sizes, [])

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
            self.assertEqual(source["explanation"], payload["explanation"])
            self.assertEqual(payload["synonyms"], DETAILS["synonyms"])
            return PAIR
        with patch("learning.providers.chat", side_effect=answer):
            work.process_generation(job.pk, claim)
        card.refresh_from_db();job.refresh_from_db()
        self.assertEqual(calls, ["DEFINITION", "GENERATOR"])
        self.assertTrue(card.ready)
        self.assertEqual(card.definition, source["explanation"])
        self.assertEqual(card.pronunciations, DETAILS["pronunciations"])
        self.assertEqual(card.synonyms, DETAILS["synonyms"])
        self.assertEqual((card.review_count, card.progress_version, card.source_version), (0, 0, 1))
        self.assertEqual(job.state, "done")
        self.assertTrue(job.provenance["definition_completed"])
        self.assertEqual(job.provenance["input_explanation"], source["explanation"])
        self.assertEqual(authoring.create_card(self.deck, "vocabulary", source), (card, False))
        self.assertEqual(self.post(SOURCE).json()["id"], card.pk)
        self.assertEqual(GenerationJob.objects.count(), 1)

    def test_whitespace_only_definition_completes_without_losing_generated_content(self):
        card, job, claim = self.claimed({**SOURCE, "explanation": " \t\n "})
        self.complete(card, job, claim)
        self.assertEqual(card.definition, DETAILS["explanation"])
        self.assertIn(DETAILS["explanation"], card.explanation)
        self.assertEqual(card.pronunciations, DETAILS["pronunciations"])
        self.assertEqual(card.synonyms, DETAILS["synonyms"])

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
            return DETAILS, {"requested_fields": list(DETAILS), "fields": DETAILS}
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
