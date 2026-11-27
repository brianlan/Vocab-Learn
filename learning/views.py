import json
import math
import os
import time
import uuid
from collections import Counter
from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.http import JsonResponse, Http404, FileResponse
from django.shortcuts import get_object_or_404, redirect, render as page
from django.template.loader import render_to_string
from django.utils import timezone
from django.urls import reverse
from urllib.parse import urlencode
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from . import authoring, illustrations, lexical, review, work
from .forms import DeckForm, CardForm, ImportForm, LearnerPreferencesForm
from .models import Deck, Card, ExamplePair, Presentation, Attempt, ScoredReview, GenerationJob, LearnerPreferences, SpeechClip
from .rendering import render


@login_required
@require_http_methods(["GET", "POST"])
def personal_settings(request):
    preferences = LearnerPreferences.objects.filter(user=request.user).first() or LearnerPreferences(user=request.user)
    form = LearnerPreferencesForm(request.POST if request.method == "POST" else None, initial={
        "selection_add_enabled": preferences.selection_add_enabled,
        "autoplay_enabled": preferences.autoplay_enabled,
        "language_pair": f"{preferences.target_language}:{preferences.native_language}",
    })
    if request.method == "POST" and form.is_valid():
        target_language, native_language = form.cleaned_data["language_pair"].split(":")
        LearnerPreferences.objects.update_or_create(user=request.user, defaults={
            "selection_add_enabled": form.cleaned_data["selection_add_enabled"],
            "autoplay_enabled": form.cleaned_data["autoplay_enabled"],
            "target_language": target_language, "native_language": native_language,
        })
        messages.success(request, "Settings saved.")
        return redirect("settings")
    return page(request, "learning/settings.html", {"form": form, "nav": "settings"})


def selection_create(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse({"error": "Sign in to add selected expressions."}, status=401)
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed."}, status=405, headers={"Allow": "POST"})
    if LearnerPreferences.objects.filter(user=request.user, selection_add_enabled=False).exists():
        return JsonResponse({"error": "Selection add is disabled in Settings.", "code": "disabled"}, status=403)
    if request.content_type != "application/json":
        return JsonResponse({"error": "Use application/json."}, status=415)
    limit = 8 * 1024
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
        if length < 0:
            raise ValueError
    except (TypeError, ValueError):
        return JsonResponse({"error": "Supply a valid Content-Length."}, status=400)
    try:
        if length > limit:
            raise RequestDataTooBig
        body = request.read(limit + 1)
        if len(body) > limit:
            raise RequestDataTooBig
    except RequestDataTooBig:
        return JsonResponse({"error": "A selection request is limited to 8 KiB."}, status=413)
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return JsonResponse({"error": "Supply a valid UTF-8 JSON object."}, status=400)
    if not isinstance(data, dict) or set(data) != {"deck_id", "text", "target_language", "native_language"}:
        return JsonResponse({"error": "Supply only deck_id, text, target_language and native_language."}, status=400)
    deck_id = data["deck_id"]
    if type(deck_id) is not int or not 0 < deck_id <= 2**63 - 1:
        return JsonResponse({"error": "Private active deck not found.", "code": "invalid_deck"}, status=404)
    try:
        if not isinstance(data["text"], str):
            raise ValidationError("Selected text must contain text.")
        text = " ".join(data["text"].split())
        if len(text) > 500:
            raise ValidationError("Select an expression of at most 500 characters.")
        source = authoring.validate_source("vocabulary", {"word": text, "explanation": "",
            "target_language": data["target_language"], "native_language": data["native_language"]})
        with transaction.atomic():
            deck = Deck.objects.filter(pk=deck_id, owner=request.user, archived=False).first()
            if not deck:
                return JsonResponse({"error": "Private active deck not found.", "code": "invalid_deck"}, status=404)
            card, created = authoring.create_card(deck, "vocabulary", source)
    except ValidationError as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=400)
    return JsonResponse({"created": created, "card_url": reverse("card", args=[card.pk]), "archived": card.archived},
                        status=201 if created else 200)


def deck_progress(user, decks):
    """Cumulative current-source D/E qualification per deck, from one read-only query."""
    decks = list(decks)
    if not decks:
        return {}
    # The inner owner join gives SQLite a card-selective history plan without a new index.
    qualifying = ScoredReview.objects.filter(user=user, card=OuterRef("pk"), card__deck__owner=user,
                                             grade__in=["D", "E"], snapshot__source_version=OuterRef("source_version"))
    cards = Card.objects.filter(deck__in=decks, deck__owner=user, archived=False).annotate(_qualified=Exists(qualifying))
    rows = {row["deck_id"]: row for row in cards.values("deck_id")
            .annotate(n=Count("pk"), done=Count("pk", filter=Q(_qualified=True)))}
    progress = {}
    for deck in decks:
        row = rows.get(deck.pk, {"n": 0, "done": 0})
        progress[deck.pk] = {"total": row["n"], "qualified": row["done"],
                             "percent": 100 * row["done"] // row["n"] if row["n"] else None}
    return progress


def counts(user, deck=None):
    cards = review.available(user, deck)
    reviews = ScoredReview.objects.filter(user=user)
    if deck:
        reviews = reviews.filter(card__deck=deck)
    today = reviews.filter(reviewed_at__date=timezone.localdate())
    total = today.count()
    complete = today.filter(grade__in=["D", "E"]).count()
    return {"due_count": review.queue(user, deck).count(), "forgot_count": cards.filter(collection="Forgot").count(),
            "cards_today": today.values("card").distinct().count(), "reviews_today": total,
            "accuracy": round(100*complete/total) if total else None}


@login_required
def dashboard(request):
    work.expire_generations()
    return page(request, "learning/dashboard.html", {**counts(request.user),
        "decks": Deck.objects.filter(owner=request.user, archived=False).order_by("name"),
        "practice_deck_id": Presentation.objects.filter(user=request.user).order_by("-created_at").values_list("scope_deck_id",flat=True).first(),
        "upcoming": review.available(request.user).order_by("_available_at", "pk")[:5], "nav": "study"})


@login_required
def library(request):
    archived = request.GET.get("archived") == "1"
    decks = list(Deck.objects.filter(owner=request.user, archived=archived).order_by("name"))
    form = DeckForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        deck = form.save(commit=False)
        deck.owner = request.user
        deck.save()
        return redirect("deck", deck.pk)
    progress = deck_progress(request.user, decks)
    return page(request, "learning/library.html", {"tiles": [{"deck": deck, "progress": progress[deck.pk]} for deck in decks],
        "form": form, "archived": archived, "nav": "decks"})


@login_required
def deck_view(request, deck_id):
    deck = get_object_or_404(Deck, pk=deck_id, owner=request.user)
    work.expire_generations()
    archived = request.GET.get("archived") == "1"
    cards = deck.cards.filter(archived=archived).select_related("active_pair").order_by("-created_at")
    if request.GET.get("q"):
        term = request.GET["q"]
        cards = cards.filter(Q(question__icontains=term)|Q(word__icontains=term)|Q(explanation__icontains=term))
    return page(request, "learning/deck.html", {"deck": deck, "page": Paginator(cards, 30).get_page(request.GET.get("page")),
        "archived": archived, "nav": "decks", **counts(request.user, deck)})


@login_required
def deck_edit(request, deck_id):
    deck = get_object_or_404(Deck, pk=deck_id, owner=request.user)
    form = DeckForm(request.POST or None, instance=deck)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("deck", deck.pk)
    return page(request, "learning/form.html", {"form": form, "title": "Edit deck", "nav": "decks"})


@login_required
@require_POST
def deck_archive(request, deck_id):
    deck = get_object_or_404(Deck, pk=deck_id, owner=request.user)
    authoring.archive_deck(deck, not deck.archived)
    if not deck.archived:
        restore_preparation(deck.cards.filter(archived=False))
    return redirect("library")


def restore_preparation(cards):
    with transaction.atomic():
        for card in cards.filter(kind="vocabulary", ready=False):
            if not card.generation_jobs.filter(source_version=card.source_version, state__in=["queued", "processing"]).exists():
                authoring.new_generation(card)


@login_required
def card_edit(request, deck_id, card_id=None):
    deck = get_object_or_404(Deck, pk=deck_id, owner=request.user)
    card = get_object_or_404(Card, pk=card_id, deck=deck) if card_id else None
    kind = card.kind if card else request.GET.get("kind", "generic")
    if kind not in authoring.SCHEMAS:
        return JsonResponse({"error": "Unknown card type."}, status=400)
    initial = {k: getattr(card, k) for k in authoring.SCHEMAS[kind]} if card else {}
    form = CardForm(request.POST or None, initial=initial, kind=kind, source_identity=card.identity if card else None)
    if request.method == "POST" and form.is_valid():
        try:
            if deck.archived or (card and card.archived):
                raise ValidationError("Restore the deck/card before editing its source.")
            if card is None and kind == "vocabulary":
                saved, created = authoring.create_card(deck, kind, form.cleaned_data)
            else:
                saved, created = authoring.save_card(deck, kind, form.cleaned_data, card,
                    expected_identity=form.cleaned_data.get("source_identity")), True
            messages.success(request, "This card already exists in this deck. Its content and progress were kept." if not created else
                             "Card saved." if saved.ready else "Source saved. Vocabulary details and examples are preparing; you can leave this page.")
            return redirect("card", saved.pk)
        except ValidationError as e:
            form.add_error(None, e)
    return page(request, "learning/form.html", {"form": form, "title": ("Edit " if card else "New ")+kind+" card",
        "editing": bool(card), "kind": kind, "deck": deck, "nav": "decks"})


@login_required
def card_view(request, card_id):
    card = get_object_or_404(Card.objects.select_related("deck", "active_pair"), pk=card_id, deck__owner=request.user)
    work.expire_generations()
    card = work.supersede_requests(card)
    job = card.generation_jobs.filter(source_version=card.source_version).exclude(mode="manual").order_by("-requested_at").first()
    # Select the learner-requested status explicitly so a newer automatic job cannot hide it.
    manual = (card.generation_jobs.filter(mode="manual", source_version=card.source_version,
              provenance__requested_pair_id=card.active_pair_id).order_by("-requested_at").first()
              if card.active_pair_id else None)
    # Keep relevant superseded information as a fallback when no request matches the current pair.
    superseded = None if manual else card.generation_jobs.filter(
        mode="manual", source_version=card.source_version, state="cancelled").order_by("-requested_at").first()
    teaching = lexical.details(card) if card.kind == "vocabulary" else {"explanation": card.explanation}
    return page(request, "learning/card.html", {"card": card, "job": job, "manual": manual, "superseded": superseded, "nav": "decks",
        "card_illustration": illustration_url(card.active_pair_id) if card.active_pair_id else None,
        "definition_generated": card.kind == "vocabulary" and authoring.definition_generated(card),
        "question_html": render(card.question, card.answer, True).html,
        "teaching": teaching, "explanation_html": render(teaching["explanation"]).html})


@login_required
@require_POST
def example_regenerate(request, card_id):
    card = get_object_or_404(Card, pk=card_id, deck__owner=request.user)
    try:
        expected_pair_id = int(request.POST.get("pair_id", ""))
        authoring.request_example_regeneration(card, expected_source_version=int(request.POST.get("source_version", "")),
                                               expected_pair_id=expected_pair_id)
    except (ValueError, ValidationError) as e:
        messages.error(request, e.messages[0] if isinstance(e, ValidationError) else
                       "This page is out of date. Reload to see the current examples.")
        return redirect("card", card.pk)
    messages.success(request, "A new example pair is being prepared. Your current examples and progress stay unchanged.")
    return redirect("card", card.pk)


@login_required
@require_POST
def card_archive(request, card_id):
    card = get_object_or_404(Card, pk=card_id, deck__owner=request.user)
    authoring.archive_card(card, not card.archived)
    if card.archived and not card.deck.archived:
        restore_preparation(Card.objects.filter(pk=card.pk))
    return redirect("deck", card.deck_id)


@login_required
def csv_import(request, deck_id):
    deck = get_object_or_404(Deck, pk=deck_id, owner=request.user)
    form = ImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            if deck.archived:
                raise ValidationError("Restore this deck before importing.")
            upload = form.cleaned_data["file"]
            if upload.size > 5*1024*1024:
                raise ValidationError("CSV imports are limited to 5 MB.")
            created, skipped = authoring.import_csv(deck, form.cleaned_data["kind"], upload.read())
            messages.success(request, f"{created} sources created; {skipped} duplicates skipped. Vocabulary details and examples prepare separately.")
            return redirect("deck", deck.pk)
        except ValidationError as e:
            form.add_error(None, e)
    return page(request, "learning/import.html", {"form": form, "deck": deck, "nav": "decks"})


@login_required
@require_POST
def generation_retry(request, job_id):
    job = get_object_or_404(GenerationJob, pk=job_id, card__deck__owner=request.user)
    work.retry_generation(job)
    return redirect("card", job.card_id)


def practice_url(deck_id=None):
    return reverse("practice")+("?"+urlencode({"deck": deck_id}) if deck_id else "")


@login_required
@require_GET
def practice(request):
    deck_id = request.GET.get("deck")
    try:
        deck = get_object_or_404(Deck, pk=int(deck_id), owner=request.user, archived=False) if deck_id else None
    except (ValueError, OverflowError):
        raise Http404("Choose an available private deck.") from None
    p = review.next_question(request.user, deck)
    if p:
        return redirect("presentation", p.pk)
    next_card = review.available(request.user, deck).order_by("_available_at", "pk").first()
    return page(request, "learning/practice_empty.html", {"deck": deck, "practice_url": practice_url(deck_id),
        "next_review": review.relative_due(next_card.available_at) if next_card else None,
        **counts(request.user, deck), "nav": "study"})


@login_required
def legacy_practice(request, legacy_id=None):
    # Old bookmarks/forms have no remaining run state; preserve a submitted deck choice.
    if request.method == "POST":
        return redirect(practice_url(request.POST.get("deck")))
    messages.info(request, "Practice is now continuous. Choose a deck to continue learning.")
    return redirect("dashboard")


def practice_audio(request, p, attempt):
    """Playable clip URLs for the current reveal state; empty means no controls.
    Before a committed action only the front-visible sentence is offered, so a guessed
    URL or a re-rendered template can never surface the hidden counterpart."""
    pair_id = p.snapshot.get("pair_id")
    if p.snapshot.get("kind") != "vocabulary" or not pair_id:
        return {}
    ready = {clip.side for clip in SpeechClip.objects.filter(pair_id=pair_id, state="done").exclude(file="")
             if (settings.TTS_DIR/clip.file).is_file()}
    if attempt is None:
        ready &= {"target" if p.snapshot.get("direction") == "recognition" else "native"}
    return {side: {"side": side, "url": reverse("clip_audio", args=[p.pk, side])}
            for side in ("target", "native") if side in ready}


@login_required
@require_GET
def clip_audio(request, presentation_id, side):
    p = get_object_or_404(Presentation.objects.select_related("card__deck"), pk=presentation_id, user=request.user)
    visible = "target" if p.snapshot.get("direction") == "recognition" else "native"
    attempt = Attempt.objects.filter(presentation=p).first()
    if attempt is None and (side != visible or not review.valid_presentation(p)):
        raise Http404("This clip is not available.")
    if side not in ("target", "native"):
        raise Http404("This clip is not available.")
    clip = (SpeechClip.objects.filter(pair_id=p.snapshot.get("pair_id"), side=side, state="done")
            .exclude(file="").first()) if p.snapshot.get("kind") == "vocabulary" else None
    if not clip:
        raise Http404("This clip is not available.")
    try:
        audio = (settings.TTS_DIR/clip.file).open("rb")
    except FileNotFoundError:
        raise Http404("This clip is not available.") from None
    response = FileResponse(audio, content_type="audio/mpeg")
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_GET
def illustration_image(request, pair_id):
    """The ready illustration of one example pair, reachable only by the pair's deck owner."""
    pair = get_object_or_404(ExamplePair.objects.select_related("card__deck"), pk=pair_id,
                             card__deck__owner=request.user)
    row = illustrations.available_illustration(pair)
    if not row:
        raise Http404("This illustration is not available.")
    try:
        image = (settings.ILLUSTRATIONS_DIR/row.file).open("rb")
    except FileNotFoundError:
        raise Http404("This illustration is not available.") from None
    response = FileResponse(image, content_type="image/webp")
    response["Cache-Control"] = "private, no-store"
    return response


def practice_illustration(p):
    """The frozen pair's ready-image URL for Practice; None renders no disclosure anywhere.
    One shared image serves both sides, so it never exposes a hidden sentence by itself."""
    pair_id = p.snapshot.get("pair_id")
    if p.snapshot.get("kind") != "vocabulary" or not pair_id:
        return None
    return illustration_url(pair_id)


def illustration_url(pair_id):
    return reverse("illustration_image", args=[pair_id]) if illustrations.ready_illustration(pair_id) else None


def render_back(request, a, audio, illustration):
    p = a.presentation
    card = Card.objects.get(pk=p.card_id)
    return render_to_string("learning/back.html", {"attempt": a, "p": p, "back": p.snapshot,
        "explanation_html": render(p.snapshot["explanation"]).html, "label": review.LABELS.get(a.grade),
        "next_review": review.relative_due(a.next_due or card.available_at) if a.state != "processing" and a.state != "submitted" else "After checking",
        "practice_url": practice_url(p.scope_deck_id), "audio": audio, "illustration": illustration,
        "terminal": a.state in review.TERMINAL,
        "can_retry": a.state == "failed" and a.duration is not None and a.error_stage != "timing"}, request=request)


def payload(request, a, *, fresh_page=False):
    p = a.presentation
    a = review.expire_attempt(a)
    a.presentation = p
    card = Card.objects.get(pk=p.card_id)
    # A fresh page of a finished review is history: no playback or illustration controls.
    history = fresh_page and a.state in review.TERMINAL
    return {"state": a.state, "transcript": a.transcript, "grade": a.grade, "next_due": a.next_due.isoformat() if a.next_due else None,
        "deadline": a.deadline.isoformat() if a.deadline and a.state in ("submitted", "processing") else None,
        "metrics": counts(request.user, p.scope_deck), "collection": card.collection,
        "back_html": render_back(request, a, {} if history else practice_audio(request, p, a),
                                 None if history else practice_illustration(p))}


@login_required
def presentation_view(request, presentation_id):
    p = get_object_or_404(Presentation.objects.select_related("card__deck", "scope_deck"), pk=presentation_id, user=request.user)
    attempt = Attempt.objects.filter(presentation=p).first()
    if not attempt and not review.valid_presentation(p):
        messages.info(request, "This question is no longer eligible. Your progress is preserved.")
        return redirect(practice_url(p.scope_deck_id))
    # Only front-safe fields reach the template or client before a committed action.
    front = {key: p.snapshot[key] for key in ["question_html", "direction", "language", "units", "kind"]}
    cue_key = "target_language" if front["direction"] == "recognition" else "native_language"
    front["cue_language"] = p.snapshot.get(cue_key, "") if front["kind"] == "vocabulary" else ""
    data = payload(request, attempt, fresh_page=True) if attempt else None
    first_display = Presentation.objects.filter(pk=p.pk, clock_claimed=False).update(clock_claimed=True) == 1 if not attempt else False
    if attempt:
        front_audio = None
    else:
        audio = practice_audio(request, p, None) if review.valid_presentation(p) else {}
        front_audio = next(iter(audio.values()), None)
    front_illustration = practice_illustration(p) if not attempt else None
    autoplay = LearnerPreferences.objects.filter(user=request.user).values_list("autoplay_enabled", flat=True).first()
    return page(request, "learning/review.html", {"p": p, "front": front, "back_html": data["back_html"] if data else "",
        "initial_state": data["state"] if data else "question", "initial_deadline": data["deadline"] if data else "",
        "first_display": first_display, "front_audio": front_audio, "front_illustration": front_illustration,
        "autoplay": autoplay is not False,
        "nav": "study", **counts(request.user, p.scope_deck)})


def owned_presentation(request, presentation_id):
    return get_object_or_404(Presentation.objects.select_related("card", "scope_deck"), pk=presentation_id, user=request.user)


@login_required
@require_POST
def action(request, presentation_id):
    p = owned_presentation(request, presentation_id)
    existing = Attempt.objects.filter(presentation=p).first()
    if existing:
        return JsonResponse(payload(request, existing))
    choice = request.POST.get("action")  # already parsed by body-consuming middleware (e.g. CSRF)
    if choice not in ["skip", "forgot", "speak"]:
        return JsonResponse({"error": "Choose Skip, Speak or Forgot."}, status=400)
    name, duration = "", None
    if choice == "speak":
        upload = request.FILES.get("audio")
        if not upload or not 0 < upload.size <= 50*1024*1024:
            return JsonResponse({"error": "Supply a complete recording up to 50 MB."}, status=400)
        try:
            duration = float(request.POST.get("duration", ""))
            if not math.isfinite(duration) or duration < 0:
                duration = None
        except ValueError:
            pass
        name = uuid.uuid4().hex+".audio"
        try:
            fd = os.open(settings.AUDIO_DIR/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                for chunk in upload.chunks():
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            directory = os.open(settings.AUDIO_DIR, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            # One immutable Stop-based window: from the earliest request moment (before any
            # body-consuming middleware) through durable staging of the recording.
            # The execution deadline is the request anchor plus the total budget, stored unchanged
            # through transaction acquisition: transfer, staging and database lock waiting each count
            # against that absolute deadline exactly once (R3a).
            anchor = getattr(request, "upload_started_wall", None)
            submission_deadline = anchor+timedelta(seconds=settings.ASSESSMENT_TIMEOUT_SECONDS) if anchor is not None else None
            a = review.submit(p, choice, duration, name, submission_deadline)
        except Exception:
            (settings.AUDIO_DIR/name).unlink(missing_ok=True)
            raise
        if a.audio_name != name:
            (settings.AUDIO_DIR/name).unlink(missing_ok=True)
    else:
        a = review.submit(p, choice)
    return JsonResponse(payload(request, a))


@login_required
@require_GET
def status(request, presentation_id):
    p = owned_presentation(request, presentation_id)
    a = Attempt.objects.filter(presentation=p).first()
    return JsonResponse(payload(request, a) if a else {"state": "not_submitted"})


@login_required
@require_POST
def attempt_retry(request, presentation_id):
    p = owned_presentation(request, presentation_id)
    a = get_object_or_404(Attempt, presentation=p)
    return JsonResponse(payload(request, review.retry_attempt(a)))


@login_required
@require_POST
def attempt_exit(request, presentation_id):
    p = owned_presentation(request, presentation_id)
    return JsonResponse(payload(request, review.exit_presentation(p)))


@login_required
@require_POST
def restart_question(request, presentation_id):
    p = owned_presentation(request, presentation_id)
    new = review.restart(p)
    return redirect("presentation", new.pk) if new else redirect(practice_url(p.scope_deck_id))


@login_required
def statistics(request):
    reviews = ScoredReview.objects.filter(user=request.user)
    deck = get_object_or_404(Deck, pk=request.GET["deck"], owner=request.user) if request.GET.get("deck") else None
    if deck:
        reviews = reviews.filter(card__deck=deck)
    window = request.GET.get("window", "today")
    if window not in ["today", "week", "all"]:
        window = "today"
    if window != "all":
        start = timezone.localdate()-timedelta(days=6 if window == "week" else 0)
        reviews = reviews.filter(reviewed_at__date__gte=start)
    total = reviews.count()
    breakdown = Counter(reviews.values_list("grade", flat=True))
    return page(request, "learning/statistics.html", {"nav": "progress", "window": window, "selected_deck": deck,
        "decks": Deck.objects.filter(owner=request.user), "total": total, "distinct": reviews.values("card").distinct().count(),
        "accuracy": round(100*(breakdown["D"]+breakdown["E"])/total) if total else None,
        "breakdown": [(g, label, breakdown[g]) for g, label in review.LABELS.items()],
        "page": Paginator(reviews.order_by("-reviewed_at"), 25).get_page(request.GET.get("page")),
        "due_count": review.available(request.user, deck).filter(due__lte=timezone.now()).count(),
        "forgot_count": review.available(request.user, deck).filter(collection="Forgot").count()})


def health(request):
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})
