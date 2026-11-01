import json
import math
import random
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Case, When, Value, IntegerField, CharField
from django.db.models.functions import Cast, Concat, MD5
from django.utils import timezone
from fsrs import Card as MemoryCard, Rating, Scheduler
from .authoring import new_generation
from .models import Card, Presentation, Attempt, ScoredReview, Deferral, GenerationJob
from .rendering import render, recall_budget, highlight

LABELS = {"A": "Needs a refresh", "B": "Needs practice", "C": "Partial recall", "D": "Correct recall", "E": "Quick recall"}
TERMINAL = {"assessed", "skipped", "closed_unassessed"}


def available(user, deck=None):
    cards = Card.objects.filter(deck__owner=user, archived=False, deck__archived=False, ready=True)
    return cards.filter(deck=deck) if deck else cards


def queue(run):
    """Prioritize due reviews, then shuffle unseen cards reproducibly within this run."""
    new_order = MD5(Concat(Value(f"{run.pk}:"), Cast("pk", output_field=CharField())))
    return available(run.user, run.deck).filter(due__lte=timezone.now()).exclude(
        pk__in=run.deferrals.values("card_id")).annotate(tier=Case(
            When(collection="Forgot", then=Value(0)), When(review_count__gt=0, then=Value(1)),
            default=Value(2), output_field=IntegerField())).order_by(
                "tier", Case(When(tier__lt=2, then="due")),
                Case(When(tier=2, then=new_order)), "pk")


def snapshot(card):
    base = {"kind": card.kind, "explanation": card.explanation, "source_version": card.source_version}
    if card.kind == "generic":
        q = render(card.question, card.answer, True)
        return {**base, "question_html": q.html, "question_text": q.text, "reference": card.answer,
                "units": q.blanks or 1, "reading_count": q.reading_count, "direction": "generic",
                "language": "", "goal": "Recall the authored reference expressions/content"}
    pair = card.cue_pair
    recognition = card.cue_direction == "recognition"
    sentence, expression = ((pair.target_sentence, pair.target_highlight) if recognition else (pair.native_sentence, pair.native_highlight))
    return {**base, "question_html": highlight(sentence, expression), "question_text": sentence,
            "reference": pair.gloss if recognition else card.word, "word": card.word,
            "units": 1, "reading_count": sum(not c.isspace() for c in sentence), "direction": card.cue_direction,
            "language": card.native_language if recognition else card.target_language,
            "goal": "Explain the complete highlighted meaning" if recognition else "Recall the authored target expression",
            "pair_id": pair.pk, "target_sentence": pair.target_sentence, "target_highlight": pair.target_highlight,
            "native_sentence": pair.native_sentence, "native_highlight": pair.native_highlight,
            "gloss": pair.gloss, "target_language": card.target_language, "native_language": card.native_language}


@transaction.atomic
def next_presentation(run):
    run.refresh_from_db()
    if run.finished:
        return None
    old = Presentation.objects.filter(run=run, invalidated=False).filter(attempt__isnull=True).order_by("created_at").first()
    if old:
        if valid_presentation(old):
            return old
        old.invalidated = True
        old.save(update_fields=["invalidated"])
    pending = Attempt.objects.filter(presentation__run=run, state__in=["submitted", "processing", "failed"]).first()
    if pending:
        return pending.presentation
    card = queue(run).first()
    if not card:
        run.finished = True
        run.save(update_fields=["finished"])
        return None
    if card.kind == "vocabulary":
        if card.cue_pair_id is None:
            candidate = card.generation_jobs.filter(mode="rotation", token=card.rotation_token, source_version=card.source_version,
                                                     state="done", result__isnull=False).first() if card.rotation_token else None
            if candidate:
                card.active_pair, card.rotation_token = candidate.result, None
            if not card.direction_block or card.direction_index >= 2:
                card.direction_block = random.sample(["recognition", "production"], 2)
                card.direction_index = 0
            card.cue_direction = card.direction_block[card.direction_index]
            card.cue_pair = card.active_pair
            card.save(update_fields=["active_pair", "rotation_token", "direction_block", "direction_index", "cue_direction", "cue_pair"])
    frozen = snapshot(card)
    return Presentation.objects.create(user=run.user, run=run, card=card, source_version=card.source_version,
        progress_version=card.progress_version, snapshot=frozen,
        budget=recall_budget(frozen["units"], frozen["reading_count"], frozen["reference"]))


def valid_presentation(p, anchor=None):
    card = Card.objects.select_related("deck").get(pk=p.card_id)
    return (not p.invalidated and not card.archived and not card.deck.archived and card.ready and
            card.deck.owner_id == p.user_id and card.source_version == p.source_version and
            card.progress_version == p.progress_version and card.due <= (anchor or timezone.now()) and
            (card.kind != "vocabulary" or (card.cue_pair_id == p.snapshot.get("pair_id") and card.cue_direction == p.snapshot["direction"])))


def defer(p):
    Deferral.objects.get_or_create(run=p.run, card=p.card)


@transaction.atomic
def restart(p):
    p = Presentation.objects.get(pk=p.pk)
    if Attempt.objects.filter(presentation=p).exists():
        return p
    p.invalidated = True
    p.save(update_fields=["invalidated"])
    if not valid_presentation_for_restart(p):
        return None
    return Presentation.objects.create(user=p.user, run=p.run, card=p.card, source_version=p.source_version,
        progress_version=p.progress_version, snapshot=p.snapshot, budget=p.budget)


def valid_presentation_for_restart(p):
    p.invalidated = False
    return valid_presentation(p)


@transaction.atomic
def submit(p, action, duration=None, audio_name=""):
    p = Presentation.objects.get(pk=p.pk)
    existing = Attempt.objects.filter(presentation=p).first()
    if existing:
        return existing
    now = timezone.now()
    a = Attempt.objects.create(presentation=p, action=action, state="submitted", submitted_at=now,
        duration=duration, audio_name=audio_name, audio_expires_at=now+timedelta(hours=24) if action == "speak" else None,
        deadline=now+timedelta(seconds=settings.ASSESSMENT_TIMEOUT_SECONDS) if action == "speak" else None)
    if not valid_presentation(p, now):
        a.state, a.error = "closed_unassessed", "This presentation is stale or no longer eligible. Your progress was preserved."
        defer(p)
    elif action == "skip":
        a.state = "skipped"
        defer(p)
    elif action == "forgot":
        return commit_grade(a.pk, a.claim, "A", [], "You chose Forgot.")
    elif duration is None or not math.isfinite(duration) or duration < 0:
        a.state, a.error_stage, a.error = "failed", "timing", "Timing was interrupted. Continue unassessed and restart this question in a new run."
    a.save()
    return a


@transaction.atomic
def commit_grade(attempt_id, claim, grade, outcomes, reason, candidate=None):
    a = Attempt.objects.select_related("presentation").get(pk=attempt_id)
    if a.state in TERMINAL or a.claim != claim or (a.deadline and a.deadline <= timezone.now()):
        return a
    p = a.presentation
    if not valid_presentation(p, a.submitted_at):
        a.state, a.error = "closed_unassessed", "A newer review or source change made this attempt stale. No score was added."
        a.save(update_fields=["state", "error"])
        defer(p)
        return a
    card = Card.objects.get(pk=p.card_id)
    candidate = {} if candidate is None else candidate
    if not candidate:
        memory = MemoryCard.from_dict(card.fsrs) if card.fsrs else MemoryCard(card_id=card.pk, due=card.due)
        updated, log = Scheduler().review_card(memory, {"A": Rating.Again, "B": Rating.Again, "C": Rating.Again,
                                                        "D": Rating.Good, "E": Rating.Easy}[grade], review_datetime=a.submitted_at)
        if grade in "AB" or card.collection == "Forgot":
            card.collection = "Forgot"
            card.streak = card.streak + 1 if grade in "DE" else 0
            if card.streak >= 3:
                card.collection = "Normal"
            else:
                updated.due = a.submitted_at + (timedelta(days=1) if grade in "DE" else timedelta(minutes=1))
        candidate.update(due=updated.due, fsrs=json.loads(updated.to_json()), log=json.loads(log.to_json()),
                         collection=card.collection, streak=card.streak)
    card.due, card.fsrs = candidate["due"], candidate["fsrs"]
    card.collection, card.streak = candidate["collection"], candidate["streak"]
    card.progress_version += 1
    card.review_count += 1
    if card.kind == "vocabulary":
        card.direction_index += 1
        card.cue_pair, card.cue_direction = None, ""
        card.generation_jobs.filter(mode="rotation", state__in=["queued", "processing", "failed", "done"]).update(state="cancelled")
        card.rotation_token = uuid.uuid4() if grade == "E" and card.collection == "Normal" else None
    card.save()
    if card.kind == "vocabulary" and card.rotation_token:
        new_generation(card, "rotation")
    a.grade, a.reason, a.outcomes, a.next_due, a.state = grade, reason, outcomes, card.due, "assessed"
    a.save(update_fields=["grade", "reason", "outcomes", "next_due", "state"])
    ScoredReview.objects.create(attempt=a, card=card, user=p.user, grade=grade, reviewed_at=a.submitted_at,
        next_due=card.due, snapshot=p.snapshot, fsrs_log=candidate["log"], duration=a.duration, budget=p.budget)
    return a


def grade_units(units, duration, budget):
    outcomes = {u["outcome"] for u in units}
    return "B" if "incorrect" in outcomes else "C" if "partial" in outcomes else "E" if duration <= budget else "D"


@transaction.atomic
def expire_attempt(a):
    a = Attempt.objects.get(pk=a.pk)
    if a.state in ("submitted", "processing") and a.deadline <= timezone.now():
        a.state, a.claim, a.error_stage, a.error = "failed", uuid.uuid4(), "timeout", "Processing expired. Retry this fixed input or continue unassessed."
        a.error_category, a.retryable = "timeout", True
        a.save(update_fields=["state", "claim", "error_stage", "error", "error_category", "retryable"])
    return a


@transaction.atomic
def exit_attempt(a):
    a = Attempt.objects.select_related("presentation").get(pk=a.pk)
    if a.state in TERMINAL:
        return a
    a.state, a.claim = "closed_unassessed", uuid.uuid4()
    a.save(update_fields=["state", "claim"])
    defer(a.presentation)
    return a


@transaction.atomic
def exit_presentation(p):
    a = Attempt.objects.filter(presentation=p).first()
    if a:
        return exit_attempt(a)
    # Close the front action even when an interrupted upload has not committed yet.
    a = Attempt.objects.create(presentation=p, action="speak", state="closed_unassessed",
        error="The interrupted submission was closed without a score.")
    defer(p)
    return a


@transaction.atomic
def retry_attempt(a):
    a = expire_attempt(a)
    if a.state in TERMINAL or a.state not in ["failed"]:
        return a
    if not valid_presentation(a.presentation, a.submitted_at):
        return exit_attempt(a)
    if a.duration is None or a.error_stage == "timing":
        return a
    if not a.transcript and (not a.audio_name or a.audio_expires_at <= timezone.now() or not (settings.AUDIO_DIR/a.audio_name).is_file()):
        a.error = "This recording is missing or expired. Continue unassessed; a later review accepts a new recording."
        a.save(update_fields=["error"])
        return a
    a.state, a.claim = "submitted", uuid.uuid4()
    a.execution += 1
    a.error, a.error_stage = "", ""
    a.error_category, a.retryable = "", True
    a.deadline = timezone.now()+timedelta(seconds=settings.ASSESSMENT_TIMEOUT_SECONDS)
    a.save(update_fields=["state", "claim", "execution", "error", "error_stage", "error_category", "retryable", "deadline"])
    return a


def relative_due(due):
    seconds = (due-timezone.now()).total_seconds()
    if seconds <= 0:
        return "Due now"
    for unit, length in [("month", 30*86400), ("day", 86400), ("hour", 3600), ("min", 60)]:
        if seconds >= length:
            count = max(1, round(seconds/length))
            return f"~{count} {unit}" + ("s" if count != 1 and unit != "min" else "")
    return "~1 min"
