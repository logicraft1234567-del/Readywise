from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("core", "0012_panel_agenda_factcheck_score")]
    operations = [
        migrations.AddField(model_name="session", name="assessment", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="evaluation", name="competencies", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="evaluation", name="unverified", field=models.JSONField(blank=True, default=list)),
    ]
