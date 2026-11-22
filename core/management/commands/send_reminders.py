from datetime import date
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from core.models import PrepTask

class Command(BaseCommand):
    help = "Email each user the prep tasks due today or overdue. Run daily (cron or Render cron job)."
    def handle(self, *a, **k):
        n = 0
        for u in User.objects.exclude(email=""):
            tasks = PrepTask.objects.filter(workspace__user=u, done=False, due__lte=date.today()).select_related("workspace")
            if not tasks: continue
            body = "Your ReadyWise tasks for today:\n\n" + "\n".join(f"- {t.title} ({t.workspace.title}, due {t.due})" for t in tasks)
            send_mail("Your ReadyWise tasks for today", body, None, [u.email]); n += 1
        self.stdout.write(f"Sent {n} reminder(s)")
