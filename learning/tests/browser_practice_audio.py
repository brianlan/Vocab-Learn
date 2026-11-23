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
PRONUNCIATION_SCRIPT = (ROOT / "static/pronunciation.js").read_text()
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
        '<button type="button" class="button pronunciation-button" aria-label="Play pronunciation"'
        ' data-pronounce="sentence" data-pronounce-language="English"><span aria-hidden="true">🔊︎</span></button>'
        '<span class="quiet" role="status" data-pronunciation-status></span>'
        '<details class="paired-examples" open><summary>Paired examples</summary>'
        '<p class="sentence-audio"><span data-selection-region>The sentence.</span>'
        '<button type="button" class="button pronunciation-button" aria-label="Play target example sentence (English)"'
        ' data-play="target" data-src="/review/p-1/audio/target/"><span aria-hidden="true">🔊︎</span></button></p>'
        '<p class="sentence-audio"><span data-selection-region>句子。</span>'
        '<button type="button" class="button pronunciation-button" aria-label="Play native example sentence (Chinese)"'
        ' data-play="native" data-src="/review/p-1/audio/native/"><span aria-hidden="true">🔊︎</span></button></p></details>'
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
COUNT_PLAYS = ("window.playCalls = 0; const originalPlay = HTMLMediaElement.prototype.play; "
    "HTMLMediaElement.prototype.play = function (...args) { window.playCalls++; "
    "return originalPlay.apply(this, args); };")


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
        self.hold_audio = False
        self.held_audio = []
        self.held_next = []
        self.held_restart = []
        self.hold_action = False
        self.held_actions = []
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
        elif path.startswith(("/review/p-1/audio/", "/review/p-2/audio/")):
            self.audio_requests.append(path.rstrip("/").rsplit("/", 1)[-1])
            if self.hold_audio:
                self.held_audio.append(route)
            else:
                route.fulfill(content_type="audio/wav", body=CLIP)
        elif path == "/next":
            self.held_next.append(route)
        elif path == "/review/p-1/restart/":
            self.held_restart.append(route)
        elif path == "/status/":
            body = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            route.fulfill(content_type="application/json", body=body)
        elif path in ("/action/", "/retry/", "/exit/"):
            if path == "/action/" and self.hold_action:
                self.held_actions.append(route)
            else:
                route.fulfill(content_type="application/json", body=SUBMITTED if path == "/action/" else ASSESSED)
        else:
            self.unexpected.append(path)
            route.abort()

    def fixture_html(self, *, first_display="1", autoplay="1", state="question", presentation="p-1"):
        article = (f'<input type="hidden" name="csrfmiddlewaretoken" value="synthetic-csrf">'
            f'<article id="review-card" data-presentation="p-1" data-state="{state}" data-deadline=""'
            f' data-first-display="{first_display}" data-autoplay="{autoplay}"'
            f' data-action-url="/action/" data-status-url="/status/" data-retry-url="/retry/" data-exit-url="/exit/">'
            '<audio id="clip-player" preload="none"></audio>'
            '<div id="front"><div class="prompt prose"><div class="sentence-audio">'
            '<span data-selection-region>The sentence.</span>'
            '<button type="button" class="button pronunciation-button" aria-label="Play question sentence"'
            ' data-play="target" data-src="/review/p-1/audio/target/"><span aria-hidden="true">🔊︎</span></button>'
            '</div></div><div id="recording-indicator" class="recording-status" aria-live="polite"></div>'
            '<div class="front-actions"><button class="button" data-action="skip">Skip</button>'
            '<button class="button primary" id="speak" data-action="speak">Speak</button>'
            '<button class="button" data-action="forgot">Forgot</button></div>'
            '<div id="record-controls" class="row" hidden><button class="button" data-action="cancel">Cancel</button>'
            '<button class="button primary" data-action="stop" id="stop">Stop</button></div></div>'
            '<div id="back" hidden></div><div id="technical-message" class="notice" role="status" hidden></div>'
            '<div id="reconnect-controls" class="row" hidden><button class="button" data-action="check">Check</button>'
            '<button class="button" data-action="resend">Resend</button>'
            '<button class="button" data-action="exit">Exit</button></div></article>'
            '<div id="clock-recovery" class="notice" hidden><p>Timing was interrupted. Restart this question with a new clock, '
            'or choose Skip/Forgot. Your learning progress is unchanged.</p>'
            '<form method="post" action="/review/p-1/restart/">'
            '<input type="hidden" name="csrfmiddlewaretoken" value="synthetic-csrf">'
            '<button class="button">Restart question</button></form></div>')
        article = article.replace("p-1", presentation)
        return (f'<!doctype html><html><head><link rel="icon" href="data:,"></head><body>{article}'
            f'<script>{SCRIPT}</script><script>{PRONUNCIATION_SCRIPT}</script></body></html>')

    def load(self, *, init=None, **kwargs):
        self.fixture = self.fixture_html(**kwargs)
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

    def test_inline_speaker_is_visible_disabled_through_permission_recording_and_upload(self):
        self.hold_action = True
        self.load(init="""const acquire = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
            window.capturePaused = [];
            navigator.mediaDevices.getUserMedia = constraints => {
                window.capturePaused.push(document.querySelector('#clip-player').paused);
                return new Promise(resolve => { window.allowMicrophone = () => resolve(acquire(constraints)); });
            };""")
        self.wait_for_audio("target")
        speaker = self.page.locator("#front [data-play]")
        position = speaker.bounding_box()
        self.page.click("#speak")
        self.until("Boolean(window.allowMicrophone)")
        self.assertEqual(self.page.evaluate("window.capturePaused"), [True])
        self.assertTrue(speaker.is_visible())
        self.assertTrue(speaker.is_disabled())
        self.assertEqual(speaker.bounding_box(), position)
        self.page.click("[data-action=cancel]")
        self.assertTrue(speaker.is_enabled())
        speaker.focus()
        speaker.press("Enter")
        self.until("!document.querySelector('#clip-player').paused")
        self.page.evaluate("window.allowMicrophone()")  # cancelled permission cannot start recording
        self.page.wait_for_timeout(200)
        self.assertTrue(self.page.is_visible("#speak"))
        self.page.click("#speak")
        self.page.evaluate("window.allowMicrophone()")
        self.until("document.querySelector('#stop').hidden === false")
        self.assertTrue(speaker.is_visible())
        self.assertTrue(speaker.is_disabled())
        self.assertEqual(speaker.bounding_box(), position)
        self.page.click("[data-action=cancel]")
        self.assertTrue(speaker.is_enabled())
        speaker.click()
        self.until("!document.querySelector('#clip-player').paused")
        self.page.click("#speak")
        self.page.evaluate("window.allowMicrophone()")
        self.until("document.querySelector('#stop').hidden === false")
        self.page.wait_for_timeout(200)
        self.page.click("#stop")
        self.until("document.querySelector('#recording-indicator').textContent.includes('Saving')")
        self.assertTrue(speaker.is_visible())
        self.assertTrue(speaker.is_disabled())
        self.assertEqual(speaker.bounding_box(), position)
        self.assertTrue(self.page.evaluate("document.querySelector('#clip-player').paused"))
        for _ in range(30):
            if self.held_actions:
                break
            self.page.wait_for_timeout(100)
        self.assertEqual(len(self.held_actions), 1)
        self.assertIn('name="audio"', self.held_actions[0].request.post_data_buffer.decode(errors="replace"))
        self.held_actions[0].fulfill(content_type="application/json", body=ASSESSED)
        self.page.wait_for_selector("#next-card")

    def test_repeated_pending_play_does_not_pause_the_latest_play(self):
        self.check_latest_pending_play()

    def test_pending_play_cancel_then_play_permits_the_latest_play(self):
        self.check_latest_pending_play(cancel_between=True)

    def check_latest_pending_play(self, cancel_between=False):
        self.hold_audio = True
        self.load(autoplay="0", init=COUNT_PLAYS)
        self.page.click("[data-play]")
        self.until("window.playCalls === 1")
        self.wait_for_audio("target")
        if cancel_between:
            self.page.click("#speak")
            self.page.click("[data-action=cancel]")
        self.page.click("[data-play]")
        self.assertEqual(self.page.evaluate("window.playCalls"), 2)
        self.assertEqual(self.page.evaluate("document.querySelector('#clip-player').readyState"), 0)
        self.hold_audio = False
        for route in self.held_audio:
            route.fulfill(content_type="audio/wav", body=CLIP)
        self.until("document.querySelector('#clip-player').currentTime > 0.1")
        self.page.wait_for_timeout(300)
        self.assertFalse(self.page.evaluate("document.querySelector('#clip-player').paused"))

    def test_pending_play_stays_cancelled_during_speak_and_after_cancel(self):
        self.check_cancelled_pending_play()

    def test_pending_play_cancel_stays_paused_after_media_response(self):
        self.check_cancelled_pending_play(cancel_before_release=True)

    def check_cancelled_pending_play(self, cancel_before_release=False):
        self.hold_audio = True
        self.load(autoplay="0")
        self.page.click("[data-play]")
        self.wait_for_audio("target")
        self.assertEqual(self.page.evaluate("document.querySelector('#clip-player').readyState"), 0)
        self.page.click("#speak")
        self.assertTrue(self.page.evaluate("document.querySelector('#clip-player').paused"))
        self.until("document.querySelector('#recording-indicator').textContent.includes('Recording')")
        self.assertTrue(self.page.is_disabled("[data-play]"))
        if cancel_before_release:
            self.page.click("[data-action=cancel]")
        self.hold_audio = False
        for route in self.held_audio:
            route.fulfill(content_type="audio/wav", body=CLIP)
        self.until("document.querySelector('#clip-player').readyState >= 2")
        self.page.wait_for_timeout(300)
        self.assertTrue(self.page.evaluate("document.querySelector('#clip-player').paused"))
        if not cancel_before_release:
            self.page.click("[data-action=cancel]")
        self.page.wait_for_timeout(300)
        self.assertTrue(self.page.evaluate("document.querySelector('#clip-player').paused"))
        self.assertFalse(self.page.is_disabled("[data-play]"))

    def test_next_click_cancels_playing_and_pending_audio_before_navigation(self):
        events = []
        self.page.on("console", lambda message: events.append(message.text))
        for pending in (False, True):
            with self.subTest(pending=pending):
                self.hold_audio = pending
                self.held_audio = []
                self.held_next = []
                self.load(state="submitted", init=COUNT_PLAYS if not pending else None)
                self.page.wait_for_selector("#next-card")
                self.page.click("#back [data-play=target]")
                self.wait_for_audio("target")
                if pending:
                    self.until("document.querySelector('#clip-player').readyState === 0")
                else:
                    self.until("document.querySelector('#clip-player').currentTime > 0.1")
                self.page.evaluate("""() => {
                    const player = document.querySelector('#clip-player');
                    document.addEventListener('click', event => {
                        if (event.target.closest('#next-card')) console.log('next-paused:' + player.paused);
                    });
                    player.addEventListener('playing', () => console.log('old-clip-playing'));
                }""")
                events.clear()
                self.page.click("#next-card", no_wait_after=True)
                for _ in range(30):
                    if self.held_next:
                        break
                    self.page.wait_for_timeout(100)
                self.assertEqual(len(self.held_next), 1)  # navigation was not prevented
                self.assertEqual(self.page.url, ORIGIN + "/fixture")
                self.assertIn("next-paused:true", events)
                self.hold_audio = False
                for route in self.held_audio:
                    route.fulfill(content_type="audio/wav", body=CLIP)
                self.page.wait_for_timeout(300)
                self.assertNotIn("old-clip-playing", events)
                self.held_next[0].fulfill(content_type="text/html", body=self.fixture_html(presentation="p-2"))
                self.page.wait_for_url(ORIGIN + "/next")
                self.until("document.querySelector('#clip-player').currentTime > 0.1")
                self.assertEqual(self.page.get_attribute("#review-card", "data-presentation"), "p-2")
                self.assertEqual(self.page.evaluate("window.playCalls"), 1)
                self.page.wait_for_timeout(300)
                self.assertEqual(self.page.evaluate("window.playCalls"), 1)

    def test_restart_submit_cancels_playing_and_pending_audio_before_navigation(self):
        events = []
        self.page.on("console", lambda message: events.append(message.text))
        self.page.add_init_script("localStorage.removeItem('vocab-clock:p-1')")
        for pending in (False, True):
            for keyboard in (False, True):
                with self.subTest(pending=pending, keyboard=keyboard):
                    self.audio_requests = []
                    self.hold_audio = pending
                    self.held_audio = []
                    self.held_restart = []
                    self.load(first_display="0", autoplay="0")
                    self.page.wait_for_selector("#clock-recovery form", state="visible")
                    self.page.click("[data-play]")
                    self.wait_for_audio("target")
                    if pending:
                        self.assertEqual(self.page.evaluate("document.querySelector('#clip-player').readyState"), 0)
                    else:
                        self.until("document.querySelector('#clip-player').currentTime > 0.1")
                    self.page.evaluate("""() => {
                        const player = document.querySelector('#clip-player');
                        document.addEventListener('submit', event => {
                            if (event.target.closest('#clock-recovery')) console.log('restart-paused:' + player.paused);
                        });
                        player.addEventListener('playing', () => console.log('old-clip-playing'));
                    }""")
                    events.clear()
                    button = self.page.locator("#clock-recovery button")
                    if keyboard:
                        button.focus()
                        button.press("Enter", no_wait_after=True)
                    else:
                        button.click(no_wait_after=True)
                    for _ in range(30):
                        if self.held_restart:
                            break
                        self.page.wait_for_timeout(100)
                    self.assertEqual(len(self.held_restart), 1)
                    request = self.held_restart[0].request
                    self.assertEqual(request.method, "POST")
                    self.assertEqual(request.post_data, "csrfmiddlewaretoken=synthetic-csrf")
                    self.assertEqual(self.page.url, ORIGIN + "/fixture")
                    self.assertIn("restart-paused:true", events)
                    self.hold_audio = False
                    for route in self.held_audio:
                        route.fulfill(content_type="audio/wav", body=CLIP)
                    self.page.wait_for_timeout(400)
                    self.assertNotIn("old-clip-playing", events)
                    self.held_restart[0].fulfill(content_type="text/html", body=self.fixture_html(
                        presentation="p-2", autoplay="0"))
                    self.page.wait_for_url(ORIGIN + "/review/p-1/restart/")

    def test_pronunciation_cancels_playing_and_pending_sentence_without_blocking_word_speech(self):
        # Adapt only speech output; sentence playback and its pending response use native media.
        self.page.add_init_script("""window.wordRequests = [];
            window.SpeechSynthesisUtterance = function (text) { this.text = text; };
            Object.defineProperty(window, 'speechSynthesis', {value: {
                getVoices: () => [{lang: 'en-US'}], cancel: () => {},
                speak: utterance => window.wordRequests.push({text: utterance.text, lang: utterance.lang,
                    sentencePaused: document.querySelector('#clip-player').paused})
            }});""")
        for pending in (False, True):
            with self.subTest(pending=pending):
                self.audio_requests = []
                self.hold_audio = pending
                self.held_audio = []
                self.load(autoplay="0")
                self.page.click('[data-action=skip]')
                self.page.wait_for_selector('[data-pronounce]', state="visible")
                self.page.click('#back [data-play=target]')
                self.wait_for_audio("target")
                if pending:
                    self.assertEqual(self.page.evaluate("document.querySelector('#clip-player').readyState"), 0)
                else:
                    self.until("document.querySelector('#clip-player').currentTime > 0.1")
                self.page.evaluate("""document.querySelector('#clip-player').addEventListener('playing',
                    () => window.lateSentenceStarted = true)""")
                self.page.click('[data-pronounce] span')  # nested icon click still reaches both handlers
                self.assertEqual(self.page.evaluate("window.wordRequests"), [
                    {"text": "sentence", "lang": "en-US", "sentencePaused": True}])
                self.hold_audio = False
                for route in self.held_audio:
                    route.fulfill(content_type="audio/wav", body=CLIP)
                self.until("document.querySelector('#clip-player').readyState >= 2")
                self.page.wait_for_timeout(400)
                self.assertTrue(self.page.evaluate("document.querySelector('#clip-player').paused"))
                self.assertFalse(self.page.evaluate("Boolean(window.lateSentenceStarted)"))

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
