"""Controlled Practice playback regression for review.js; run explicitly, not through Django discovery.

PLAYWRIGHT_CHROMIUM_EXECUTABLE=/path/to/chromium python -m unittest learning.tests.browser_practice_audio
Requires the optional Playwright Python installation and a Chromium browser, not a running app/database.
"""

import io
import json
import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit
import wave

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "static/review.js").read_text()
ORIGIN = "https://practice.test"  # getUserMedia needs a secure context


def clip_bytes(seconds=6):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b"\0\0"*16000*seconds)
    return buffer.getvalue()


CLIP = clip_bytes()


def back_html(marker=""):
    return ('<section class="recall-result"><span class="eyebrow">YOUR RECALL THIS TIME</span>' + marker + "</section>"
        '<details class="paired-examples" open><summary>Paired examples</summary>'
        '<p><button class="button" data-play="target" data-src="/review/p-1/audio/target/">Play</button> The sentence.</p>'
        '<p><button class="button" data-play="native" data-src="/review/p-1/audio/native/">Play</button> 句子。</p></details>'
        '<div class="back-actions"><a id="next-card" class="button primary" href="/next">Next card</a></div>')


def payload_json(state, html):
    return json.dumps({"state": state, "transcript": "", "grade": None, "next_due": None, "deadline": None,
        "metrics": {}, "collection": "Normal", "back_html": html})


PROCESSING_A = payload_json("processing", back_html())
PROCESSING_B = payload_json("processing", back_html("<p>updated</p>"))
ASSESSED = payload_json("assessed", back_html())
SUBMITTED = payload_json("submitted", "<p>checking</p>")
BLOCKED_PLAY = ("(() => { let blocked = true; const original = HTMLMediaElement.prototype.play; "
    "HTMLMediaElement.prototype.play = function (...args) { "
    "if (blocked) { blocked = false; return Promise.reject(new DOMException('blocked', 'NotAllowedError')); } "
    "return original.apply(this, args); }; })();")


class PracticeAudioBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None,
            headless=True,
            # The synthetic page has no user gesture for the autoplay attempt; the
            # blocked-autoplay path is exercised separately through an injected rejection.
            args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required",
                  "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1000, "height": 900}, ignore_https_errors=True)
        self.page = self.context.new_page()
        self.errors = []
        self.unexpected = []
        self.audio_requests = []
        self.statuses = [ASSESSED]
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.route("**/*", self.route)

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.unexpected, [])

    def route(self, route):
        path = urlsplit(route.request.url).path
        if path == "/fixture":
            route.fulfill(content_type="text/html", body=self.fixture)
        elif path.startswith("/review/p-1/audio/"):
            self.audio_requests.append(path.rstrip("/").rsplit("/", 1)[-1])
            route.fulfill(content_type="audio/wav", body=CLIP)
        elif path == "/status/":
            body = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            route.fulfill(content_type="application/json", body=body)
        elif path in ("/action/", "/retry/", "/exit/"):
            route.fulfill(content_type="application/json", body=SUBMITTED if path == "/action/" else ASSESSED)
        else:
            self.unexpected.append(path)
            route.abort()

    def load(self, *, first_display="1", autoplay="1", state="question", init=None):
        article = (f'<input type="hidden" name="csrfmiddlewaretoken" value="synthetic-csrf">'
            f'<article id="review-card" data-presentation="p-1" data-state="{state}" data-deadline=""'
            f' data-first-display="{first_display}" data-autoplay="{autoplay}"'
            f' data-action-url="/action/" data-status-url="/status/" data-retry-url="/retry/" data-exit-url="/exit/">'
            '<audio id="clip-player" preload="none"></audio>'
            '<div id="front"><div id="recording-indicator" class="recording-status" aria-live="polite"></div>'
            '<div class="front-actions"><button class="button" data-action="skip">Skip</button>'
            '<button class="button" data-play="target" data-src="/review/p-1/audio/target/">Play</button>'
            '<button class="button primary" id="speak" data-action="speak">Speak</button>'
            '<button class="button" data-action="forgot">Forgot</button></div>'
            '<div id="record-controls" class="row" hidden><button class="button" data-action="cancel">Cancel</button>'
            '<button class="button primary" data-action="stop" id="stop">Stop</button></div></div>'
            '<div id="back" hidden></div><div id="technical-message" class="notice" role="status" hidden></div>'
            '<div id="reconnect-controls" class="row" hidden><button class="button" data-action="check">Check</button>'
            '<button class="button" data-action="resend">Resend</button>'
            '<button class="button" data-action="exit">Exit</button></div></article><div id="clock-recovery" hidden></div>')
        self.fixture = f'<!doctype html><html><head><link rel="icon" href="data:,"></head><body>{article}<script>{SCRIPT}</script></body></html>'
        if init:
            self.page.add_init_script(init)
        self.page.goto(ORIGIN + "/fixture")

    def wait_for_audio(self, side, limit=30):
        for _ in range(limit):
            if side in self.audio_requests:
                return
            self.page.wait_for_timeout(100)
        self.fail(f"no {side} audio request; got {self.audio_requests}")

    def clock_elapsed(self):
        return self.page.evaluate("JSON.parse(localStorage.getItem('vocab-clock:p-1')).elapsed")

    def until(self, expression, limit=30):
        for _ in range(limit):
            if self.page.evaluate(expression):
                return
            self.page.wait_for_timeout(100)
        self.fail(f"condition never held: {expression}")

    def test_first_display_autoplays_once_and_the_recall_clock_keeps_running(self):
        self.load()
        self.wait_for_audio("target")
        self.assertFalse(self.page.evaluate("document.querySelector('#clip-player').paused"))
        before = self.clock_elapsed()
        self.page.wait_for_timeout(1200)
        self.assertGreater(self.page.evaluate("document.querySelector('#clip-player').currentTime"), 0)
        # Listening consumes ordinary recall time: the clock keeps counting while the clip plays.
        self.assertGreater(self.clock_elapsed(), before)
        self.page.wait_for_timeout(400)
        self.assertEqual(self.audio_requests, ["target"])  # exactly one autoplay attempt, no repeats

    def test_disabled_autoplay_and_a_reload_use_manual_playback(self):
        self.load(autoplay="0")
        self.page.wait_for_timeout(800)
        self.assertEqual(self.audio_requests, [])
        self.assertTrue(self.page.evaluate("document.querySelector('#clip-player').paused"))
        self.page.click("[data-play]")
        self.wait_for_audio("target")
        self.assertFalse(self.page.evaluate("document.querySelector('#clip-player').paused"))
        self.load(first_display="0")  # a resumed question never autoplays again
        self.page.wait_for_timeout(800)
        self.assertEqual(self.audio_requests, ["target"])
        self.assertTrue(self.page.evaluate("document.querySelector('#clip-player').paused"))

    def test_a_blocked_autoplay_keeps_play_available(self):
        self.load(init=BLOCKED_PLAY)
        self.page.wait_for_timeout(600)  # the injected rejection refuses the autoplay attempt
        self.assertTrue(self.page.evaluate("document.querySelector('#clip-player').paused"))
        self.assertFalse(self.page.evaluate("document.querySelector('[data-play]').disabled"))
        self.page.click("[data-play]")
        self.wait_for_audio("target")
        self.until("!document.querySelector('#clip-player').paused")

    def test_speak_pauses_first_and_other_controls_cancel_playback(self):
        self.load()
        self.page.click("[data-play]")
        self.wait_for_audio("target")
        self.page.click("#speak")
        self.assertTrue(self.page.evaluate("document.querySelector('#clip-player').paused"))
        self.until("document.querySelector('[data-play]').disabled")  # Play disabled while requesting/recording
        self.page.click("[data-action=cancel]")
        self.assertFalse(self.page.evaluate("document.querySelector('[data-play]').disabled"))
        self.assertTrue(self.page.evaluate("document.querySelector('#clip-player').paused"))
        self.page.click("[data-play]")
        self.page.click("[data-action=skip]")  # any Practice control cancels playback
        self.assertTrue(self.page.evaluate("document.querySelector('#clip-player').paused"))

    def test_polling_preserves_one_player_and_back_controls_without_implicit_replay(self):
        self.statuses = [PROCESSING_A, PROCESSING_B, ASSESSED]
        self.load(state="submitted")
        self.page.wait_for_selector("[data-play=native]", state="visible")
        self.assertEqual(self.audio_requests, [])  # polling never starts a clip
        self.page.click("[data-play=native]")
        self.wait_for_audio("native")
        self.assertFalse(self.page.evaluate("document.querySelector('#clip-player').paused"))
        self.page.evaluate("window.__player = document.querySelector('#clip-player')")
        self.page.wait_for_timeout(1500)  # a status update replaces the back while the clip plays
        self.assertTrue(self.page.evaluate("document.querySelector('#clip-player') === window.__player"))
        self.assertFalse(self.page.evaluate("document.querySelector('#clip-player').paused"))
        self.assertEqual(self.audio_requests, ["native"])
