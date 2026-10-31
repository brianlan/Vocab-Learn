from django.contrib import admin
from .models import Deck, Card

@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "archived"]
    search_fields = ["name", "owner__username"]
    readonly_fields = [f.name for f in Deck._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ["id", "kind", "deck", "collection", "ready", "archived"]
    readonly_fields = [f.name for f in Card._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
