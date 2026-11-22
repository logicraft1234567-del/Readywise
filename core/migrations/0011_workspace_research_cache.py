from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("core", "0010_workspace_documents")]
    operations = [migrations.AddField(model_name="workspace", name="research_cache", field=models.JSONField(blank=True, default=dict))]
