from django.urls import include, path
from rest_framework import routers, serializers, viewsets
from .models import *

class WorkspaceS(serializers.ModelSerializer):
    class Meta: model = Workspace; fields = ["id", "title", "kind", "company", "position", "date", "duration", "difficulty", "research", "sources", "created"]
class TaskS(serializers.ModelSerializer):
    class Meta: model = PrepTask; fields = ["id", "workspace", "due", "title", "detail", "category", "kind", "done", "priority", "auto_added"]
class SessionS(serializers.ModelSerializer):
    evaluation = serializers.SerializerMethodField()
    def get_evaluation(self, o):
        e = getattr(o, "evaluation", None); return e and {"overall": e.overall, "verdict": e.verdict, "competencies": e.competencies, "unverified": e.unverified, "scores": e.scores, "summary": e.summary, "observations": e.observations}
    class Meta: model = Session; fields = ["id", "workspace", "mode", "started_at", "ended_at", "status", "vision", "evaluation"]
class MemoryS(serializers.ModelSerializer):
    class Meta: model = MemoryItem; fields = ["category", "score", "observations", "note", "updated"]

def _vs(model, ser, field):
    return type(model.__name__ + "VS", (viewsets.ReadOnlyModelViewSet,), {"serializer_class": ser, "get_queryset": lambda self: model.objects.filter(**{field: self.request.user})})
router = routers.DefaultRouter()
router.register("workspaces", _vs(Workspace, WorkspaceS, "user"), basename="api-ws")
router.register("tasks", _vs(PrepTask, TaskS, "workspace__user"), basename="api-task")
router.register("sessions", _vs(Session, SessionS, "workspace__user"), basename="api-session")
router.register("memory", _vs(MemoryItem, MemoryS, "user"), basename="api-memory")
urlpatterns = [path("", include(router.urls))]
