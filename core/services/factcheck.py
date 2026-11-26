"""Live fact checker. While the interview runs, whatever the candidate states as a fact (a price, a date, a figure, a name, how something works) is looked up
online with a dedicated API key (FACTCHECK_GEMINI_KEYS / GROQ_FACTCHECK_KEYS, see ai.factcheck_search). If a claim is wrong, the panel is given the verified
figure and the source, so the next question can confront the candidate with it the way a real interviewer who had checked would.

Speed: the claims of one answer are picked quickly, then checked in parallel on all the research keys (Groq browser search first, Gemini as a fallback).
Rules: only public, checkable facts are looked up (never the candidate's private life); personal claims are only flagged when they are implausible on their face
(for example "my mother is a CEO and we have one million dollars" with no evidence). A check that cannot finish in time never blocks the interview: it is saved
when it arrives and used on the following turn."""
import re, threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from django.conf import settings
from django.db import connection
from . import ai

VERDICTS = ("correct", "wrong", "implausible", "unverifiable")
_CLAIMY = re.compile(r"\d|million|billion|thousand|hundred|percent|per cent|%|dollar|naira|pound|euro|founded|invented|ceo|revenue|profit|price|cost|market|users|customers|"
                     r"law|rule|policy|visa|tuition|fee|salary|record|largest|biggest|first|only|never|always|year|\bin (19|20)\d\d", re.I)
_pool = ThreadPoolExecutor(max_workers=8)             # one worker per candidate answer being checked
_claim_pool = ThreadPoolExecutor(max_workers=12)      # one worker per claim, so the claims of an answer are checked side by side

def worth_checking(text):
    """Cheap filter so a plain 'yes' or 'I am a hard worker' does not cost a web lookup."""
    t = re.sub(r"^\[[^\]]*\]\s*", "", str(text or "")).strip()
    return len(t.split()) >= 6 and bool(_CLAIMY.search(t))

def _extract_prompt(ws, question, answer):
    return f"""Interview: {ws.title} ({ws.kind}), organisation: {ws.company or 'n/a'}, role: {ws.position or 'n/a'}.
The panel asked: "{question[:240]}"
The candidate answered (speech-to-text, ignore misspellings): "{answer[:1200]}"
Pick at most 3 PUBLIC, checkable factual claims in the answer (prices, dates, figures, sizes, who did what, how a technology or rule works, official requirements). Ignore opinions, plans and private personal details. A personal claim is only worth picking when it is implausible on its face (for example "my mother is a CEO and we have one million dollars").
Return ONLY JSON: {{"claims": ["the claim in at most 20 words, with the numbers", ...]}}. If nothing is checkable return {{"claims": []}}."""

def _verify_prompt(ws, claim):
    return f"""Fact check ONE claim a candidate made in an interview. Organisation: {ws.company or 'n/a'}. Use current sources (today's date is in the web results).
Claim: "{claim}"
Search the web, then decide: "correct", "wrong" (sources clearly say otherwise), "implausible" (not a public fact, but cannot be true or is wildly out of proportion; explain why) or "unverifiable". Do any arithmetic yourself.
For "wrong" or "implausible" give the correct or realistic figure in "truth" (with the year) and the site in "source". Never invent a source; if you find none use "unverifiable".
Return ONLY JSON: {{"verdict": "correct|wrong|implausible|unverifiable", "truth": "the verified fact, at most 30 words", "source": "site name or URL"}}"""

def _one(ws, claim, secs):
    """Check one claim on its own thread (and so on its own key). Returns a claim dict, or None when it could not be checked in time."""
    try:
        with ai.budget(secs): text, _ = ai.factcheck_search(_verify_prompt(ws, claim), wait=6)
        d = ai.parse_json(text)
    except Exception: return None
    d = d if isinstance(d, dict) else {}
    v = str(d.get("verdict", "")).lower().strip(); v = v if v in VERDICTS else "unverifiable"
    truth, source = str(d.get("truth", ""))[:240], str(d.get("source", ""))[:120]
    if v in ("wrong", "implausible") and not truth: v = "unverifiable"   # a "wrong" verdict with no correct figure is not something the panel can use
    return {"claim": claim[:200], "verdict": v, "truth": truth, "source": source}

def check(ws, question, answer):
    """Returns {"claims": [...]} (possibly empty) or {} when the lookup failed. Two quick steps: pick the checkable claims (no web, about a second; most
    answers have none, so no web lookup is made at all), then check every claim at the same time, each on its own research key."""
    if not worth_checking(answer): return {"claims": [], "skipped": True}
    try:
        with ai.budget(5): text, _ = ai.call(_extract_prompt(ws, question, answer), json_mode=True, temperature=0.1, purpose="factcheck", max_tokens=300, light=True, wait=3, effort="low")
        d = ai.parse_json(text)
    except ai.AIError: return {}
    claims = [str(c).strip() for c in ((d.get("claims") if isinstance(d, dict) else None) or []) if isinstance(c, str) and len(str(c).strip()) >= 8][:3]
    if not claims: return {"claims": []}
    left = ai._left(); secs = max(3.0, min(9.0, left if left is not None else 9.0))
    futs = [_claim_pool.submit(_one, ws, c, secs) for c in claims]
    out = [r for r in (f.result() for f in futs) if r]
    return {"claims": out} if out else {}

def _compute(ws, question, answer):
    """Runs in a worker thread and touches no database: it only looks things up. The caller saves the result."""
    with ai.budget(max(4, float(getattr(settings, "FACTCHECK_SECONDS", 9)) + 6)):
        return check(ws, question, answer)

def _save(turn_id, result):
    from ..models import Turn
    Turn.objects.filter(pk=turn_id).update(factcheck=result or {"claims": [], "failed": True})

def _late(turn_id):
    """The check missed the interview's deadline: save it whenever it arrives, so the NEXT question can still use it."""
    def cb(fut):
        try: _save(turn_id, fut.result())
        except Exception: pass
        finally: connection.close()
    return cb

def start(turn, question):
    """Begin checking one candidate turn and wait up to FACTCHECK_SECONDS for the answer. On time: saved here, in the request. Late: saved by a callback when it finishes."""
    fut = _pool.submit(_compute, turn.session.workspace, str(question or ""), re.sub(r"^\[[^\]]*\]\s*", "", turn.text))
    try: result = fut.result(timeout=float(getattr(settings, "FACTCHECK_SECONDS", 9)))
    except FutTimeout: fut.add_done_callback(_late(turn.pk)); return
    except Exception: result = None
    _save(turn.pk, result); turn.factcheck = result or {"claims": [], "failed": True}

def pending_for_panel(turns):
    """Verified corrections the panel has not used yet, from the most recent candidate answers (newest first). Returns [(turn, claim_dict)]."""
    from ..models import Turn
    out = []
    for t in reversed([x for x in turns if x.role == "candidate"][-3:]):
        t.refresh_from_db(fields=["factcheck"])
        ck = t.factcheck or {}
        if ck.get("used"): continue
        for c in ck.get("claims", []):
            if c.get("verdict") in ("wrong", "implausible"): out.append((t, c))
    return out

def mark_used(pairs):
    from ..models import Turn
    for t in {p[0].pk: p[0] for p in pairs}.values():
        ck = dict(t.factcheck or {}); ck["used"] = True; Turn.objects.filter(pk=t.pk).update(factcheck=ck)

def all_findings(session):
    """Every wrong or implausible claim of a finished interview, for the report and the score."""
    out = []
    for t in session.turns.filter(role="candidate").order_by("id"):
        for c in (t.factcheck or {}).get("claims", []):
            if c.get("verdict") in ("wrong", "implausible"): out.append(dict(c, turn_id=t.id, offset=t.offset))
    return out
