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
from . import identity as ident, findings as fnd, questions as qq

VERDICTS = ("correct", "wrong", "implausible", "unverifiable")
_CLAIMY = re.compile(r"\d|million|billion|thousand|hundred|percent|per cent|%|dollar|naira|pound|euro|founded|invented|ceo|revenue|profit|price|cost|market|users|customers|"
                     r"law|rule|policy|visa|tuition|fee|salary|record|largest|biggest|first|only|never|always|year|\bin (19|20)\d\d", re.I)
_pool = ThreadPoolExecutor(max_workers=8)             # one worker per candidate answer being checked
_claim_pool = ThreadPoolExecutor(max_workers=12)      # one worker per claim, so the claims of an answer are checked side by side

def worth_checking(text):
    """Cheap filter so a plain 'yes' or 'I am a hard worker' does not cost a web lookup."""
    t = re.sub(r"^\[[^\]]*\]\s*", "", str(text or "")).strip()
    return len(t.split()) >= 6 and bool(_CLAIMY.search(t))

def _extract_prompt(ws, question, answer, profile):
    return f"""Interview: {ws.title} ({ws.kind}), organisation: {ws.company or 'n/a'}, role: {ws.position or 'n/a'}.
{ident.prompt_block(profile)}
The panel asked: "{question[:240]}"
The candidate answered (speech-to-text, ignore misspellings): "{answer[:1200]}"
Pick at most 3 checkable factual claims in the answer (prices, dates, figures, sizes, who did what, how a technology or rule works, official requirements). Ignore opinions and private personal details.
For each claim say whether it is about the candidate's OWN project, company, role or finances ("own_project"), or a public fact that can be checked without knowing who they are ("public_fact"). Keep the candidate's own words, including hedges such as "around" or "estimated".
Return ONLY JSON: {{"claims": [{{"claim": "the claim in at most 20 words, with the numbers and any hedge", "scope": "own_project|public_fact"}}]}}. If nothing is checkable return {{"claims": []}}."""

def _verify_prompt(ws, claim, profile):
    return f"""Fact check ONE claim a candidate made in an interview. Use current sources (today's date is in the web results).
{ident.prompt_block(profile)}
Claim: "{claim}"
Search the web, then decide: "correct", "wrong" (a cited source clearly says otherwise), "partial", "conflicting" (reliable sources disagree), or "unverifiable". Do any arithmetic yourself.
CRITICAL: a source only counts if it is about the SAME entity as the identity above. Companies and products often share a name. If the best source is about a different company, product or founders, report THAT entity in "source_entity", its own domain in "source_domain", and do not apply its facts to the candidate. A price quoted per workspace is not a price per user; a published price is not the candidate's cost; a projection or estimate is not a lie.
For "wrong" give the correct figure in "truth" (with the year). Never invent a source or a URL; if you find none use "unverifiable" with empty source fields.
Return ONLY JSON: {{"verdict": "correct|wrong|partial|conflicting|unverifiable", "truth": "the verified fact, at most 30 words", "source_url": "full URL", "source_title": "page title", "source_date": "publication or update date if shown",
"source_entity": "the company or product the source is about", "source_domain": "its domain", "source_description": "one line on what that entity does", "source_founders": ["names the source gives, if any"], "source_pricing_unit": "per user|per workspace|per request|token|monthly cost|revenue|other|"}}"""

def _one(ws, claim, scope, secs, profile):
    """Check one claim on its own thread (and so on its own key). Returns a CLASSIFIED finding (findings.classify), or None when it could not be checked in time.
    A claim about the candidate's own project is never searched against the public web while the project's identity is unverified: it becomes a clarification instead."""
    own = scope == "own_project" or fnd.scope_of(claim, profile) == fnd.OWN_PROJECT
    if own and profile.get("status") != ident.VERIFIED:
        f = fnd.classify(claim, "unverifiable", {}, profile)
        f["reason"] = "the project's identity is not verified, so this claim was not checked against other companies' sources; ask the candidate instead"
    else:
        try:
            with ai.budget(secs): text, _ = ai.factcheck_search(_verify_prompt(ws, claim, profile), wait=6)
            d = ai.parse_json(text)
        except Exception: return None
        d = d if isinstance(d, dict) else {}
        src = {"url": str(d.get("source_url", ""))[:300], "title": str(d.get("source_title", ""))[:200], "date": str(d.get("source_date", ""))[:40], "entity": str(d.get("source_entity", ""))[:160],
               "domain": str(d.get("source_domain", ""))[:120], "description": str(d.get("source_description", ""))[:300], "founders": d.get("source_founders") if isinstance(d.get("source_founders"), list) else [],
               "unit": {"per user": "per_user", "per workspace": "per_workspace", "per request": "per_request", "token": "token", "monthly cost": "monthly_operating", "revenue": "revenue"}.get(str(d.get("source_pricing_unit", "")).lower(), "")}
        f = fnd.classify(claim, str(d.get("verdict", "")).lower().strip(), src, profile, truth=str(d.get("truth", ""))[:240])
    f["panel_action"] = "confront" if (f["classification"] == fnd.VERIFIED_FALSE and f["penalty_eligible"]) else (
        "clarify" if f["claim_kind"] in (fnd.OWNERSHIP, fnd.FINANCIAL, fnd.ESTIMATE) and f["classification"] in (fnd.UNVERIFIED, fnd.WRONG_ENTITY, fnd.PARTIALLY_VERIFIED, fnd.OUTDATED) else "")
    f["ask"] = qq.clarification_for_claim(profile, claim) if f["panel_action"] == "clarify" else ""
    return f

def check(ws, question, answer, profile=None):
    """Returns {"claims": [...]} (possibly empty) or {} when the lookup failed. Two quick steps: pick the checkable claims (no web, about a second; most
    answers have none, so no web lookup is made at all), then check every claim at the same time, each on its own research key. profile: identity.build_profile()."""
    profile = profile or {}
    if not worth_checking(answer): return {"claims": [], "skipped": True}
    try:
        with ai.budget(5): text, _ = ai.call(_extract_prompt(ws, question, answer, profile), json_mode=True, temperature=0.1, purpose="factcheck", max_tokens=400, light=True, wait=3, effort="low")
        d = ai.parse_json(text)
    except ai.AIError: return {}
    raw = (d.get("claims") if isinstance(d, dict) else None) or []
    claims = []
    for c in raw:
        if isinstance(c, str) and len(c.strip()) >= 8: claims.append((c.strip(), ""))
        elif isinstance(c, dict) and isinstance(c.get("claim"), str) and len(c["claim"].strip()) >= 8: claims.append((c["claim"].strip(), str(c.get("scope", ""))))
    claims = claims[:3]
    if not claims: return {"claims": []}
    left = ai._left(); secs = max(3.0, min(9.0, left if left is not None else 9.0))
    futs = [_claim_pool.submit(_one, ws, c, sc, secs, profile) for c, sc in claims]
    out = [r for r in (f.result() for f in futs) if r]
    return {"claims": out} if out else {}

def _compute(ws, question, answer, profile):
    """Runs in a worker thread and touches no database: it only looks things up. The caller saves the result."""
    with ai.budget(max(4, float(getattr(settings, "FACTCHECK_SECONDS", 9)) + 6)):
        return check(ws, question, answer, profile)

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
    from . import agents   # imported here: agents imports this module
    ws = turn.session.workspace; profile = agents.identity_of(ws)   # the identity is read in this thread (it touches the database); the worker only looks things up
    fut = _pool.submit(_compute, ws, str(question or ""), re.sub(r"^\[[^\]]*\]\s*", "", turn.text), profile)
    try: result = fut.result(timeout=float(getattr(settings, "FACTCHECK_SECONDS", 9)))
    except FutTimeout: fut.add_done_callback(_late(turn.pk)); return
    except Exception: result = None
    _save(turn.pk, result); turn.factcheck = result or {"claims": [], "failed": True}

def pending_for_panel(turns):
    """What the panel has not used yet, from the most recent candidate answers (newest first). Returns [(turn, claim_dict)] for two kinds only: a VERIFIED FALSE claim about the correct entity
    (to confront) and a claim worth a clarifying question (an estimate, an unverified ownership or financial claim). Wrong-entity and unverified research is never handed over as a contradiction."""
    out = []
    for t in reversed([x for x in turns if x.role == "candidate"][-3:]):
        t.refresh_from_db(fields=["factcheck"])
        ck = t.factcheck or {}
        if ck.get("used"): continue
        for c in ck.get("claims", []):
            if c.get("panel_action") in ("confront", "clarify"): out.append((t, c))
    return out

def mark_used(pairs):
    from ..models import Turn
    for t in {p[0].pk: p[0] for p in pairs}.values():
        ck = dict(t.factcheck or {}); ck["used"] = True; Turn.objects.filter(pk=t.pk).update(factcheck=ck)

def all_findings(session):
    """Every checked claim of a finished interview, each with its classification (old rows without entity information are migrated to UNVERIFIED and cost nothing).
    Whether any of them reduces the score is decided only by findings.penalty_policy."""
    out = []
    for t in session.turns.filter(role="candidate").order_by("id"):
        for c in (t.factcheck or {}).get("claims", []):
            out.append(dict(fnd.migrate_legacy(c), turn_id=t.id, offset=t.offset))
    return out
