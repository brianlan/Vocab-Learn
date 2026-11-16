"""Isolated browser states; run explicitly, not through Django test discovery.

PLAYWRIGHT_CHROMIUM_EXECUTABLE=/path/to/chromium python -m unittest learning.tests.browser_selection_add
Requires the optional Playwright Python installation and a Chromium browser, not a running app/database.
"""

import json
import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "static/selection-add.js").read_text()
CSS = (ROOT / "static/app.css").read_text()
PARTIAL = (ROOT / "templates/learning/selection_add.html").read_text()
ORIGIN = "http://selection.test"
STORAGE_KEY = "vocab-selection-deck:learner-a"
CONTENT = """
<input type="hidden" name="csrfmiddlewaretoken" value="synthetic-csrf">
<p id="outside" tabindex="0">Outside the learning content</p>
<main id="content">
  <article id="review-card">
    <p id="english" data-selection-region data-selection-language="English" tabindex="0">  <span>Café</span>\n <strong>isn't</strong>  <em>state-of-the-art</em>.  </p>
    <p id="unknown" data-selection-region tabindex="0">naïve co-op’s déjà vu</p>
    <p id="spanish" data-selection-region data-selection-language="Spanish">¿Dónde está el café?</p>
    <p id="chinese" data-selection-region data-selection-language="Chinese">这是中文。</p>
    <p id="unsupported" data-selection-region data-selection-language="French">bonjour</p>
    <div id="guarded" data-selection-region>safe
      <a id="link" href="#">linked words</a><button id="control" type="button">a control</button>
      <input id="input" value="input words"><textarea id="textarea">textarea words</textarea>
      <span id="editing" contenteditable="true">editable words</span>
      <nav id="navigation">navigation words</nav><span id="hidden" hidden>secret answer</span>
      <span id="invisible" style="visibility:hidden">invisible answer</span>
      <span id="transparent" style="opacity:0">transparent answer</span>
      <span id="role-control" role="button">custom control</span> tail
    </div>
    <p id="blank" data-selection-region> \n\t </p>
    <div id="nested" data-selection-region>outer <span data-selection-region>inner</span> outer</div>
    <p id="dynamic" data-selection-region>Initial answer</p>
    <button id="practice-control" type="button" data-action="speak">Practice control</button>
  </article>
</main>
"""


class SelectionAddBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None,
            headless=True,
            args=["--no-sandbox"],
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1000, "height": 900})
        self.page = self.context.new_page()
        self.errors = []
        self.unexpected_requests = []
        self.requests = []
        self.routes = []
        self.hold = False
        self.failure = None
        self.reply = (201, {"created": True, "card_url": "/cards/42/", "archived": False})
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.route("**/*", self.route)

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.unexpected_requests, [])

    def route(self, route):
        path = urlsplit(route.request.url).path
        if path == "/fixture":
            route.fulfill(content_type="text/html", body=self.fixture)
        elif path == "/selection-add/":
            self.requests.append({"body": route.request.post_data_json, "headers": route.request.headers})
            if self.hold:
                self.routes.append(route)
            elif self.failure == "network":
                route.abort("failed")
            elif self.failure == "html":
                route.fulfill(status=403, content_type="text/html", body="Sign in")
            else:
                self.respond(route)
        else:
            self.unexpected_requests.append(route.request.url)
            route.abort()

    def respond(self, route=None):
        status, body = self.reply
        (route or self.routes.pop(0)).fulfill(status=status, content_type="application/json", body=json.dumps(body))

    def load(self, *, remembered=None, storage_failure=None, clear_storage=False, **changes):
        self.config = {
            "user_id": "learner-a", "enabled": True,
            "target_language": "English", "native_language": "Chinese",
            "decks": [{"id": 1, "name": "Reading"}, {"id": 2, "name": "Spanish shelf"}],
            "language_pairs": [["English", "Chinese"], ["English", "Spanish"], ["Spanish", "Chinese"]],
            "create_url": "/selection-add/", "create_deck_url": "/decks/", "settings_url": "/settings/",
        }
        self.config.update(changes)
        bootstrap = json.dumps(self.config).replace("<", "\\u003c")
        self.fixture = (
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><link rel="icon" href="data:,">'
            f"<style>{CSS}\nbody{{padding:24px}}#content{{max-width:700px}}p{{margin-bottom:16px}}</style>"
            f"</head><body>{CONTENT}{PARTIAL}"
            f'<script type="application/json" id="selection-add-config">{bootstrap}</script></body></html>'
        )
        self.page.goto(ORIGIN + "/fixture")
        if clear_storage:
            self.page.evaluate("localStorage.clear()")
        if remembered is not None:
            self.page.evaluate("([key, value]) => localStorage.setItem(key, String(value))", [self.key, remembered])
        if storage_failure == "access":
            self.page.evaluate("Object.defineProperty(window, 'localStorage', {get() {throw new Error('Storage blocked')}})")
        elif storage_failure:
            self.page.evaluate("method => {Storage.prototype[method] = () => {throw new Error('Storage blocked')}}", storage_failure)
        self.page.add_script_tag(content=SCRIPT)

    @property
    def key(self):
        return "vocab-selection-deck:" + self.config["user_id"]

    def settle(self):
        self.page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

    def select(self, selector):
        self.page.locator(selector).evaluate("""element => {
            const range = document.createRange(); range.selectNodeContents(element);
            const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
        }""")
        self.settle()

    def picker(self, deck=None, pair=None):
        if not self.page.locator("#selection-add-picker").is_visible():
            self.page.locator("#selection-add-toggle").click()
        if deck is not None:
            self.page.locator("#selection-add-deck").select_option(str(deck))
        if pair is not None:
            self.page.locator("#selection-add-language").select_option(str(pair))

    def add(self, button="#selection-add-submit"):
        with self.page.expect_request("**/selection-add/"):
            self.page.locator(button).click()
        self.settle()

    def assert_payload(self, text, deck=1, target="English", native="Chinese"):
        self.assertEqual(self.requests[-1]["body"], {
            "deck_id": deck, "text": text, "target_language": target, "native_language": native,
        })
        self.assertEqual(self.requests[-1]["headers"]["x-csrftoken"], "synthetic-csrf")
        self.assertIn("application/json", self.requests[-1]["headers"]["content-type"])

    def assert_bounded(self):
        expect(self.page.locator("#selection-add")).to_be_visible()
        self.assertTrue(self.page.evaluate("""() => {
            const box = document.querySelector('#selection-add').getBoundingClientRect();
            const selected = getSelection().rangeCount ? [...getSelection().getRangeAt(0).getClientRects()] : [];
            return box.left >= 0 && box.top >= 0 && box.right <= innerWidth && box.bottom <= innerHeight &&
                selected.every(rect => box.right <= rect.left || box.left >= rect.right || box.bottom <= rect.top || box.top >= rect.bottom);
        }"""))

    def test_inline_capture_normalizes_only_whitespace_and_does_not_steal_focus(self):
        self.load()
        self.page.locator("#outside").focus()
        self.select("#english")
        expect(self.page.locator("#selection-add-submit")).to_have_text("Choose a deck")
        expect(self.page.locator("#outside")).to_be_focused()
        self.assertEqual(self.requests, [])
        self.picker()
        expect(self.page.locator("#selection-add-expression")).to_have_text("Café isn't state-of-the-art.")
        expect(self.page.locator("#selection-add-deck")).to_have_value("")
        self.assert_bounded()

    def test_empty_editing_hidden_controls_and_cross_region_are_excluded(self):
        self.load(remembered=1)
        for selector in ("#outside", "#link", "#control", "#input", "#textarea", "#editing", "#navigation",
                         "#hidden", "#invisible", "#transparent", "#role-control", "#guarded", "#blank", "#nested"):
            with self.subTest(selector=selector):
                self.select(selector)
                expect(self.page.locator("#selection-add")).to_be_hidden()
        self.page.evaluate("""() => {
            const range = document.createRange();
            range.setStart(document.querySelector('#english').firstChild, 0);
            range.setEnd(document.querySelector('#unknown').firstChild, 4);
            getSelection().removeAllRanges(); getSelection().addRange(range);
        }""")
        self.settle()
        expect(self.page.locator("#selection-add")).to_be_hidden()
        self.select("#unknown")
        expect(self.page.locator("#selection-add")).to_be_visible()
        self.page.evaluate("getSelection().removeAllRanges()")
        self.settle()
        expect(self.page.locator("#selection-add")).to_be_hidden()
        self.assertEqual(self.requests, [])

    def test_native_mouse_keyboard_copy_and_escape(self):
        self.load()
        self.page.locator("#unknown").evaluate("element => element.textContent = 'keyboard choice'")
        box = self.page.locator("#unknown").bounding_box()
        self.page.mouse.move(box["x"] + 2, box["y"] + 10)
        self.page.mouse.down()
        self.page.mouse.move(box["x"] + 110, box["y"] + 10, steps=10)
        self.page.mouse.up()
        expect(self.page.locator("#selection-add")).to_be_visible()
        self.page.locator("#unknown").focus()
        self.select("#unknown")
        self.page.keyboard.press("Shift+ArrowLeft")
        self.settle()
        self.assertEqual(self.page.evaluate("getSelection().toString()"), "keyboard choic")
        self.page.keyboard.press("Shift+ArrowRight")
        self.settle()
        expect(self.page.locator("#selection-add")).to_be_visible()
        expect(self.page.locator("#unknown")).to_be_focused()
        self.page.evaluate("document.addEventListener('copy', event => {window.copyPrevented = event.defaultPrevented})")
        self.page.keyboard.press("Control+c")
        self.assertFalse(self.page.evaluate("window.copyPrevented"))
        self.assertEqual(self.page.evaluate("getSelection().toString()"), "keyboard choice")
        self.page.locator("#selection-add-toggle").focus()
        self.page.keyboard.press("Enter")
        expect(self.page.locator("#selection-add-toggle")).to_have_attribute("aria-expanded", "true")
        expect(self.page.locator("#selection-add-deck")).to_be_focused()
        self.page.keyboard.press("ArrowDown")
        self.page.keyboard.press("Tab")
        expect(self.page.locator("#selection-add-language")).to_be_focused()
        self.page.keyboard.press("Escape")
        expect(self.page.locator("#selection-add")).to_be_hidden()
        expect(self.page.locator("#unknown")).to_be_focused()
        self.assertEqual(self.requests, [])

    def test_picker_keeps_capture_after_native_selection_collapses(self):
        self.load()
        self.select("#english")
        self.page.locator("#selection-add-submit").click()
        expect(self.page.locator("#selection-add-deck")).to_have_value("")
        self.picker(deck=2, pair=1)
        self.page.evaluate("getSelection().removeAllRanges()")
        self.settle()
        expect(self.page.locator("#selection-add-expression")).to_have_text("Café isn't state-of-the-art.")
        self.add()
        self.assert_payload("Café isn't state-of-the-art.", deck=2, native="Spanish")
        expect(self.page.locator("#selection-add-status")).to_have_text("Added to Spanish shelf · Preparing")
        self.assertEqual(self.page.url, ORIGIN + "/fixture")

    def test_fresh_pointer_selection_of_the_same_text_can_reopen_after_dismissal(self):
        self.load(remembered=1)
        for dismissal in ("success", "escape", "outside"):
            with self.subTest(dismissal=dismissal):
                self.page.locator("#unknown").click()
                self.select("#unknown")
                expect(self.page.locator("#selection-add")).to_be_visible()
                if dismissal == "success":
                    self.add()
                elif dismissal == "escape":
                    self.page.keyboard.press("Escape")
                else:
                    self.page.locator("#outside").click()
                self.page.locator("#unknown").click()
                self.select("#unknown")
                expect(self.page.locator("#selection-add-submit")).to_have_text("Add to Reading")
                self.assert_bounded()

    def test_first_stale_and_no_decks_never_pick_the_first_destination(self):
        for remembered in (None, 99, -1, "broken"):
            with self.subTest(remembered=remembered):
                self.load(remembered=remembered, clear_storage=True)
                self.select("#unknown")
                self.page.locator("#selection-add-submit").click()
                expect(self.page.locator("#selection-add-deck")).to_have_value("")
                self.assertEqual(self.requests, [])
        self.load(decks=[], remembered=1)
        self.select("#unknown")
        self.page.locator("#selection-add-submit").click()
        expect(self.page.locator("#selection-add-deck")).to_be_disabled()
        expect(self.page.locator("#selection-add-create-deck")).to_have_attribute("href", "/decks/")
        expect(self.page.locator("#selection-add-no-decks")).to_be_visible()
        self.assertEqual(self.requests, [])

    def test_only_accepted_success_or_duplicate_remembers_a_destination(self):
        self.load(remembered=1)
        self.select("#english")
        self.picker(deck=2)
        self.select("#unknown")
        expect(self.page.locator("#selection-add-submit")).to_have_text("Add to Reading")
        self.picker(deck=2)
        self.reply = (500, {"error": "Please try later"})
        self.add()
        expect(self.page.locator("#selection-add-retry")).to_be_visible()
        self.assertEqual(self.page.evaluate("key => localStorage.getItem(key)", self.key), "1")
        self.select("#spanish")
        expect(self.page.locator("#selection-add-submit")).to_have_text("Add to Reading")
        self.reply = (200, {"created": False, "card_url": "/cards/42/", "archived": False})
        self.add("#selection-add-retry")
        self.assert_payload("naïve co-op’s déjà vu", deck=2)
        expect(self.page.locator("#selection-add-status")).to_have_text("Already in Spanish shelf")
        self.assertEqual(self.page.evaluate("key => localStorage.getItem(key)", self.key), "2")
        expect(self.page.locator("#selection-add-submit")).to_have_text("Add to Reading")
        self.select("#unknown")
        expect(self.page.locator("#selection-add-submit")).to_have_text("Add to Spanish shelf")

    def test_unavailable_storage_keeps_page_local_accepted_memory(self):
        for failure in ("access", "getItem", "setItem"):
            with self.subTest(failure=failure):
                self.load(storage_failure=failure, clear_storage=True)
                self.select("#english")
                self.picker(deck=2)
                self.add()
                expect(self.page.locator("#selection-add-status")).to_have_text("Added to Spanish shelf · Preparing")
                self.select("#unknown")
                expect(self.page.locator("#selection-add-submit")).to_have_text("Add to Spanish shelf")

    def test_account_memory_and_transient_state_are_isolated(self):
        self.load()
        self.select("#english")
        self.picker(deck=2)
        self.add()
        self.load(user_id="learner-b")
        expect(self.page.locator("#selection-add-feedback")).to_be_hidden()
        expect(self.page.locator("#selection-add-expression")).to_be_empty()
        self.select("#unknown")
        expect(self.page.locator("#selection-add-submit")).to_have_text("Choose a deck")
        self.assertIsNone(self.page.evaluate("key => localStorage.getItem(key)", self.key))
        self.assertEqual(self.page.evaluate("key => localStorage.getItem(key)", STORAGE_KEY), "2")
        self.load()
        self.select("#unknown")
        expect(self.page.locator("#selection-add-submit")).to_have_text("Add to Spanish shelf")
        self.assertEqual(self.page.evaluate("Object.keys(localStorage)"), [STORAGE_KEY])

    def test_language_defaults_visible_metadata_and_temporary_override(self):
        cases = [
            ("#unknown", "English", "Chinese", "English", "Chinese"),
            ("#unknown", "Spanish", "Chinese", "Spanish", "Chinese"),
            ("#unknown", "English", "Spanish", "English", "Spanish"),
            ("#english", "Spanish", "Chinese", "English", "Chinese"),
            ("#spanish", "English", "Chinese", "Spanish", "Chinese"),
        ]
        for selector, default_target, default_native, target, native in cases:
            with self.subTest(selector=selector, default_target=default_target, default_native=default_native):
                self.load(remembered=2, target_language=default_target, native_language=default_native)
                self.select(selector)
                text = self.page.evaluate("getSelection().toString().replace(/\\s+/gu, ' ').trim()")
                self.add()
                self.assert_payload(text, deck=2, target=target, native=native)
        self.load(remembered=1)
        self.select("#spanish")
        self.picker(pair=1)
        self.add()
        self.assert_payload("¿Dónde está el café?", target="English", native="Spanish")
        self.select("#unknown")
        self.select("#spanish")
        self.add()
        self.assert_payload("¿Dónde está el café?", target="Spanish")

    def test_invalid_pair_requires_explicit_choice_and_known_unsupported_is_suppressed(self):
        self.load(remembered=1, native_language="Spanish")
        self.select("#spanish")
        self.page.locator("#selection-add-submit").click()
        expect(self.page.locator("#selection-add-language")).to_have_value("")
        expect(self.page.locator("#selection-add-language")).to_be_focused()
        expect(self.page.locator("#selection-add-hint")).to_have_text("Choose a supported language pair for this text.")
        self.assertEqual(self.requests, [])
        self.picker(pair=2)
        self.add()
        self.assert_payload("¿Dónde está el café?", target="Spanish")
        for selector in ("#chinese", "#unsupported"):
            self.select(selector)
            expect(self.page.locator("#selection-add")).to_be_hidden()

    def test_pending_snapshot_prevents_double_submission_and_keeps_original_values(self):
        self.load(remembered=1)
        self.hold = True
        self.select("#english")
        self.add()
        expect(self.page.locator("#selection-add-submit")).to_be_disabled()
        self.page.locator("#selection-add-submit").evaluate("element => {element.click(); element.dispatchEvent(new MouseEvent('click', {bubbles:true}))}")
        self.picker(deck=2, pair=1)
        self.settle()
        self.assertEqual(len(self.requests), 1)
        self.assert_payload("Café isn't state-of-the-art.")
        self.respond()
        expect(self.page.locator("#selection-add-status")).to_have_text("Added to Reading · Preparing")
        expect(self.page.locator("#selection-add-submit")).to_have_text("Add to Spanish shelf")
        expect(self.page.locator("#selection-add-language")).to_have_value("1")

    def test_late_success_or_failure_never_replaces_a_newer_selection(self):
        for succeeds in (True, False):
            with self.subTest(succeeds=succeeds):
                self.load(remembered=1)
                self.hold = True
                self.select("#english")
                self.add()
                self.select("#spanish")
                self.picker(deck=2, pair=2)
                self.reply = ((201, {"created": True, "card_url": "/cards/42/", "archived": False}) if succeeds else
                              (503, {"error": "Temporarily unavailable"}))
                self.respond()
                expect(self.page.locator("#selection-add-submit")).to_be_enabled()
                expect(self.page.locator("#selection-add-expression")).to_have_text("¿Dónde está el café?")
                expect(self.page.locator("#selection-add-deck")).to_have_value("2")
                expect(self.page.locator("#selection-add-language")).to_have_value("2")
                expect(self.page.locator("#selection-add-feedback-expression")).to_have_text("Café isn't state-of-the-art.")
                expect(self.page.locator("#selection-add-feedback-destination")).to_have_text("To Reading · English → Chinese")
                if not succeeds:
                    old_payload = self.requests[-1]["body"]
                    count = len(self.requests)
                    self.settle()
                    self.assertEqual(len(self.requests), count)
                    self.add("#selection-add-retry")
                    self.assertEqual(self.requests[-1]["body"], old_payload)
                    self.respond()
                    expect(self.page.locator("#selection-add-retry")).to_be_visible()

    def test_network_server_and_session_errors_allow_only_explicit_identical_retry(self):
        for failure in ("network", "html", "json"):
            with self.subTest(failure=failure):
                self.load(remembered=1)
                self.hold = False
                self.failure = failure
                self.reply = (500, {"error": "Try again later"})
                self.select("#unknown")
                self.add()
                expect(self.page.locator("#selection-add-retry")).to_be_visible()
                old_payload = self.requests[-1]["body"]
                self.page.locator("#outside").click()
                self.page.evaluate("getSelection().removeAllRanges()")
                self.settle()
                expect(self.page.locator("#selection-add")).to_be_hidden()
                self.assertEqual(self.page.evaluate("key => localStorage.getItem(key)", self.key), "1")
                self.failure = None
                self.reply = (200, {"created": False, "card_url": "/cards/42/", "archived": False})
                self.add("#selection-add-retry")
                expect(self.page.locator("#selection-add-status")).to_have_text("Already in Reading")
                self.assertEqual(self.requests[-1]["body"], old_payload)

    def test_invalid_deck_requires_another_explicit_choice_or_reload(self):
        self.load(remembered=1)
        self.reply = (400, {"error": "Unavailable", "code": "invalid_deck"})
        self.select("#unknown")
        self.add()
        expect(self.page.locator("#selection-add-reload")).to_be_visible()
        expect(self.page.locator("#selection-add-retry")).to_be_hidden()
        expect(self.page.locator("#selection-add-submit")).to_have_text("Choose a deck")
        self.picker()
        expect(self.page.locator("#selection-add-deck")).to_have_value("")
        expect(self.page.locator('#selection-add-deck option[value="1"]')).to_be_disabled()
        self.select("#spanish")
        expect(self.page.locator("#selection-add-submit")).to_have_text("Choose a deck")
        self.picker(deck=2)
        self.reply = (201, {"created": True, "card_url": "/cards/42/", "archived": False})
        self.add()
        self.assert_payload("¿Dónde está el café?", deck=2, target="Spanish")

    def test_disabled_bootstrap_and_stale_rejection_leave_native_selection_alone(self):
        self.load(enabled=False)
        self.select("#english")
        expect(self.page.locator("#selection-add")).to_be_hidden()
        self.assertIn("Café", self.page.evaluate("getSelection().toString()"))
        self.load(remembered=1)
        self.reply = (403, {"error": "Disabled", "code": "disabled"})
        self.select("#unknown")
        self.add()
        expect(self.page.locator("#selection-add")).to_be_hidden()
        expect(self.page.locator("#selection-add-disabled-settings")).to_have_attribute("href", "/settings/")
        expect(self.page.locator("#selection-add-status")).to_contain_text("Selection add is disabled")
        expect(self.page.locator("#selection-add-retry")).to_be_hidden()
        self.select("#english")
        expect(self.page.locator("#selection-add")).to_be_hidden()
        self.assertEqual(len(self.requests), 1)

    def test_archived_duplicate_and_untrusted_text_stay_text_without_navigation(self):
        expression = "<svg onload=window.injected=true> café isn't co-op’s"
        deck_name = '<img src=x onerror="window.injected=true">'
        self.load(decks=[{"id": 3, "name": deck_name}], remembered=3)
        self.page.locator("#unknown").evaluate("(element, text) => element.textContent = text", expression)
        self.select("#unknown")
        self.picker()
        expect(self.page.locator("#selection-add-expression")).to_have_text(expression)
        self.reply = (200, {"created": False, "card_url": "/cards/42/", "archived": True})
        self.add()
        self.assert_payload(expression, deck=3)
        expect(self.page.locator("#selection-add-status")).to_have_text("Already in " + deck_name + " · Archived (not restored)")
        expect(self.page.locator("#selection-add-card-link")).to_have_attribute("href", ORIGIN + "/cards/42/")
        self.assertEqual(self.page.locator("#selection-add img, #selection-add svg, #selection-add-feedback img, #selection-add-feedback svg").count(), 0)
        self.assertIsNone(self.page.evaluate("window.injected"))
        self.assertEqual(self.page.url, ORIGIN + "/fixture")
        self.assertEqual(self.page.evaluate("key => localStorage.getItem(key)", self.key), "3")

    def test_dynamic_region_replacement_and_practice_event_isolation(self):
        self.load(remembered=1)
        self.page.evaluate("""() => {
            window.practiceClicks = 0;
            document.querySelector('#review-card').addEventListener('click', event => {
                if (event.target.closest('[data-action]')) window.practiceClicks++;
            });
            const answer = document.createElement('p');
            answer.id = 'dynamic'; answer.dataset.selectionRegion = ''; answer.dataset.selectionLanguage = 'Spanish';
            answer.textContent = 'Una respuesta nueva'; document.querySelector('#dynamic').replaceWith(answer);
        }""")
        self.select("#dynamic")
        self.add()
        self.assert_payload("Una respuesta nueva", target="Spanish")
        self.assertEqual(self.page.evaluate("window.practiceClicks"), 0)
        self.assertEqual(self.page.locator("#selection-add [data-action], #selection-add-feedback [data-action]").count(), 0)
        self.assertFalse(self.page.locator("#selection-add").evaluate("element => Boolean(element.closest('#review-card'))"))

    def test_open_picker_keeps_its_capture_when_polling_replaces_the_answer(self):
        self.load()
        self.select("#dynamic")
        self.page.locator("#selection-add-submit").click()
        self.page.evaluate("""() => {
            const answer = document.createElement('p');
            answer.id = 'dynamic'; answer.dataset.selectionRegion = ''; answer.dataset.selectionLanguage = 'Spanish';
            answer.textContent = 'Una respuesta nueva'; document.querySelector('#dynamic').replaceWith(answer);
        }""")
        self.settle()
        self.page.locator("#selection-add-deck").select_option("2")
        expect(self.page.locator("#selection-add-picker")).to_be_visible()
        self.page.locator("#selection-add-language").select_option("1")
        expect(self.page.locator("#selection-add-expression")).to_have_text("Initial answer")
        self.add()
        self.assert_payload("Initial answer", deck=2, native="Spanish")
        self.select("#dynamic")
        self.add()
        self.assert_payload("Una respuesta nueva", deck=2, target="Spanish")

    def test_viewport_edges_resize_scroll_and_long_text_are_bounded(self):
        self.load(remembered=1, decks=[{"id": 1, "name": "A very long deck name " * 20}])
        self.page.set_viewport_size({"width": 380, "height": 640})
        for top, left in ((4, 4), (600, 260), (260, 4)):
            with self.subTest(top=top, left=left):
                self.page.locator("#unknown").evaluate("""(element, position) => {
                    element.style = `position:absolute;top:${position[0]}px;left:${position[1]}px;width:110px;margin:0`;
                    element.textContent = 'edge phrase';
                }""", [top, left])
                self.page.locator("#outside").focus()
                self.select("#unknown")
                self.assert_bounded()
                self.picker()
                self.assert_bounded()
                self.page.keyboard.press("Escape")
                self.page.evaluate("getSelection().removeAllRanges()")
                self.settle()
        self.page.locator("#unknown").evaluate("""element => {
            document.body.style.minHeight = '2200px';
            element.style = 'position:absolute;top:1200px;left:20px;width:330px;margin:0';
            element.textContent = 'long-word '.repeat(30);
        }""")
        self.page.evaluate("scrollTo(0, 1050)")
        self.select("#unknown")
        self.assert_bounded()
        self.picker()
        self.assert_bounded()
        self.page.set_viewport_size({"width": 360, "height": 600})
        self.settle()
        self.assert_bounded()
        self.page.evaluate("scrollTo(0, 1090)")
        self.settle()
        self.assert_bounded()
        self.page.evaluate("scrollTo(0, 0)")
        self.settle()
        expect(self.page.locator("#selection-add")).to_be_hidden()

    def test_oversized_expression_shows_guidance_without_sending(self):
        self.load(remembered=1)
        self.page.locator("#unknown").evaluate("element => element.textContent = 'é'.repeat(501)")
        self.select("#unknown")
        self.page.locator("#selection-add-submit").click()
        expect(self.page.locator("#selection-add-hint")).to_contain_text("at most 500 characters")
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
