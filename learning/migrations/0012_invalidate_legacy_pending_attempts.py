from django.db import migrations
import uuid


def invalidate_unverifiable_legacy(apps, schema_editor):
    """Pending spoken attempts created before the request-anchored budget cannot prove budget
    compliance, so they are invalidated conservatively at upgrade (issue #12 R3c): receipt, audio
    and history are preserved, the old claim is rotated, and only explicit Retry re-enters."""
    alias = schema_editor.connection.alias
    Attempt = apps.get_model("learning", "Attempt")
    for a in Attempt.objects.using(alias).filter(state__in=["submitted", "processing"]):
        a.state, a.claim, a.deadline = "failed", uuid.uuid4(), None
        a.error_stage, a.error, a.error_category, a.retryable = \
            "timeout", "Processing expired. Retry this fixed input or continue unassessed.", "timeout", True
        a.save(using=alias, update_fields=["state", "claim", "deadline", "error_stage", "error", "error_category", "retryable"])


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0011_learner_preferences"),
    ]

    operations = [
        migrations.RunPython(invalidate_unverifiable_legacy, migrations.RunPython.noop),
    ]
