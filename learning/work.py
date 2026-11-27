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
from django.db.models import F, Q
from django.db.models.functions import Now
from django.utils import timezone
from . import providers, lexical
from .models import Attempt, Card, ExampleIllustration, ExamplePair, GenerationJob, SpeechClip
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
def cleanup_speech():
    """Reclaim clips whose example revision has been without any reference for a full day.
    The grace starts when the last reference disappears and restarts if a reference returns;
    the clip's own age never retires it. Example Revision text and frozen review records stay
    untouched; current references are rechecked immediately before each retirement."""
    now = timezone.now()
    cutoff = now-timedelta(hours=24)
    for clip in SpeechClip.objects.select_related("pair").all():
        if speech_referenced(clip.pair):
            if clip.unreferenced_at is not None:
                SpeechClip.objects.filter(pk=clip.pk).update(unreferenced_at=None)
            continue
        if clip.unreferenced_at is None:
            SpeechClip.objects.filter(pk=clip.pk).update(unreferenced_at=now)  # grace begins
            continue
        if clip.unreferenced_at <= cutoff:  # still unreferenced a full day later
            if clip.file:
                (settings.TTS_DIR/clip.file).unlink(missing_ok=True)
            clip.delete()
    # Interrupted or stale executions may leave final files and writer partials that no clip
    # row references; the sweep stays inside the speech file namespace.
    known = set(SpeechClip.objects.exclude(file="").values_list("file", flat=True))
    for path in settings.TTS_DIR.glob("*.mp3*"):
        if path.is_file() and path.name not in known and path.stat().st_mtime < time.time()-86400:
            path.unlink(missing_ok=True)


def speech_referenced(pair):
    """Current references keep clips: the card's active pair, a pinned cue, and any completed
    rotation candidate carrying the current source and rotation token. Archived decks count too."""
    return (Card.objects.filter(Q(active_pair=pair) | Q(cue_pair=pair)).exists() or
            GenerationJob.objects.filter(mode="rotation", state="done", result=pair,
                token=F("card__rotation_token"), source_version=F("card__source_version")).exists())


def enqueue_speech(pair, *, backfill=False):
    """Queue both sentence sides in the caller's pair-save transaction; a rejected or rolled-back
    save therefore produces no speech tasks."""
    card = pair.card
    for side, language in [("target", card.target_language), ("native", card.native_language)]:
        SpeechClip.objects.get_or_create(pair=pair, side=side, defaults={"language": language, "backfill": backfill})


def available_speech(pair):
    return {clip.side: clip for clip in SpeechClip.objects.filter(pair=pair, state="done").exclude(file="")}


def expire_speech():
    SpeechClip.objects.filter(state="processing", deadline__lte=timezone.now()).update(
        state="failed", claim=uuid.uuid4(), error="Speech execution expired. Retry the side explicitly.",
        error_category="timeout")


@transaction.atomic
def claim_speech():
    """Atomic claim, mirroring claim_work: a competing connection that already selected the
    same queued row loses the conditional claim and gets nothing instead of a duplicate."""
    expire_speech()
    clip = SpeechClip.objects.filter(state="queued").order_by("backfill", "requested_at", "pk").first()
    if not clip:
        return None
    now = timezone.now()
    deadline = now+timedelta(seconds=settings.SPEECH_TIMEOUT_SECONDS)
    claim = uuid.uuid4()
    claimed = SpeechClip.objects.filter(pk=clip.pk, claim=clip.claim, state="queued").update(
        state="processing", claim=claim, started_at=now, deadline=deadline)
    return (clip.pk, claim, deadline) if claimed else None


def process_speech(clip_id, claim):
    clip = SpeechClip.objects.select_related("pair__card").get(pk=clip_id)
    if clip.state != "processing" or clip.claim != claim:
        return
    if not speech_referenced(clip.pair):
        clip.state, clip.claim, clip.error = "skipped", uuid.uuid4(), "The example is no longer referenced."
        clip.save(update_fields=["state", "claim", "error"])
        return
    text = getattr(clip.pair, {"target": "target_sentence", "native": "native_sentence"}[clip.side]).strip()
    p = bounded_profile("SPEECH", clip.deadline)
    voice = providers.speech_voice(clip.language)
    # Record model and voice at dispatch; each successful file keeps its synthesis provenance.
    if not SpeechClip.objects.filter(pk=clip_id, claim=claim, state="processing").update(
            provenance={**clip.provenance, "voice": voice, "language": clip.language, **p.metadata()}):
        return
    sound = providers.speech(replace(p, timeout=min(p.timeout, remaining(clip.deadline))), text, voice)
    publish_speech(clip_id, claim, sound)


def publish_speech(clip_id, claim, sound):
    """Claim-specific file names: a stale execution can never replace a newer clip's file.
    Finalization rechecks the claim, remaining budget, and current references in one short
    transaction; any failed guard reclaims the unpublished artifact instead of publishing it."""
    name = f"{clip_id}.{claim.hex}.mp3"
    path = settings.TTS_DIR/name
    temporary = path.with_name(path.name+".part")
    try:
        with open(temporary, "wb") as handle:
            handle.write(sound)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        # The renamed directory entry must be durable before the database records Done.
        directory = os.open(settings.TTS_DIR, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        raise providers.StageError("SPEECH", "The clip could not be stored. Retry the side explicitly.", "worker") from None
    finally:
        temporary.unlink(missing_ok=True)
    with transaction.atomic():
        clip = SpeechClip.objects.filter(pk=clip_id, claim=claim, state="processing").first()
        referenced = bool(clip and speech_referenced(clip.pair))
        if referenced:
            # The deadline and completion clock are evaluated inside the UPDATE statement, after
            # SQLite grants the writer lock: a lock wait that crosses the deadline can neither
            # record Done nor backdate completed_at (the save_stage/save_pair clock discipline).
            published = SpeechClip.objects.filter(pk=clip_id, claim=claim, state="processing",
                deadline__gt=Now()).update(
                state="done", file=name, completed_at=Now(), error="", error_category="")
        else:
            published = False
    if not published:
        path.unlink(missing_ok=True)  # stale, expired, or unreferenced: never publish the artifact


@transaction.atomic
def save_stage(attempt_id, claim, **fields):
    a = Attempt.objects.select_related("presentation").get(pk=attempt_id)
    now = timezone.now()
    # The budget invariant is shared with persistence: a processing result under a deadline beyond the
    # current budget (legacy/config-shrunk) is refused, not scored (R3c).
    if a.state != "processing" or a.claim != claim or a.deadline <= now \
            or a.deadline > now+timedelta(seconds=settings.ASSESSMENT_TIMEOUT_SECONDS):
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
    model = {"assessment": Attempt, "generation": GenerationJob, "speech": SpeechClip,
             "illustration": ExampleIllustration}[kind]
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
    elif kind == "generation":
        job.provenance = {**job.provenance, "failed_stage": getattr(error, "stage", "worker")}
        fields.append("provenance")
    if kind == "generation" and job.mode == "manual" and not current_generation(job, job.card):
        # An obsolete learner request is superseded, not retryable against a newer pair.
        job.state = "cancelled"
    job.claim = uuid.uuid4()
    job.save(update_fields=fields+["claim"])


def process_assessment(job_id, claim):
    a = Attempt.objects.select_related("presentation").get(pk=job_id)
    if a.state != "processing" or a.claim != claim:
        return
    if not save_stage(a.pk, claim):
        return
    # Every execution assesses the fixed recording; a saved transcript never replaces the audio.
    if a.audio_expires_at <= timezone.now() or not (settings.AUDIO_DIR / a.audio_name).is_file():
        raise providers.StageError("audio", "The original recording is missing or expired. Continue unassessed; a later review accepts a new recording.")
    normalized = normalize(settings.AUDIO_DIR/a.audio_name, a.deadline)
    p = bounded_profile("AUDIO_ASSESS", a.deadline)
    if not save_stage(a.pk, claim, judge_provenance=p.metadata()):
        return
    # The provenance transaction may wait on a writer lock and consume real window; re-bound the
    # already-selected profile against the absolute deadline before any inference is dispatched.
    p = replace(p, timeout=min(p.timeout, remaining(a.deadline)))
    units, provenance = providers.audio_assessment(a.presentation.snapshot, normalized, p)
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
    if job.mode == "manual":
        return (not card.archived and not card.deck.archived and card.source_version == job.source_version and
                card.active_pair_id == job.provenance.get("requested_pair_id"))
    return (not card.archived and not card.deck.archived and card.source_version == job.source_version and
            (not card.ready if job.mode == "initial" else card.rotation_token == job.token))


@transaction.atomic
def supersede_requests(card):
    # Another tab may have replaced the pair since the caller loaded this card.
    card = Card.objects.select_related("deck", "active_pair").get(pk=card.pk)
    card.generation_jobs.filter(mode="manual", state__in=["queued", "processing", "failed"]).exclude(
        provenance__requested_pair_id=card.active_pair_id).update(state="cancelled", claim=uuid.uuid4())
    return card


@transaction.atomic
def save_pair(job_id, claim, data, provenance):
    job = GenerationJob.objects.select_related("card__deck").get(pk=job_id)
    if job.state == "done":
        return job.result
    if job.state != "processing" or job.claim != claim or job.deadline <= timezone.now():
        return None
    if not current_generation(job, job.card):
        if job.mode == "manual":
            # A changed base pair or archived/source change supersedes the late learner request.
            job.state, job.claim = "cancelled", uuid.uuid4()
            job.save(update_fields=["state", "claim"])
        return None
    if job.mode == "initial" and not lexical.details(job.card)["explanation"].strip():
        return None
    if job.mode == "manual":
        # A learner request applies immediately; operator correction keeps cancelling rotation intent.
        pair = save_corrected_pair(job.card_id, job.source_version, job.provenance["requested_pair_id"],
                                   data, provenance, preserve_rotation=True)
    else:
        pair = ExamplePair.objects.create(card=job.card, source_version=job.source_version, provenance=provenance, **data)
        if job.mode == "initial":
            Card.objects.filter(pk=job.card_id).update(active_pair=pair, ready=True)
        enqueue_speech(pair)
        from .illustrations import enqueue_illustration
        enqueue_illustration(pair)
    if pair is None:
        return None
    job.result, job.provenance, job.state = pair, {**job.provenance, **provenance, "phase": "ready"}, "done"
    job.save(update_fields=["result", "provenance", "state"])
    return pair


@transaction.atomic
def save_corrected_pair(card_id, source_version, previous_pair_id, data, provenance, *, preserve_rotation=False):
    card = Card.objects.select_related("deck", "active_pair").get(pk=card_id)
    if (card.archived or card.deck.archived or not card.ready or
            card.source_version != source_version or card.active_pair_id != previous_pair_id):
        return None
    pair = ExamplePair.objects.create(card=card, source_version=source_version, **data,
        provenance={**provenance, "corrects_pair_id": previous_pair_id})
    if preserve_rotation:
        card.active_pair = pair
        card.save(update_fields=["active_pair"])
    else:
        card.active_pair, card.rotation_token = pair, None
        card.save(update_fields=["active_pair", "rotation_token"])
        card.generation_jobs.filter(mode="rotation", state__in=["queued", "processing", "failed"]).update(
            state="cancelled", claim=uuid.uuid4())
    adopt_corrected_cue(card)
    enqueue_speech(pair)
    from .illustrations import enqueue_illustration
    enqueue_illustration(pair)
    return pair


@transaction.atomic
def save_definition(job_id, claim, details, provenance):
    from .authoring import identity
    job = GenerationJob.objects.select_related("card__deck").get(pk=job_id)
    if (job.state != "processing" or job.claim != claim or job.deadline <= timezone.now() or
            job.mode != "initial" or not current_generation(job, job.card)):
        return False
    source = {key: getattr(job.card, key) for key in ["word", "target_language", "native_language"]}
    explanation = lexical.combine(job.card.explanation, provenance.get("fields", {}))
    key = identity("vocabulary", {**source, "explanation": explanation})
    if Card.objects.filter(deck=job.card.deck, identity=key).exclude(pk=job.card_id).exists():
        raise providers.StageError("DEFINITION", "The completed source already exists in this deck. Update this card's intended meaning.", "content")
    Card.objects.filter(pk=job.card_id).update(explanation=explanation, identity=key, **lexical.columns(details))
    job.provenance = {**job.provenance, "definition": provenance, "definition_completed": True,
                      "teaching_details": {"source": explanation, "details": details},
                      "definition_generated": "explanation" in provenance["requested_fields"], "phase": "examples"}
    job.save(update_fields=["provenance"])
    return True


def process_generation(job_id, claim):
    job = GenerationJob.objects.select_related("card__deck").get(pk=job_id)
    if job.state != "processing" or job.claim != claim:
        return
    if not current_generation(job, job.card):
        if job.mode == "manual":
            # A changed base pair or archived/source change supersedes the late learner request.
            job.state, job.claim = "cancelled", uuid.uuid4()
            job.save(update_fields=["state", "claim"])
        return
    if job.mode == "initial" and job.provenance.get("enrich_source") and not job.provenance.get("definition_completed"):
        source = lexical.source(job.card)
        p = bounded_profile("DEFINITION", job.deadline) if lexical.missing(lexical.details(job.card)) else None
        provenance = {**job.provenance, "phase": "definition"}
        if p:
            provenance["definition"] = p.metadata()
        if not GenerationJob.objects.filter(pk=job_id, claim=claim, state="processing", deadline__gt=timezone.now()).update(provenance=provenance):
            return
        details, provenance = providers.define(source, p)
        if not save_definition(job_id, claim, details, provenance):
            return
        job = GenerationJob.objects.select_related("card__deck").get(pk=job_id)
    source = lexical.source(job.card)
    if job.mode in ("rotation", "manual") and job.card.active_pair_id:
        pair = job.card.active_pair
        source["previous_pair"] = {"target_sentence": pair.target_sentence, "native_sentence": pair.native_sentence}
    p = bounded_profile("GENERATOR", job.deadline)
    reviewer = bounded_profile("EXAMPLE_REVIEWER", job.deadline)
    if not GenerationJob.objects.filter(pk=job_id, claim=claim, state="processing", deadline__gt=timezone.now()).update(
            provenance={**job.provenance, **p.metadata(), "example_reviewer": reviewer.metadata(), "phase": "examples"}):
        return
    result, provenance = providers.generate(source, p, reviewer=reviewer, budget_seconds=remaining(job.deadline))
    save_pair(job_id, claim, result, provenance)


@transaction.atomic
def expire_generations():
    # Obsolete learner requests are superseded before the generic expiry marks jobs retryable.
    for job in GenerationJob.objects.filter(state="processing", mode="manual", deadline__lte=timezone.now()).select_related("card"):
        if not current_generation(job, job.card):
            job.state, job.claim = "cancelled", uuid.uuid4()
            job.save(update_fields=["state", "claim"])
    GenerationJob.objects.filter(state="processing", deadline__lte=timezone.now()).update(
        state="failed", claim=uuid.uuid4(), error="Example preparation expired. Retry explicitly; your source is saved.", error_category="timeout", retryable=True)


@transaction.atomic
def retry_generation(job):
    expire_generations()
    job = GenerationJob.objects.select_related("card__deck").get(pk=job.pk)
    if job.state != "failed":
        return job
    if not current_generation(job, job.card):
        if job.mode == "manual":
            # A stale retry request gets a clear terminal status instead of a silent no-op.
            job.state, job.claim = "cancelled", uuid.uuid4()
            job.save(update_fields=["state", "claim"])
        return job
    job.execution += 1
    job.state, job.claim, job.error = "queued", uuid.uuid4(), ""
    job.error_category, job.retryable = "", True
    job.requested_at = timezone.now()
    job.started_at, job.deadline = None, None
    job.provenance = {key: value for key, value in job.provenance.items() if key in
                      {"enrich_source", "input_identity", "input_explanation", "definition", "definition_completed", "definition_generated", "teaching_details", "requested_pair_id"}}
    job.save(update_fields=["execution", "state", "claim", "error", "error_category", "retryable", "requested_at", "started_at", "deadline", "provenance"])
    return job


@transaction.atomic
def claim_work():
    from .review import expire_attempt
    now = timezone.now()
    job = Attempt.objects.filter(state="submitted", deadline__gt=now).order_by("submitted_at").first()
    kind = "assessment"
    if not job:
        job = GenerationJob.objects.filter(state="queued").order_by("requested_at", "pk").first()
        kind = "generation"
    if not job:
        return None
    if kind == "assessment" and job.deadline > now+timedelta(seconds=settings.ASSESSMENT_TIMEOUT_SECONDS):
        # Obsolete execution (legacy/config-shrunk): its Stop-anchored budget is unrecoverable,
        # so it is invalidated instead of claimed; only explicit Retry re-enters the queue.
        expire_attempt(job)
        return None
    job.state = "processing"
    fields = ["state"]
    if kind == "generation":
        job.started_at, job.deadline, job.claim = now, now+timedelta(seconds=settings.GENERATION_TIMEOUT_SECONDS), uuid.uuid4()
        fields += ["started_at", "deadline", "claim"]
    job.save(update_fields=fields)
    return kind, job.pk, job.claim, job.deadline
