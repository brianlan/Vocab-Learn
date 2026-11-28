"""Issue #26: one durable illustration per Example Pair revision, private retrieval and retention."""
import argparse
import hashlib
import http.client
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta
from django.db import transaction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from learning import authoring, illustrations, providers, review, work
from learning.models import Attempt, Card, Deck, ExampleIllustration, SpeechClip
from learning.providers import StageError
from .test_learning import GENERIC, PAIR, VOCAB, audio_bytes


WEBP_CACHE = {}
CAPTION = "Two people face each other across a table. One has stopped speaking and lowers an open hand."
RENDER_PROMPT = (f"{CAPTION} Soft gouache on warm ivory paper, matte colors, soft edges and a light brush texture. "
                 "A wordless scene with plain, unlettered surfaces.")
CAPTION_RESPONSE = json.dumps({"choices": [{"finish_reason": "stop", "message": {
    "role": "assistant", "content": f" {CAPTION}\n", "reasoning_content": "Private reasoning"}}]}).encode()


def marker_webp(payload=b"scene"):
    """Header-valid but undecodable bytes: only for paths that never decode by design."""
    return b"RIFF" + (12+len(payload)).to_bytes(4, "little") + b"WEBP" + payload


def webp_image(size="512x384"):
    """A real WebP rendered once by the local FFmpeg toolchain; no committed fixture."""
    if size not in WEBP_CACHE:
        WEBP_CACHE[size] = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
            "-i", f"color=c=steelblue:s={size}", "-frames:v", "1", "-c:v", "libwebp",
            "-f", "webp", "pipe:1"], capture_output=True, check=True).stdout
    return WEBP_CACHE[size]


@contextmanager
def fake_renderer(content=None, status=200, revision="3b767", slow=False, extra_headers=None,
                  content_type="image/webp"):
    """A local fake renderer that records each request; serves WebP bytes by default. With `slow`,
    the body streams in small chunks and `state["consumed"]` records what the client accepted."""
    requests = []
    state = {}
    class Handler(BaseHTTPRequestHandler):
        def do_POST(inner):
            length = int(inner.headers.get("Content-Length", "0"))
            requests.append({"path": inner.path, "authorization": inner.headers.get("Authorization"),
                             "body": json.loads(inner.rfile.read(length)) if length else {}})
            body = content if content is not None else webp_image()
            inner.send_response(status)
            inner.send_header("Content-Type", content_type)
            inner.send_header("Content-Length", str(len(body)))
            inner.send_header("X-Illustration-Revision", revision)
            for key, value in (extra_headers or {}).items():
                inner.send_header(key, value)
            inner.end_headers()
            if slow:
                consumed = 0
                for offset in range(0, len(body), 16*1024):
                    try:
                        inner.wfile.write(body[offset:offset+16*1024])
                        inner.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        break
                    consumed += min(16*1024, len(body)-offset)
                    time.sleep(0.01)
                state["consumed"] = consumed
            else:
                try:
                    inner.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass  # the client rejected the response before reading the body
        def log_message(inner, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield requests, server.server_port, state
    finally:
        server.shutdown(); server.server_close()
        thread.join(timeout=5)


def wait_consumed(state, timeout=5):
    limit = time.monotonic()+timeout
    while "consumed" not in state and time.monotonic() < limit:
        time.sleep(0.05)
    return state.get("consumed", 0)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class IllustrationTests(TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        override = override_settings(ILLUSTRATIONS_DIR=self.folder)
        override.enable(); self.addCleanup(override.disable)
        self.environ = patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": "http://renderer.internal/render",
            "ILLUSTRATION_MODEL": "", "ILLUSTRATION_API_KEY": "test-only",
            "ILLUSTRATION_CAPTION_ENDPOINT": "https://caption.test/chat", "ILLUSTRATION_CAPTION_MODEL": "caption-model",
            "ILLUSTRATION_CAPTION_API_KEY": "caption-only",
            "ALLOW_INSECURE_PROVIDER_HTTP": "1"})
        self.environ.start(); self.addCleanup(self.environ.stop)
        self.caption_patch = patch.object(providers, "illustration_caption", return_value=CAPTION)
        self.caption = self.caption_patch.start()
        self.addCleanup(self.caption_patch.stop)
        self.user = get_user_model().objects.create_user("illustrator", password="test-password")
        self.other = get_user_model().objects.create_user("other", password="test-password")
        self.deck = Deck.objects.create(owner=self.user, name="Illustrated")
        self.output = io.StringIO()

    def vocabulary(self, **overrides):
        return authoring.save_card(self.deck, "vocabulary", {**VOCAB, **overrides})

    def ready(self, card, data=PAIR):
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300); job.save()
        work.save_pair(job.pk, job.claim, data, {"model": "test"})
        card.refresh_from_db()
        return card

    def row(self, card):
        return ExampleIllustration.objects.get(pair_id=card.active_pair_id)

    def processing(self):
        row = ExampleIllustration.objects.filter(state__in=["queued", "failed"]).first()
        claim, now = uuid.uuid4(), timezone.now()
        ExampleIllustration.objects.filter(pk=row.pk).update(state="processing", claim=claim,
            started_at=now, deadline=now+timedelta(seconds=settings.ILLUSTRATION_TIMEOUT_SECONDS))
        return row.pk, claim

    def run_render(self, effect):
        """Render one queued row under a patched adapter; record StageError failures as the worker does."""
        pk, claim = self.processing()
        with patch.object(providers, "render_illustration", side_effect=effect):
            try:
                illustrations.process_illustration(pk, claim)
            except StageError as failure:
                work.fail("illustration", pk, claim, failure)
        return ExampleIllustration.objects.get(pk=pk)

    def run_live_render(self, port):
        """Render one queued row against a real fake HTTP renderer, as the worker's child would."""
        pk, claim = self.processing()
        env = patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": f"http://127.0.0.1:{port}/render"})
        env.start(); self.addCleanup(env.stop)
        try:
            illustrations.process_illustration(pk, claim)
        except StageError as failure:
            work.fail("illustration", pk, claim, failure)
        return ExampleIllustration.objects.get(pk=pk)

    def absence(self, row, **delta):
        ExampleIllustration.objects.filter(pk=row.pk).update(unreferenced_at=timezone.now()-timedelta(**delta))

    # --- Pair-save enqueue coverage -----------------------------------------------------------

    def test_initial_correction_and_rotation_saves_queue_one_illustration_once(self):
        card = self.ready(self.vocabulary())
        row = self.row(card)
        self.assertEqual(row.state, "queued")
        self.assertEqual(row.backfill, False)
        illustrations.enqueue_illustration(card.active_pair)  # duplicate invocation coalesces
        self.assertEqual(ExampleIllustration.objects.count(), 1)
        # Operator correction saves a replacement pair through the correction path.
        pair = work.save_corrected_pair(card.pk, card.source_version, card.active_pair_id, PAIR, {"model": "op"})
        self.assertEqual(pair.illustration.state, "queued")
        self.assertNotEqual(pair.illustration.pk, row.pk)
        # A learner regeneration (manual mode) also travels the correction path.
        fresh = Card.objects.get(pk=card.pk)
        authoring.request_example_regeneration(fresh,
            expected_source_version=fresh.source_version, expected_pair_id=fresh.active_pair_id)
        job = fresh.generation_jobs.filter(mode="manual", state="queued").get()
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300)
        job.provenance = {**job.provenance, "requested_pair_id": fresh.active_pair_id}; job.save()
        pair = work.save_pair(job.pk, job.claim, PAIR, {"model": "learner"})
        self.assertEqual(pair.illustration.state, "queued")
        self.assertEqual(ExampleIllustration.objects.count(), 3)

    def test_disabled_configuration_queues_nothing_and_saves_stay_usable(self):
        card = self.vocabulary()
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300); job.save()
        with patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": ""}):
            self.assertFalse(illustrations.illustration_enabled())
            self.ready(card)
        self.assertEqual(ExampleIllustration.objects.count(), 0)
        self.assertTrue(Card.objects.get(pk=card.pk).ready)
        self.assertEqual(card.active_pair.speech_clips.count(), 2)  # speech unaffected

    def test_rejected_and_rolled_back_saves_leave_no_illustration_jobs(self):
        card = self.vocabulary()
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300); job.save()
        self.assertIsNone(work.save_pair(job.pk, uuid.uuid4(), PAIR, {}))
        self.assertEqual(ExampleIllustration.objects.count(), 0)
        sid = transaction.savepoint()
        self.assertIsNotNone(work.save_pair(job.pk, job.claim, PAIR, {}))
        self.assertEqual(ExampleIllustration.objects.count(), 1)
        transaction.savepoint_rollback(sid)
        self.assertEqual(ExampleIllustration.objects.count(), 0)

    # --- Prompt and seed ----------------------------------------------------------------------

    def test_caption_receives_the_target_expression_and_both_validated_sentences(self):
        examples = (
            ("English", "Chinese", "glow", "The coals still <focus>glow</focus> at dawn.", "黎明时木炭仍在<focus>发光</focus>。"),
            ("English", "Spanish", "lean", "They <focus>lean</focus> against the fence.", "Se <focus>apoyan</focus> contra la cerca."),
            ("Spanish", "Chinese", "barrer", "Lucía va a <focus>barrer</focus> los escalones.", "露西亚要<focus>扫</focus>台阶。"),
        )
        for target, native, word, target_sentence, native_sentence in examples:
            with self.subTest(target=target, native=native):
                pair_data = providers.validate_pair({"target_sentence": target_sentence,
                    "native_sentence": native_sentence}, word, native)
                card = self.ready(self.vocabulary(word=word, target_language=target, native_language=native), pair_data)
                self.caption.reset_mock()
                def render(profile, prompt, seed):
                    self.caption.assert_called_once()
                    self.assertEqual((prompt, seed), (RENDER_PROMPT, illustrations.revision_seed(card.active_pair)))
                    return webp_image(), "3b767"
                row = self.run_render(render)
                self.assertEqual(row.state, "done")
                self.assertEqual(self.caption.call_args.args[2], {
                    "target_expression": word,
                    f"{target.lower()}_sentence": pair_data["target_sentence"],
                    f"{native.lower()}_sentence": pair_data["native_sentence"],
                })

    # --- Dispatch, validation and publication -------------------------------------------------

    def test_adapter_targets_the_configured_url_model_and_bearer(self):
        card = self.ready(self.vocabulary())
        with fake_renderer() as (requests, port, state):
            row = self.run_live_render(port)
        self.assertEqual(row.state, "done")
        request = requests[0]
        self.assertEqual(request["path"], "/render")
        self.assertEqual(request["authorization"], "Bearer test-only")
        self.assertEqual(request["body"]["model"], "black-forest-labs/flux-3-image-klein")  # documented default
        self.assertEqual(request["body"]["seed"], illustrations.revision_seed(row.pair))
        self.assertEqual(request["body"]["prompt"], RENDER_PROMPT)
        self.assertEqual(row.provenance["model"], "black-forest-labs/flux-3-image-klein")
        self.assertEqual(row.provenance["checkpoint"], "3b767")
        self.assertEqual(row.provenance["prompt_version"], "illustration-v2")
        self.assertEqual(row.provenance["caption_model"], "caption-model")
        self.assertEqual(set(row.provenance), {"task", "endpoint", "model", "timeout",
            "prompt_version", "caption_model", "seed", "checkpoint"})
        self.assertEqual(row.file, f"{row.pk}.{row.claim.hex}.webp")
        path = self.folder/row.file
        self.assertEqual(path.read_bytes(), webp_image())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(illustrations.ready_illustration(row.pair_id).pk, row.pk)
        self.client.force_login(self.user)
        response = self.client.get(reverse("illustration_image", args=[row.pair_id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/webp")
        self.assertEqual(b"".join(response.streaming_content), webp_image())

    def test_another_learner_and_missing_images_are_denied(self):
        card = self.ready(self.vocabulary())
        row = self.run_render(lambda *a: (webp_image(), ""))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("illustration_image", args=[row.pair_id])).status_code, 404)
        self.client.force_login(self.user)
        (self.folder/row.file).unlink()
        self.assertEqual(self.client.get(reverse("illustration_image", args=[row.pair_id])).status_code, 404)
        self.assertIsNone(illustrations.ready_illustration(row.pair_id))  # missing file advertises nothing

    def test_response_validation_rejects_bad_images(self):
        card = self.ready(self.vocabulary())
        oversized = self.run_live(b"RIFFWEBP" + b"x" * providers.ILLUSTRATION_MAX_BYTES)
        self.assertEqual((oversized.state, oversized.error_category, oversized.retryable),
                         ("failed", "invalid_output", True))
        not_webp = self.run_live(b"png-data-at-least-sixteen-bytes!")
        self.assertEqual((not_webp.state, not_webp.error_category, not_webp.retryable),
                         ("failed", "invalid_output", True))
        self.assertFalse(not_webp.file)
        self.assertEqual(list(self.folder.glob("*.webp*")), [])  # nothing was ever written
        service = self.run_live(b"RIFFWEBP" + b"x" * (4 * 1024 * 1024), status=500, slow=True)
        self.assertEqual((service.state, service.error_category, service.retryable), ("failed", "provider", True))
        rejected = self.run_live(b"RIFFWEBP" + b"x" * (4 * 1024 * 1024), status=400)
        self.assertEqual((rejected.state, rejected.error_category, rejected.retryable),
                         ("failed", "configuration", False))  # a renderer/model mismatch stays explicit

    def run_live(self, content, status=200, slow=False):
        with fake_renderer(content=content, status=status, slow=slow) as (_, port, state):
            return self.run_live_render(port)

    def test_the_adapter_stops_reading_past_the_128_kib_bound(self):
        card = self.ready(self.vocabulary())
        oversized = b"RIFFWEBP" + b"x" * (16 * 1024 * 1024)
        with fake_renderer(content=oversized, slow=True) as (_, port, state):
            row = self.run_live_render(port)
        self.assertEqual((row.state, row.error_category, row.retryable), ("failed", "invalid_output", True))
        self.assertFalse(row.file)
        self.assertLess(wait_consumed(state), len(oversized))  # the unread tail was never consumed

    def test_error_statuses_are_rejected_before_their_bodies_are_read(self):
        card = self.ready(self.vocabulary())
        body = b"x" * (4 * 1024 * 1024)
        with fake_renderer(content=body, status=500, slow=True) as (_, port, state):
            row = self.run_live_render(port)
        self.assertEqual((row.state, row.error_category, row.retryable), ("failed", "provider", True))
        self.assertLess(wait_consumed(state), len(body))  # the error body was not buffered

    def test_a_corrupt_webp_is_rejected_before_publication(self):
        card = self.ready(self.vocabulary())
        good = self.run_render(lambda *a: (webp_image(), "3b767"))
        self.assertEqual(good.state, "done")  # a real, completely decodable image publishes
        broken = self.ready(self.vocabulary(word="broken"))
        corrupt = self.run_render(lambda *a: (webp_image()[:-8], ""))
        self.assertEqual((corrupt.state, corrupt.error_category, corrupt.retryable),
                         ("failed", "invalid_output", True))
        self.assertFalse(corrupt.file)
        self.assertTrue(list(self.folder.glob("*.webp")))  # only the good claim-published name exists

    def test_an_invalid_riff_container_is_rejected_before_decoding(self):
        card = self.ready(self.vocabulary())
        lying = bytearray(webp_image())
        lying[4:8] = (32).to_bytes(4, "little")  # the declared container size contradicts the body
        row = self.run_live(bytes(lying))
        self.assertEqual((row.state, row.error_category, row.retryable), ("failed", "invalid_output", True))
        self.assertFalse(row.file)
        self.assertEqual(list(self.folder.glob("*.webp")), [])

    def test_oversized_pixel_canvases_are_rejected_before_decoding(self):
        card = self.ready(self.vocabulary())
        huge = webp_image("2048x2048")  # a tiny encoded blob that decodes to 4M pixels
        self.assertLess(len(huge), providers.ILLUSTRATION_MAX_BYTES)
        row = self.run_live(huge)
        self.assertEqual((row.state, row.error_category, row.retryable), ("failed", "invalid_output", True))
        self.assertFalse(row.file)
        self.assertEqual(list(self.folder.glob("*.webp")), [])

    def test_a_compressed_response_is_rejected_before_its_body_is_read(self):
        card = self.ready(self.vocabulary())
        body = b"\x1f\x8b" + b"compressed-junk" * (4 * 1024)
        with fake_renderer(content=body, slow=True, extra_headers={"Content-Encoding": "gzip"}) as (_, port, state):
            row = self.run_live_render(port)
        self.assertEqual((row.state, row.error_category, row.retryable), ("failed", "invalid_output", True))
        self.assertFalse(row.file)
        self.assertLess(wait_consumed(state), len(body))  # the compressed body was never consumed

    def test_an_invalid_port_is_a_configuration_error(self):
        with patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": "https://isolated.invalid:not-a-port/render"}):
            with self.assertRaises(StageError) as ctx:
                providers.illustration_profile()
        self.assertEqual(ctx.exception.category, "configuration")

    def test_expired_execution_budget_fails_before_dispatch(self):
        card = self.ready(self.vocabulary())
        pk, claim = self.processing()
        ExampleIllustration.objects.filter(pk=pk).update(deadline=timezone.now()-timedelta(seconds=1))
        called = []
        with patch.object(providers, "render_illustration", side_effect=lambda *a: called.append(1)):
            with self.assertRaises(StageError) as ctx:
                illustrations.process_illustration(pk, claim)
        work.fail("illustration", pk, claim, ctx.exception)
        row = ExampleIllustration.objects.get(pk=pk)
        self.assertEqual((row.state, row.error_category), ("failed", "timeout"))
        self.caption.assert_not_called()
        self.assertFalse(called)

    def test_caption_failure_leaves_a_retryable_row_without_dispatching_flux(self):
        self.ready(self.vocabulary())
        self.caption.side_effect = StageError("ILLUSTRATION_CAPTION", "Caption writer unavailable.", "provider")
        row = self.run_render(lambda *args: self.fail("The renderer must wait for an accepted caption."))
        self.assertEqual((row.state, row.error_category, row.retryable), ("failed", "provider", True))
        self.assertFalse(row.file)

    def test_invalid_caption_roles_fail_before_dispatching_flux(self):
        self.ready(self.vocabulary())
        self.caption_patch.stop()
        for role_field in ({}, {"role": "user"}, {"role": "system"}, {"role": "tool"}):
            with self.subTest(role_field=role_field), transaction.atomic():
                response = {"choices": [{"finish_reason": "stop", "message": {"content": CAPTION, **role_field}}]}
                with patch.object(providers, "request", return_value=response):
                    row = self.run_render(lambda *args: self.fail("The renderer received a non-assistant caption."))
                self.assertEqual((row.state, row.error_category, row.retryable), ("failed", "invalid_output", True))
                self.assertFalse(row.file)
                self.assertEqual(list(self.folder.iterdir()), [])

    @override_settings(ILLUSTRATION_TIMEOUT_SECONDS=30)
    def test_caption_and_render_consume_the_same_deadline(self):
        start = timezone.now()
        for elapsed in (25, 31):
            with self.subTest(elapsed=elapsed), patch.object(timezone, "now", return_value=start) as clock:
                self.ready(self.vocabulary(word=f"word-{elapsed}"))

                def caption(profile, instruction, payload):
                    self.assertEqual(profile.timeout, 30)
                    clock.return_value = start+timedelta(seconds=elapsed)
                    return CAPTION

                def render(profile, prompt, seed):
                    self.assertEqual(profile.timeout, 30-elapsed)
                    return webp_image(), ""

                self.caption.side_effect = caption
                row = self.run_render(render)
                self.assertEqual((row.state, row.error_category),
                                 ("done", "") if elapsed < 30 else ("failed", "timeout"))

    def test_render_rechecks_claim_and_reference_after_caption(self):
        for invalidated in ("claim", "reference"):
            with self.subTest(invalidated=invalidated):
                card = self.ready(self.vocabulary(word=invalidated))
                pk, claim = self.processing()
                replacement = uuid.uuid4()

                def caption(*args):
                    if invalidated == "claim":
                        ExampleIllustration.objects.filter(pk=pk).update(claim=replacement)
                    else:
                        Card.objects.filter(pk=card.pk).update(active_pair=None)
                    return CAPTION

                self.caption.side_effect = caption
                with patch.object(providers, "render_illustration") as render:
                    illustrations.process_illustration(pk, claim)
                render.assert_not_called()
                row = ExampleIllustration.objects.get(pk=pk)
                if invalidated == "claim":
                    self.assertEqual((row.state, row.claim), ("processing", replacement))
                else:
                    self.assertEqual(row.state, "skipped")

    def test_stale_publication_cannot_replace_a_newer_image(self):
        card = self.ready(self.vocabulary())
        pk, claim = self.processing()
        ExampleIllustration.objects.filter(pk=pk).update(claim=uuid.uuid4())  # an explicit retry rotated the claim
        illustrations.publish_illustration(pk, claim, webp_image(), "")
        row = ExampleIllustration.objects.get(pk=pk)
        self.assertEqual((row.state, row.file), ("processing", ""))
        self.assertFalse(list(self.folder.glob(f"{pk}.{claim.hex}.webp")))

    def test_publication_rejects_images_that_lost_eligibility_during_dispatch(self):
        card = self.ready(self.vocabulary())
        pk, claim = self.processing()
        ExampleIllustration.objects.filter(pk=pk).update(deadline=timezone.now()-timedelta(seconds=1))
        illustrations.publish_illustration(pk, claim, marker_webp(b"late"), "")  # direct publish: never decoded
        row = ExampleIllustration.objects.get(pk=pk)
        self.assertNotEqual(row.state, "done")
        self.assertFalse((self.folder/f"{pk}.{claim.hex}.webp").exists())
        lost = self.ready(self.vocabulary(word="lost"))
        pk, claim = self.processing()
        Card.objects.filter(pk=lost.pk).update(active_pair=None)  # the last reference disappears mid-call
        illustrations.publish_illustration(pk, claim, marker_webp(b"orphan"), "")
        row = ExampleIllustration.objects.get(pk=pk)
        self.assertNotEqual(row.state, "done")
        self.assertIsNone(illustrations.ready_illustration(lost.active_pair_id))
        self.assertFalse(list(self.folder.glob("*.webp")))

    def test_a_directory_sync_failure_fails_the_row_without_publishing(self):
        card = self.ready(self.vocabulary())
        original = os.fsync
        calls = []
        def flaky(fd):
            calls.append(fd)
            if len(calls) == 2:  # the file's own sync succeeds; the renamed directory entry fails
                raise OSError
            return original(fd)
        with patch("os.fsync", side_effect=flaky):
            row = self.run_render(lambda *a: (webp_image(), ""))
        self.assertEqual(row.state, "failed")
        self.assertEqual(row.error_category, "worker")
        self.assertEqual(len(calls), 2)

    def test_a_stalled_render_occupies_only_the_illustration_slot(self):
        card = self.ready(self.vocabulary())
        work.claim_speech()  # a stalled speech execution occupies its dedicated slot
        self.assertIsNotNone(illustrations.claim_illustration())  # the render occupies its own slot
        p = review.next_question(self.user, self.deck)
        review.submit(p, "speak", 2)
        self.assertEqual(work.claim_work()[0], "assessment")  # assessment capacity stays healthy
        self.assertEqual(ExampleIllustration.objects.filter(state="processing").count(), 1)
        self.assertEqual(SpeechClip.objects.filter(state="processing").count(), 1)

    def test_a_disabled_endpoint_never_dispatches_the_queued_backlog(self):
        card = self.ready(self.vocabulary())
        row = self.row(card)
        with patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": ""}):
            self.assertFalse(illustrations.illustration_enabled())
            self.assertIsNone(illustrations.claim_illustration())  # no claim, no dispatch
        row = ExampleIllustration.objects.get(pk=row.pk)
        self.assertEqual(row.state, "queued")
        self.assertIsNone(row.started_at)
        self.assertIsNotNone(illustrations.claim_illustration())  # re-enabled: preserved work serves

    def test_a_failed_retry_yields_to_newly_saved_revisions(self):
        broken = self.ready(self.vocabulary(word="broken"))
        ExampleIllustration.objects.filter(pk=self.row(broken).pk).update(
            state="failed", error="boom", error_category="provider", retryable=True)
        call_command("queue_example_illustrations", self.user.username, stdout=self.output)
        retried = self.row(broken)
        self.assertEqual((retried.state, retried.backfill), ("queued", True))
        later = self.ready(self.vocabulary(word="later"))  # a fresh revision saved after the retry
        self.assertEqual(self.row(later).backfill, False)
        self.assertEqual(illustrations.claim_illustration()[0], self.row(later).pk)  # fresh work first
        self.assertEqual(illustrations.claim_illustration()[0], retried.pk)

    def test_configured_profile_requires_https_credentials_and_positive_budget(self):
        with patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": "", "ILLUSTRATION_API_KEY": "",
                                     "ALLOW_INSECURE_PROVIDER_HTTP": ""}):
            with self.assertRaises(StageError) as ctx:
                providers.illustration_profile()
        self.assertEqual(ctx.exception.category, "configuration")
        with patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": "http://renderer.internal/render",
                                     "ALLOW_INSECURE_PROVIDER_HTTP": ""}):
            with self.assertRaises(StageError):  # plain HTTP needs the explicit development override
                providers.illustration_profile()
            with patch.dict(os.environ, {"ALLOW_INSECURE_PROVIDER_HTTP": "1"}):
                self.assertEqual(providers.illustration_profile().model, "black-forest-labs/flux-3-image-klein")
                self.assertEqual(providers.illustration_profile().timeout, 300.0)
        with patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": "http://renderer.internal/render",
                                     "ILLUSTRATION_API_KEY": "", "MINIMAX_API_KEY": "shared"}):
            with self.assertRaises(StageError):  # the renderer has no shared-key fallback
                providers.illustration_profile()
        with patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": "http://renderer.internal/render",
                                     "ILLUSTRATION_MODEL": "other-model", "ILLUSTRATION_TIMEOUT_SECONDS": "0"}):
            with self.assertRaises(StageError):
                providers.illustration_profile()

    # --- Backfill command ---------------------------------------------------------------------

    def test_backfill_previews_limits_retries_and_coalesces(self):
        done = self.ready(self.vocabulary())
        missing = self.ready(self.vocabulary(word="missing"))
        broken = self.ready(self.vocabulary(word="broken"))
        foreign_deck = __import__("learning.models", fromlist=["Deck"]).Deck.objects.create(owner=self.other, name="Elsewhere")
        foreign = self.ready(authoring.save_card(foreign_deck, "vocabulary", VOCAB))
        self.row(foreign).delete()
        missing.active_pair.illustration.delete()
        ExampleIllustration.objects.filter(pk=self.row(broken).pk).update(
            state="failed", error="boom", error_category="provider", retryable=True)
        legacy = {"prompt_version": "illustration-v1", "model": "legacy-renderer"}
        (self.folder/"legacy.webp").write_bytes(webp_image())
        ExampleIllustration.objects.filter(pk=self.row(done).pk).update(
            state="done", file="legacy.webp", provenance=legacy)

        call_command("queue_example_illustrations", self.user.username, dry_run=True, stdout=self.output)
        self.assertIn("missing 1, failed 1, queued 0, processing 0, ready 1", self.output.getvalue())
        self.assertEqual(ExampleIllustration.objects.filter(backfill=True).count(), 0)

        call_command("queue_example_illustrations", self.user.username, limit=1, stdout=self.output)
        self.assertEqual(ExampleIllustration.objects.filter(backfill=True).count(), 1)  # the limit bounded the enqueue
        call_command("queue_example_illustrations", self.user.username, stdout=self.output)
        backfilled = ExampleIllustration.objects.get(pair=missing.active_pair)
        self.assertTrue(backfilled.backfill)
        self.assertEqual((self.row(broken).state, self.row(broken).execution), ("queued", 2))  # failed retried
        before = sorted(ExampleIllustration.objects.values_list("pk", flat=True))
        call_command("queue_example_illustrations", self.user.username, stdout=self.output)  # repeated run coalesces
        self.assertEqual(sorted(ExampleIllustration.objects.values_list("pk", flat=True)), before)
        self.assertFalse(ExampleIllustration.objects.filter(pair=foreign.active_pair).exists())
        self.caption.assert_not_called()
        for card in (broken, missing):
            row = self.run_render(lambda *args: (webp_image(), "3b767"))
            self.assertEqual((row.pair_id, row.state, row.provenance["prompt_version"]),
                             (card.active_pair_id, "done", "illustration-v2"))
        self.assertEqual(self.caption.call_count, 2)
        previous = illustrations.ready_illustration(done.active_pair_id)
        self.assertEqual((previous.provenance, previous.file), (legacy, "legacy.webp"))
        self.assertEqual((self.folder/previous.file).read_bytes(), webp_image())

    def test_backfill_requires_a_configured_endpoint(self):
        self.ready(self.vocabulary())
        with patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": ""}):
            with self.assertRaises(Exception):
                call_command("queue_example_illustrations", self.user.username, stdout=self.output)
        self.assertEqual(ExampleIllustration.objects.filter(backfill=True).count(), 0)  # the disabled command wrote nothing

    # --- Retention and cleanup ----------------------------------------------------------------

    def test_cleanup_keeps_referenced_and_retires_abandoned_images(self):
        active = self.ready(self.vocabulary())
        active_row = self.row(active)
        # An older pinned cue keeps its image.
        p = review.next_question(self.user, self.deck)
        work.save_corrected_pair(active.pk, active.source_version, active.active_pair_id, PAIR, {"model": "op"})
        active.refresh_from_db()
        self.assertEqual(active.cue_pair_id, p.snapshot["pair_id"])
        pinned = ExampleIllustration.objects.get(pair_id=p.snapshot["pair_id"])
        # An abandoned revision has no reference; the grace starts, nothing retires yet.
        abandoned = self.ready(self.vocabulary(word="abandoned"))
        abandoned_row = self.row(abandoned)
        Card.objects.filter(pk=abandoned.pk).update(active_pair=None)
        self.assertFalse(work.speech_referenced(abandoned_row.pair))
        # An archived card keeps its image.
        archived = self.ready(self.vocabulary(word="archived"))
        archived_row = self.row(archived)
        authoring.archive_card(archived, True)
        for row in (pinned, abandoned_row, archived_row):
            name = f"{row.pk}.{row.claim.hex}.webp"
            ExampleIllustration.objects.filter(pk=row.pk).update(file=name)
            (self.folder/name).write_bytes(webp_image())
        orphan = self.folder/"stray.webp"; orphan.write_bytes(b"nobody")
        stale = orphan.stat().st_mtime-90000
        os.utime(orphan, (stale, stale))
        stale_partial = self.folder/"interrupted.webp.part"; stale_partial.write_bytes(b"half")
        os.utime(stale_partial, (stale, stale))
        fresh_partial = self.folder/"active-writer.webp.part"; fresh_partial.write_bytes(b"writing")

        illustrations.cleanup_illustrations()  # first pass: the grace begins for the abandoned row only

        self.assertTrue(ExampleIllustration.objects.filter(pk=pinned.pk).exists())
        self.assertTrue(ExampleIllustration.objects.filter(pk=archived_row.pk).exists())
        self.assertIsNotNone(ExampleIllustration.objects.get(pk=abandoned_row.pk).unreferenced_at)
        self.assertTrue((self.folder/f"{abandoned_row.pk}.{abandoned_row.claim.hex}.webp").exists())
        self.assertFalse(orphan.exists())  # aged orphan files still go in the first pass
        self.assertFalse(stale_partial.exists())  # interrupted writer partials are reclaimed too
        self.assertTrue(fresh_partial.exists())  # a live execution's partial is untouched

        ExampleIllustration.objects.filter(pk=abandoned_row.pk).update(unreferenced_at=timezone.now()-timedelta(hours=25))
        illustrations.cleanup_illustrations()  # past the grace: the abandoned image is retired

        self.assertFalse(ExampleIllustration.objects.filter(pk=abandoned_row.pk).exists())
        self.assertFalse((self.folder/f"{abandoned_row.pk}.{abandoned_row.claim.hex}.webp").exists())
        # Restore keeps archived-card images usable.
        authoring.archive_card(archived, False)
        illustrations.cleanup_illustrations()
        self.assertTrue(ExampleIllustration.objects.filter(pk=archived_row.pk).exists())

    def test_cleanup_respects_the_retention_boundary_and_a_returning_reference(self):
        card = self.ready(self.vocabulary())
        row = self.run_render(lambda *a: (webp_image(), ""))
        Card.objects.filter(pk=card.pk).update(active_pair=None)  # abandon the revision
        illustrations.cleanup_illustrations()  # the grace starts now, whatever the image's earlier history
        self.assertTrue(ExampleIllustration.objects.filter(pk=row.pk).exists())
        self.assertTrue((self.folder/row.file).exists())
        self.absence(row, hours=23, minutes=59)
        illustrations.cleanup_illustrations()  # still inside the 24-hour grace
        self.assertTrue(ExampleIllustration.objects.filter(pk=row.pk).exists())
        self.assertTrue((self.folder/row.file).exists())
        self.absence(row, hours=24, seconds=1)
        illustrations.cleanup_illustrations()  # past the grace
        self.assertFalse(ExampleIllustration.objects.filter(pk=row.pk).exists())
        self.assertFalse((self.folder/row.file).exists())
        # A returning reference resets the grace before retirement completes.
        second = self.ready(self.vocabulary(word="returning"))
        Card.objects.filter(pk=second.pk).update(active_pair=None)
        illustrations.cleanup_illustrations()
        self.assertIsNotNone(ExampleIllustration.objects.get(pk=self.row(second).pk).unreferenced_at)
        Card.objects.filter(pk=second.pk).update(active_pair=second.active_pair)  # the reference returns
        illustrations.cleanup_illustrations()
        self.assertIsNone(ExampleIllustration.objects.get(pk=self.row(second).pk).unreferenced_at)


from django.test import TransactionTestCase
from django.db import connections
from learning.worker import run_worker


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class IllustrationWorkerTests(TransactionTestCase):
    """The supervisor owns captioning and rendering in one dedicated illustration slot."""

    def prepared_card(self):
        user = get_user_model().objects.create_user("render-worker")
        deck = Deck.objects.create(owner=user, name="Rendered")
        card = authoring.save_card(deck, "vocabulary", VOCAB)
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300); job.save()
        work.save_pair(job.pk, job.claim, PAIR, {"model": "test"})
        card.refresh_from_db()
        return user, deck, card

    def test_worker_renders_the_caption_through_the_configured_providers(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        with (
            fake_renderer() as (renders, port, _),
            fake_renderer(content=CAPTION_RESPONSE, content_type="application/json") as (captions, caption_port, _),
            patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": f"http://127.0.0.1:{port}/render",
                "ILLUSTRATION_MODEL": "black-forest-labs/flux-3-image-klein", "ILLUSTRATION_API_KEY": "test-only",
                "ILLUSTRATION_CAPTION_ENDPOINT": f"http://127.0.0.1:{caption_port}/chat/completions",
                "ILLUSTRATION_CAPTION_MODEL": "custom-caption-model", "ILLUSTRATION_CAPTION_API_KEY": "caption-only",
                "MINIMAX_API_KEY": "shared-key", "ALLOW_INSECURE_PROVIDER_HTTP": "1"}),
            override_settings(ILLUSTRATIONS_DIR=folder),
        ):
            _, _, card = self.prepared_card()  # the save-time enqueue needs the configured endpoint
            card.active_pair.speech_clips.all().delete()  # this illustration-only test never synthesizes
            run_worker(once=True, concurrency=1)
        connections.close_all()
        row = card.active_pair.illustration
        self.assertEqual(row.state, "done")
        self.assertEqual((folder/row.file).read_bytes(), webp_image())
        self.assertEqual(row.provenance["checkpoint"], "3b767")
        self.assertEqual(row.provenance["model"], "black-forest-labs/flux-3-image-klein")
        self.assertEqual(row.provenance["caption_model"], "custom-caption-model")
        self.assertEqual(len(captions), 1)
        self.assertEqual((captions[0]["path"], captions[0]["authorization"]),
                         ("/chat/completions", "Bearer caption-only"))
        caption_body = captions[0]["body"]
        system, user = caption_body.pop("messages")
        self.assertEqual(caption_body, {"model": "custom-caption-model", "stream": False,
            "reasoning_effort": "max", "reasoning_split": True, "max_completion_tokens": 4096})
        self.assertEqual((system["role"], user["role"]), ("system", "user"))
        self.assertEqual(hashlib.sha256(system["content"].encode()).hexdigest(),
                         "56df3945780599e019674b597f59de668132c706497de52d74d62d9993933515")
        self.assertEqual(json.loads(user["content"]), {"target_expression": VOCAB["word"],
            "english_sentence": PAIR["target_sentence"], "chinese_sentence": PAIR["native_sentence"]})
        self.assertEqual(len(renders), 1)
        self.assertEqual(renders[0]["body"], {"model": "black-forest-labs/flux-3-image-klein",
            "prompt": RENDER_PROMPT, "seed": illustrations.revision_seed(row.pair)})

    # --- Supervisor capacity: R1 regressions --------------------------------------------------

    def test_a_stalled_caption_leaves_assessment_capacity_healthy(self):
        stop = threading.Event(); stalled = threading.Event(); kinds = []
        judge = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(
            {"units": [{"id": 1, "outcome": "complete", "reason": "Complete fixture"}]})}}]}).encode()
        responses = {"render": webp_image(), "caption": CAPTION_RESPONSE, "assessment": judge}
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                length = int(inner.headers.get("Content-Length", "0"))
                inner.rfile.read(length)
                kind = inner.path[1:]
                kinds.append(kind)
                if kind == "caption":  # hold the request open silently, then answer completely
                    stalled.set()
                    while not stop.wait(0.04):
                        pass
                payload = responses[kind]
                inner.send_response(200)
                inner.send_header("Content-Type", "image/webp" if kind == "render" else "application/json")
                inner.send_header("Content-Length", str(len(payload)))
                inner.end_headers()
                inner.wfile.write(payload)
            def log_message(inner, *args): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler); server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        folder = Path(tempfile.mkdtemp()); audio = folder/"audio"; audio.mkdir()
        self.addCleanup(shutil.rmtree, folder, True)
        self.addCleanup(stop.set); self.addCleanup(server.shutdown)
        observed = []
        def watch():
            try:
                if not stalled.wait(30):
                    return
                connections.close_all()
                p = review.next_question(card.deck.owner, spoken_deck)
                a = review.submit(p, "speak", 1, "missing")
                (audio/a.audio_name).write_bytes(audio_bytes())
                a.save()
                limit = time.monotonic()+40
                while time.monotonic() < limit:
                    connections.close_all()
                    attempt = Attempt.objects.get(pk=a.pk)
                    row = ExampleIllustration.objects.get(pair=card.active_pair)
                    if attempt.state == "assessed" and row.state == "processing":
                        observed.append((attempt.state, row.state))
                        return
                    time.sleep(0.1)
            finally:
                stop.set()
                connections.close_all()
        watcher = threading.Thread(target=watch, daemon=True)
        with patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": f"http://127.0.0.1:{server.server_port}/render",
                                     "ILLUSTRATION_API_KEY": "test-only", "ALLOW_INSECURE_PROVIDER_HTTP": "1",
                                     "ILLUSTRATION_CAPTION_ENDPOINT": f"http://127.0.0.1:{server.server_port}/caption",
                                     "ILLUSTRATION_CAPTION_API_KEY": "caption-only",
                                     "AUDIO_ASSESS_ENDPOINT": f"http://127.0.0.1:{server.server_port}/assessment",
                                     "AUDIO_ASSESS_API_KEY": "test-only"}), \
                override_settings(ILLUSTRATIONS_DIR=folder/"render", AUDIO_DIR=audio):
            _, _, card = self.prepared_card()
            card.active_pair.speech_clips.all().delete()  # keep this test about capacity only
            spoken_deck = Deck.objects.create(owner=card.deck.owner, name="Healthy")
            authoring.save_card(spoken_deck, "generic", GENERIC)
            (folder/"render").mkdir()
            watcher.start()
            try:
                run_worker(once=True, concurrency=1)
            finally:
                watcher.join(timeout=10)
        connections.close_all()
        self.assertEqual(observed, [("assessed", "processing")])
        self.assertEqual(kinds, ["caption", "assessment", "render"])
        row = ExampleIllustration.objects.get(pair=card.active_pair)
        self.assertEqual(row.state, "done")  # the released render then published normally
        self.assertEqual((folder/"render"/row.file).read_bytes(), webp_image())

    def test_speech_is_served_alongside_a_held_render_and_assessment(self):
        stop = threading.Event(); render_stalled = threading.Event(); judge_stalled = threading.Event()
        kinds = []
        judge = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(
            {"units": [{"id": 1, "outcome": "complete", "reason": "Complete fixture"}]})}}]}).encode()
        speech = json.dumps({"data": {"audio": b"released-clip".hex(), "status": 2},
                             "base_resp": {"status_code": 0}}).encode()
        responses = {"render": webp_image(), "speech": speech, "caption": CAPTION_RESPONSE, "assessment": judge}
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                length = int(inner.headers.get("Content-Length", "0"))
                inner.rfile.read(length)
                kind = inner.path[1:]
                kinds.append(kind)
                if kind == "render":
                    render_stalled.set()
                    while not stop.wait(0.04):
                        pass
                elif kind == "assessment":
                    judge_stalled.set()
                    while not stop.wait(0.04):
                        pass
                payload = responses[kind]
                inner.send_response(200)
                inner.send_header("Content-Type", "image/webp" if kind == "render" else "application/json")
                inner.send_header("Content-Length", str(len(payload)))
                if kind == "render":
                    inner.send_header("X-Illustration-Revision", "3b767")
                inner.end_headers()
                inner.wfile.write(payload)
            def log_message(inner, *args): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler); server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        folder = Path(tempfile.mkdtemp()); audio = folder/"audio"; audio.mkdir()
        self.addCleanup(shutil.rmtree, folder, True)
        self.addCleanup(stop.set); self.addCleanup(server.shutdown)
        observed = []
        def watch():
            try:
                if not (render_stalled.wait(30) and judge_stalled.wait(5)):
                    return
                connections.close_all()
                work.enqueue_speech(late_card.active_pair)  # speech arrives late, both slots occupied
                limit = time.monotonic()+40
                while time.monotonic() < limit:
                    connections.close_all()
                    clip = SpeechClip.objects.get(pair=late_card.active_pair, side="target")
                    attempt = Attempt.objects.filter(state="processing").first()
                    if clip.state == "done" and attempt is not None:
                        observed.append((clip.state, attempt.state))
                        return
                    time.sleep(0.1)
            finally:
                stop.set()
                connections.close_all()
        watcher = threading.Thread(target=watch, daemon=True)
        with patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": f"http://127.0.0.1:{server.server_port}/render",
                                     "ILLUSTRATION_API_KEY": "test-only", "ALLOW_INSECURE_PROVIDER_HTTP": "1",
                                     "ILLUSTRATION_CAPTION_ENDPOINT": f"http://127.0.0.1:{server.server_port}/caption",
                                     "ILLUSTRATION_CAPTION_API_KEY": "caption-only",
                                     "SPEECH_ENDPOINT": f"http://127.0.0.1:{server.server_port}/speech",
                                     "SPEECH_API_KEY": "test-only",
                                     "AUDIO_ASSESS_ENDPOINT": f"http://127.0.0.1:{server.server_port}/assessment",
                                     "AUDIO_ASSESS_API_KEY": "test-only"}), \
                override_settings(ILLUSTRATIONS_DIR=folder/"render", AUDIO_DIR=audio, TTS_DIR=folder/"tts"):
            _, _, card = self.prepared_card()
            card.active_pair.speech_clips.all().delete()  # speech arrives late through the watcher
            spoken_deck = Deck.objects.create(owner=card.deck.owner, name="Held")
            authoring.save_card(spoken_deck, "generic", GENERIC)
            p = review.next_question(card.deck.owner, spoken_deck)
            held = review.submit(p, "speak", 1, "missing")
            (audio/held.audio_name).write_bytes(audio_bytes()); held.save()
            late_card = card
            (folder/"render").mkdir(); (folder/"tts").mkdir()
            watcher.start()
            try:
                run_worker(once=True, concurrency=1)
            finally:
                watcher.join(timeout=10)
        connections.close_all()
        self.assertEqual(observed, [("done", "processing")])  # speech completed around the held pair
        self.assertIn("speech", kinds)
        self.assertEqual(SpeechClip.objects.get(pair=card.active_pair, side="target").state, "done")
        self.assertEqual(ExampleIllustration.objects.get(pair=card.active_pair).state, "done")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RendererScriptTests(TestCase):
    """The operator-run renderer authenticates every request and validates the model identifier."""

    def load(self):
        spec = importlib.util.spec_from_file_location(
            "illustration_renderer", Path(__file__).resolve().parents[2]/"ops"/"illustration-renderer.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_startup_refuses_without_a_worker_credential(self):
        module = self.load()
        with self.assertRaises(SystemExit):
            module.require_worker_credential(module.build_parser().parse_args(
                ["--comfyui", "http://127.0.0.1:8188", "--temp-dir", "/tmp/x"]))
        module.require_worker_credential(module.build_parser().parse_args(
            ["--comfyui", "http://127.0.0.1:8188", "--temp-dir", "/tmp/x", "--api-key", "secret"]))  # configured: no refusal

    def test_the_renderer_authenticates_and_validates_the_model(self):
        module = self.load()
        module.Handler.arguments = argparse.Namespace(api_key="secret",
            model="black-forest-labs/flux-3-image-klein", revision="3b767", timeout=120)
        def post(authorization, body):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            headers = {"Authorization": authorization} if authorization is not None else {}
            connection.request("POST", "/render", body=json.dumps(body).encode(), headers=headers)
            response = connection.getresponse()
            payload, status = response.read(), response.status
            connection.close()
            return status, payload
        with patch.object(module, "render", return_value=webp_image()):
            server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                self.assertEqual(post(None, {"model": "x", "prompt": "s", "seed": 1})[0], 401)
                self.assertEqual(post("Bearer wrong", {"model": "x", "prompt": "s", "seed": 1})[0], 401)
                status, _ = post("Bearer secret", {"model": "other/model", "prompt": "s", "seed": 1})
                self.assertEqual(status, 400)  # a model mismatch is a clear configuration error
                status, payload = post("Bearer secret",
                                       {"model": "black-forest-labs/flux-3-image-klein", "prompt": "scene", "seed": 1})
                self.assertEqual((status, payload), (200, webp_image()))
            finally:
                server.shutdown(); server.server_close()
                thread.join(timeout=5)
