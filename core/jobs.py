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
def plan_task(ws_id):
    _tracked(ws_id, agents.prepare)
    try:   # a team's plan is shared out between everyone as soon as it exists
        from .models import Workspace
        from .services import team
        team.split_tasks(Workspace.objects.get(pk=ws_id))
    except Exception: pass

_PRE = {}   # session id -> (turn count, future): an evaluation started early, while the closing words are spoken

def prefetch_evaluation(sid):
    """Called the moment the panel says its closing words. The evaluation (the slow part of finishing) runs now, in the background; finalize_task uses the result
    if nothing was said since. Any problem, a second server process or a different transcript simply means the normal evaluation runs when the interview is finished."""
    if settings.CELERY_ENABLED or sid in _PRE: return
    s = Session.objects.get(pk=sid)
    if not s.turns.filter(role="candidate").exists(): return
    from concurrent.futures import ThreadPoolExecutor
    def run():
        try:
            with ai.patient(60): return agents.evaluate(Session.objects.get(pk=sid))
        finally: connection.close()
    ex = ThreadPoolExecutor(1); _PRE[sid] = (s.turns.count(), ex.submit(run)); ex.shutdown(wait=False)
    for k in [k for k in _PRE if k != sid][:-20]: _PRE.pop(k, None)   # never let this grow

@shared_task
def finalize_task(sid, frames, camera=None):
    s = Session.objects.get(pk=sid)
    try:
        vis = {}
        def _look():   # the camera review runs at the same time as the evaluation and saves itself when it is done: the report never waits long for it
            try:
                with ai.budget(25): vis["v"] = agents.vision_review(frames)
                if vis.get("v"): Session.objects.filter(pk=sid).update(vision={**(Session.objects.get(pk=sid).vision or {}), **vis["v"]} if isinstance(vis["v"], dict) else vis["v"])
            except Exception: pass  # presentation feedback is optional, never blocks the evaluation
            finally: connection.close()
        th = threading.Thread(target=_look, daemon=True) if frames else None
        if th: th.start()
        ev = notes = None; pre = _PRE.pop(sid, None)
        if s.turns.filter(role="candidate").exists():
            if pre and pre[0] == s.turns.count():
                try: ev, notes = pre[1].result(timeout=75)
                except Exception: ev = notes = None
            if ev is None:
                with ai.patient(60): ev, notes = agents.evaluate(s)
        if th: th.join(timeout=3)
        v = vis.get("v")
        if v: s.vision = v
        if camera: s.vision = {**(s.vision or {}), "camera": camera}
        s.status = "done"; s.save(update_fields=["status"] + (["vision"] if (v or camera) else []))   # the report opens now; the bookkeeping below only touches the next session's plan
        if ev is not None:
            try: logic.update_memory(s.workspace.user, ev.scores, notes, (ev.breakdown or {}).get("confidence")); logic.adjust_plan(s.workspace); panelplan.adapt_after_session(s.workspace)
            except Exception: pass
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
    if task is finalize_task and getattr(settings, "FINISH_IN_THREAD", True): _in_thread(task, args); return True   # the evaluation runs in the background: Finish answers at once and the room page polls until the report is ready
    task(*args); return False
