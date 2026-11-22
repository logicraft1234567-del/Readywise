from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0008_session_panel_ids")]
    operations = [migrations.AddField(model_name="session", name="challenge", field=models.JSONField(blank=True, default=dict))]
