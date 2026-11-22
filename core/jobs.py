"""Background jobs. With REDIS_URL set they run on Celery workers. Without it, research runs in a background thread (so the page can show live progress)
and everything else runs inline."""
import threading, time
from celery import shared_task
from django.db import connection
from django.conf import settings
from .models import Workspace, Session
from .services import agents, logic, panelplan, ai

def _tracked(ws_id, fn):
    ws = Workspace.objects.get(pk=ws_id); Workspace.objects.filter(pk=ws_id).update(job_state="running", job_error="")
    try:
        with ai.patient(150): fn(ws)   # nobody is waiting on a button here, so a rate limit is waited out (up to 2.5 minutes) instead of failing the run
    except Exception as e:
        Workspace.objects.filter(pk=ws_id).update(job_state="error", job_error=str(e)[:700]); raise
    Workspace.objects.filter(pk=ws_id).update(job_state="idle")

def _progress(ws_id):
    """Callback that saves which research step is running, so the research page can poll it."""
    def cb(step, steps, found, done=None, active=None): Workspace.objects.filter(pk=ws_id).update(job_progress={"step": step, "steps": steps, "found": found, "done": done or [], "active": active or [], "t": int(time.time())})
    return cb

@shared_task
def research_task(ws_id):
    Workspace.objects.filter(pk=ws_id).update(job_progress={})
    _tracked(ws_id, lambda ws: agents.research(ws, _progress(ws_id)))

@shared_task
def plan_task(ws_id): _tracked(ws_id, agents.prepare)

@shared_task
def finalize_task(sid, frames, camera=None):
    s = Session.objects.get(pk=sid)
    try:
        if s.turns.filter(role="candidate").exists():
            with ai.patient(150): ev, notes = agents.evaluate(s)
            logic.update_memory(s.workspace.user, ev.scores, notes); logic.adjust_plan(s.workspace); panelplan.adapt_after_session(s.workspace)
        if frames:
            try: s.vision = agents.vision_review(frames)
            except Exception: pass  # presentation feedback is optional, never blocks the evaluation
        if camera: s.vision = {**(s.vision or {}), "camera": camera}
        s.status = "done"; s.save()
    except Exception:
        Session.objects.filter(pk=sid).update(status="error"); raise

def _in_thread(task, args):
    def go():
        try: task(*args)
        except Exception: pass  # the failure is already saved on the workspace by _tracked and shown on the page
        finally: connection.close()
    threading.Thread(target=go, daemon=True).start()

def dispatch(task, *args):
    """Returns True if queued (client must poll), False if it already ran inline."""
    if settings.CELERY_ENABLED:
        if task in (research_task, plan_task): Workspace.objects.filter(pk=args[0]).update(job_state="running", job_error="")
        task.delay(*args); return True
    if task is research_task and getattr(settings, "RESEARCH_IN_THREAD", True):
        Workspace.objects.filter(pk=args[0]).update(job_state="running", job_error="", job_progress={}); _in_thread(task, args); return True
    task(*args); return False
