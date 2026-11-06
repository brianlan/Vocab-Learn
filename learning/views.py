import json
import math
import os
import uuid
from collections import Counter
from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render as page
from django.template.loader import render_to_string
from django.utils import timezone
from django.urls import reverse
from urllib.parse import urlencode
from django.views.decorators.http import require_POST, require_GET
from . import authoring, review, work
from .forms import DeckForm, CardForm, ImportForm
from .models import Deck, Card, Presentation, Attempt, ScoredReview, GenerationJob
from .rendering import render


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
    decks = Deck.objects.filter(owner=request.user, archived=archived).order_by("name")
    form = DeckForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        deck = form.save(commit=False)
        deck.owner = request.user
        deck.save()
        return redirect("deck", deck.pk)
    return page(request, "learning/library.html", {"decks": decks, "form": form, "archived": archived, "nav": "decks"})


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
    job = card.generation_jobs.filter(source_version=card.source_version).order_by("-requested_at").first()
    return page(request, "learning/card.html", {"card": card, "job": job, "nav": "decks",
        "definition_generated": card.kind == "vocabulary" and authoring.definition_generated(card),
        "question_html": render(card.question, card.answer, True).html,
        "explanation_html": render(card.explanation).html})


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


def payload(request, a):
    p = a.presentation
    a = review.expire_attempt(a)
    a.presentation = p
    card = Card.objects.get(pk=p.card_id)
    return {"state": a.state, "transcript": a.transcript, "grade": a.grade, "next_due": a.next_due.isoformat() if a.next_due else None,
        "metrics": counts(request.user, p.scope_deck), "collection": card.collection,
        "back_html": render_to_string("learning/back.html", {"attempt": a, "p": p, "back": p.snapshot,
        "explanation_html": render(p.snapshot["explanation"]).html, "label": review.LABELS.get(a.grade),
        "next_review": review.relative_due(a.next_due or card.available_at) if a.state != "processing" and a.state != "submitted" else "After checking",
        "practice_url": practice_url(p.scope_deck_id),
        "terminal": a.state in review.TERMINAL,
        "can_retry": a.state == "failed" and a.duration is not None and a.error_stage != "timing"}, request=request)}


@login_required
def presentation_view(request, presentation_id):
    p = get_object_or_404(Presentation.objects.select_related("card__deck", "scope_deck"), pk=presentation_id, user=request.user)
    attempt = Attempt.objects.filter(presentation=p).first()
    if not attempt and not review.valid_presentation(p):
        messages.info(request, "This question is no longer eligible. Your progress is preserved.")
        return redirect(practice_url(p.scope_deck_id))
    # Only front-safe fields reach the template or client before a committed action.
    front = {key: p.snapshot[key] for key in ["question_html", "direction", "language", "units", "kind"]}
    data = payload(request, attempt) if attempt else None
    first_display = Presentation.objects.filter(pk=p.pk, clock_claimed=False).update(clock_claimed=True) == 1 if not attempt else False
    return page(request, "learning/review.html", {"p": p, "front": front, "back_html": data["back_html"] if data else "",
        "first_display": first_display, "initial_state": data["state"] if data else "question", "nav": "study", **counts(request.user, p.scope_deck)})


def owned_presentation(request, presentation_id):
    return get_object_or_404(Presentation.objects.select_related("card", "scope_deck"), pk=presentation_id, user=request.user)


@login_required
@require_POST
def action(request, presentation_id):
    p = owned_presentation(request, presentation_id)
    existing = Attempt.objects.filter(presentation=p).first()
    if existing:
        return JsonResponse(payload(request, existing))
    choice = request.POST.get("action")
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
            a = review.submit(p, choice, duration, name)
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
