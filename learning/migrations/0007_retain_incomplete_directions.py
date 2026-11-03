from django.db import migrations


def retain_incomplete_directions(apps, schema_editor):
    alias = schema_editor.connection.alias
    Card = apps.get_model("learning", "Card")
    Review = apps.get_model("learning", "ScoredReview")
    cards = Card.objects.using(alias).filter(kind="vocabulary", review_count__gt=0,
        active_pair__isnull=False, cue_pair__isnull=True, cue_direction="")
    for card in cards.iterator():
        last = Review.objects.using(alias).filter(card_id=card.pk,
            snapshot__source_version=card.source_version).order_by("-reviewed_at", "-pk").first()
        if last is None or (card.collection != "Forgot" and last.grade != "C"):
            continue
        direction = last.snapshot["direction"]
        card.direction_index = card.direction_block.index(direction)
        card.cue_direction, card.cue_pair_id = direction, card.active_pair_id
        card.save(using=alias, update_fields=["direction_index", "cue_direction", "cue_pair"])


class Migration(migrations.Migration):
    dependencies = [("learning", "0006_generation_execution_budget")]
    operations = [migrations.RunPython(retain_incomplete_directions, migrations.RunPython.noop)]
