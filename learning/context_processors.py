from django.urls import reverse
from . import authoring
from .models import Deck, LearnerPreferences


def selection_add(request):
    if not request.user.is_authenticated:
        return {}
    preferences = LearnerPreferences.objects.filter(user=request.user).first() or LearnerPreferences(user=request.user)
    return {"selection_add": {
        "user_id": str(request.user.pk),
        "enabled": preferences.selection_add_enabled,
        "target_language": preferences.target_language,
        "native_language": preferences.native_language,
        "decks": list(Deck.objects.filter(owner=request.user, archived=False).order_by("name").values("id", "name"))
                 if preferences.selection_add_enabled else [],
        "language_pairs": [list(pair) for pair in sorted(authoring.LANGUAGE_PAIRS)],
        "create_url": reverse("selection_create"),
        "create_deck_url": reverse("library"),
        "settings_url": reverse("settings"),
    }}
