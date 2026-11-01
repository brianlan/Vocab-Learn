from datetime import timedelta
from django.db import migrations, models
from django.db.models import F
from django.utils import timezone
import django.db.models.deletion


def preserve_practice_state(apps, schema_editor):
    alias = schema_editor.connection.alias
    Presentation = apps.get_model("learning", "Presentation")
    Card = apps.get_model("learning", "Card")
    for p in Presentation.objects.using(alias).select_related("run").iterator():
        Presentation.objects.using(alias).filter(pk=p.pk).update(scope_deck_id=p.run.deck_id)
    cutoff = timezone.now()-timedelta(minutes=30)
    recent = Presentation.objects.using(alias).filter(
        invalidated=False, attempt__state__in=["skipped", "closed_unassessed"],
        attempt__submitted_at__gt=cutoff, source_version=F("card__source_version"),
        progress_version=F("card__progress_version")
    ).order_by("attempt__submitted_at").values("card_id", "attempt__submitted_at")
    for p in recent.iterator():
        Card.objects.using(alias).filter(pk=p["card_id"]).update(
            deferred_until=p["attempt__submitted_at"]+timedelta(minutes=30))


class Migration(migrations.Migration):
    dependencies = [("learning", "0003_attempt_error_category_attempt_retryable_and_more")]
    operations = [
        migrations.AddField(model_name="card", name="deferred_until",
            field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="presentation", name="scope_deck",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to="learning.deck")),
        # Removing a run must never cascade through presentations, attempts or scored history.
        migrations.RunPython(preserve_practice_state),
        migrations.RemoveField(model_name="presentation", name="run"),
        migrations.DeleteModel(name="Deferral"),
        migrations.DeleteModel(name="StudyRun"),
    ]
