from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_interviewer_avatar'),
    ]

    operations = [
        migrations.AddField(
            model_name='workspace',
            name='job_progress',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
