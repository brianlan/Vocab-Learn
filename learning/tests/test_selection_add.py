import io
import json
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.template import Context, Template
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from learning import api_keys, authoring, context_processors, review, views
from learning.models import Card, Deck, ExamplePair, GenerationJob, LearnerPreferences, Presentation, Attempt, ScoredReview


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SelectionAddTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("owner", password="test-password")
        self.other = get_user_model().objects.create_user("other")
        self.deck = Deck.objects.create(owner=self.owner, name="Reading")
        self.foreign = Deck.objects.create(owner=self.other, name="Other private deck")
        self.archived = Deck.objects.create(owner=self.owner, name="Archived", archived=True)
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        self.settings_url = reverse("settings")
        self.url = reverse("selection_create")
        self.assertEqual(self.client.get(self.settings_url).status_code, 200)
        self.csrf = self.client.cookies["csrftoken"].value
        self.source = {"deck_id": self.deck.pk, "text": "absorb", "target_language": "English", "native_language": "Chinese"}
        self.provider_mocks = []
        for name in ["define", "generate", "chat", "request"]:
            mocked = patch("learning.providers." + name, side_effect=AssertionError("No synchronous provider calls"))
            self.provider_mocks.append(mocked.start())
            self.addCleanup(mocked.stop)

    def tearDown(self):
        for mocked in self.provider_mocks:
            mocked.assert_not_called()

    def post(self, data):
        return self.client.post(self.url, json.dumps(data), content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf)

    def bootstrap(self, user=None):
        request = RequestFactory().get("/")
        request.user = self.owner if user is None else user
        return context_processors.selection_add(request)

    def learning_rows(self):
        return {model.__name__: list(model.objects.order_by("pk").values()) for model in
                [Card, ExamplePair, GenerationJob, Presentation, Attempt, ScoredReview]}

    def assert_no_creation(self):
        self.assertFalse(Card.objects.exists())
        self.assertFalse(GenerationJob.objects.exists())

    def test_defaults_and_repeated_page_reads_do_not_create_preferences(self):
        for url in [self.settings_url, reverse("library"), reverse("dashboard"), self.settings_url]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["selection_add"]["enabled"], True)
            self.assertEqual(response.context["selection_add"]["target_language"], "English")
            self.assertEqual(response.context["selection_add"]["native_language"], "Chinese")
        form = response.context["form"]
        self.assertEqual(set(form.fields), {"selection_add_enabled", "language_pair"})
        self.assertTrue(form["selection_add_enabled"].value())
        self.assertEqual(form["language_pair"].value(), "English:Chinese")
        self.bootstrap()
        self.assertFalse(LearnerPreferences.objects.exists())

    def test_settings_first_save_update_and_all_supported_pairs(self):
        preference_id = None
        for index, (target, native) in enumerate(sorted(authoring.LANGUAGE_PAIRS)):
            payload = {"language_pair": f"{target}:{native}"}
            if index % 2 == 0:
                payload["selection_add_enabled"] = "on"
            response = self.client.post(self.settings_url, payload, HTTP_X_CSRFTOKEN=self.csrf)
            self.assertRedirects(response, self.settings_url)
            preferences = LearnerPreferences.objects.get(user=self.owner)
            preference_id = preference_id or preferences.pk
            self.assertEqual(preferences.pk, preference_id)
            self.assertEqual((preferences.target_language, preferences.native_language), (target, native))
            self.assertEqual(preferences.selection_add_enabled, index % 2 == 0)
            self.assertEqual(LearnerPreferences.objects.count(), 1)

    def test_invalid_settings_pairs_neither_create_nor_overwrite_preferences(self):
        for existing in [False, True]:
            if existing:
                LearnerPreferences.objects.create(user=self.owner, selection_add_enabled=False,
                                                 target_language="Spanish", native_language="Chinese")
            before = list(LearnerPreferences.objects.values())
            for pair in ["", "Spanish:Spanish", "Chinese:English", "English:Chinese:extra", "English"]:
                with self.subTest(existing=existing, pair=pair):
                    response = self.client.post(self.settings_url, {"language_pair": pair, "selection_add_enabled": "on"},
                                                HTTP_X_CSRFTOKEN=self.csrf)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("language_pair", response.context["form"].errors)
                    self.assertEqual(list(LearnerPreferences.objects.values()), before)
            response = self.client.post(self.settings_url, {}, HTTP_X_CSRFTOKEN=self.csrf)
            self.assertIn("language_pair", response.context["form"].errors)
            self.assertEqual(list(LearnerPreferences.objects.values()), before)

    def test_settings_and_defaults_are_account_scoped(self):
        foreign = LearnerPreferences.objects.create(user=self.other, selection_add_enabled=False,
                                                  target_language="Spanish", native_language="Chinese")
        before = LearnerPreferences.objects.values().get(pk=foreign.pk)
        self.assertTrue(self.bootstrap()["selection_add"]["enabled"])
        response = self.client.post(self.settings_url, {"language_pair": "English:Spanish", "user_id": self.other.pk},
                                    HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LearnerPreferences.objects.values().get(pk=foreign.pk), before)
        self.assertEqual(LearnerPreferences.objects.get(user=self.owner).native_language, "Spanish")
        self.client.force_login(self.other)
        response = self.client.get(self.settings_url)
        self.assertEqual(response.context["form"]["language_pair"].value(), "Spanish:Chinese")
        response = self.client.post(self.settings_url, {"language_pair": "English:Chinese", "selection_add_enabled": "on"},
                                    HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LearnerPreferences.objects.get(user=self.owner).native_language, "Spanish")
        self.assertTrue(LearnerPreferences.objects.get(user=self.other).selection_add_enabled)

    def test_settings_require_login_csrf_and_get_or_post(self):
        self.assertEqual(Client().get(self.settings_url).status_code, 302)
        self.assertEqual(self.client.post(self.settings_url, {"language_pair": "English:Chinese"}).status_code, 403)
        self.assertEqual(self.client.put(self.settings_url, HTTP_X_CSRFTOKEN=self.csrf).status_code, 405)
        self.assertFalse(LearnerPreferences.objects.exists())

    def test_bootstrap_is_minimal_owner_scoped_sorted_and_safe_for_json_script(self):
        dangerous = '</script><img src=x onerror="bad()"> & deck'
        extra = Deck.objects.create(owner=self.owner, name=dangerous, description="private description")
        authoring.create_card(self.deck, "generic", {"question": "Visible", "answer": "HIDDEN REFERENCE",
                                                    "explanation": "HIDDEN EXPLANATION"})
        key, token = api_keys.issue(self.owner)
        data = self.bootstrap()
        self.assertEqual(data, {"selection_add": {
            "user_id": str(self.owner.pk), "enabled": True, "target_language": "English", "native_language": "Chinese",
            "decks": [{"id": extra.pk, "name": dangerous}, {"id": self.deck.pk, "name": "Reading"}],
            "language_pairs": [["English", "Chinese"], ["English", "Spanish"], ["Spanish", "Chinese"]],
            "create_url": self.url, "create_deck_url": reverse("library"), "settings_url": self.settings_url,
        }})
        html = Template('{{ selection_add|json_script:"selection-add-config" }}').render(Context(data))
        self.assertNotIn(dangerous, html)
        self.assertIn(r"\u003C/script\u003E", html)
        for secret in [token, key.digest, "HIDDEN REFERENCE", "HIDDEN EXPLANATION", "private description", self.foreign.name]:
            self.assertNotIn(secret, html)
        self.assertFalse(LearnerPreferences.objects.exists())

    def test_anonymous_bootstrap_is_empty_and_disabled_bootstrap_skips_decks(self):
        with self.assertNumQueries(0):
            self.assertEqual(self.bootstrap(AnonymousUser()), {})
        LearnerPreferences.objects.create(user=self.owner, selection_add_enabled=False,
                                         target_language="English", native_language="Spanish")
        with self.assertNumQueries(1):
            data = self.bootstrap()["selection_add"]
        self.assertFalse(data["enabled"])
        self.assertEqual(data["decks"], [])
        self.assertEqual(data["native_language"], "Spanish")

    def test_old_page_cannot_submit_after_settings_disable(self):
        self.assertTrue(self.client.get(reverse("library")).context["selection_add"]["enabled"])
        self.client.post(self.settings_url, {"language_pair": "English:Chinese"}, HTTP_X_CSRFTOKEN=self.csrf)
        with patch("learning.authoring.create_card") as create:
            response = self.post(self.source)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "disabled")
        create.assert_not_called()
        self.assert_no_creation()

    def test_creation_requires_session_active_user_csrf_and_same_origin(self):
        self.assertEqual(self.client.post(self.url, json.dumps(self.source), content_type="application/json").status_code, 403)
        response = self.client.post(self.url, json.dumps(self.source), content_type="application/json",
                                    HTTP_X_CSRFTOKEN=self.csrf, HTTP_ORIGIN="https://other.example")
        self.assertEqual(response.status_code, 403)
        _, token = api_keys.issue(self.owner)
        anonymous = Client(enforce_csrf_checks=True)
        anonymous.get(reverse("login"))
        response = anonymous.post(self.url, json.dumps(self.source), content_type="application/json",
                                  HTTP_X_CSRFTOKEN=anonymous.cookies["csrftoken"].value,
                                  HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(response.status_code, 401)
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.assertEqual(self.post(self.source).status_code, 401)
        request = RequestFactory().post(self.url, json.dumps(self.source), content_type="application/json")
        request.user = self.owner
        self.assertEqual(views.selection_create(request).status_code, 401)
        self.assert_no_creation()

    def test_wrong_methods_are_rejected_without_creating_sources(self):
        for method in ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"]:
            with self.subTest(method=method):
                response = self.client.generic(method, self.url, HTTP_X_CSRFTOKEN=self.csrf)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "POST")
        self.assert_no_creation()

    def test_invalid_foreign_archived_and_unavailable_decks_are_rejected(self):
        with patch("learning.authoring.create_card") as create:
            for deck_id in [self.foreign.pk, self.archived.pk, 999999, 0, -1, True, False, None, "1", 1.5, [], {}, 2**63, 10**100]:
                with self.subTest(deck_id=deck_id):
                    response = self.post({**self.source, "deck_id": deck_id})
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.json()["code"], "invalid_deck")
        create.assert_not_called()
        self.assert_no_creation()

    def test_invalid_payload_fields_and_languages_never_reach_creation(self):
        invalid = [None, [], "expression", True, {}]
        invalid += [{key: value for key, value in self.source.items() if key != missing} for missing in self.source]
        invalid += [{**self.source, extra: "not accepted"} for extra in
                    ["context", "url", "explanation", "word", "owner_id", "api_key", "presentation_id"]]
        invalid += [{**self.source, "text": value} for value in ["", " \t\r\n", 1, True, [], {}, None, "\ud800", "x" * 501]]
        for field in ["target_language", "native_language"]:
            invalid += [{**self.source, field: value} for value in [None, False, 1, [], {}, "", "\ud800", "French"]]
        invalid += [{**self.source, "target_language": "Spanish", "native_language": "Spanish"},
                    {**self.source, "target_language": "Chinese", "native_language": "English"}]
        with patch("learning.authoring.create_card") as create:
            for payload in invalid:
                with self.subTest(payload=payload):
                    self.assertEqual(self.post(payload).status_code, 400)
        create.assert_not_called()
        self.assert_no_creation()

    def test_malformed_json_utf8_and_wrong_content_type_are_rejected(self):
        for body in [b"", b"{", b"\xff", b"[" * 1100 + b"]" * 1100, b"NaN"]:
            with self.subTest(body=body[:30]):
                response = self.client.post(self.url, body, content_type="application/json", CONTENT_TYPE="application/json",
                                            HTTP_X_CSRFTOKEN=self.csrf)
                self.assertEqual(response.status_code, 400)
        for content_type in ["text/plain", "application/x-www-form-urlencoded"]:
            response = self.client.post(self.url, "{}", content_type=content_type, HTTP_X_CSRFTOKEN=self.csrf)
            self.assertEqual(response.status_code, 415)
        self.assert_no_creation()

    def streamed_request(self, body, length):
        class CountedStream(io.BytesIO):
            def __init__(self, data):
                super().__init__(data)
                self.read_sizes = []

            def read(self, size=-1):
                self.read_sizes.append(size)
                return super().read(size)

        request = RequestFactory().post(self.url, body, content_type="application/json")
        request.user = self.owner
        request._stream = CountedStream(body)
        if length is None:
            request.META.pop("CONTENT_LENGTH", None)
        else:
            request.META["CONTENT_LENGTH"] = length
        return request

    def test_declared_oversize_and_invalid_lengths_are_rejected_before_stream_reads(self):
        for length, status in [("8193", 413), ("1048576", 413), ("-1", 400), ("invalid", 400), ("1.5", 400)]:
            with self.subTest(length=length):
                request = self.streamed_request(b"x" * 1048576, length)
                self.assertEqual(views.selection_create(request).status_code, status)
                self.assertEqual(request._stream.read_sizes, [])
        self.assert_no_creation()

    def test_stream_reads_are_bounded_even_without_a_reliable_declared_length(self):
        for length in [None, "", "1"]:
            with self.subTest(length=length):
                request = self.streamed_request(b"x" * 1048576, length)
                self.assertEqual(views.selection_create(request).status_code, 413)
                self.assertEqual(request._stream.read_sizes, [8193])
                self.assertEqual(request._stream.tell(), 8193)
                self.assertFalse(hasattr(request, "_body"))
        self.assert_no_creation()

    def test_exact_request_and_expression_limits_are_accepted_but_not_truncated(self):
        body = json.dumps({**self.source, "text": "x" * 500}).encode()
        body += b" " * (8192 - len(body))
        self.assertEqual(len(body), 8192)
        response = views.selection_create(self.streamed_request(body, "8192"))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Card.objects.get().word, "x" * 500)
        self.assertEqual(views.selection_create(self.streamed_request(body + b" ", None)).status_code, 413)
        self.assertEqual(self.post({**self.source, "text": "x" * 501}).status_code, 400)
        self.assertEqual((Card.objects.count(), GenerationJob.objects.count()), (1, 1))

    def test_new_words_phrases_and_whitespace_use_blank_async_creation_and_minimal_responses(self):
        preferences = LearnerPreferences.objects.create(user=self.owner)
        before = LearnerPreferences.objects.values().get(pk=preferences.pk)
        cases = [("absorb", "absorb", "English", "Chinese"),
                 (" \t Café’s\n well-known\u00a0 phrase! \r\n", "Café’s well-known phrase!", "English", "Spanish"),
                 ("aprovechar", "aprovechar", "Spanish", "Chinese")]
        for selected, word, target, native in cases:
            with self.subTest(word=word):
                body = json.dumps({**self.source, "text": selected, "target_language": target, "native_language": native}, ensure_ascii=False)
                response = self.client.post(self.url, body, content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf)
                self.assertEqual(response.status_code, 201)
                card = Card.objects.get(word=word)
                self.assertEqual(response.json(), {"created": True, "card_url": reverse("card", args=[card.pk]), "archived": False})
                self.assertEqual((card.explanation, card.target_language, card.native_language), ("", target, native))
                self.assertFalse(card.ready)
                job = card.generation_jobs.get()
                self.assertEqual(job.state, "queued")
                self.assertEqual(job.provenance["input_explanation"], "")
                self.assertIsNone(job.started_at)
                self.assertIsNone(job.deadline)
        self.assertEqual(LearnerPreferences.objects.values().get(pk=preferences.pk), before)
        self.assertFalse(Presentation.objects.exists())
        self.assertFalse(ScoredReview.objects.exists())

    def test_exact_duplicates_are_scoped_to_deck_languages_and_case(self):
        first = self.post(self.source)
        self.assertEqual(first.status_code, 201)
        again = self.post(self.source)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json(), {**first.json(), "created": False})
        another = Deck.objects.create(owner=self.owner, name="Independent")
        for changes in [{"deck_id": another.pk}, {"native_language": "Spanish"}, {"text": "Absorb"}]:
            self.assertEqual(self.post({**self.source, **changes}).status_code, 201)
        self.assertEqual((Card.objects.count(), GenerationJob.objects.count()), (4, 4))
        self.assertFalse(LearnerPreferences.objects.exists())

    def test_active_and_archived_duplicates_preserve_source_progress_examples_and_frozen_history(self):
        card, _ = authoring.create_card(self.deck, "vocabulary", {"word": "absorb", "explanation": "An authored meaning.",
                                                               "target_language": "English", "native_language": "Chinese"})
        pair = ExamplePair.objects.create(card=card, source_version=1, target_sentence="We absorb water.",
            target_highlight="absorb", target_highlight_start=3, native_sentence="我们吸收水。", native_highlight="吸收", native_highlight_start=2)
        Card.objects.filter(pk=card.pk).update(ready=True, active_pair=pair, cue_pair=pair, cue_direction="recognition",
                                             direction_block=["recognition", "production"], direction_index=1)
        card.generation_jobs.update(state="done", result=pair, provenance={"original": True})
        review.submit(review.next_question(self.owner, self.deck), "forgot")
        card.refresh_from_db()
        self.assertEqual((card.collection, card.review_count), ("Forgot", 1))
        for archived in [False, True]:
            if archived:
                authoring.archive_card(card, True)
            before = self.learning_rows()
            response = self.post(self.source)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"created": False, "card_url": reverse("card", args=[card.pk]), "archived": archived})
            self.assertEqual(self.learning_rows(), before)

    def test_uncertain_response_retries_do_not_requeue_or_change_preparation(self):
        self.assertEqual(self.post(self.source).status_code, 201)
        job = GenerationJob.objects.get()
        for state in ["queued", "processing", "failed"]:
            job.state = state
            if state != "queued":
                job.started_at = timezone.now()
                job.deadline = job.started_at + timedelta(minutes=5)
                job.provenance["original"] = state
            job.save()
            before = self.learning_rows()
            for _ in range(2):
                response = self.post(self.source)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()["created"])
                self.assertEqual(self.learning_rows(), before)
        authoring.archive_card(job.card, True)
        before = self.learning_rows()
        self.assertTrue(self.post(self.source).json()["archived"])
        self.assertEqual(self.learning_rows(), before)

    def test_disabled_selection_does_not_change_api_key_or_normal_authoring_contracts(self):
        LearnerPreferences.objects.create(user=self.owner, selection_add_enabled=False)
        api_url = reverse("api_vocabulary_create", args=[self.deck.pk])
        source = {"word": "absorb", "target_language": "English", "native_language": "Chinese"}
        response = self.client.post(api_url, json.dumps(source), content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(response.status_code, 401)
        self.assert_no_creation()
        _, token = api_keys.issue(self.owner)
        response = self.client.post(api_url, json.dumps(source), content_type="application/json", HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(response.status_code, 201)
        response = self.client.post(reverse("card_create", args=[self.deck.pk]) + "?kind=vocabulary",
                                    {**source, "word": "ordinary form"}, HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.post(self.source).status_code, 403)
        self.assertEqual((Card.objects.count(), GenerationJob.objects.count()), (2, 2))
