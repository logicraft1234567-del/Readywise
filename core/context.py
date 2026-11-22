from datetime import date
from .models import Workspace, PrepTask
def shell(request):
    if request.user.is_authenticated:
        return {"side_ws": Workspace.objects.filter(user=request.user).order_by("-created")[:8],
                "due_count": PrepTask.objects.filter(workspace__user=request.user, done=False, due__lte=date.today()).count()}
    return {}
