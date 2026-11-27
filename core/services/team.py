"""Teams: the person who creates the interview is the COORDINATOR; up to four teammates (five people in all) are invited by email, accept from their own notifications, fill in their own part,
share the same workspace and plan (the coordinator's plan is split between everyone), and agree one time for the practice interview."""
import re
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone
from ..models import PrepTask, TeamMember, TimeSlot, Workspace

MAX_TEAM = 5   # the coordinator plus up to four teammates
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def workspaces_for(user):
    """Every workspace the person owns or has joined."""
    return Workspace.objects.filter(Q(user=user) | Q(team__user=user, team__status="accepted")).distinct()

def tasks_for(user):
    """The tasks that are the person's: in their workspaces, assigned to them or to the whole team."""
    return PrepTask.objects.filter(Q(workspace__user=user) | Q(workspace__team__user=user, workspace__team__status="accepted")).filter(Q(assignee=None) | Q(assignee=user)).distinct()

def can_access(user, ws): return ws.user_id == user.id or ws.team.filter(user=user, status="accepted").exists()
def is_coordinator(user, ws): return ws.user_id == user.id

def people(ws):
    """The coordinator first, then accepted teammates."""
    return [ws.user] + [m.user for m in ws.team.filter(status="accepted").select_related("user").order_by("responded_at", "id") if m.user]

def display(user, ws=None):
    from .agents import profile_of
    return (profile_of(user).full_name or "").strip() or user.username

def size(ws): return 1 + ws.team.exclude(status="declined").count()

def parse_emails(raw):
    """Emails from a list or a pasted block (commas, spaces or new lines), lower-cased, valid and without repeats."""
    items = raw if isinstance(raw, (list, tuple)) else re.split(r"[,\s;]+", str(raw or ""))
    out = []
    for x in items:
        e = str(x).strip().lower()
        if e and _EMAIL.match(e) and e not in out: out.append(e)
    return out

def invite(ws, raw_emails, by):
    """Invites teammates. Returns (invited, problems). The invitation shows in the teammate's notifications as soon as they sign in (or sign up) with that email."""
    emails = parse_emails(raw_emails); invited, problems = [], []
    for e in emails:
        if e == (by.email or "").lower(): problems.append(f"{e}: that is you"); continue
        old = ws.team.filter(email__iexact=e).first()
        if old and old.status in ("invited", "accepted"): problems.append(f"{e}: already {'on the team' if old.status == 'accepted' else 'invited'}"); continue
        if size(ws) >= MAX_TEAM: problems.append(f"{e}: a team can have at most {MAX_TEAM} people"); continue
        u = User.objects.filter(email__iexact=e).first()
        m = old or TeamMember(workspace=ws, email=e, invited_by=by)
        m.status = "invited"; m.user = u; m.responded_at = None; m.invited_by = by; m.save(); invited.append(m)
        try:
            send_mail(f"{display(by)} invited you to present together on ReadyWise",
                      f"{display(by)} added you to the team for \"{ws.title}\" on ReadyWise. Sign in with this email address and open your notifications to accept.", getattr(settings, "DEFAULT_FROM_EMAIL", None), [e], fail_silently=True)
        except Exception: pass
    return invited, problems

def pending_for(user):
    """Invitations waiting for this person, matched by the email they signed up with."""
    if not user.email: return TeamMember.objects.none()
    return TeamMember.objects.filter(email__iexact=user.email, status="invited").select_related("workspace", "invited_by")

def respond(member, user, accept):
    """Accept or decline. Accepting joins the team, and if a plan already exists it is split again so the new member gets their share."""
    if member.status != "invited": return member
    member.user = user; member.status = "accepted" if accept else "declined"; member.responded_at = timezone.now()
    if not member.name: member.name = display(user)
    member.save()
    if accept and member.workspace.tasks.exists(): split_tasks(member.workspace)
    return member

def _words(t): return {w for w in re.findall(r"[a-z]{4,}", (t or "").lower())}

def split_tasks(ws):
    """Shares the open prep tasks between the team: tasks that match a person's own part go to them, the rest to whoever has the least so far; practice interviews stay with the whole team.
    With only the coordinator, every task goes back to them."""
    from .planner import is_interview
    ppl = people(ws); tasks = list(ws.tasks.filter(done=False).order_by("due", "-priority", "id"))
    if len(ppl) < 2:
        ws.tasks.filter(done=False).update(assignee=None); return {}
    parts = {ws.user_id: _words(ws.details.get("team", "") if isinstance(ws.details, dict) else "")}
    for m in ws.team.filter(status="accepted"): parts[m.user_id] = _words(f"{m.part} {m.name}")
    load = {u.id: 0 for u in ppl}
    for t in tasks:
        if is_interview(t): t.assignee = None; t.save(update_fields=["assignee"]); continue
        ws_ = _words(f"{t.title} {t.detail}")
        score = {u.id: len(parts.get(u.id, set()) & ws_) for u in ppl}; least = min(load.values())
        best = max(ppl, key=lambda u: (score[u.id] if load[u.id] <= least + 2 else -1, -load[u.id]))
        t.assignee = best; t.save(update_fields=["assignee"]); load[best.id] += 1
    return {u.id: load[u.id] for u in ppl}

def context(ws):
    """Who is presenting, for the interviewers' briefing. Empty for a solo candidate."""
    ppl = people(ws)
    if len(ppl) < 2: return ""
    lines = [f"- {display(ws.user)} (coordinator): {(ws.details or {}).get('team', '')[:300] or 'leads the presentation'}"]
    for m in ws.team.filter(status="accepted").select_related("user"): lines.append(f"- {m.name or display(m.user)}: {m.part[:300] or 'presents part of the project'}")
    return f"THE CANDIDATE SIDE IS A TEAM OF {len(ppl)} PRESENTING TOGETHER (they share one microphone and answer in turn). Address questions to a specific person by name when it fits their part, and expect any of them to answer:\n" + "\n".join(lines) + "\n"

# ---------- scheduling ----------
def propose_slot(ws, user, starts):
    if starts < timezone.now() - timedelta(minutes=1): raise ValueError("Pick a time in the future.")
    if ws.slots.count() >= 8: raise ValueError("There are already several proposed times. Vote on one of them first.")
    s = TimeSlot.objects.create(workspace=ws, starts=starts, proposed_by=user, votes={str(user.id): "yes"}); return check_slot(s)

def vote_slot(slot, user, yes):
    v = dict(slot.votes or {}); v[str(user.id)] = "yes" if yes else "no"; slot.votes = v; slot.save(update_fields=["votes"]); return check_slot(slot)

def check_slot(slot):
    """A time is confirmed when every person on the team has said yes; the workspace then carries that date and time (and the calendar shows it)."""
    ids = {str(u.id) for u in people(slot.workspace)}
    if ids and all((slot.votes or {}).get(i) == "yes" for i in ids) and not slot.chosen:
        slot.workspace.slots.update(chosen=False); slot.chosen = True; slot.save(update_fields=["chosen"])
        ws = slot.workspace; local = timezone.localtime(slot.starts); ws.scheduled_at = slot.starts; ws.date = local.date(); ws.save(update_fields=["scheduled_at", "date"])
    return slot

def slot_view(slot, user):
    ppl = people(slot.workspace); v = slot.votes or {}
    return {"id": slot.id, "starts": timezone.localtime(slot.starts).strftime("%a %d %b, %H:%M"), "iso": timezone.localtime(slot.starts).isoformat(), "chosen": slot.chosen, "mine": v.get(str(user.id)),
            "who": [{"name": display(u), "vote": v.get(str(u.id))} for u in ppl], "yes": sum(1 for u in ppl if v.get(str(u.id)) == "yes"), "total": len(ppl)}
