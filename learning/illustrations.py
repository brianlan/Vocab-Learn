"""One shared illustration per Example Pair revision, captioned before rendering."""
import hashlib
import os
import time
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models.functions import Now
from django.utils import timezone

from . import providers
from .models import ExampleIllustration
from .work import speech_referenced

PROMPT_VERSION = "illustration-v2"
CAPTION_INSTRUCTION = """Write one English scene caption for a single illustration of the supplied bilingual example pair. Use both sentences and the target expression to choose the meaning the illustration should convey.

Choose the instant at which a viewer can most clearly see evidence of that meaning. Start with what is visible in the frame and describe the main physical cue in plain present tense. Make that cue large and clear enough to recognize in a small illustration.

Find the specific behavior, changed condition, or omission that makes the target expression evident in the sentences. Make its visible evidence the focus of the frame. If another event happened earlier, show it only through a passive trace in the surroundings. For an activity that has stopped, show recognizable signs of disuse prominently alongside the subject's current behavior.

If the meaning involves a change or difference in intensity, describe the visible state at the chosen instant. Let earlier conditions be inferred from physical traces. If people interact, give the initiator and recipient distinct positions and describe their visible gestures, posture, gaze, or expressions so their roles are clear.

Preserve the important people, objects, setting, and time implied by the pair. Include people only when the pair implies their presence. Use the surroundings, lighting, and visible behavior to convey time and secondary context. Add an object only when it helps show the main action or state. Keep visible surfaces unlettered.

Return only the visible scene caption in 2–4 sentences."""
STYLE_SUFFIX = ("Soft gouache on warm ivory paper, matte colors, soft edges and a light brush texture. "
                "A wordless scene with plain, unlettered surfaces.")


def illustration_enabled():
    """An empty endpoint disables queueing and dispatch; saves and playback stay unaffected."""
    return bool(os.getenv("ILLUSTRATION_ENDPOINT", "").strip())


def caption_payload(pair):
    card = pair.card
    return {"target_expression": card.word,
            f"{card.target_language.lower()}_sentence": pair.target_sentence,
            f"{card.native_language.lower()}_sentence": pair.native_sentence}


def revision_seed(pair):
    """Keep the renderer seed stable across executions of the same revision."""
    return int.from_bytes(hashlib.sha256(f"illustration:{pair.pk}".encode()).digest()[:4], "big")


def enqueue_illustration(pair, *, backfill=False):
    """Queue the pair's single illustration in the caller's pair-save transaction; a rejected or
    rolled-back save therefore produces no illustration work. Disabled configuration queues none."""
    if illustration_enabled():
        ExampleIllustration.objects.get_or_create(pair=pair, defaults={"backfill": backfill})


def ready_illustration(pair_id):
    """The ready row of one pair by id, so frozen Practice snapshots can resolve their image."""
    row = ExampleIllustration.objects.filter(pair_id=pair_id, state="done").exclude(file="").first()
    if row and (settings.ILLUSTRATIONS_DIR/row.file).is_file():
        return row
    return None


def expire_illustration():
    ExampleIllustration.objects.filter(state="processing", deadline__lte=timezone.now()).update(
        state="failed", claim=uuid.uuid4(), error="Illustration execution expired. Retry explicitly.",
        error_category="timeout")


@transaction.atomic
def claim_illustration():
    """Atomic claim mirroring claim_speech; new revisions are served before queued backfill. A
    disabled endpoint never dispatches: queued work is preserved intact for re-enabling."""
    expire_illustration()
    if not illustration_enabled():
        return None
    row = ExampleIllustration.objects.filter(state="queued").order_by("backfill", "requested_at", "pk").first()
    if not row:
        return None
    now = timezone.now()
    deadline = now+timedelta(seconds=settings.ILLUSTRATION_TIMEOUT_SECONDS)
    claim = uuid.uuid4()
    claimed = ExampleIllustration.objects.filter(pk=row.pk, claim=row.claim, state="queued").update(
        state="processing", claim=claim, started_at=now, deadline=deadline)
    return (row.pk, claim, deadline) if claimed else None


def _skip_unreferenced(active, pair):
    if speech_referenced(pair):
        return False
    active.update(state="skipped", claim=uuid.uuid4(), error="The example is no longer referenced.")
    return True


def process_illustration(row_id, claim):
    active = ExampleIllustration.objects.filter(pk=row_id, claim=claim, state="processing")
    row = active.select_related("pair__card").first()
    if row is None or _skip_unreferenced(active, row.pair):
        return
    renderer = providers.illustration_profile()
    writer = providers.profile("ILLUSTRATION_CAPTION")
    seed = revision_seed(row.pair)
    # Record model, seed and prompt version at dispatch; each successful file keeps its provenance.
    if not active.update(provenance={"task": renderer.task, "endpoint": renderer.endpoint,
            "model": renderer.model, "timeout": renderer.timeout, "caption_model": writer.model,
            "prompt_version": PROMPT_VERSION, "seed": seed}):
        return
    caption = providers.illustration_caption(
        providers.replace(writer, timeout=min(writer.timeout, remaining(row.deadline))),
        CAPTION_INSTRUCTION, caption_payload(row.pair))
    if _skip_unreferenced(active, row.pair) or not active.exists():
        return
    image, checkpoint = providers.render_illustration(
        providers.replace(renderer, timeout=min(renderer.timeout, remaining(row.deadline))),
        f"{caption} {STYLE_SUFFIX}", seed)
    providers.decode_webp(image, min(20, remaining(row.deadline)))
    publish_illustration(row_id, claim, image, checkpoint)


def remaining(deadline):
    seconds = (deadline-timezone.now()).total_seconds()
    if seconds <= 0:
        raise providers.StageError("ILLUSTRATION", "This execution expired. Retry explicitly.", "timeout")
    return seconds


def publish_illustration(row_id, claim, image, checkpoint):
    """Claim-specific file name and atomic publication; finalization rechecks the claim, remaining
    budget and current references in one short transaction before recording Done."""
    name = f"{row_id}.{claim.hex}.webp"
    path = settings.ILLUSTRATIONS_DIR/name
    temporary = path.with_name(path.name+".part")
    try:
        with open(temporary, "wb") as handle:
            handle.write(image)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory = os.open(settings.ILLUSTRATIONS_DIR, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        raise providers.StageError("ILLUSTRATION", "The image could not be stored. Retry explicitly.", "worker") from None
    finally:
        temporary.unlink(missing_ok=True)
    with transaction.atomic():
        row = ExampleIllustration.objects.filter(pk=row_id, claim=claim, state="processing").first()
        referenced = bool(row and speech_referenced(row.pair))
        if referenced:
            # The completion clock is evaluated inside the UPDATE, after SQLite grants the writer
            # lock: a lock wait that crosses the deadline can neither record Done nor backdate.
            published = ExampleIllustration.objects.filter(pk=row_id, claim=claim, state="processing",
                deadline__gt=Now()).update(
                state="done", file=name, completed_at=Now(),
                provenance={**row.provenance, "checkpoint": checkpoint}, error="", error_category="")
        else:
            published = False
    if not published:
        path.unlink(missing_ok=True)  # stale, expired, or unreferenced: never publish the artifact


@transaction.atomic
def cleanup_illustrations():
    """Reclaim images whose revision lost its last reference for a full day, using the shared
    speech reference rules; a returning reference resets the grace. Revision text and frozen
    history stay untouched."""
    now = timezone.now()
    cutoff = now-timedelta(hours=24)
    for row in ExampleIllustration.objects.select_related("pair").all():
        if speech_referenced(row.pair):
            if row.unreferenced_at is not None:
                ExampleIllustration.objects.filter(pk=row.pk).update(unreferenced_at=None)
            continue
        if row.unreferenced_at is None:
            ExampleIllustration.objects.filter(pk=row.pk).update(unreferenced_at=now)  # grace begins
            continue
        if row.unreferenced_at <= cutoff:  # still unreferenced a full day later
            if row.file:
                (settings.ILLUSTRATIONS_DIR/row.file).unlink(missing_ok=True)
            row.delete()
    # Interrupted writer partials and unreferenced final files never linger in the namespace.
    known = set(ExampleIllustration.objects.exclude(file="").values_list("file", flat=True))
    for path in settings.ILLUSTRATIONS_DIR.glob("*.webp*"):
        if path.is_file() and path.name not in known and path.stat().st_mtime < time.time()-86400:
            path.unlink(missing_ok=True)
