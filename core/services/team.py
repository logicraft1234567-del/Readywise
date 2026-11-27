"""Team workspaces. An investor pitch or a hackathon presentation can be prepared by up to five people who share the same workspace:
research, panel, documents, schedule and plan. The person who creates it is the coordinator. Everyone fills in their own part,
the prep plan is split between them, and the team picks a time when everyone is free."""
import re
from datetime import timedelta
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from . import ai, kinds
from ..models import Profile, PrepTask, TeamSlot, Workspace, WorkspaceMember

MAX_TEAM = 5
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# ---------- who can see what ----------
def ws_q(user, prefix=""):
    """Workspaces the user owns or has joined (use .distinct()). prefix is "workspace__" when filtering something that belongs to a workspace."""
    return Q(**{f"{prefix}user": user}) | Q(**{f"{prefix}members__user": user, f"{prefix}members__status": "accepted"})

def task_q(user):
    """Tasks that are the user's own: assigned to them, or unassigned tasks in a workspace they own."""
    return Q(assignee=user) | Q(assignee__isnull=True, workspace__user=user)

def sess_q(user, prefix=""):
    """Interview sessions the user sat themselves (older sessions have no user: they belong to the workspace owner)."""
    return Q(**{f"{prefix}user": user}) | Q(**{f"{prefix}user__isnull": True, f"{prefix}workspace__user": user})

def name_of(user):
    if not user: return "Someone"
    return Profile.objects.filter(user=user).values_list("full_name", flat=True).first() or user.username

# ---------- the roster ----------
def ensure_coordinator(ws):
    m, _ = WorkspaceMember.objects.get_or_create(workspace=ws, email=(ws.user.email or f"user{ws.user_id}@local").lower(), defaults={"user": ws.user, "role": "coordinator", "status": "accepted"})
    if m.role != "coordinator" or m.user_id != ws.user_id: m.role = "coordinator"; m.user = ws.user; m.status = "accepted"; m.save()
    return m

def roster(ws): return list(ws.members.select_related("user").order_by("role", "id"))
def accepted(ws): return [m for m in roster(ws) if m.status == "accepted" and m.user_id]
def is_team(ws): return ws.members.filter(role="member", status="accepted").exists()
def active_count(ws): return ws.members.exclude(status="declined").count()
def spots_left(ws): return max(0, MAX_TEAM - active_count(ws))

def parse_emails(text, own=""):
    out = []
    for e in EMAIL.findall(text or ""):
        e = e.lower()
        if e != (own or "").lower() and e not in out: out.append(e)
    return out

def invite(ws, coord, emails):
    """Invite people by email. Returns (invited, skipped) where skipped is a list of (email, reason). The coordinator counts as one of the five."""
    invited, skipped = [], []
    if ws.kind not in kinds.TEAM_KINDS: return invited, [(e, "This interview type is not for teams") for e in emails]
    ensure_coordinator(ws)
    for e in emails:
        m = WorkspaceMember.objects.filter(workspace=ws, email__iexact=e).first()
        if m and m.status != "declined": skipped.append((e, "already on the team" if m.status == "accepted" else "already invited")); continue
        if spots_left(ws) <= 0: skipped.append((e, f"the team is full ({MAX_TEAM} people)")); continue
        u = User.objects.filter(email__iexact=e).exclude(pk=coord.pk).first()
        if m: m.status = "invited"; m.user = u; m.responded_at = None; m.save()
        else: WorkspaceMember.objects.create(workspace=ws, email=e, user=u, role="member", status="invited")
        invited.append(e)
    return invited, skipped

def pending_for(user):
    q = Q(user=user)
    if user.email: q |= Q(email__iexact=user.email)
    return list(WorkspaceMember.objects.filter(q, status="invited").select_related("workspace", "workspace__user").order_by("-invited_at"))

def respond(m, user, accept):
    """The invited person answers. Their account is tied to the invitation, and the tasks are split again if a plan already exists."""
    m.user = user; m.status = "accepted" if accept else "declined"; m.responded_at = timezone.now(); m.save()
    if accept and m.workspace.tasks.exists(): split_tasks(m.workspace)

def context(ws):
    """One line for the prompts: the team and what each person presents."""
    ms = accepted(ws)
    if len(ms) < 2: return ""
    return f"TEAM (presenting together as one team of {len(ms)}; the interviewers question the whole team): " + "; ".join(f"{name_of(m.user)}: {(m.part or 'part not described yet')[:220]}" for m in ms) + ".\n"

# ---------- splitting the plan ----------
def split_tasks(ws):
    """Share the unfinished prep tasks between the accepted members, by what each one presents. A practice interview is copied so everyone sits their own.
    Returns the number of tasks shared (0 when there is nobody to share with)."""
    from . import planner
    ms = accepted(ws)
    if len(ms) < 2: return 0
    ws.tasks.filter(team_copy=True, done=False).delete()
    base = list(ws.tasks.filter(done=False, team_copy=False).order_by("due", "id"))
    mock = [t for t in base if planner.is_interview(t)]; rest = [t for t in base if t not in mock]
    assign = {}
    if rest:
        who = "\n".join(f"{i}: {name_of(m.user)} presents: {m.part or 'not described yet'}" for i, m in enumerate(ms))
        what = "\n".join(f"{t.pk}: [{t.category}] {t.title}" for t in rest[:60])
        prompt = (f"Split these preparation tasks between {len(ms)} teammates who are presenting together ({kinds.profile(ws.kind)['label']}: {ws.title}).\nTEAMMATES (index: part they present):\n{who}\n"
                  f"TASKS (id: [category] title):\n{what}\nGive each task to the person whose part it fits best, and keep the workload fair (nobody gets far more than the others). Tasks that are about the whole project can go to anyone, so spread them.\n"
                  'Return JSON only: {"assignments": {"<task id>": <teammate index>}}')
        try:
            d = ai.parse_json(ai.call(prompt, json_mode=True, temperature=0.2, purpose="interview", max_tokens=1200, effort="low")[0]); raw = d.get("assignments") if isinstance(d, dict) else {}
            for k, v in (raw or {}).items():
                try: k, v = int(k), int(v)
                except (TypeError, ValueError): continue
                if 0 <= v < len(ms): assign[k] = v
        except Exception: assign = {}
    load = [0] * len(ms)
    for t in rest:
        i = assign.get(t.pk)
        if i is not None: load[i] += 1
    for t in rest:   # anything the model left out, or a lopsided split, goes to whoever has the fewest
        i = assign.get(t.pk)
        if i is None or load[i] > (len(rest) // len(ms)) + 2:
            if i is not None: load[i] -= 1
            i = load.index(min(load)); load[i] += 1
        t.assignee = ms[i].user; t.save(update_fields=["assignee"])
    for t in mock:
        t.assignee = ms[0].user; t.save(update_fields=["assignee"])
        for m in ms[1:]:
            PrepTask.objects.create(workspace=ws, due=t.due, title=t.title, detail=t.detail, category=t.category, kind=t.kind, priority=t.priority, query=t.query, assignee=m.user, team_copy=True)
    return len(base)

# ---------- finding a time ----------
def slots(ws, user):
    ms = accepted(ws); ids = {m.user_id for m in ms}; out = []
    for s in ws.slots.all():
        free = set(s.free or []); loc = timezone.localtime(s.start)
        out.append({"id": s.pk, "label": f"{loc:%a %d %b, %H:%M}", "names": [name_of(m.user) for m in ms if m.user_id in free], "count": len(free & ids), "total": len(ids),
                    "all": bool(ids) and ids <= free, "mine": user.pk in free, "chosen": s.chosen, "past": s.start < timezone.now()})
    return out

def confirm_slot(ws, slot):
    ws.slots.exclude(pk=slot.pk).update(chosen=False); slot.chosen = True; slot.save(update_fields=["chosen"])
    loc = timezone.localtime(slot.start); ws.date = loc.date(); ws.general = False; ws.details = {**(ws.details or {}), "team_time": loc.strftime("%Y-%m-%d %H:%M"), "team_time_set": timezone.now().isoformat()}
    ws.save(update_fields=["date", "general", "details"])
