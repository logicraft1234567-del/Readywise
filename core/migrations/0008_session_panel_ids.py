from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0007_workspace_job_progress")]
    operations = [migrations.AddField(model_name="session", name="panel_ids", field=models.JSONField(blank=True, default=list))]
