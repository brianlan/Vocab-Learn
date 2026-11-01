from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("learning", "0004_continuous_practice")]
    operations = [migrations.RemoveField(model_name="examplepair", name="gloss")]
