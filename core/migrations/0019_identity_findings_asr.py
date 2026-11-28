from django.db import migrations, models


class Migration(migrations.Migration):
    """Identity profile per interview, entity-aware research findings, and the speech-recognition quality of each candidate answer."""

    dependencies = [
        ('core', '0018_evaluation_breakdown'),
    ]

    operations = [
        migrations.AddField(model_name='workspace', name='identity', field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='turn', name='asr', field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='finding', name='classification', field=models.CharField(default='unverified', max_length=24)),
        migrations.AddField(model_name='finding', name='source_url', field=models.CharField(blank=True, default='', max_length=400)),
        migrations.AddField(model_name='finding', name='source_title', field=models.CharField(blank=True, default='', max_length=200)),
        migrations.AddField(model_name='finding', name='entity', field=models.CharField(blank=True, default='', max_length=160)),
    ]
