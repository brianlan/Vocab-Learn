"""Private Vocabulary creation and preparation queries, authenticated only by API key."""
import json
from functools import wraps
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from . import api_keys, authoring, work
from .models import Card, Deck


def authorized(method):
    def decorate(view):
        @csrf_exempt
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            key = api_keys.authenticate(request.headers.get("Authorization", ""))
            if not key:
                return JsonResponse({"error": "Supply an active Vocabulary API key in the Authorization header."},
                                    status=401, headers={"WWW-Authenticate": "Bearer"})
            if request.method != method:
                return JsonResponse({"error": "Method not allowed."}, status=405, headers={"Allow": method})
            return view(request, key.owner, *args, **kwargs)
        return wrapped
    return decorate


def representation(card):
    job = card.generation_jobs.filter(source_version=card.source_version).order_by("-requested_at").first()
    preparation = {"state": "ready" if card.ready else job.state if job else "unavailable"}
    if job and not card.ready:
        phase = "definition" if job.provenance.get("enrich_source") and not job.provenance.get("definition_completed") else "examples"
        preparation.update(phase=job.provenance.get("phase", phase), error=job.error,
                           retryable=job.state == "failed" and job.retryable)
    return {"id": card.pk, "deck_id": card.deck_id, "word": card.word, "explanation": card.explanation,
            "target_language": card.target_language, "native_language": card.native_language,
            "ready": card.ready, "archived": card.archived, "preparation": preparation,
            "ai_generated_explanation": authoring.definition_generated(card),
            "status_url": reverse("api_vocabulary", args=[card.pk])}


@authorized("POST")
def create_vocabulary(request, owner, deck_id):
    deck = Deck.objects.filter(pk=deck_id, owner=owner, archived=False).first()
    if not deck:
        return JsonResponse({"error": "Private active deck not found."}, status=404)
    if request.content_type != "application/json":
        return JsonResponse({"error": "Use application/json."}, status=415)
    try:
        body = request.body
    except RequestDataTooBig:
        return JsonResponse({"error": "A Vocabulary request is limited to 64 KB."}, status=413)
    if len(body) > 64 * 1024:
        return JsonResponse({"error": "A Vocabulary request is limited to 64 KB."}, status=413)
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return JsonResponse({"error": "Supply a valid UTF-8 JSON object."}, status=400)
    if not isinstance(data, dict) or set(data) - set(authoring.SCHEMAS["vocabulary"]):
        return JsonResponse({"error": "Use only word, target_language, native_language and optional explanation."}, status=400)
    try:
        card, created = authoring.create_card(deck, "vocabulary", data)
    except ValidationError as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=400)
    return JsonResponse({**representation(card), "created": created}, status=201 if created else 200,
                        headers={"Location": reverse("api_vocabulary", args=[card.pk])})


@authorized("GET")
def vocabulary(request, owner, card_id):
    card = Card.objects.filter(pk=card_id, kind="vocabulary", deck__owner=owner).first()
    if not card:
        return JsonResponse({"error": "Private Vocabulary Card not found."}, status=404)
    work.expire_generations()
    return JsonResponse(representation(card))
