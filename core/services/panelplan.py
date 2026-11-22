"""ReadyWise, not the candidate, decides panel size (max 3), who sits on it, difficulty and session mode."""
from django.db.models import Q
from . import ai, kinds
from ..models import Interviewer, MemoryItem, CAT_LABEL

LEVELS = ["standard", "advanced", "expert"]; MAX_PANEL = 3

def pool(ws): return Interviewer.objects.filter(Q(owner=None) | Q(owner=ws.user))

def _difficulty(ws):
    r = ws.research or {}; i = LEVELS.index(kinds.profile(ws.kind)["base"])
    if r.get("competitiveness") == "high": i += 1
    if r.get("competitiveness") == "low": i -= 1
    if r.get("role_level") in ("senior", "executive"): i += 1
    return LEVELS[max(0, min(2, i))]

def _apply(ws, ivs, difficulty, rationale, source):
    ivs = list(ivs)[:MAX_PANEL]; ws.panel.set(ivs); ws.difficulty = difficulty
    ws.allocation = {"size": len(ivs), "difficulty": difficulty, "rationale": rationale, "source": source}; ws.save()

def allocate(ws, use_ai=False):
    p = kinds.profile(ws.kind); by_name = {i.name: i for i in pool(ws)}
    base = [by_name[n] for n in p["panel"] if n in by_name][:MAX_PANEL] or list(pool(ws)[:2])
    diff = _difficulty(ws)
    note = f"Default {p['label'].lower()} panel of {len(base)}: " + ", ".join(f"{i.name} ({i.position})" for i in base) + f". Difficulty set to {diff}."
    if use_ai and ws.research:
        try:
            people = "\n".join(f"- id={i.id} {i.name}, {i.position}. Expertise: {i.expertise}. Covers: {i.focus}. Style: {i.personality}" for i in pool(ws))
            prompt = f"""Choose the interview panel for this candidate. Return JSON only.
INTERVIEW TYPE: {p['label']}. GUIDE: {p['guide']}
TARGET: {ws.title} at {ws.company}, {ws.position}. DETAILS: {ws.details}. KNOWN REAL INTERVIEWERS (match their kinds of roles if given): {ws.known_interviewers or 'unknown'}
RESEARCH SUMMARY: {ws.research.get('summary','')}. Stages: {ws.research.get('stages')}. Topics: {ws.research.get('topics')}. Role level: {ws.research.get('role_level')}. Competitiveness: {ws.research.get('competitiveness')}.
AVAILABLE INTERVIEWERS:\n{people}
Rules: choose 1 to {MAX_PANEL} interviewers (fewer is right when the real process uses fewer, for example one visa officer). Choose difficulty "standard", "advanced" or "expert" from how senior and competitive the real process is.
Shape: {{"interviewer_ids": [int], "difficulty": "standard|advanced|expert", "rationale": "two sentences naming what in the research drove this"}}"""
            text, _ = ai.call(prompt, json_mode=True, temperature=0.2); d = ai.parse_json(text); ok = {i.id: i for i in pool(ws)}
            ivs = [ok[i] for i in d.get("interviewer_ids", []) if i in ok][:MAX_PANEL]
            if ivs and d.get("difficulty") in LEVELS: return _apply(ws, ivs, d["difficulty"], str(d.get("rationale", ""))[:500], "research")
        except ai.AIError: pass
    _apply(ws, base, diff, note, "default")

def choose_mode(ws):
    n = ws.sessions.filter(status="done").count(); mem = [m.score for m in MemoryItem.objects.filter(user=ws.user)]; avg = sum(mem) / len(mem) if mem else None
    size = ws.panel.count(); lv = LEVELS.index(ws.difficulty if ws.difficulty in LEVELS else "standard")
    if n == 0: return "normal", "First session: a standard run so ReadyWise can see where you are."
    if avg is not None and avg >= 75 and n >= 2:
        return ("unknown", "You are scoring well, so this one uses unfamiliar questions.") if n % 2 == 0 else (("executive", "You are scoring well, so the panel will challenge each other's questions.") if size >= 2 else ("high_pressure", "You are scoring well, so expect tighter time and tougher follow-ups."))
    if lv == 2 and avg is not None and avg >= 65: return "high_pressure", "This process is highly competitive and you are ready for tighter time limits."
    if (avg is not None and avg >= 60) or lv >= 1: return "challenging", "More follow-ups to test how deep your answers go."
    return "normal", "A standard session while you build your foundations."

def adapt_after_session(ws):
    mem = [m.score for m in MemoryItem.objects.filter(user=ws.user)]
    if not mem: return
    avg = sum(mem) / len(mem); i = LEVELS.index(ws.difficulty if ws.difficulty in LEVELS else "standard"); new = i
    if avg >= 80: new = min(2, i + 1)
    elif avg <= 45: new = max(0, i - 1)
    if new != i:
        ws.difficulty = LEVELS[new]; a = dict(ws.allocation or {}); a["difficulty"] = ws.difficulty
        a["rationale"] = (a.get("rationale", "") + f" Difficulty {'raised' if new > i else 'lowered'} to {ws.difficulty} after your latest results.").strip(); ws.allocation = a; ws.save()
