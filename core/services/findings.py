"""Research evidence: how an external finding is classified, and the only way it can ever touch a score. Pure Python: no database, network or AI.

Every finding records: the exact claim, the source URL and title, the date, WHICH ENTITY the source is about, the evidence, a confidence, and whether it applies to the
candidate's project. It is then given exactly one of seven classifications. Only a VERIFIED FALSE finding about the correct entity can ever reduce a score, and then
only through penalty_policy(), which is proportional, de-duplicated, capped, explained, and shown in the report. Estimates, hypotheticals and other companies' pricing
never reduce a score: they become a question about the candidate's assumptions instead."""
import re
from datetime import date

from . import identity

VERIFIED_TRUE, VERIFIED_FALSE, PARTIALLY_VERIFIED, UNVERIFIED, CONFLICTING, WRONG_ENTITY, OUTDATED = (
    "verified_true", "verified_false", "partially_verified", "unverified", "conflicting_sources", "wrong_entity", "outdated_information")
CLASSES = (VERIFIED_TRUE, VERIFIED_FALSE, PARTIALLY_VERIFIED, UNVERIFIED, CONFLICTING, WRONG_ENTITY, OUTDATED)
LABEL = {VERIFIED_TRUE: "Verified true", VERIFIED_FALSE: "Verified false", PARTIALLY_VERIFIED: "Partially verified", UNVERIFIED: "Unverified",
         CONFLICTING: "Conflicting sources", WRONG_ENTITY: "Wrong entity", OUTDATED: "Outdated information"}
# Only this class may lower a score. The other six are shown to the candidate as research, never as a mark against them.
PENALTY_CLASSES = (VERIFIED_FALSE,)

# What the claim is about.
OWN_PROJECT, PUBLIC_FACT = "own_project", "public_fact"
# What kind of statement it is.
FACT, ESTIMATE, OWNERSHIP, FINANCIAL = "fact", "estimate", "ownership", "financial"

_ESTIMATE = re.compile(r"\b(around|about(?= [$€£]?\d)|roughly|approximately|approx\.?|estimate[sd]?|estimated|expect(ed)?|i think|i guess|probably|maybe|could be|would be|should be|will be|"
                       r"projected|projection|forecast|assum(e|ing|ption)|hypothetical|target|aim(s|ing)? (to|for)|if we|we plan|plan(ning)? to|in the future|rough(ly)?|ballpark)\b", re.I)
_OWNERSHIP = re.compile(r"\b(i am|i'm|i was|i\s+co-?)?\s*(the |a |an )?(co-?)?(founder|founded|ceo|owner|created|started)\b|\bmy (own )?(startup|company|project|business)\b|\bi built\b|\bi (made|created) (it|this)\b", re.I)
_MONEY = re.compile(r"[$€£₦]\s?\d|\d\s?(usd|dollars?|naira|euros?|pounds?|k\b|million|billion)|\b(price|pricing|cost|costs|revenue|profit|margin|salary|budget|funding|raised|valuation|arr|mrr)\b", re.I)

# Units a price or cost can be quoted in. A figure quoted in one unit does not contradict the same figure in another.
UNITS = [("per_user", r"per[- ]user|/user|each user|per seat|per student|per learner|per customer|per member"),
         ("per_workspace", r"per[- ]workspace|/workspace|per team|per organi[sz]ation|per account|per project"),
         ("per_request", r"per (api )?(request|call|query|generation|lesson|prompt)|/request|/call"),
         ("token", r"\btokens?\b|token (cost|usage|consumption)|per (1k|1,000|million|1m) tokens"),
         ("monthly_operating", r"operating cost|running cost|monthly (cost|spend|bill|burn)|burn rate|infrastructure cost|hosting cost"),
         ("revenue", r"\brevenue\b|\barr\b|\bmrr\b|\bsales\b|turnover"), ("margin", r"margin|profit"),
         ("projection", r"projected|projection|forecast|hypothetical|scenario|if we|at scale")]


def claim_kind(text):
    """fact | estimate | ownership | financial. An ownership statement outranks the rest; a hedged or forward-looking figure is an estimate."""
    t = str(text or "")
    if _OWNERSHIP.search(t) and re.search(r"\b(founder|founded|ceo|owner|co-?found|created|started|my (own )?(startup|company|project|business)|i built)\b", t, re.I): return OWNERSHIP
    if _ESTIMATE.search(t): return ESTIMATE
    if _MONEY.search(t): return FINANCIAL
    return FACT


def financial_unit(text):
    """The unit a price, cost or revenue figure is quoted in (per_user, per_workspace, per_request, token, monthly_operating, revenue, margin, projection), or ''."""
    t = str(text or "")
    for key, rx in UNITS:
        if re.search(rx, t, re.I): return key
    return ""


def units_conflict(claim_unit, source_unit):
    """A comparison is only a contradiction when both sides use the same unit. Different units (per user against per workspace) say nothing about each other."""
    return bool(claim_unit and source_unit and claim_unit != source_unit)


def scope_of(text, p=None):
    """own_project when the claim is about the candidate's own project, company, role or finances; public_fact when it is checkable without knowing who they are.
    A price, cost, revenue or estimate in an interview about the candidate's own project or startup is about THEIR product, so it can never be checked against a published price of some other company."""
    t = str(text or""); kind = claim_kind(t); first_person = bool(re.search(r"\b(my|our|we|i|i'm|we're|us)\b", t, re.I))
    if kind == OWNERSHIP: return OWN_PROJECT
    owner = bool(p and (p.get("candidate_owns") or p.get("entity_type") in ("own_startup", "hackathon_project")))
    if kind in (FINANCIAL, ESTIMATE) and (owner or first_person): return OWN_PROJECT
    if first_person and re.search(r"\b(users?|customers?|traction|team|built|launched|product|startup|app|pipeline|architecture|stack|revenue|cost|price|pricing)\b", t, re.I): return OWN_PROJECT
    if p and p.get("name") and re.search(re.escape(p["name"]), t, re.I) and p.get("candidate_owns"): return OWN_PROJECT
    return PUBLIC_FACT


def _year(s):
    ys = [int(y) for y in re.findall(r"\b(20\d\d|19\d\d)\b", str(s or ""))]
    return max(ys) if ys else 0


def is_outdated(src_date, claim_kind_=FACT, today=None, max_years=2):
    """A source more than max_years old is outdated for time-sensitive claims (prices, costs, revenue, current roles). Settled facts do not age."""
    y = _year(src_date); today = today or date.today()
    return bool(y) and claim_kind_ in (FINANCIAL, OWNERSHIP) and today.year - y > max_years


def _key(text):
    """A stable identity for 'the same statement', so repeating it is not punished twice: its numbers and its content words."""
    nums = sorted(set(re.findall(r"\d[\d,.]*", str(text or ""))))
    words = sorted(set(identity.keywords(text, 12)))
    return "|".join(nums) + "#" + " ".join(words[:8])


def similar_claims(a, b):
    """Two claims are the same statement when they share their figures and most of their content words."""
    na, nb = set(re.findall(r"\d[\d,.]*", str(a or ""))), set(re.findall(r"\d[\d,.]*", str(b or "")))
    if na != nb: return False
    ka, kb = set(identity.keywords(a)), set(identity.keywords(b))
    return bool(ka and kb) and len(ka & kb) / min(len(ka), len(kb)) >= 0.5


def classify(claim, raw_verdict, source, profile, today=None, truth=""):
    """The one place a finding gets its classification. Returns a complete finding dict.
    raw_verdict: what the lookup said ("correct", "wrong", "partial", "implausible", "conflicting", "unverifiable"), which is advice, not the final word.
    source: {url, title, date, entity, domain, description, founders, industry, country, type, pricing, unit, snippet}. profile: identity.build_profile()."""
    source = source or {}; profile = profile or {}
    kind = claim_kind(claim); scope = scope_of(claim, profile); unit = financial_unit(claim); sunit = source.get("unit") or financial_unit(" ".join(str(source.get(k) or "") for k in ("pricing", "description", "snippet")))
    m = identity.match_source(profile, source) if source.get("url") or source.get("domain") else {"verdict": identity.UNKNOWN, "same": [], "different": [], "reason": "no source was found"}
    cls, why, applies, conf = UNVERIFIED, "", False, "low"
    has_src = bool(str(source.get("url") or "").strip()) and bool(str(source.get("title") or source.get("entity") or "").strip())
    raw = str(raw_verdict or "").lower()
    needs_assumptions = False
    if not has_src:
        cls, why = UNVERIFIED, "no source was found that can be cited"
    elif scope == OWN_PROJECT and m["verdict"] == identity.DIFFERENT:
        cls, why = WRONG_ENTITY, f"the source describes a different entity ({m['reason']}); its facts do not apply to the candidate's project"
    elif scope == OWN_PROJECT and m["verdict"] != identity.SAME:
        cls, why = UNVERIFIED, "the project's identity is not verified, so no source can be applied to it; " + m["reason"]
        needs_assumptions = kind in (ESTIMATE, FINANCIAL)
        if profile.get("status") != identity.VERIFIED: why += " (add a website, repository or submission link to verify it)"
    elif is_outdated(source.get("date"), kind, today):
        cls, why, applies = OUTDATED, f"the source is from {_year(source.get('date'))} and the claim is time-sensitive", m["verdict"] == identity.SAME or scope == PUBLIC_FACT
    elif raw in ("conflicting", "conflict", "mixed"):
        cls, why, applies = CONFLICTING, "sources disagree", True
    elif raw in ("partial", "partially_correct", "partly"):
        cls, why, applies = PARTIALLY_VERIFIED, "the source supports part of the claim", True
    elif raw == "correct":
        cls, why, applies = VERIFIED_TRUE, "the source supports the claim", True
    elif raw in ("wrong", "implausible"):
        applies = True
        if kind == ESTIMATE:
            cls, why, needs_assumptions = UNVERIFIED, "the candidate gave an estimate or projection, which a published figure cannot disprove; ask for the assumptions behind it", True
        elif kind == FINANCIAL and units_conflict(unit, sunit):
            cls, why, needs_assumptions = PARTIALLY_VERIFIED, f"the source quotes a figure {sunit.replace('_', ' ')}, the candidate {unit.replace('_', ' ')}: different units do not contradict each other", True
        elif kind == FINANCIAL and scope == OWN_PROJECT and not (m["verdict"] == identity.SAME):
            cls, why, needs_assumptions = UNVERIFIED, "another company's published price is not the candidate's cost", True
        elif raw == "implausible" and scope == OWN_PROJECT:
            cls, why, needs_assumptions = UNVERIFIED, "an implausible but unverifiable personal claim: ask for evidence, do not mark it false", True
        elif not str(truth or "").strip():
            cls, why = UNVERIFIED, "the lookup gave no verified figure to contradict the claim"
        else:
            cls, why = VERIFIED_FALSE, "a cited source for the correct entity (or a public fact) contradicts the claim"
    else:
        cls, why = UNVERIFIED, "nothing was found that confirms or contradicts the claim"
    if cls in (VERIFIED_TRUE, VERIFIED_FALSE, PARTIALLY_VERIFIED, CONFLICTING):
        conf = "high" if (m["verdict"] == identity.SAME or scope == PUBLIC_FACT and str(source.get("url") or "").startswith("http")) and source.get("date") else "medium"
        if scope == PUBLIC_FACT and not source.get("date"): conf = "medium"
    elif cls in (OUTDATED, WRONG_ENTITY): conf = "medium"
    f = {"claim": str(claim)[:300], "claim_kind": kind, "scope": scope, "unit": unit, "classification": cls, "label": LABEL[cls], "reason": why,
         "source_url": str(source.get("url") or "")[:300], "source_title": str(source.get("title") or "")[:200], "source_date": str(source.get("date") or "")[:40],
         "source_entity": str(source.get("entity") or source.get("domain") or "")[:160], "evidence": str(truth or "")[:300] if cls not in (WRONG_ENTITY,) else str(source.get("description") or truth or "")[:300],
         "confidence": conf, "applies_to_candidate": bool(applies and cls in (VERIFIED_TRUE, VERIFIED_FALSE, PARTIALLY_VERIFIED, CONFLICTING)),
         "entity_match": m, "needs_assumptions": needs_assumptions, "penalty_eligible": cls in PENALTY_CLASSES and conf in ("medium", "high") and kind != ESTIMATE}
    # legacy fields the panel and older reports read
    f["verdict"] = {VERIFIED_FALSE: "wrong", VERIFIED_TRUE: "correct"}.get(cls, "unverifiable"); f["truth"] = f["evidence"] if cls == VERIFIED_FALSE else ""; f["source"] = f["source_title"] or f["source_url"]
    return f


def migrate_legacy(c):
    """An old fact-check row ({claim, verdict, truth, source}) has no entity information, so it can never be proven to be about the right entity: it is UNVERIFIED and carries no penalty."""
    if isinstance(c, dict) and c.get("classification") in CLASSES: return c
    c = c if isinstance(c, dict) else {}
    return {"claim": str(c.get("claim", ""))[:300], "claim_kind": claim_kind(c.get("claim")), "scope": scope_of(c.get("claim")), "unit": financial_unit(c.get("claim")), "classification": UNVERIFIED, "label": LABEL[UNVERIFIED],
            "reason": "this check was made before entity matching existed, so it cannot be applied to the candidate", "source_url": "", "source_title": str(c.get("source", ""))[:200], "source_date": "", "source_entity": "",
            "evidence": str(c.get("truth", ""))[:300], "confidence": "low", "applies_to_candidate": False, "entity_match": {"verdict": identity.UNKNOWN, "same": [], "different": [], "reason": "legacy record"},
            "needs_assumptions": False, "penalty_eligible": False, "verdict": "unverifiable", "truth": "", "source": str(c.get("source", ""))[:200]}


# ---------- the only route from a research finding to a score ----------
SEVERITY = {"minor": 2, "moderate": 4, "major": 8}
CONFIDENCE_FACTOR = {"high": 1.0, "medium": 0.5}
MAX_TOTAL = 15   # however many verified errors there are, factual accuracy alone can cost at most this many points


def materiality(f, kind="", position=""):
    """How serious a verified error is. major: a credential, role or ownership claim, or a core figure the whole answer rests on. moderate: a figure that bears on the role. minor: anything else."""
    t = str(f.get("claim", "")).lower()
    if f.get("claim_kind") == OWNERSHIP or re.search(r"\b(degree|phd|certified|certification|licen[cs]e|years? of experience|worked at|employed|graduated)\b", t): return "major"
    if f.get("claim_kind") == FINANCIAL or re.search(r"\d", t) and re.search(r"\b(users|revenue|funding|market|customers|accuracy|latency|scale)\b", t): return "moderate"
    return "minor"


def penalty_policy(findings, kind="", position=""):
    """Turn findings into score deductions, or none. Each deduction is: linked to ONE verified-false finding about the correct entity, documented, proportional to its seriousness
    and to the source's confidence, never repeated for the same statement, and capped. Returns {"items": [...], "total": int, "skipped": [...]}; skipped says why a finding cost nothing."""
    items, skipped, seen = [], [], []
    for f in findings:
        f = migrate_legacy(f)
        if not f["penalty_eligible"] or not f["applies_to_candidate"]:
            skipped.append({"claim": f["claim"], "classification": f["classification"], "why": f["reason"] or "not a verified contradiction about the candidate's own entity"}); continue
        if any(similar_claims(f["claim"], s) or _key(f["claim"]) == _key(s) for s in seen):
            skipped.append({"claim": f["claim"], "classification": f["classification"], "why": "the same statement was already counted once"}); continue
        seen.append(f["claim"])
        sev = materiality(f, kind, position); pts = max(1, int(round(SEVERITY[sev] * CONFIDENCE_FACTOR.get(f["confidence"], 0.5))))
        items.append({"claim": f["claim"], "points": pts, "severity": sev, "confidence": f["confidence"], "source_url": f["source_url"], "source_title": f["source_title"], "evidence": f["evidence"],
                      "reason": f"Verified false about the correct entity ({sev} error, {f['confidence']} confidence): {f['evidence'] or f['reason']}"})
    total = 0
    items.sort(key=lambda i: -i["points"]); room = MAX_TOTAL   # the cap is applied in order of seriousness so the largest errors keep their points
    for it in items:
        it["points"] = min(it["points"], room); room -= it["points"]; total += it["points"]
    return {"items": [i for i in items if i["points"] > 0], "total": total, "skipped": skipped, "cap": MAX_TOTAL}


def summarise(findings):
    """Counts per classification, for the report and tests."""
    out = {c: 0 for c in CLASSES}
    for f in findings: out[migrate_legacy(f)["classification"]] += 1
    return out
