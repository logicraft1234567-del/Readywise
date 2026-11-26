from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0013_assessment_record")]
    operations = [
        migrations.AddField(model_name="preptask", name="completed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="preptask", name="orig_due", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="preptask", name="query", field=models.CharField(blank=True, default="", max_length=160)),
    ]
