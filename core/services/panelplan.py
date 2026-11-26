"""ReadyWise decides who sits on the panel, how hard it is and the session mode. The panel SIZE comes from the research first (the real process for this
organisation and role: one visa officer, a three-person panel, a founder and a CTO...). Only when the research cannot say does the candidate get to choose
1, 2 or 3 interviewers; even then ReadyWise picks WHICH interviewers from the available ones, by fit with the role."""
import re
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

def _apply(ws, ivs, difficulty, rationale, source, extra=None):
    ivs = list(ivs)[:MAX_PANEL]; ws.panel.set(ivs); ws.difficulty = difficulty
    ws.allocation = dict({"size": len(ivs), "difficulty": difficulty, "rationale": rationale, "source": source}, **(extra or {})); ws.save()

def research_size(ws):
    """The panel size the research found for the real process (1 to 3), or None when it did not find one."""
    pn = (ws.research or {}).get("panel") if isinstance(ws.research, dict) else None
    if not isinstance(pn, dict): return None
    try: n = int(pn.get("count"))
    except (TypeError, ValueError): return None
    return n if 1 <= n <= MAX_PANEL and pn.get("status") in ("confirmed", "candidate_reported", "inferred") and pn.get("found", True) else None

_W = re.compile(r"[a-z]{4,}")
def _fit(i, ws, hint_roles):
    """Rule-based fit of one interviewer to this interview: type preference, the roles the research named, and the categories the research weights most."""
    p = kinds.profile(ws.kind); score = 0.0
    if i.name in p["panel"]: score += 6 - p["panel"].index(i.name)
    text = f"{i.position} {i.expertise} {i.responsibilities}".lower(); words = set(_W.findall(text))
    for r in hint_roles:
        rw = set(_W.findall(str(r).lower()))
        if rw and (rw & words): score += 3 + len(rw & words)
    w = ws.weights()
    score += sum(w.get(c, 5) for c in i.focus_list()) / max(1, len(i.focus_list())) / 4
    return score

def _best(ws, n, hint_roles):
    ranked = sorted(pool(ws), key=lambda i: (-_fit(i, ws, hint_roles), i.id)); out = []
    for i in ranked:
        if i.name not in [x.name for x in out]: out.append(i)
        if len(out) == n: break
    return out

def allocate(ws, use_ai=False, size=None):
    """size: the candidate's own choice, used only when the research did not find the real panel size. Returns nothing; sets ws.panel, difficulty and allocation."""
    p = kinds.profile(ws.kind); r = ws.research or {}; pn = r.get("panel") if isinstance(r.get("panel"), dict) else {}
    rs = research_size(ws); hint_roles = [str(x) for x in (pn.get("roles") or [])][:4]
    chosen = max(1, min(MAX_PANEL, int(size))) if size else None
    n = rs or chosen or None; source_size = "research" if rs else ("candidate" if chosen else "default")
    needs_choice = bool(ws.research) and not rs and not chosen and not (ws.allocation or {}).get("chosen")
    if not rs and not chosen and (ws.allocation or {}).get("chosen"): n = int(ws.allocation["chosen"]); source_size = "candidate"; needs_choice = False
    by_name = {i.name: i for i in pool(ws)}
    base = [by_name[x] for x in p["panel"] if x in by_name][:MAX_PANEL] or list(pool(ws)[:2])
    if n: base = _best(ws, n, hint_roles) or base[:n]
    diff = _difficulty(ws)
    why = str(pn.get("why", ""))[:240] if rs else ""
    note = (f"The research found a panel of {len(base)}" + (f" ({why})" if why else "") if rs else f"Default {p['label'].lower()} panel of {len(base)}") + ": " + ", ".join(f"{i.name} ({i.position})" for i in base) + f". Difficulty set to {diff}."
    extra = {"size_source": source_size, "needs_choice": needs_choice, "chosen": chosen or (ws.allocation or {}).get("chosen")}
    if use_ai and ws.research:
        try:
            people = "\n".join(f"- id={i.id} {i.name}, {i.position}. Expertise: {i.expertise}. Covers: {i.focus}. Style: {i.personality}" for i in pool(ws))
            count_rule = (f"Choose EXACTLY {n} interviewers" + (" (the real process uses this many)" if rs else " (the candidate asked for this many)")) if n else f"choose 1 to {MAX_PANEL} interviewers (fewer is right when the real process uses fewer, for example one visa officer)"
            prompt = f"""Choose the interview panel for this candidate. Return JSON only.
INTERVIEW TYPE: {p['label']}. GUIDE: {p['guide']}
TARGET: {ws.title} at {ws.company}, {ws.position}. DETAILS: {ws.details}. KNOWN REAL INTERVIEWERS (match their kinds of roles if given): {ws.known_interviewers or 'unknown'}
ROLES THE RESEARCH FOUND IN THE REAL PROCESS: {hint_roles or 'not found'}.
RESEARCH SUMMARY: {r.get('summary','')}. Stages: {r.get('stages')}. Topics: {r.get('topics')}. Role level: {r.get('role_level')}. Competitiveness: {r.get('competitiveness')}.
AVAILABLE INTERVIEWERS:\n{people}
Rules: {count_rule}. Pick the people who best match the real process: the roles above first, then the areas the research says matter most. Do not pick two people who cover the same ground. Choose difficulty "standard", "advanced" or "expert" from how senior and competitive the real process is.
Shape: {{"interviewer_ids": [int], "difficulty": "standard|advanced|expert", "rationale": "two sentences naming what in the research drove this"}}"""
            text, _ = ai.call(prompt, json_mode=True, temperature=0.2); d = ai.parse_json(text); ok = {i.id: i for i in pool(ws)}
            ivs = []
            for x in d.get("interviewer_ids", []):
                if x in ok and ok[x] not in ivs: ivs.append(ok[x])
            ivs = ivs[:(n or MAX_PANEL)]
            if n and len(ivs) < n: ivs += [i for i in _best(ws, n, hint_roles) if i not in ivs][:n - len(ivs)]   # the model named too few: the rule-based fit fills the seats
            if ivs and d.get("difficulty") in LEVELS: return _apply(ws, ivs, d["difficulty"], str(d.get("rationale", ""))[:500], "research", extra)
        except ai.AIError: pass
    _apply(ws, base, diff, note, "default" if not ws.research else "research", extra)

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
