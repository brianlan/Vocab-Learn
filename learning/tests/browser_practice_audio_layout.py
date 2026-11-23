"""Issue #24: real styled Practice, sentence selection and keyboard playback.

Run explicitly with manage.py test learning.tests.browser_practice_audio_layout.
PLAYWRIGHT_CHROMIUM_EXECUTABLE can select a locally installed Chromium.
"""
import io
import os
from contextlib import asynccontextmanager
from pathlib import Path
import re
import tempfile
from unittest.mock import patch
import wave

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse
from playwright.async_api import async_playwright, expect

from learning import authoring, review
from learning.models import Deck, ExamplePair, LearnerPreferences, SpeechClip


ENGLISH = (
    "A glimmer appeared beyond the quiet garden while we watched the evening clouds "
    "drift over the distant mountains, and everyone waited patiently for the final light."
)
MANDARIN = (
    "我们站在安静的花园里，看着远处的山峰和慢慢飘过的晚云，忽然发现天边出现了一丝微光，"
    "于是大家都耐心地等待着，希望在夜幕降临之前还能看见最后的一点光亮。"
)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PracticeAudioLayoutTests(StaticLiveServerTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir="/tmp/opencode", prefix="practice-layout-tts-")
        self.addCleanup(directory.cleanup)
        override = override_settings(TTS_DIR=Path(directory.name))
        override.enable()
        self.addCleanup(override.disable)
        self.user = get_user_model().objects.create_user("practice-layout-learner")
        self.client.force_login(self.user)
        LearnerPreferences.objects.create(user=self.user, autoplay_enabled=False, selection_add_enabled=True)
        network = patch("learning.providers.request", side_effect=AssertionError("No provider network calls"))
        self.request = network.start()
        self.addCleanup(network.stop)
        sound = io.BytesIO()
        with wave.open(sound, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\0\0" * 16000 * 6)
        self.sound = sound.getvalue()

    def tearDown(self):
        self.request.assert_not_called()

    def presentation(self, direction):
        deck = Deck.objects.create(owner=self.user, name=f"Layout {direction}")
        card = authoring.save_card(deck, "vocabulary", {
            "word": "glimmer", "explanation": "A faint light.",
            "target_language": "English", "native_language": "Chinese",
        })
        pair = ExamplePair.objects.create(
            card=card, source_version=card.source_version,
            target_sentence=ENGLISH, target_highlight="glimmer", target_highlight_start=ENGLISH.index("glimmer"),
            native_sentence=MANDARIN, native_highlight="微光", native_highlight_start=MANDARIN.index("微光"),
        )
        card.ready, card.active_pair = True, pair
        card.direction_block = [direction, "production" if direction == "recognition" else "recognition"]
        card.save()
        card.generation_jobs.update(state="done", result=pair)
        for side, language in [("target", "English"), ("native", "Chinese")]:
            name = f"{pair.pk}.{side}.mp3"
            SpeechClip.objects.update_or_create(pair=pair, side=side,
                defaults={"language": language, "state": "done", "file": name})
            (settings.TTS_DIR / name).write_bytes(self.sound)
        return review.next_question(self.user, deck)

    @asynccontextmanager
    async def browser_page(self, width):
        async with async_playwright() as runtime:
            browser = await runtime.chromium.launch(
                executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE"), args=["--no-sandbox"])
            context = await browser.new_context(base_url=self.live_server_url,
                                                viewport={"width": width, "height": 900})
            await context.add_cookies([{"name": settings.SESSION_COOKIE_NAME,
                "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value, "url": self.live_server_url}])
            # Observe native playback without replacing media, templates, styles or application scripts.
            await context.add_init_script("""window.practicePlays = [];
                const nativePlay = HTMLMediaElement.prototype.play;
                HTMLMediaElement.prototype.play = function (...args) {
                    window.practicePlays.push({src: this.src, time: this.currentTime});
                    return nativePlay.apply(this, args);
                };""")
            page = await context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                yield page
            finally:
                await context.close()
                await browser.close()
            self.assertEqual(errors, [])

    async def assert_actions(self, page):
        actions = page.locator("#front .front-actions > button")
        self.assertEqual(await actions.evaluate_all("nodes => nodes.map(node => node.dataset.action)"),
                         ["skip", "speak", "forgot"])
        boxes = [await actions.nth(index).bounding_box() for index in range(3)]
        self.assertTrue(all(box is not None for box in boxes))
        skip, speak, forgot = boxes
        self.assertAlmostEqual(skip["y"], speak["y"], delta=1)
        self.assertAlmostEqual(speak["y"], forgot["y"], delta=1)
        self.assertLess(skip["x"], speak["x"])
        self.assertLess(speak["x"], forgot["x"])
        self.assertGreater(speak["width"], skip["width"])
        self.assertGreater(speak["width"], forgot["width"])
        self.assertEqual(await page.locator(".front-actions [data-play]").count(), 0)

    async def assert_sentence(self, page, selector, text, language):
        sentence = page.locator(selector)
        region = sentence.locator("[data-selection-region]")
        button = sentence.locator("[data-play]")
        await expect(region).to_have_text(text)
        await expect(button).to_have_count(1)
        await expect(button).to_have_accessible_name(re.compile(r"Play .+ sentence"))
        geometry = await sentence.evaluate("""node => {
            const region = node.querySelector('[data-selection-region]');
            const button = node.querySelector('[data-play]');
            const walker = document.createTreeWalker(region, NodeFilter.SHOW_TEXT);
            const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
            const first = document.createRange(); first.setStart(nodes[0], 0); first.setEnd(nodes[0], 1);
            const lastNode = nodes.at(-1), last = document.createRange();
            last.setStart(lastNode, lastNode.length - 1); last.setEnd(lastNode, lastNode.length);
            const end = last.getBoundingClientRect(), start = first.getBoundingClientRect();
            const speaker = button.getBoundingClientRect();
            const width = node.getBoundingClientRect().width;
            let orphaned = false;
            for (let tight = 160; tight <= width; tight += 7) {
                node.style.width = tight + 'px';
                const ending = last.getBoundingClientRect(), icon = button.getBoundingClientRect();
                if (Math.min(ending.bottom, icon.bottom) <= Math.max(ending.top, icon.top)) orphaned = true;
            }
            node.style.removeProperty('width');
            return {outside: !button.closest('[data-selection-region]'),
                follows: !!(region.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING),
                wraps: end.top > start.top, orphaned,
                end: end.toJSON(), speaker: speaker.toJSON(),
                overflow: document.documentElement.scrollWidth > innerWidth};
        }""")
        self.assertTrue(geometry["outside"])
        self.assertTrue(geometry["follows"])
        self.assertTrue(geometry["wraps"], f"Fixture must wrap: {selector}")
        self.assertFalse(geometry["overflow"], f"Horizontal overflow: {selector}")
        self.assertFalse(geometry["orphaned"], f"Speaker separated at a tight wrap: {selector}")
        end, speaker = geometry["end"], geometry["speaker"]
        self.assertGreater(min(end["bottom"], speaker["bottom"]), max(end["top"], speaker["top"]),
                           f"Sentence ending orphaned from speaker: {selector}: {geometry}")
        self.assertGreaterEqual(speaker["left"], end["right"] - 1)

        await region.scroll_into_view_if_needed()
        await region.click()
        selected = await region.evaluate("""node => {
            const range = document.createRange(); range.selectNodeContents(node);
            const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
            return selection.toString();
        }""")
        self.assertEqual(selected, text)  # Includes highlighted text and punctuation, never the speaker glyph.
        if language == "English":
            await expect(page.locator("#selection-add")).to_be_visible()
            await page.locator("#selection-add-toggle").click()
            await expect(page.locator("#selection-add-expression")).to_have_text(text)
        else:
            # Chinese is not an authoring target; selection must still work without offering an unsupported add.
            await expect(page.locator("#selection-add")).to_be_hidden()
        await page.keyboard.press("Escape")
        await page.evaluate("getSelection().removeAllRanges()")

    async def assert_keyboard_replay(self, page, selector, presentation, side):
        button = page.locator(selector)
        await button.focus()
        await page.keyboard.press("Shift+Tab")
        await expect(button).not_to_be_focused()
        await page.keyboard.press("Tab")
        await expect(button).to_be_focused()
        self.assertEqual(await button.evaluate("node => getComputedStyle(node).outlineStyle"), "solid")
        url = self.live_server_url + reverse("clip_audio", args=[presentation.pk, side])
        self.assertEqual(await button.get_attribute("data-src"), reverse("clip_audio", args=[presentation.pk, side]))
        for replay in (False, True):
            if replay:
                await page.locator("#clip-player").evaluate("player => { player.currentTime = 2; }")
            count = await page.evaluate("practicePlays.length")
            await page.keyboard.press("Enter")
            await page.wait_for_function("count => practicePlays.length === count + 1", arg=count)
            played = await page.evaluate("practicePlays.at(-1)")
            self.assertEqual(played["src"], url)
            self.assertEqual(played["time"], 0)
            await page.wait_for_function("""url => {
                const player = document.querySelector('#clip-player');
                return player.currentSrc === url && !player.paused && player.currentTime > 0.1;
            }""", arg=url)

    async def layout_flow(self, presentation, width):
        async with self.browser_page(width) as page:
            await page.goto(reverse("presentation", args=[presentation.pk]))
            # A computed grid proves the real stylesheet loaded, rather than testing unstyled fixture HTML.
            self.assertEqual(await page.locator(".front-actions").evaluate("node => getComputedStyle(node).display"), "grid")
            await self.assert_actions(page)
            side = "target" if presentation.snapshot["direction"] == "recognition" else "native"
            text, language = (ENGLISH, "English") if side == "target" else (MANDARIN, "Chinese")
            await self.assert_sentence(page, "#front .sentence-audio", text, language)
            await self.assert_keyboard_replay(page, "#front [data-play]", presentation, side)

            async with page.expect_response(self.live_server_url + reverse("action", args=[presentation.pk])) as response:
                await page.locator('[data-action="skip"]').click()
            self.assertTrue((await response.value).ok)
            await expect(page.locator("#back")).to_be_visible()
            await page.locator("#back .paired-examples > summary").click()
            for index, (side, text, language) in enumerate([
                ("target", ENGLISH, "English"), ("native", MANDARIN, "Chinese"),
            ]):
                await self.assert_sentence(page, f"#back .paired-examples .sentence-audio:nth-of-type({index + 1})",
                                           text, language)
                await self.assert_keyboard_replay(page, f'#back [data-play="{side}"]', presentation, side)

    def test_desktop_styled_sentences_selection_and_keyboard_playback(self):
        for direction in ("recognition", "production"):
            with self.subTest(direction=direction, width=1366):
                async_to_sync(self.layout_flow)(self.presentation(direction), 1366)

    def test_narrow_styled_sentences_selection_and_keyboard_playback(self):
        for direction in ("recognition", "production"):
            with self.subTest(direction=direction, width=360):
                async_to_sync(self.layout_flow)(self.presentation(direction), 360)
