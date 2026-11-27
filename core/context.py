from datetime import date
from .models import Workspace, PrepTask
from .services import planner, team
def shell(request):
    if request.user.is_authenticated:
        try: planner.reschedule_missed(request.user)   # a missed day moves its tasks forward the next time the app is opened
        except Exception: pass
        return {"side_ws": Workspace.objects.filter(team.ws_q(request.user)).distinct().order_by("-created")[:8],
                "due_count": PrepTask.objects.filter(team.task_q(request.user), done=False, due__lte=date.today()).count() + len(team.pending_for(request.user))}
    return {}
