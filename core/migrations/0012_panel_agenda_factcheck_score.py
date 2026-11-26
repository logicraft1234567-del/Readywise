from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("core", "0011_workspace_research_cache")]
    operations = [
        migrations.AddField(model_name="session", name="agenda", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="session", name="board", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="turn", name="factcheck", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="evaluation", name="overall", field=models.IntegerField(blank=True, null=True)),
        migrations.AddField(model_name="evaluation", name="verdict", field=models.CharField(blank=True, max_length=40, default="")),
        migrations.AddField(model_name="evaluation", name="checks", field=models.JSONField(blank=True, default=list)),
    ]
