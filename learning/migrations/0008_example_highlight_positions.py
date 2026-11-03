from django.db import migrations, models


def locate_legacy_highlights(apps, schema_editor):
    Pair = apps.get_model("learning", "ExamplePair")
    alias = schema_editor.connection.alias
    for pair in Pair.objects.using(alias).all():
        for language in ("target", "native"):
            sentence, expression = getattr(pair, language + "_sentence"), getattr(pair, language + "_highlight")
            start = sentence.find(expression)
            if not expression or start < 0:
                raise ValueError("A saved example has no matching highlight; repair it before upgrading.")
            setattr(pair, language + "_highlight_start", start)
        pair.save(using=alias, update_fields=["target_highlight_start", "native_highlight_start"])


class Migration(migrations.Migration):
    dependencies = [("learning", "0007_retain_incomplete_directions")]
    operations = [
        migrations.AddField("examplepair", "target_highlight_start", models.PositiveIntegerField(null=True)),
        migrations.AddField("examplepair", "native_highlight_start", models.PositiveIntegerField(null=True)),
        migrations.RunPython(locate_legacy_highlights, migrations.RunPython.noop),
        migrations.AlterField("examplepair", "target_highlight_start", models.PositiveIntegerField()),
        migrations.AlterField("examplepair", "native_highlight_start", models.PositiveIntegerField()),
    ]
