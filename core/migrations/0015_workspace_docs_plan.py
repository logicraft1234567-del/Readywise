from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0014_preptask_planner")]
    operations = [migrations.AddField(model_name="workspace", name="docs_plan", field=models.JSONField(blank=True, default=list))]
