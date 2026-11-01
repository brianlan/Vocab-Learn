"""Durable pipeline stages. Slow I/O always runs outside database transactions."""
import json
import math
import os
import subprocess
import time
import uuid
import wave
from dataclasses import replace
from datetime import timedelta
from django.conf import settings
from django.db import transaction, OperationalError
from django.utils import timezone
from . import providers
from .models import Attempt, Card, ExamplePair, GenerationJob
from .review import TERMINAL, commit_grade, grade_units, valid_presentation, defer, adopt_corrected_cue


def remaining(deadline):
    seconds = (deadline-timezone.now()).total_seconds()
    if seconds <= 0:
        raise providers.StageError("timeout", "This execution expired. Retry explicitly.", "timeout")
    return seconds


def bounded_profile(task, deadline):
    p = providers.profile(task)
    return replace(p, timeout=min(p.timeout, remaining(deadline)))


def normalize(path, deadline):
    if not path.is_file() or path.stat().st_size > 50*1024*1024:
        raise providers.StageError("audio", "Recording is missing or exceeds the 50 MB limit.")
    output = path.with_name(path.name+".wav")
    if output.exists():
        return output
    temporary = path.with_name(path.name+"."+uuid.uuid4().hex+".wav")
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-show_entries",
            "format=duration:stream=codec_type", "-of", "json", str(path)], capture_output=True, timeout=min(20, remaining(deadline)), check=True)
        metadata = json.loads(result.stdout)
        if not metadata["streams"] or any(s["codec_type"] != "audio" for s in metadata["streams"]):
            raise providers.StageError("audio", "Supply a complete audio recording no longer than 500 seconds.")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", str(path),
            "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-threads", "1", "-c:a", "pcm_s16le", "-fs", str(16000*2*502), "-f", "wav", str(temporary)],
            capture_output=True, timeout=remaining(deadline), check=True)
        # Browser WebM often has no duration header. Measure decoded PCM; capped excess is always rejected, never transcribed.
        with wave.open(str(temporary), "rb") as decoded:
            duration = decoded.getnframes()/decoded.getframerate()
        if not math.isfinite(duration) or not 0 < duration <= 500:
            raise providers.StageError("audio", "The decoded recording exceeds 500 seconds or contains no audio. Nothing was transcribed.")
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
        return output
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, wave.Error):
        raise providers.StageError("audio", "Audio could not be fully decoded or converted. Continue unassessed or retry the fixed recording.") from None
    finally:
        temporary.unlink(missing_ok=True)


def cleanup_attempt_audio(a):
    if not a.audio_name:
        return
    for path in [settings.AUDIO_DIR/a.audio_name, *settings.AUDIO_DIR.glob(a.audio_name+".*")]:
        path.unlink(missing_ok=True)


def cleanup_audio():
    now = timezone.now()
    for a in Attempt.objects.exclude(audio_name="").filter(state="assessed"):
        cleanup_attempt_audio(a)
    for a in Attempt.objects.exclude(audio_name="").filter(audio_expires_at__lte=now):
        cleanup_attempt_audio(a)
    # Interrupted file writes may never acquire a database row.
    for path in settings.AUDIO_DIR.iterdir():
        if path.is_file() and path.stat().st_mtime < time.time()-86400:
            path.unlink(missing_ok=True)


@transaction.atomic
def save_stage(attempt_id, claim, **fields):
    a = Attempt.objects.select_related("presentation").get(pk=attempt_id)
    if a.state != "processing" or a.claim != claim or a.deadline <= timezone.now():
        return False
    if not valid_presentation(a.presentation, a.submitted_at):
        a.state, a.claim = "closed_unassessed", uuid.uuid4()
        a.error = "A newer review or source change made this attempt stale. No score was added."
        a.save(update_fields=["state", "claim", "error"])
        defer(a.presentation)
        return False
    for key, value in fields.items():
        setattr(a, key, value)
    a.save(update_fields=list(fields))
    return True


@transaction.atomic
def fail(kind, job_id, claim, error):
    model = Attempt if kind == "assessment" else GenerationJob
    job = model.objects.get(pk=job_id)
    if job.claim != claim or job.state not in ["processing", "submitted", "queued"]:
        return
    job.state, job.error = "failed", str(error)[:300]
    job.error_category = getattr(error, "category", "worker")
    job.retryable = job.error_category not in {"configuration", "content"}
    fields = ["state", "error", "error_category", "retryable"]
    if kind == "assessment":
        job.error_stage = error.stage if isinstance(error, providers.StageError) else "worker"
        fields.append("error_stage")
    job.claim = uuid.uuid4()
    job.save(update_fields=fields+["claim"])


def process_assessment(job_id, claim):
    a = Attempt.objects.select_related("presentation").get(pk=job_id)
    if a.state != "processing" or a.claim != claim:
        return
    if not save_stage(a.pk, claim):
        return
    if not a.transcript:
        if a.audio_expires_at <= timezone.now():
            raise providers.StageError("audio", "The original recording has expired. Continue unassessed.")
        normalized = normalize(settings.AUDIO_DIR/a.audio_name, a.deadline)
        p = bounded_profile("ASR", a.deadline)
        if not save_stage(a.pk, claim, asr_provenance=p.metadata()):
            return
        transcript, provenance = providers.transcribe(normalized, a.presentation.snapshot["language"], p)
        if not save_stage(a.pk, claim, transcript=transcript, asr_provenance=provenance):
            return
        a.transcript = transcript
    p = bounded_profile("JUDGE", a.deadline)
    if not save_stage(a.pk, claim, judge_provenance=p.metadata()):
        return
    units, provenance = providers.assess(a.presentation.snapshot, a.transcript, p)
    if not save_stage(a.pk, claim, judge_provenance=provenance):
        return
    grade = grade_units(units, a.duration, a.presentation.budget)
    candidate = {}
    for index in range(3):
        remaining(a.deadline)
        try:
            result = commit_grade(a.pk, claim, grade, units, " ".join(u["reason"] for u in units), candidate)
            break
        except OperationalError as error:
            if "locked" not in str(error).lower() or index == 2:
                raise
            time.sleep(.05)
    if result.state == "assessed":
        cleanup_attempt_audio(result)


def current_generation(job, card):
    return (not card.archived and not card.deck.archived and card.source_version == job.source_version and
            (not card.ready if job.mode == "initial" else card.rotation_token == job.token))


@transaction.atomic
def save_pair(job_id, claim, data, provenance):
    job = GenerationJob.objects.select_related("card__deck").get(pk=job_id)
    if job.state == "done":
        return job.result
    if job.state != "processing" or job.claim != claim or job.deadline <= timezone.now() or not current_generation(job, job.card):
        return None
    pair = ExamplePair.objects.create(card=job.card, source_version=job.source_version, provenance=provenance, **data)
    if job.mode == "initial":
        Card.objects.filter(pk=job.card_id).update(active_pair=pair, ready=True)
    job.result, job.provenance, job.state = pair, provenance, "done"
    job.save(update_fields=["result", "provenance", "state"])
    return pair


@transaction.atomic
def save_corrected_pair(card_id, source_version, previous_pair_id, data, provenance):
    card = Card.objects.select_related("deck", "active_pair").get(pk=card_id)
    if (card.archived or card.deck.archived or not card.ready or
            card.source_version != source_version or card.active_pair_id != previous_pair_id):
        return None
    pair = ExamplePair.objects.create(card=card, source_version=source_version, **data,
        provenance={**provenance, "corrects_pair_id": previous_pair_id})
    card.active_pair, card.rotation_token = pair, None
    card.save(update_fields=["active_pair", "rotation_token"])
    card.generation_jobs.filter(mode="rotation", state__in=["queued", "processing", "failed"]).update(
        state="cancelled", claim=uuid.uuid4())
    adopt_corrected_cue(card)
    return pair


def process_generation(job_id, claim):
    job = GenerationJob.objects.select_related("card__deck").get(pk=job_id)
    if job.state != "processing" or job.claim != claim or not current_generation(job, job.card):
        return
    source = {key: getattr(job.card, key) for key in ["word", "explanation", "target_language", "native_language"]}
    if job.mode == "rotation" and job.card.active_pair_id:
        pair = job.card.active_pair
        source["previous_pair"] = {"target_sentence": pair.target_sentence, "native_sentence": pair.native_sentence}
    p = bounded_profile("GENERATOR", job.deadline)
    GenerationJob.objects.filter(pk=job_id, claim=claim, state="processing").update(provenance=p.metadata())
    result, provenance = providers.generate(source, p)
    save_pair(job_id, claim, result, provenance)


@transaction.atomic
def expire_generations():
    GenerationJob.objects.filter(state__in=["queued", "processing"], deadline__lte=timezone.now()).update(
        state="failed", error="Example preparation expired. Retry explicitly; your source is saved.", error_category="timeout", retryable=True)


@transaction.atomic
def retry_generation(job):
    expire_generations()
    job = GenerationJob.objects.select_related("card__deck").get(pk=job.pk)
    if job.state != "failed" or not current_generation(job, job.card):
        return job
    job.execution += 1
    job.state, job.claim, job.error = "queued", uuid.uuid4(), ""
    job.error_category, job.retryable = "", True
    job.requested_at = timezone.now()
    job.deadline = job.requested_at+timedelta(seconds=settings.GENERATION_TIMEOUT_SECONDS)
    job.save(update_fields=["execution", "state", "claim", "error", "error_category", "retryable", "requested_at", "deadline"])
    return job


@transaction.atomic
def claim_work():
    now = timezone.now()
    job = Attempt.objects.filter(state="submitted", deadline__gt=now).order_by("submitted_at").first()
    kind = "assessment"
    if not job:
        job = GenerationJob.objects.filter(state="queued", deadline__gt=now).order_by("requested_at").first()
        kind = "generation"
    if not job:
        return None
    job.state = "processing"
    job.save(update_fields=["state"])
    return kind, job.pk, job.claim, job.deadline
