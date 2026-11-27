from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0015_workspace_docs_plan"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AlterField(model_name="workspace", name="kind", field=models.CharField(choices=[("startup","Startup job"),("employment","Corporate job"),("internship","Internship"),("graduate","Graduate programme"),("admission","University admission"),("scholarship","Scholarship"),("visa","Visa practice"),("fellowship","Fellowship"),("pitch","Investor pitch"),("hackathon","Hackathon presentation"),("certification","Certification")], default="employment", max_length=20)),
        migrations.AddField(model_name="preptask", name="assignee", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_tasks", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="preptask", name="team_copy", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="session", name="user", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="team_sessions", to=settings.AUTH_USER_MODEL)),
        migrations.CreateModel(name="WorkspaceMember", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("email", models.EmailField(max_length=254)), ("role", models.CharField(default="member", max_length=12)), ("status", models.CharField(default="invited", max_length=10)),
            ("part", models.TextField(blank=True)), ("invited_at", models.DateTimeField(auto_now_add=True)), ("responded_at", models.DateTimeField(blank=True, null=True)),
            ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="team_memberships", to=settings.AUTH_USER_MODEL)),
            ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="members", to="core.workspace")),
        ], options={"ordering": ["role", "id"], "unique_together": {("workspace", "email")}}),
        migrations.CreateModel(name="TeamSlot", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("start", models.DateTimeField()), ("free", models.JSONField(blank=True, default=list)), ("chosen", models.BooleanField(default=False)),
            ("proposed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="slots", to="core.workspace")),
        ], options={"ordering": ["start"]}),
    ]
