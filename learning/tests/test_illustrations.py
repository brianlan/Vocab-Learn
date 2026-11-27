"""Issue #26: one durable illustration per Example Pair revision, private retrieval and retention."""
import io
import json
import os
import shutil
import tempfile
import threading
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
from learning.models import Card, Deck, ExampleIllustration, SpeechClip
from learning.providers import StageError
from .test_learning import PAIR, VOCAB


def webp_bytes(payload=b"scene"):
    body = b"RIFF" + (12+len(payload)).to_bytes(4, "little") + b"WEBP" + payload
    assert len(body) <= providers.ILLUSTRATION_MAX_BYTES
    return body


@contextmanager
def fake_renderer(content=None, status=200, revision="3b767"):
    """A local fake renderer that records each request; serves WebP bytes by default."""
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(inner):
            length = int(inner.headers.get("Content-Length", "0"))
            requests.append({"path": inner.path, "authorization": inner.headers.get("Authorization"),
                             "body": json.loads(inner.rfile.read(length)) if length else {}})
            body = content if content is not None else webp_bytes()
            inner.send_response(status)
            inner.send_header("Content-Type", "image/webp")
            inner.send_header("Content-Length", str(len(body)))
            inner.send_header("X-Illustration-Revision", revision)
            inner.end_headers()
            inner.wfile.write(body)
        def log_message(inner, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield requests, server.server_port
    finally:
        server.shutdown(); server.server_close()
        thread.join(timeout=5)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class IllustrationTests(TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        override = override_settings(ILLUSTRATIONS_DIR=self.folder)
        override.enable(); self.addCleanup(override.disable)
        self.environ = patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": "http://renderer.internal/render",
            "ILLUSTRATION_MODEL": "", "ILLUSTRATION_API_KEY": "test-only",
            "ALLOW_INSECURE_PROVIDER_HTTP": "1"})
        self.environ.start(); self.addCleanup(self.environ.stop)
        self.user = get_user_model().objects.create_user("illustrator", password="test-password")
        self.other = get_user_model().objects.create_user("other", password="test-password")
        self.deck = Deck.objects.create(owner=self.user, name="Illustrated")
        self.output = io.StringIO()

    def vocabulary(self, **overrides):
        return authoring.save_card(self.deck, "vocabulary", {**VOCAB, **overrides})

    def ready(self, card):
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300); job.save()
        work.save_pair(job.pk, job.claim, PAIR, {"model": "test"})
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

    def test_prompt_uses_english_or_spanish_sentence_with_a_stable_seed(self):
        english = self.ready(self.vocabulary()).active_pair
        self.assertEqual(illustrations.scene_sentence(english)[1], "English")
        spanish = self.ready(self.vocabulary(word="vela", target_language="Spanish", native_language="Chinese")).active_pair
        sentence, language = illustrations.scene_sentence(spanish)
        self.assertEqual((sentence, language), (spanish.target_sentence, "Spanish"))
        self.assertIn("no text, letters, numbers", illustrations.illustration_prompt(english))
        self.assertIn(english.target_sentence, illustrations.illustration_prompt(english))
        self.assertEqual(illustrations.revision_seed(english), illustrations.revision_seed(english))
        self.assertNotEqual(illustrations.revision_seed(english), illustrations.revision_seed(spanish))

    # --- Dispatch, validation and publication -------------------------------------------------

    def test_adapter_targets_the_configured_url_model_and_bearer(self):
        card = self.ready(self.vocabulary())
        with fake_renderer() as (requests, port):
            row = self.run_live_render(port)
        self.assertEqual(row.state, "done")
        request = requests[0]
        self.assertEqual(request["path"], "/render")
        self.assertEqual(request["authorization"], "Bearer test-only")
        self.assertEqual(request["body"]["model"], "black-forest-labs/flux-3-image-klein")  # documented default
        self.assertEqual(request["body"]["seed"], illustrations.revision_seed(row.pair))
        self.assertIn(row.pair.target_sentence, request["body"]["prompt"])
        self.assertIn("no text, letters, numbers", request["body"]["prompt"])
        self.assertEqual(row.provenance["model"], "black-forest-labs/flux-3-image-klein")
        self.assertEqual(row.provenance["checkpoint"], "3b767")
        self.assertEqual(row.provenance["prompt_version"], illustrations.PROMPT_VERSION)
        self.assertLessEqual(set(row.provenance), {"task", "endpoint", "model", "timeout",
            "prompt_version", "seed", "checkpoint"})  # secret-free provenance
        self.assertEqual(row.file, f"{row.pk}.{row.claim.hex}.webp")
        path = self.folder/row.file
        self.assertEqual(path.read_bytes(), webp_bytes())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(illustrations.available_illustration(row.pair).pk, row.pk)
        self.client.force_login(self.user)
        response = self.client.get(reverse("illustration_image", args=[row.pair_id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/webp")
        self.assertEqual(b"".join(response.streaming_content), webp_bytes())

    def test_another_learner_and_missing_images_are_denied(self):
        card = self.ready(self.vocabulary())
        row = self.run_render(lambda *a: (webp_bytes(), ""))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("illustration_image", args=[row.pair_id])).status_code, 404)
        self.client.force_login(self.user)
        (self.folder/row.file).unlink()
        self.assertEqual(self.client.get(reverse("illustration_image", args=[row.pair_id])).status_code, 404)
        self.assertIsNone(illustrations.available_illustration(row.pair))  # missing file advertises nothing

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
        service = self.run_live(webp_bytes(), status=500)
        self.assertEqual((service.state, service.error_category, service.retryable), ("failed", "provider", True))
        rejected = self.run_live(webp_bytes(), status=400)
        self.assertEqual((rejected.state, rejected.error_category, rejected.retryable),
                         ("failed", "configuration", False))  # a renderer/model mismatch stays explicit

    def run_live(self, content, status=200):
        with fake_renderer(content=content, status=status) as (_, port):
            return self.run_live_render(port)

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
        self.assertFalse(called)

    def test_stale_publication_cannot_replace_a_newer_image(self):
        card = self.ready(self.vocabulary())
        pk, claim = self.processing()
        ExampleIllustration.objects.filter(pk=pk).update(claim=uuid.uuid4())  # an explicit retry rotated the claim
        illustrations.publish_illustration(pk, claim, webp_bytes(), "")
        row = ExampleIllustration.objects.get(pk=pk)
        self.assertEqual((row.state, row.file), ("processing", ""))
        self.assertFalse(list(self.folder.glob(f"{pk}.{claim.hex}.webp")))

    def test_publication_rejects_images_that_lost_eligibility_during_dispatch(self):
        card = self.ready(self.vocabulary())
        pk, claim = self.processing()
        ExampleIllustration.objects.filter(pk=pk).update(deadline=timezone.now()-timedelta(seconds=1))
        illustrations.publish_illustration(pk, claim, webp_bytes(b"late"), "")  # the budget expired during rendering
        row = ExampleIllustration.objects.get(pk=pk)
        self.assertNotEqual(row.state, "done")
        self.assertFalse((self.folder/f"{pk}.{claim.hex}.webp").exists())
        lost = self.ready(self.vocabulary(word="lost"))
        pk, claim = self.processing()
        Card.objects.filter(pk=lost.pk).update(active_pair=None)  # the last reference disappears mid-call
        illustrations.publish_illustration(pk, claim, webp_bytes(b"orphan"), "")
        row = ExampleIllustration.objects.get(pk=pk)
        self.assertNotEqual(row.state, "done")
        self.assertIsNone(illustrations.available_illustration(lost.active_pair))
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
            row = self.run_render(lambda *a: (webp_bytes(), ""))
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
        self.ready(authoring.save_card(foreign_deck, "vocabulary", VOCAB))
        missing.active_pair.illustration.delete()
        ExampleIllustration.objects.filter(pk=self.row(broken).pk).update(
            state="failed", error="boom", error_category="provider", retryable=True)
        ExampleIllustration.objects.filter(pk=self.row(done).pk).update(state="queued")

        call_command("queue_example_illustrations", self.user.username, dry_run=True, stdout=self.output)
        self.assertIn("missing 1, failed 1, queued 1, processing 0, ready 0", self.output.getvalue())
        self.assertEqual(ExampleIllustration.objects.filter(backfill=True).count(), 0)

        call_command("queue_example_illustrations", self.user.username, limit=1, stdout=self.output)
        self.assertEqual(ExampleIllustration.objects.filter(backfill=True).count(), 1)  # the limit bounded the enqueue
        call_command("queue_example_illustrations", self.user.username, stdout=self.output)
        backfilled = ExampleIllustration.objects.filter(backfill=True).get()
        self.assertEqual(backfilled.pair_id, missing.active_pair_id)
        self.assertEqual((self.row(broken).state, self.row(broken).execution), ("queued", 2))  # failed retried
        self.assertEqual(self.row(done).state, "queued")  # queued work untouched
        before = sorted(ExampleIllustration.objects.values_list("pk", flat=True))
        call_command("queue_example_illustrations", self.user.username, stdout=self.output)  # repeated run coalesces
        self.assertEqual(sorted(ExampleIllustration.objects.values_list("pk", flat=True)), before)

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
            (self.folder/name).write_bytes(webp_bytes())
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
        row = self.run_render(lambda *a: (webp_bytes(), ""))
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
    """The supervisor owns the illustration spawn path: one dedicated slot through a fake renderer."""

    def prepared_card(self):
        user = get_user_model().objects.create_user("render-worker")
        deck = Deck.objects.create(owner=user, name="Rendered")
        card = authoring.save_card(deck, "vocabulary", VOCAB)
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300); job.save()
        work.save_pair(job.pk, job.claim, PAIR, {"model": "test"})
        card.refresh_from_db()
        return user, deck, card

    def test_worker_renders_the_illustration_through_a_fake_renderer(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                requests.append(json.loads(inner.rfile.read(int(inner.headers["Content-Length"]))))
                inner.send_response(200)
                inner.send_header("Content-Type", "image/webp")
                inner.send_header("Content-Length", str(len(webp_bytes(b"worker-image"))))
                inner.send_header("X-Illustration-Revision", "3b767")
                inner.end_headers()
                inner.wfile.write(webp_bytes(b"worker-image"))
            def log_message(inner, *args): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler); server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        self.addCleanup(server.shutdown)
        try:
            with patch.dict(os.environ, {"ILLUSTRATION_ENDPOINT": f"http://127.0.0.1:{server.server_port}/render",
                                         "ILLUSTRATION_MODEL": "black-forest-labs/flux-3-image-klein",
                                         "ILLUSTRATION_API_KEY": "test-only", "ALLOW_INSECURE_PROVIDER_HTTP": "1"}), \
                    override_settings(ILLUSTRATIONS_DIR=folder):
                _, _, card = self.prepared_card()  # the save-time enqueue needs the configured endpoint
                run_worker(once=True, concurrency=1)
        finally:
            connections.close_all()
        row = card.active_pair.illustration
        self.assertEqual(row.state, "done")
        self.assertEqual((folder/row.file).read_bytes(), webp_bytes(b"worker-image"))
        self.assertEqual(row.provenance["checkpoint"], "3b767")
        self.assertEqual(row.provenance["model"], "black-forest-labs/flux-3-image-klein")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["model"], "black-forest-labs/flux-3-image-klein")
        self.assertIn("prompt", requests[0])
