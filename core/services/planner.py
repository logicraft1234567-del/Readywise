"""The in-app planner: which tasks belong to which day, what may be completed today, where each task's reading and video links point,
the notifications built from the plan, and the numbers behind the dashboard graphs.

Rules the rest of the app relies on:
 - a task can only be completed on its own day (never ahead of time);
 - a task that was missed is moved forward the next time the person opens the app, and keeps a note of the day it was first planned for,
   so the notification can say "moved from Monday";
 - nothing here calls an AI: the links are built from the research already saved on the interview.
"""
import re
from datetime import date, timedelta
from urllib.parse import quote_plus
from django.utils import timezone
from ..models import PrepTask, Evaluation, CATS

PER_DAY = 4   # a missed task is moved to the next day that has room for it (at most this many per interview per day)
_MOCK = re.compile(r"\b(mock|simulation|panel (session|interview)|practice interview|full interview)\b", re.I)
_W = re.compile(r"[a-z]{4,}")


def today(): return date.today()


def is_interview(t): return t.kind == "mock" or bool(_MOCK.search(t.title or ""))


def reschedule_missed(user, day=None):
    """Move every unfinished task from a past day forward. Returns how many were moved."""
    day = day or today()
    missed = list(PrepTask.objects.filter(workspace__user=user, done=False, due__lt=day).select_related("workspace").order_by("-priority", "due", "id"))
    if not missed: return 0
    load = {}
    for ws_id, d in PrepTask.objects.filter(workspace__user=user, done=False, due__gte=day).values_list("workspace_id", "due"): load[(ws_id, d)] = load.get((ws_id, d), 0) + 1
    for t in missed:
        ws = t.workspace; last = ws.date if (ws.date and not ws.general and ws.date >= day) else None
        d = day
        while load.get((ws.id, d), 0) >= PER_DAY and (last is None or d < last): d += timedelta(days=1)
        load[(ws.id, d)] = load.get((ws.id, d), 0) + 1
        t.orig_due = t.orig_due or t.due; t.due = d; t.save(update_fields=["due", "orig_due"])
    return len(missed)


def can_complete(t, day=None): return t.due <= (day or today())


def day_label(d, day=None):
    day = day or today(); n = (d - day).days
    return "Today" if n == 0 else "Tomorrow" if n == 1 else "Yesterday" if n == -1 else f"{d:%a %d %b}"


def _words(text): return set(_W.findall((text or "").lower()))


def _best(sources, want, video):
    """The saved research source whose title or snippet shares most words with the task. Videos and pages are chosen separately."""
    best, top = None, 0
    for s in sources or []:
        if not isinstance(s, dict) or not str(s.get("url", "")).startswith("http") or bool(s.get("video")) != video: continue
        n = len(want & _words(f"{s.get('title', '')} {s.get('snippet', '')}"))
        if n > top: best, top = s, n
    return best if top >= 1 else None


def links(t, ws):
    """Where to read, what to watch and (for an interview task) which interview to start. Every link is real: a page or video the research found, or a search."""
    base = (t.query or f"{t.title} {ws.position or ws.title}").strip()[:140]; want = _words(f"{t.title} {t.detail} {t.query}")
    src = ws.sources if isinstance(ws.sources, list) else []
    page, vid = _best(src, want, False), _best(src, want, True)
    out = {"read": {"url": page["url"], "label": (page.get("title") or "Read the source")[:70], "found": True} if page else
                   {"url": "https://www.google.com/search?q=" + quote_plus(base + " interview preparation"), "label": "Search for guides on this", "found": False},
           "watch": {"url": vid["url"], "label": (vid.get("title") or "Watch the video")[:70], "found": True} if vid else
                    {"url": "https://www.youtube.com/results?search_query=" + quote_plus(base + " interview"), "label": "Find videos on YouTube", "found": False},
           "interview": None}
    if is_interview(t): out["interview"] = {"workspace": ws.pk, "label": "Start the interview"}
    return out


def card(t, ws=None, day=None):
    """Everything the browser needs to draw one task, as plain data."""
    ws = ws or t.workspace; day = day or today()
    moved = bool(t.orig_due and t.orig_due != t.due and not t.done)
    return {"id": t.pk, "title": t.title, "detail": t.detail, "kind": t.kind, "category": t.category, "done": t.done, "due": t.due.isoformat(), "when": day_label(t.due, day),
            "state": "done" if t.done else "today" if t.due <= day else "later", "can": can_complete(t, day), "workspace": ws.title, "workspace_id": ws.pk,
            "moved": ({"from": t.orig_due.isoformat(), "label": f"{t.orig_due:%a %d %b}"} if moved else None), "auto": t.auto_added, "links": links(t, ws)}


def notifications(user, day=None):
    """What the bell shows. Built fresh each time from the plan, so it can never be out of date."""
    day = day or today(); items = []
    todo = list(PrepTask.objects.filter(workspace__user=user, done=False, due__lte=day).select_related("workspace").order_by("-priority", "due", "id"))
    for t in todo:
        c = card(t, day=day)
        if c["moved"]: msg = f"You missed this on {c['moved']['label']}, so it moved to {day_label(t.due, day).lower()}. Finish it today to stay on track."
        else: msg = t.detail or "Planned for today."
        items.append({"type": "task", "title": t.title, "message": msg, "workspace": t.workspace.title, "task": c})
    tomorrow = list(PrepTask.objects.filter(workspace__user=user, done=False, due=day + timedelta(days=1)).select_related("workspace"))
    if tomorrow: items.append({"type": "info", "title": f"Tomorrow: {len(tomorrow)} task{'s' if len(tomorrow) != 1 else ''}", "message": "; ".join(t.title for t in tomorrow[:5]) + ("." if len(tomorrow) <= 5 else f" and {len(tomorrow) - 5} more."), "workspace": "", "task": None})
    from ..models import Workspace
    for w in Workspace.objects.filter(user=user, general=False, date__gte=day, date__lte=day + timedelta(days=3)).order_by("date"):
        n = (w.date - day).days
        items.append({"type": "interview", "title": f"{w.title}: " + ("your interview is today" if n == 0 else "your interview is tomorrow" if n == 1 else f"your interview is in {n} days"), "message": "Run one more practice interview and review your weakest area.", "workspace": w.title, "task": None, "workspace_id": w.pk})
    done_today = PrepTask.objects.filter(workspace__user=user, done=True, due=day).count()
    if not todo and done_today: items.insert(0, {"type": "ok", "title": "Everything for today is done", "message": f"{done_today} task{'s' if done_today != 1 else ''} completed. Rest, or run a practice interview.", "workspace": "", "task": None})
    return {"items": items, "count": len(todo), "today": day.isoformat()}


def progress(user):
    """Numbers for the dashboard graphs: the score over time, each skill's first and latest score, daily completed tasks and how consistent the person has been."""
    day = today()
    evs = list(Evaluation.objects.filter(session__workspace__user=user, session__status="done", overall__isnull=False).select_related("session__workspace").order_by("session__started_at", "id"))
    series = [{"label": f"{timezone.localtime(e.session.started_at):%d %b}", "score": e.overall, "title": e.session.workspace.title, "report": e.session_id} for e in evs]
    cats = []
    for key, label in CATS:
        vals = [(e.scores or {}).get(key) for e in evs]; vals = [v for v in vals if isinstance(v, (int, float))]
        if vals: cats.append({"key": key, "label": label, "first": round(vals[0]), "latest": round(vals[-1]), "delta": round(vals[-1] - vals[0]), "n": len(vals)})
    trend = {"state": "none", "delta": 0, "last": None, "text": "Finish an interview to see your trend."}
    if series:
        trend.update(last=series[-1]["score"], state="first", text=f"Your first score is {series[-1]['score']}. Practise again to see the direction.")
    if len(series) >= 2:
        d = series[-1]["score"] - series[0]["score"]; r = series[-1]["score"] - series[-2]["score"]
        state = "up" if d >= 3 else "down" if d <= -3 else "flat"
        word = {"up": "Improving", "down": "Declining", "flat": "Holding steady"}[state]
        trend.update(state=state, delta=d, recent=r, text=f"{word}: {d:+d} points since your first interview, {r:+d} since the last one.")
    window = [day - timedelta(days=i) for i in range(13, -1, -1)]
    done_by = {}
    for ts in PrepTask.objects.filter(workspace__user=user, done=True, completed_at__isnull=False, completed_at__date__gte=window[0]).values_list("completed_at", flat=True):
        k = timezone.localtime(ts).date(); done_by[k] = done_by.get(k, 0) + 1
    activity = {"labels": [f"{d:%d %b}" for d in window], "values": [done_by.get(d, 0) for d in window]}
    streak = 0; d = day if done_by.get(day) else day - timedelta(days=1)   # a day that is not over yet does not break the streak
    while done_by.get(d): streak += 1; d -= timedelta(days=1)
    due_total = PrepTask.objects.filter(workspace__user=user, due__lte=day).count(); due_done = PrepTask.objects.filter(workspace__user=user, due__lte=day, done=True).count()
    moved = PrepTask.objects.filter(workspace__user=user, orig_due__isnull=False).count()
    return {"series": series, "cats": cats, "trend": trend, "activity": activity, "streak": streak, "completion": round(100 * due_done / due_total) if due_total else None,
            "moved": moved, "week_done": sum(activity["values"][-7:])}
