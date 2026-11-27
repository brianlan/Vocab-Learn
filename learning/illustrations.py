"""One shared illustration per Example Pair revision, rendered by the private FLUX.3 renderer."""
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

PROMPT_VERSION = "illustration-v1"
# The agreed soft gouache style: the complete scene of one validated sentence, never any lettering.
STYLE = ("Soft gouache storybook illustration of the complete scene described by this sentence, with "
         "gentle textures, muted colors and warm light. Depict every participant, action and setting "
         "detail the sentence describes. Use no text, letters, numbers, captions or borders anywhere.")


def illustration_enabled():
    """An empty endpoint disables queueing and dispatch; saves and playback stay unaffected."""
    return bool(os.getenv("ILLUSTRATION_ENDPOINT", "").strip())


def scene_sentence(pair):
    """English when present, otherwise the Spanish sentence of Spanish–Chinese pairs."""
    card = pair.card
    if card.target_language == "English":
        return pair.target_sentence, "English"
    if card.native_language == "English":
        return pair.native_sentence, "English"
    return pair.target_sentence, card.target_language


def illustration_prompt(pair):
    sentence, language = scene_sentence(pair)
    return f"{STYLE}\n\nScene sentence ({language}): {sentence.strip()}"


def revision_seed(pair):
    """A stable seed per revision: every execution of the same pair renders the same scene."""
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


def process_illustration(row_id, claim):
    row = ExampleIllustration.objects.select_related("pair__card").get(pk=row_id)
    if row.state != "processing" or row.claim != claim:
        return
    if not speech_referenced(row.pair):
        row.state, row.claim, row.error = "skipped", uuid.uuid4(), "The example is no longer referenced."
        row.save(update_fields=["state", "claim", "error"])
        return
    p = providers.illustration_profile()
    prompt, seed = illustration_prompt(row.pair), revision_seed(row.pair)
    # Record model, seed and prompt version at dispatch; each successful file keeps its provenance.
    if not ExampleIllustration.objects.filter(pk=row_id, claim=claim, state="processing").update(
            provenance={"task": p.task, "endpoint": p.endpoint, "model": p.model, "timeout": p.timeout,
                        "prompt_version": PROMPT_VERSION, "seed": seed}):
        return
    image, checkpoint = providers.render_illustration(
        providers.replace(p, timeout=min(p.timeout, remaining(row.deadline))), prompt, seed)
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
