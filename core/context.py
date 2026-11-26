from datetime import date
from .models import Workspace, PrepTask
from .services import planner
def shell(request):
    if request.user.is_authenticated:
        try: planner.reschedule_missed(request.user)   # a missed day moves its tasks forward the next time the app is opened
        except Exception: pass
        return {"side_ws": Workspace.objects.filter(user=request.user).order_by("-created")[:8],
                "due_count": PrepTask.objects.filter(workspace__user=request.user, done=False, due__lte=date.today()).count()}
    return {}
