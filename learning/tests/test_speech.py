import json
import os
import shutil
import tempfile
import io
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from learning import authoring, review, work
from learning.models import Card, Deck, ExamplePair, Presentation, SpeechClip
from learning.providers import StageError
from .test_learning import VOCAB, PAIR


def minimax_response(sound=b"clip-bytes"):
    return {"data": {"audio": sound.hex(), "status": 2},
            "extra_info": {"audio_format": "mp3", "audio_channel": 1, "audio_size": len(sound)},
            "base_resp": {"status_code": 0, "status_msg": "success"}}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SpeechTests(TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        tts = self.folder/"tts"
        tts.mkdir()
        self.override = override_settings(TTS_DIR=tts)
        self.override.enable(); self.addCleanup(self.override.disable)
        self.environ = patch.dict(os.environ, {"SPEECH_API_KEY": "test-only"})
        self.environ.start(); self.addCleanup(self.environ.stop)
        self.user = get_user_model().objects.create_user("learner", password="test-password")
        self.other = get_user_model().objects.create_user("other", password="test-password")
        self.deck = Deck.objects.create(owner=self.user, name="Speech")
        self.output = io.StringIO()

    def vocabulary(self, **overrides):
        return authoring.save_card(self.deck, "vocabulary", {**VOCAB, **overrides})

    def ready(self, card):
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300); job.save()
        work.save_pair(job.pk, job.claim, PAIR, {"model": "test"})
        card.refresh_from_db()
        return card

    def clip(self, card, side):
        return card.active_pair.speech_clips.get(side=side)

    def processing(self, side):
        """Move one not-done side into a processing execution with a fresh claim."""
        clip = SpeechClip.objects.filter(side=side, state__in=["queued", "failed"]).first()
        claim, now = uuid.uuid4(), timezone.now()
        SpeechClip.objects.filter(pk=clip.pk).update(state="processing", claim=claim,
            started_at=now, deadline=now+timedelta(seconds=settings.SPEECH_TIMEOUT_SECONDS))
        return clip.pk, claim

    def run_speech(self, side, request_side_effect):
        """Synthesize one side under a patched provider; record StageError failures as the worker does."""
        pk, claim = self.processing(side)
        with patch("learning.providers.request", side_effect=request_side_effect):
            try:
                work.process_speech(pk, claim)
            except StageError as failure:
                work.fail("speech", pk, claim, failure)
        return SpeechClip.objects.get(pk=pk)

    def rotate(self, card):
        """Run one automatic rotation to a done candidate pair for the card."""
        Presentation.objects.filter(user=self.user).update(invalidated=True)
        others = Card.objects.filter(deck__owner=self.user).exclude(pk=card.pk)
        others.update(deferred_until=timezone.now()+timedelta(days=30))  # keep random tier-2 selection on the card
        card.due = timezone.now()-timedelta(seconds=1); card.save(update_fields=["due"])
        p = review.next_question(self.user, self.deck)
        self.assertEqual(p.card_id, card.pk)
        a = review.submit(p, "speak", 2)
        review.commit_grade(a.pk, a.claim, "E", [], "Rotation fixture.")
        others.update(deferred_until=None)
        card.refresh_from_db()
        job = card.generation_jobs.filter(mode="rotation", state="queued").get()
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300); job.save()
        candidate = {"target_sentence": f"The <focus>{card.word}</focus> of the plan improved the result.",
                     "native_sentence": f"计划的<focus>调整</focus>改善了结果。"}
        envelope = {"verdict": "accept", "issues": [], "pair": candidate}
        def chat(profile, rules, payload):
            return candidate if profile.task == "GENERATOR" else envelope
        with patch.dict(os.environ, {"GENERATOR_API_KEY": "test-only", "EXAMPLE_REVIEWER_API_KEY": "test-only"}), \
                patch("learning.providers.chat", side_effect=chat):
            work.process_generation(job.pk, job.claim)
        card.refresh_from_db()
        return card.generation_jobs.get(mode="rotation", state="done").result

    def age(self, clip, hours=25):
        SpeechClip.objects.filter(pk=clip.pk).update(updated_at=timezone.now()-timedelta(hours=hours))

    # --- Pair-save enqueue coverage -----------------------------------------------------------

    def test_initial_correction_and_rotation_saves_queue_both_sides_once(self):
        card = self.ready(self.vocabulary())
        target, native = self.clip(card, "target"), self.clip(card, "native")
        self.assertEqual((target.language, native.language), ("English", "Chinese"))
        self.assertEqual(target.state, "queued")
        work.enqueue_speech(card.active_pair)  # duplicate invocation coalesces
        self.assertEqual(card.active_pair.speech_clips.count(), 2)

        # Operator correction saves a replacement pair through the correction path.
        pair = work.save_corrected_pair(card.pk, card.source_version, card.active_pair_id, PAIR, {"model": "op"})
        self.assertEqual(pair.speech_clips.count(), 2)
        self.assertNotEqual(pair.speech_clips.get(side="target").pk, target.pk)

        # Automatic rotation saves a candidate pair with its own sides.
        self.rotate(card)
        self.assertEqual(ExamplePair.objects.count(), 3)
        self.assertEqual(SpeechClip.objects.count(), 6)

    def test_rejected_and_rolled_back_saves_leave_no_speech_tasks(self):
        card = self.vocabulary()
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300); job.save()
        # Rejected execution: a stale claim persists nothing.
        self.assertIsNone(work.save_pair(job.pk, uuid.uuid4(), PAIR, {}))
        self.assertEqual(SpeechClip.objects.count(), 0)
        # Rolled-back execution: a committed pair save is undone with its speech tasks.
        sid = transaction.savepoint()
        self.assertIsNotNone(work.save_pair(job.pk, job.claim, PAIR, {}))
        self.assertEqual(SpeechClip.objects.count(), 2)
        transaction.savepoint_rollback(sid)
        self.assertEqual(SpeechClip.objects.count(), 0)
        self.assertEqual(ExamplePair.objects.count(), 0)

    # --- Worker synthesis ---------------------------------------------------------------------

    def test_success_publishes_private_clip_with_secret_free_provenance(self):
        card = self.ready(self.vocabulary())
        target = self.run_speech("target", [minimax_response(b"target-audio")])
        self.assertEqual(target.state, "done")
        path = settings.TTS_DIR/target.file
        self.assertTrue(target.file.endswith(".mp3") and path.is_file())
        self.assertEqual(path.read_bytes(), b"target-audio")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.provenance["voice"], "English_CalmWoman")
        self.assertEqual(target.provenance["task"], "SPEECH")
        self.assertEqual(target.provenance["model"], "speech-2.8-turbo")
        self.assertNotIn("key", target.provenance)
        self.assertEqual(work.available_speech(card.active_pair)["target"].pk, target.pk)
        self.assertNotIn("native", work.available_speech(card.active_pair))

    def test_request_body_pins_voice_model_and_encoding(self):
        card = self.ready(self.vocabulary())
        bodies = []
        def record(request, **kwargs):
            bodies.append(kwargs["json"])
            return minimax_response()
        with patch.dict(os.environ, {"SPEECH_VOICE_MANDARIN": "Chinese (Mandarin)_Other"}):
            self.run_speech("native", record)
        body = bodies[0]
        self.assertEqual(body["model"], "speech-2.8-turbo")
        self.assertEqual(body["stream"], False)
        self.assertEqual(body["output_format"], "hex")
        self.assertEqual(body["voice_setting"], {"voice_id": "Chinese (Mandarin)_Other", "speed": 1, "vol": 1, "pitch": 0})
        self.assertEqual(body["audio_setting"], {"sample_rate": 32000, "bitrate": 64000, "format": "mp3", "channel": 1})
        self.assertEqual(body["text"], card.active_pair.native_sentence)

    def test_malformed_and_one_side_failures_stay_isolated(self):
        self.ready(self.vocabulary())
        # Malformed: not-completed status is rejected before any file is written.
        target = self.run_speech("target", [{"data": {"audio": b"x".hex(), "status": 1}}])
        self.assertEqual(target.state, "failed")
        self.assertFalse(target.file)
        # One-side failure keeps the successful sibling available.
        native = self.run_speech("native", [minimax_response(b"native-audio")])
        self.assertEqual(native.state, "done")
        # Provider transport failure stays retryable; configuration failures do not.
        blocked = self.run_speech("target", [StageError("SPEECH", "down", "provider")])
        self.assertEqual((blocked.error_category, blocked.retryable), ("provider", True))
        unkeyed = self.run_speech("target", [StageError("SPEECH", "no key", "configuration")])
        self.assertEqual((unkeyed.error_category, unkeyed.retryable), ("configuration", False))

    def test_expired_execution_budget_fails_before_dispatch(self):
        self.ready(self.vocabulary())
        pk, claim = self.processing("target")
        SpeechClip.objects.filter(pk=pk).update(deadline=timezone.now()-timedelta(seconds=1))
        called = []
        with patch("learning.providers.request", side_effect=lambda *a, **k: called.append(1)):
            with self.assertRaises(StageError) as ctx:
                work.process_speech(pk, claim)
        work.fail("speech", pk, claim, ctx.exception)
        clip = SpeechClip.objects.get(pk=pk)
        self.assertEqual((clip.state, clip.error_category), ("failed", "timeout"))
        self.assertFalse(called)

    def test_stale_publication_cannot_replace_a_newer_clip(self):
        self.ready(self.vocabulary())
        pk, claim = self.processing("target")
        # An explicit retry rotated the claim before the stale execution finished.
        SpeechClip.objects.filter(pk=pk).update(claim=uuid.uuid4())
        work.publish_speech(pk, claim, b"stale-audio")
        clip = SpeechClip.objects.get(pk=pk)
        self.assertEqual((clip.state, clip.file), ("processing", ""))
        self.assertFalse(list(settings.TTS_DIR.glob(f"{pk}.{claim.hex}.mp3")))

    def test_explicit_retry_applies_changed_profile(self):
        self.ready(self.vocabulary())
        failed = self.run_speech("target", [StageError("SPEECH", "rejected", "provider")])
        self.assertEqual(failed.execution, 1)
        call_command("queue_example_speech", self.user.username, stdout=self.output)
        self.assertIn("Queued 1 sides (missing 0, failed 1)", self.output.getvalue())
        retried = self.run_speech("target", [minimax_response(b"again")])
        self.assertEqual((retried.state, retried.execution), ("done", 2))
        self.assertEqual(retried.provenance["voice"], "English_CalmWoman")
        with patch.dict(os.environ, {"SPEECH_VOICE_MANDARIN": "Chinese (Mandarin)_Other"}):
            other = self.run_speech("native", [minimax_response()])
        self.assertEqual(other.provenance["voice"], "Chinese (Mandarin)_Other")

    def test_spoken_assessment_is_claimable_while_speech_is_stalled(self):
        self.ready(self.vocabulary())
        work.claim_speech()  # a stalled speech execution occupies its dedicated slot
        p = review.next_question(self.user, self.deck)
        review.submit(p, "speak", 2)
        self.assertEqual(work.claim_work()[0], "assessment")
        self.assertEqual(SpeechClip.objects.filter(state="processing").count(), 1)

    # --- Backfill command ---------------------------------------------------------------------

    def test_backfill_command_previews_queues_and_coalesces(self):
        done = self.ready(self.vocabulary())
        missing = self.ready(self.vocabulary(word="missing"))
        broken = self.ready(self.vocabulary(word="broken"))
        missing.active_pair.speech_clips.all().delete()
        SpeechClip.objects.filter(pk=self.clip(broken, "target").pk).update(
            state="failed", error="boom", error_category="provider", retryable=True)
        foreign_deck = Deck.objects.create(owner=self.other, name="Elsewhere")
        self.ready(authoring.save_card(foreign_deck, "vocabulary", VOCAB))
        call_command("queue_example_speech", self.user.username, dry_run=True, stdout=self.output)
        self.assertIn("missing sides 2, failed sides 1", self.output.getvalue())
        self.assertEqual(SpeechClip.objects.filter(backfill=True).count(), 0)

        call_command("queue_example_speech", self.user.username, stdout=self.output)
        backfilled = SpeechClip.objects.filter(backfill=True)
        self.assertEqual(backfilled.count(), 2)  # both deleted sides of the missing pair
        self.assertEqual(backfilled.distinct().values_list("pair_id", flat=True).get(), missing.active_pair_id)
        self.assertEqual((self.clip(broken, "target").state, self.clip(broken, "target").execution), ("queued", 2))
        self.assertEqual(self.clip(done, "target").state, "queued")  # queued work untouched
        before = sorted(SpeechClip.objects.values_list("pk", flat=True))
        call_command("queue_example_speech", self.user.username, stdout=self.output)  # repeated run coalesces
        self.assertEqual(sorted(SpeechClip.objects.values_list("pk", flat=True)), before)

    # --- Retention and cleanup ----------------------------------------------------------------

    def test_cleanup_keeps_referenced_and_retires_abandoned_clips(self):
        active = self.ready(self.vocabulary())
        self.age(self.clip(active, "target"))  # referenced by active_pair despite age
        # An older pinned cue keeps its clips.
        p = review.next_question(self.user, self.deck)
        work.save_corrected_pair(active.pk, active.source_version, active.active_pair_id, PAIR, {"model": "op"})
        active.refresh_from_db()
        self.assertEqual(active.cue_pair_id, p.snapshot["pair_id"])
        pinned = SpeechClip.objects.get(pair_id=p.snapshot["pair_id"], side="target")
        self.age(pinned)
        # A superseded rotation candidate loses its reference and is retired.
        card = self.ready(self.vocabulary(word="rotation"))
        candidate = self.rotate(card)
        self.assertTrue(work.speech_referenced(candidate))
        Card.objects.filter(pk=card.pk).update(rotation_token=None)  # superseded before adoption
        self.assertFalse(work.speech_referenced(candidate))
        for clip in candidate.speech_clips.all():
            self.age(clip)
        # An archived card keeps its clips; restore changes nothing.
        archived = self.ready(self.vocabulary(word="archived"))
        authoring.archive_card(archived, True)
        self.age(self.clip(archived, "native"))
        orphan = settings.TTS_DIR/"stray.mp3"; orphan.write_bytes(b"nobody")
        stale = orphan.stat().st_mtime-90000
        os.utime(orphan, (stale, stale))
        fresh_orphan = settings.TTS_DIR/"fresh.mp3"; fresh_orphan.write_bytes(b"soon")

        work.cleanup_speech()

        self.assertTrue(SpeechClip.objects.filter(pair=active.active_pair, side="target").exists())
        self.assertTrue(SpeechClip.objects.filter(pk=pinned.pk).exists())
        self.assertTrue(SpeechClip.objects.filter(pair=archived.active_pair, side="native").exists())
        self.assertFalse(SpeechClip.objects.filter(pair=candidate).exists())
        self.assertFalse(orphan.exists())
        self.assertTrue(fresh_orphan.exists())
        # Restore keeps archived-card clips usable.
        authoring.archive_card(archived, False)
        work.cleanup_speech()
        self.assertTrue(SpeechClip.objects.filter(pair=archived.active_pair, side="native").exists())

    def test_cleanup_respects_the_retention_boundary(self):
        card = self.ready(self.vocabulary())
        clip = self.run_speech("target", [minimax_response()])
        Card.objects.filter(pk=card.pk).update(active_pair=None)  # abandon the revision
        self.assertFalse(work.speech_referenced(card.active_pair))
        work.cleanup_speech()  # inside the 24-hour grace
        self.assertTrue(SpeechClip.objects.filter(pk=clip.pk).exists())
        self.assertTrue((settings.TTS_DIR/clip.file).exists())
        self.age(clip)
        work.cleanup_speech()  # past the grace
        self.assertFalse(SpeechClip.objects.filter(pk=clip.pk).exists())
        self.assertFalse((settings.TTS_DIR/clip.file).exists())


from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from django.test import TransactionTestCase
from learning.models import ExamplePair
from learning.worker import run_worker


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SpeechWorkerTests(TransactionTestCase):
    """The supervisor owns the speech spawn path: one dedicated slot, both sides through a fake MiniMax."""

    def test_worker_synthesizes_both_sides_through_a_fake_provider(self):
        stop = threading.Event()
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                requests.append(json.loads(inner.rfile.read(int(inner.headers["Content-Length"]))))
                inner.send_response(200); inner.send_header("Content-Type", "application/json"); inner.end_headers()
                time.sleep(0.3)
                inner.wfile.write(json.dumps(minimax_response(b"worker-clip")).encode())
            def log_message(inner, *args): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler); server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        self.addCleanup(stop.set)
        self.addCleanup(server.shutdown)
        user = get_user_model().objects.create_user("speech-worker")
        deck = Deck.objects.create(owner=user, name="Spoken")
        card = authoring.save_card(deck, "vocabulary", VOCAB)
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300); job.save()
        work.save_pair(job.pk, job.claim, PAIR, {"model": "test"})
        card.refresh_from_db()
        try:
            with patch.dict(os.environ, {"SPEECH_ENDPOINT": f"http://127.0.0.1:{server.server_port}/t2a_v2",
                                         "SPEECH_API_KEY": "test-only", "ALLOW_INSECURE_PROVIDER_HTTP": "1"}), \
                    override_settings(TTS_DIR=Path(folder)):
                run_worker(once=True, concurrency=1)
        finally:
            connections.close_all()
        clips = list(card.active_pair.speech_clips.order_by("side"))
        self.assertEqual([c.state for c in clips], ["done", "done"])
        for clip in clips:
            self.assertEqual((Path(folder)/clip.file).read_bytes(), b"worker-clip")
            self.assertEqual(clip.provenance["task"], "SPEECH")
        self.assertEqual(len(requests), 2)
        self.assertEqual({body["voice_setting"]["voice_id"] for body in requests},
                         {"English_CalmWoman", "Chinese (Mandarin)_Warm_Bestie"})
