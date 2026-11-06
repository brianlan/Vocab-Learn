from django.urls import path
from . import views, api

urlpatterns = [
    path("api/v1/decks/<int:deck_id>/vocabulary-cards/", api.create_vocabulary, name="api_vocabulary_create"),
    path("api/v1/vocabulary-cards/<int:card_id>/", api.vocabulary, name="api_vocabulary"),
    path("", views.dashboard, name="dashboard"), path("health/", views.health, name="health"),
    path("decks/", views.library, name="library"), path("decks/<int:deck_id>/", views.deck_view, name="deck"),
    path("decks/<int:deck_id>/edit/", views.deck_edit, name="deck_edit"),
    path("decks/<int:deck_id>/archive/", views.deck_archive, name="deck_archive"),
    path("decks/<int:deck_id>/new/", views.card_edit, name="card_create"),
    path("decks/<int:deck_id>/cards/<int:card_id>/edit/", views.card_edit, name="card_edit"),
    path("decks/<int:deck_id>/import/", views.csv_import, name="csv_import"),
    path("cards/<int:card_id>/", views.card_view, name="card"),
    path("cards/<int:card_id>/archive/", views.card_archive, name="card_archive"),
    path("generation/<uuid:job_id>/retry/", views.generation_retry, name="generation_retry"),
    path("practice/", views.practice, name="practice"),
    path("runs/start/", views.legacy_practice), path("runs/<uuid:legacy_id>/", views.legacy_practice),
    path("review/<uuid:presentation_id>/", views.presentation_view, name="presentation"),
    path("review/<uuid:presentation_id>/action/", views.action, name="action"),
    path("review/<uuid:presentation_id>/status/", views.status, name="status"),
    path("review/<uuid:presentation_id>/retry/", views.attempt_retry, name="attempt_retry"),
    path("review/<uuid:presentation_id>/exit/", views.attempt_exit, name="attempt_exit"),
    path("review/<uuid:presentation_id>/restart/", views.restart_question, name="restart_question"),
    path("progress/", views.statistics, name="statistics"),
]
