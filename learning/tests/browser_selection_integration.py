"""Explicit Playwright checks against real Django/session/CSRF and practice scripts.

Run with manage.py test learning.tests.browser_selection_integration. Browser tooling
is development-only; PLAYWRIGHT_CHROMIUM_EXECUTABLE can select desktop Chrome/Edge.
"""
import json
import os
from contextlib import asynccontextmanager
from unittest.mock import patch

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse
from playwright.async_api import async_playwright, expect

from learning import authoring, providers, review, work
from learning.models import Attempt, Card, Deck, ExamplePair, GenerationJob, LearnerPreferences, Presentation, ScoredReview


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SelectionAddIntegrationTests(StaticLiveServerTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("browser-learner")
        self.client.force_login(self.user)
        self.source_deck = Deck.objects.create(owner=self.user, name="Source content")
        self.destination = Deck.objects.create(owner=self.user, name="Reading")
        self.source = authoring.save_card(self.source_deck, "generic", {
            "question": "  Café’s\n **well-known** phrase!  ", "answer": "private-reference-74",
            "explanation": "An author-written explanation.",
        })
        self.network = patch("learning.providers.request", side_effect=AssertionError("No provider network calls"))
        self.request = self.network.start()
        self.addCleanup(self.network.stop)

    def tearDown(self):
        self.request.assert_not_called()

    @asynccontextmanager
    async def browser_page(self):
        async with async_playwright() as runtime:
            browser = await runtime.chromium.launch(
                executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE"),
                args=["--no-sandbox", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
            )
            context = await browser.new_context(base_url=self.live_server_url, viewport={"width": 1366, "height": 900},
                                                permissions=["microphone"])
            await context.add_cookies([{"name": settings.SESSION_COOKIE_NAME,
                "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value, "url": self.live_server_url}])
            errors = []
            context.on("page", lambda page: page.on("pageerror", lambda error: errors.append(str(error))))
            try:
                yield await context.new_page()
            finally:
                await context.close()
                await browser.close()
            self.assertEqual(errors, [])

    async def select(self, page, selector):
        region = page.locator(selector)
        await region.scroll_into_view_if_needed()
        await region.click()
        await region.evaluate("""node => {
            const range = document.createRange(); range.selectNodeContents(node);
            const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
        }""")

    async def choose_destination(self, page):
        await page.locator("#selection-add-toggle").click()
        await page.locator("#selection-add-deck").select_option(str(self.destination.pk))

    async def submit(self, page):
        async with page.expect_response(lambda response: response.url == self.live_server_url + reverse("selection_create")) as pending:
            await page.locator("#selection-add-submit").click()
        response = await pending.value
        self.assertEqual(set(response.request.post_data_json), {"deck_id", "text", "target_language", "native_language"})
        self.assertTrue(response.request.headers.get("x-csrftoken"))
        if response.ok:
            self.assertEqual(set(await response.json()), {"created", "card_url", "archived"})
        return response

    def test_real_creation_duplicates_settings_and_stale_disable(self):
        async_to_sync(self.creation_settings_flow)()
        cards = Card.objects.filter(deck=self.destination).order_by("pk")
        self.assertEqual(list(cards.values_list("word", "target_language", "native_language", "archived")), [
            ("Café’s well-known phrase!", "English", "Chinese", True),
            ("Café’s well-known phrase!", "Spanish", "Chinese", False),
            ("Café’s well-known phrase!", "English", "Spanish", False),
        ])
        self.assertTrue(all(card.explanation == "" and not card.ready for card in cards))
        self.assertEqual(GenerationJob.objects.count(), 3)
        self.assertFalse(Attempt.objects.exists())
        self.assertFalse(ScoredReview.objects.exists())
        preferences = LearnerPreferences.objects.get(user=self.user)
        self.assertEqual((preferences.selection_add_enabled, preferences.target_language, preferences.native_language),
                         (True, "Spanish", "Chinese"))

    async def creation_settings_flow(self):
        async with self.browser_page() as page:
            url = self.live_server_url + reverse("card", args=[self.source.pk])
            source_region = "section.panel.prose > div[data-selection-region]"
            posts = []
            page.on("request", lambda request: posts.append(request.post_data_json)
                    if request.url.endswith(reverse("selection_create")) else None)
            await page.goto(url)
            await self.select(page, source_region)
            await expect(page.locator("#selection-add-submit")).to_have_text("Choose a deck")
            self.assertEqual(posts, [])
            await self.choose_destination(page)
            await expect(page.locator("#selection-add-expression")).to_have_text("Café’s well-known phrase!")
            await expect(page.locator("#selection-add-language option:checked")).to_have_text("English → Chinese")
            response = await self.submit(page)
            self.assertEqual(response.status, 201)
            self.assertEqual(posts[-1], {"deck_id": self.destination.pk, "text": "Café’s well-known phrase!",
                                        "target_language": "English", "native_language": "Chinese"})
            await expect(page.locator("#selection-add-status")).to_have_text("Added to Reading · Preparing")
            self.assertEqual(page.url, url)

            for archived in [False, True]:
                if archived:
                    def archive():
                        card = Card.objects.get(deck=self.destination)
                        authoring.archive_card(card, True)
                        return Card.objects.values().get(pk=card.pk)
                    before = await sync_to_async(archive)()
                await self.select(page, source_region)
                await expect(page.locator("#selection-add-submit")).to_have_text("Add to Reading")
                response = await self.submit(page)
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())["archived"], archived)
                await expect(page.locator("#selection-add-status")).to_contain_text("Already in Reading")
                if archived:
                    await expect(page.locator("#selection-add-status")).to_contain_text("Archived")
                    self.assertEqual(await sync_to_async(lambda: Card.objects.values().get(pk=before["id"]))(), before)

            settings_page = await page.context.new_page()
            await settings_page.goto(reverse("settings"))
            await expect(settings_page.get_by_label("Enable selection add")).to_be_checked()
            await settings_page.get_by_label("Enable selection add").uncheck()
            await settings_page.get_by_role("button", name="Save settings").click()
            await expect(settings_page.get_by_text("Settings saved.", exact=True)).to_be_visible()
            await self.select(page, source_region)
            response = await self.submit(page)
            self.assertEqual(response.status, 403)
            self.assertEqual((await response.json())["code"], "disabled")
            await expect(page.locator("#selection-add-status")).to_contain_text("disabled")
            await expect(page.locator("#selection-add")).to_be_hidden()
            await page.reload()
            await self.select(page, source_region)
            await expect(page.locator("#selection-add")).to_be_hidden()

            await settings_page.get_by_label("Enable selection add").check()
            await settings_page.get_by_label("Default language pair").select_option(label="Spanish → Chinese")
            await settings_page.get_by_role("button", name="Save settings").click()
            await page.reload()
            await self.select(page, source_region)
            await expect(page.locator("#selection-add-submit")).to_have_text("Add to Reading")
            self.assertEqual((await self.submit(page)).status, 201)
            self.assertEqual(posts[-1]["target_language"], "Spanish")
            await self.select(page, source_region)
            await self.choose_destination(page)
            await page.locator("#selection-add-language").select_option(label="English → Spanish")
            self.assertEqual((await self.submit(page)).status, 201)
            await self.select(page, source_region)
            await page.locator("#selection-add-toggle").click()
            await expect(page.locator("#selection-add-language option:checked")).to_have_text("Spanish → Chinese")
            self.assertEqual(page.url, url)

    def vocabulary(self, target="English", native="Chinese", direction="recognition"):
        deck = Deck.objects.create(owner=self.user, name=f"{target}/{native}/{direction}")
        word = "glimmer" if target == "English" else "destello"
        card = authoring.save_card(deck, "vocabulary", {"word": word, "explanation": "A faint **light**.",
                                                       "target_language": target, "native_language": native})
        target_sentence = f"A {word} appeared."
        native_sentence, native_highlight = ("出现了一丝微光。", "微光") if native == "Chinese" else ("Apareció un destello.", "destello")
        pair = ExamplePair.objects.create(card=card, source_version=1, target_sentence=target_sentence,
            target_highlight=word, target_highlight_start=target_sentence.index(word), native_sentence=native_sentence,
            native_highlight=native_highlight, native_highlight_start=native_sentence.index(native_highlight))
        card.ready, card.active_pair = True, pair
        card.direction_block = [direction, "production" if direction == "recognition" else "recognition"]
        card.save()
        card.generation_jobs.update(state="done", result=pair)
        return card, review.next_question(self.user, deck)

    def test_practice_clock_recording_and_dynamic_assessment_are_isolated(self):
        card, presentation = self.vocabulary()
        before = Card.objects.values().get(pk=card.pk)
        frozen = presentation.snapshot.copy()
        async_to_sync(self.practice_flow)(presentation)
        self.assertEqual(Card.objects.values().get(pk=card.pk), before)
        presentation.refresh_from_db()
        self.assertEqual(presentation.snapshot, frozen)
        attempt = Attempt.objects.get(presentation=presentation)
        self.assertEqual((attempt.state, attempt.action, attempt.grade), ("failed", "speak", ""))
        self.assertGreater(attempt.duration, 1)
        self.assertTrue((settings.AUDIO_DIR / attempt.audio_name).is_file())
        self.assertFalse(ScoredReview.objects.exists())

    async def practice_flow(self, presentation):
        async with self.browser_page() as page:
            await page.add_init_script("""(() => {
                window.captureCalls = 0; window.capturedStreams = [];
                const acquire = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                navigator.mediaDevices.getUserMedia = async constraints => {
                    window.captureCalls++; const stream = await acquire(constraints);
                    window.capturedStreams.push(stream); return stream;
                };
            })();""")
            actions = []
            action_url = self.live_server_url + reverse("action", args=[presentation.pk])
            page.on("request", lambda request: actions.append(request) if request.url == action_url else None)
            await page.goto(reverse("presentation", args=[presentation.pk]))
            url = page.url
            clock_key = "vocab-clock:" + str(presentation.pk)
            self.assertNotIn(presentation.snapshot["native_sentence"], await page.content())
            self.assertNotIn(presentation.snapshot["explanation"], await page.content())
            await self.select(page, "#front .prompt")
            await self.choose_destination(page)
            first = await page.evaluate("key => JSON.parse(localStorage.getItem(key)).elapsed", clock_key)
            await page.wait_for_function("([key, first]) => JSON.parse(localStorage.getItem(key)).elapsed > first + 0.6",
                                         arg=[clock_key, first])
            self.assertEqual((await self.submit(page)).status, 201)
            clock = await page.evaluate("key => JSON.parse(localStorage.getItem(key))", clock_key)
            self.assertFalse(clock["waiting"])
            self.assertFalse(clock.get("pending", False))
            await expect(page.locator("#back")).to_be_hidden()
            self.assertEqual(await page.evaluate("captureCalls"), 0)
            self.assertEqual(actions, [])

            await page.locator("#speak").click()
            await expect(page.locator("#recording-indicator")).to_have_class("recording-status recording")
            await self.select(page, "#front .prompt")
            self.assertEqual((await self.submit(page)).status, 200)
            await expect(page.locator("#recording-indicator")).to_have_class("recording-status recording")
            self.assertTrue(await page.evaluate("capturedStreams[0].getAudioTracks().every(track => track.readyState === 'live')"))
            self.assertEqual(await page.evaluate("captureCalls"), 1)
            self.assertEqual(actions, [])
            await page.wait_for_function("([key, first]) => JSON.parse(localStorage.getItem(key)).elapsed > first + 1.3",
                                         arg=[clock_key, first])
            async with page.expect_response(action_url):
                await page.locator("#stop").click()
            await expect(page.locator("#back")).to_be_visible()
            await expect(page.locator("#front")).to_be_hidden()
            self.assertEqual(len(actions), 1)
            self.assertTrue(await page.evaluate("capturedStreams[0].getAudioTracks().every(track => track.readyState === 'ended')"))
            fixed = await sync_to_async(lambda: Attempt.objects.values().get(presentation=presentation))()
            self.assertGreaterEqual(fixed["duration"], clock["elapsed"])
            await self.select(page, "#back .explanation")
            self.assertEqual((await self.submit(page)).status, 201)
            self.assertEqual(await sync_to_async(lambda: Attempt.objects.values().get(pk=fixed["id"]))(), fixed)

            await page.locator("#selection-add-toggle").click()
            kind, attempt_id, claim, _ = await sync_to_async(work.claim_work)()
            self.assertEqual(kind, "assessment")
            await sync_to_async(work.save_stage)(attempt_id, claim, transcript="A glimmer of light")
            await expect(page.locator("#back .transcript")).to_have_text("A glimmer of light")
            processing = await sync_to_async(lambda: Attempt.objects.values().get(pk=attempt_id))()
            await page.locator("#selection-add-deck").select_option(str(self.destination.pk))
            await page.locator("#selection-add-language").select_option(label="English → Spanish")
            response = await self.submit(page)
            self.assertEqual(response.status, 201)
            self.assertEqual(response.request.post_data_json["text"], "A faint light.")
            self.assertEqual(await sync_to_async(lambda: Attempt.objects.values().get(pk=attempt_id))(), processing)
            await self.select(page, "#back .transcript")
            self.assertEqual((await self.submit(page)).status, 201)
            self.assertEqual(await sync_to_async(lambda: Attempt.objects.values().get(pk=attempt_id))(), processing)
            await sync_to_async(work.fail)("assessment", attempt_id, claim,
                                          providers.StageError("judge", "Controlled assessment failure."))
            await expect(page.locator("#back .recall-result h3")).to_have_text("Not assessed")
            failed = await sync_to_async(lambda: Attempt.objects.values().get(pk=attempt_id))()
            await self.select(page, "#back .answer")
            self.assertEqual((await self.submit(page)).status, 201)
            self.assertEqual(await sync_to_async(lambda: Attempt.objects.values().get(pk=attempt_id))(), failed)
            self.assertEqual((failed["audio_name"], failed["duration"]), (fixed["audio_name"], fixed["duration"]))
            self.assertEqual(len(actions), 1)
            self.assertEqual(await page.locator("#review-card #selection-add, #selection-add [data-action]").count(), 0)
            self.assertEqual(page.url, url)

    def test_frozen_visible_languages_not_hidden_response_drive_the_picker(self):
        LearnerPreferences.objects.create(user=self.user, native_language="Spanish")
        cases = [self.vocabulary(target, native, direction) for target, native in sorted(authoring.LANGUAGE_PAIRS)
                 for direction in ["recognition", "production"]]
        before = list(Presentation.objects.order_by("pk").values_list("snapshot", flat=True))
        async_to_sync(self.language_flow)(cases)
        self.assertEqual(list(Presentation.objects.order_by("pk").values_list("snapshot", flat=True)), before)
        self.assertFalse(Attempt.objects.exists())
        self.assertFalse(Card.objects.filter(deck=self.destination).exists())
        self.assertEqual(LearnerPreferences.objects.get(user=self.user).native_language, "Spanish")

    async def language_flow(self, cases):
        async with self.browser_page() as page:
            for card, presentation in cases:
                snapshot = presentation.snapshot
                language = snapshot["target_language"] if snapshot["direction"] == "recognition" else snapshot["native_language"]
                await page.goto(reverse("presentation", args=[presentation.pk]))
                self.assertEqual(await page.locator("#front .prompt").get_attribute("data-selection-language"), language)
                bootstrap = json.loads(await page.locator("#selection-add-config").text_content())
                self.assertFalse({"word", "reference", "snapshot", "question_html", "explanation"} & bootstrap.keys())
                if snapshot["direction"] == "production":
                    self.assertNotIn(card.word, await page.content())
                await self.select(page, "#front .prompt")
                await page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                if language == "Chinese":
                    await expect(page.locator("#selection-add")).to_be_hidden()
                else:
                    await expect(page.locator("#selection-add")).to_be_visible()
                    await self.choose_destination(page)
                    if language == "Spanish":
                        await expect(page.locator("#selection-add-language")).to_have_value("")
                        await page.locator("#selection-add-language").select_option(label="Spanish → Chinese")
                    else:
                        await expect(page.locator("#selection-add-language option:checked")).to_have_text("English → Spanish")
                    await page.keyboard.press("Escape")
                    await expect(page.locator("#selection-add")).to_be_hidden()
