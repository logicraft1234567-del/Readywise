"""The scoring engine. The AI judges EVIDENCE (what the candidate actually said or did, against explicit criteria); this module,
plain Python with no AI, turns those judgements into the numbers. Nothing here can be raised or lowered by how friendly the AI felt.

Three things are kept apart, as a fair assessment must:
  PERFORMANCE  what the candidate demonstrated (0 to 100, per competency, per dimension, overall)
  EVIDENCE     how much of the role was actually assessed (coverage) and how far the score can be trusted (confidence)
  REQUIREMENTS the critical competencies of the opportunity, each reported as met, not met or not assessed

Every type of interview has its OWN dimensions. A visa officer does not test technical skill, so a visa interview has no technical
dimension; it has purpose, consistency, funds and ties instead. A dimension that does not matter for a type is simply not part of it.

Missing evidence is never turned into a low score: a competency the interview did not reach is left out and the weights of the
rest are rescaled, while the report says the confidence is lower.

Fairness rules enforced here (each has a test):
  * the final score is calculated by this module, never by the AI;
  * the weights depend on the ROLE (weights_for), not only on the type of interview;
  * "not assessed" and "insufficient evidence" are never zero and never a deduction;
  * there are no score floors; a score is never raised to make a rating look consistent;
  * the ONLY deductions are the documented penalties handed in by findings.penalty_policy (verified, entity-matched, proportional, de-duplicated, capped);
  * a critical requirement the interview did not reach is NOT ASSESSED, never "failed"."""
import re

# Every dimension that any type of interview can use: key -> (default label, what it means)
DIM_DEFAULT = {
    "technical": ("Technical or domain competence", "can solve the actual problems the role requires"),
    "reasoning": ("Problem-solving and reasoning", "reasons through unfamiliar problems, explains decisions, handles constraints"),
    "execution": ("Role-specific execution", "can do the responsibilities and tasks of the actual position, with concrete results"),
    "communication": ("Communication", "explains their thinking clearly and appropriately"),
    "judgment": ("Judgment and decision-making", "sees trade-offs, risks, uncertainty and consequences"),
    "professional": ("Professional behaviour", "teamwork, accountability, honesty and professional conduct"),
    "motivation": ("Motivation and fit", "genuine, specific reasons for this opportunity and for choosing it now"),
    "potential": ("Learning ability and potential", "learns quickly, takes feedback, shows curiosity and growth"),
    "purpose": ("Purpose and plans", "a clear purpose and a realistic plan for what they will do"),
    "consistency": ("Consistency and credibility", "the answers fit together, fit the documents, and are believable"),
    "ties": ("Funds and ties", "a credible way to pay and real reasons to return home"),
    "impact": ("Achievement and impact", "what they really achieved and the difference it made"),
    "vision": ("Vision and originality", "original ideas and a clear direction for their work"),
    "market": ("Market and business case", "knows the customers, market, competitors and how the business earns"),
    "traction": ("Traction and proof", "real evidence it works: users, revenue, results"),
}

# The dimensions of each interview type, with their weights (each type adds to 100) and, where the type needs different words, its own label and meaning.
# Row: (dimension key, weight, label or None, meaning or None)
KIND_DIMS = {
    "employment": [("technical", 30, None, None), ("reasoning", 20, None, None), ("execution", 20, None, None),
                   ("communication", 15, None, None), ("judgment", 10, None, None), ("professional", 5, None, None)],
    "startup": [("technical", 25, None, None), ("reasoning", 15, None, None),
                ("execution", 25, "Ownership and shipping", "built and shipped things end to end, with speed and initiative"),
                ("communication", 10, None, None),
                ("judgment", 15, "Judgment under constraints", "makes trade-offs with little time, money or certainty"),
                ("motivation", 10, "Why this startup", "honest, specific reasons for this startup and this stage")],
    "internship": [("technical", 20, "Skills and foundations", "has the basics of the field and can apply them"),
                   ("potential", 25, None, None),
                   ("execution", 10, "Experience and projects", "what they actually did in projects, study or work"),
                   ("communication", 20, None, None), ("motivation", 15, None, None),
                   ("professional", 10, "Reliability and attitude", "reliable, respectful, open to feedback")],
    "graduate": [("technical", 20, "Skills and foundations", "has the basics of the field and can apply them"),
                 ("reasoning", 20, None, None), ("potential", 20, None, None), ("communication", 15, None, None),
                 ("motivation", 10, None, None), ("professional", 15, "Teamwork and attitude", "teamwork, reliability, openness to feedback")],
    "admission": [("technical", 25, "Academic and subject ability", "understands the subject and can think in it"),
                  ("reasoning", 25, "Critical thinking", "thinks independently, questions ideas, reasons to a conclusion"),
                  ("motivation", 20, "Motivation and fit with the programme", "genuine reasons for this subject and this programme"),
                  ("communication", 15, None, None),
                  ("professional", 15, "Character and maturity", "honest, mature, ready for independent study")],
    "scholarship": [("technical", 15, "Academic and subject ability", "knows their field and what they will study"),
                    ("impact", 25, None, None),
                    ("purpose", 15, "Goals and plan", "clear goals, and a realistic plan to reach them and to give back"),
                    ("communication", 20, None, None),
                    ("professional", 25, "Character and values", "integrity, resilience, commitment to others")],
    "visa": [("purpose", 25, "Purpose of the trip, study or job", "a clear, specific purpose and a plan that makes sense"),
             ("consistency", 25, None, None),
             ("ties", 20, None, None),
             ("communication", 15, "Clear, direct answers", "answers the question asked, simply and directly"),
             ("professional", 15, "Honesty and composure", "truthful and calm under direct questions")],
    "fellowship": [("technical", 25, "Expertise in the field", "depth of knowledge in the field"),
                   ("vision", 20, None, None),
                   ("impact", 20, "Track record and impact", "what they have delivered and the difference it made"),
                   ("communication", 15, None, None),
                   ("purpose", 10, "Plan for the fellowship", "a credible plan for the fellowship period"),
                   ("professional", 10, "Character and collaboration", "integrity and ability to work with others")],
    "pitch": [("market", 20, None, None), ("traction", 20, None, None),
              ("technical", 10, "Product knowledge", "knows exactly what the product does and how it works"),
              ("communication", 25, "Pitch and story", "tells the story clearly and persuasively"),
              ("judgment", 20, "Judgment on risk", "honest about risks, competitors and what they do not know yet"),
              ("professional", 5, "Honesty and coachability", "straight about gaps, takes hard questions well")],
    "hackathon": [("technical", 30, "Technical depth", "what truly works in the demo and how it is built"),
                  ("execution", 25, "Working result", "a real, working solution to the problem"),
                  ("reasoning", 10, None, None),
                  ("communication", 20, "Demo and story", "explains the idea, the demo and the team story clearly"),
                  ("judgment", 10, None, None), ("professional", 5, "Teamwork", "how the team worked together")],
    "certification": [("technical", 55, "Knowledge of the subject", "correct, precise knowledge of the material tested"),
                      ("reasoning", 30, "Applying the knowledge", "applies concepts to new scenarios and explains why"),
                      ("judgment", 15, "Judgment in practice", "chooses the right approach and sees the risks")],
}

# The five-level scale every score uses.
LEVELS = [(90, "Exceptional"), (75, "Strong"), (60, "Competent"), (40, "Developing"), (20, "Beginning"), (0, "No demonstrated ability")]
MET = 60   # a critical requirement is met from the Competent level up


def level_for(score):
    return next(l for lo, l in LEVELS if score >= lo)


def kind_key(kind):
    return kind if kind in KIND_DIMS else "employment"


def dims_for(kind):
    """The dimension keys of this type of interview, in order."""
    return [r[0] for r in KIND_DIMS[kind_key(kind)]]


def weights(kind):
    return {r[0]: r[1] for r in KIND_DIMS[kind_key(kind)]}


TABLE_LABELS = {   # the names shown for each scoring area, exactly as published in the scoring table
    "employment": {"technical": "Technical", "reasoning": "Reasoning", "execution": "Execution", "communication": "Communication", "judgment": "Judgment", "professional": "Professional"},
    "startup": {"technical": "Technical", "reasoning": "Reasoning", "execution": "Ownership and shipping", "communication": "Communication", "judgment": "Judgment under constraints", "motivation": "Why this startup"},
    "internship": {"technical": "Skills and foundations", "potential": "Learning ability and potential", "execution": "Experience and projects", "communication": "Communication", "motivation": "Motivation and fit", "professional": "Reliability and attitude"},
    "graduate": {"technical": "Skills and foundations", "reasoning": "Reasoning", "potential": "Learning ability and potential", "communication": "Communication", "motivation": "Motivation and fit", "professional": "Teamwork and attitude"},
    "admission": {"technical": "Academic ability", "reasoning": "Critical thinking", "motivation": "Motivation and fit with the programme", "communication": "Communication", "professional": "Character and maturity"},
    "scholarship": {"technical": "Academic ability", "impact": "Achievement and impact", "purpose": "Goals and plan", "communication": "Communication", "professional": "Character and values"},
    "fellowship": {"technical": "Expertise", "vision": "Vision and originality", "impact": "Track record and impact", "communication": "Communication", "purpose": "Plan for the fellowship", "professional": "Character and collaboration"},
    "pitch": {"market": "Market and business case", "traction": "Traction and proof", "technical": "Product knowledge", "communication": "Pitch and story", "judgment": "Judgment on risk", "professional": "Honesty and coachability"},
    "hackathon": {"technical": "Technical depth", "execution": "Working result", "reasoning": "Reasoning", "communication": "Demo and story", "judgment": "Judgment", "professional": "Teamwork"},
    "certification": {"technical": "Knowledge of the subject", "execution": "Applying the knowledge", "judgment": "Judgment in practice"},
}


def dim_info(kind):
    """{dimension: (label, meaning)} for the dimensions of this type of interview."""
    tl = TABLE_LABELS.get(kind_key(kind), {})
    return {k: (tl.get(k) or lab or DIM_DEFAULT[k][0], mean or DIM_DEFAULT[k][1]) for k, _, lab, mean in KIND_DIMS[kind_key(kind)]}


def dim_keys_str(kind):
    return "|".join(dims_for(kind))


def prompt_hint(kind):
    """Tells the rubric writer which dimensions this type of interview has, what each means and how much it weighs."""
    w, info = weights(kind), dim_info(kind)
    return "; ".join(f"{k} = {info[k][0]} ({info[k][1]}; weight {w[k]}%)" for k in dims_for(kind))


_KEYS = [
    ("consistency", r"consisten|credib|contradict|story|documents?\b|truth"),
    ("ties", r"\bties\b|fund|financ|afford|return|sponsor|pay\b|budget"),
    ("purpose", r"purpose|goal|plan|itinerary|intent|why (study|travel|visit)|objective"),
    ("market", r"market|customer|compet|business (case|model)|pricing|revenue model"),
    ("traction", r"traction|users|revenue|growth|proof|validation|metrics"),
    ("vision", r"vision|original|novel|research direction|innovation|ideas?\b"),
    ("impact", r"impact|achievement|result|track record|contribution|leadership|give back|community"),
    ("potential", r"potential|learning|curios|adaptab|coachab|growth mindset"),
    ("motivation", r"motivation|fit|why this|interest|commitment|passion"),
    ("professional", r"honest|integrity|ethic|conduct|teamwork|team ?work|collaborat|accountab|reliab|attitude|character|values|resilien|compos|maturity"),
    ("communication", r"communicat|clarity|explain|storytell|present|articulat|listening|persuas|demo and story|pitch"),
    ("judgment", r"judg|trade-?off|risk|decision|priorit|uncertain|stakeholder"),
    ("execution", r"execut|deliver|ship|own(ership)?|working|experience|project|initiative"),
    ("reasoning", r"reason|problem|analy|logic|think|debug|approach|strateg|critical"),
    ("technical", r"technical|technology|domain|knowledge|skill|code|coding|system|architecture|data|engineering|subject|academic|fundamental|product|finance"),
]


def dimension_for(comp, kind=None):
    """The dimension of a rubric competency within THIS type of interview: the one the rubric writer chose if it belongs to the type, otherwise inferred
    from the competency's words, otherwise the type's heaviest dimension. A visa competency can never land in a dimension a visa interview does not have."""
    ks = dims_for(kind); d = comp.get("dimension")
    if d in ks: return d
    t = f"{comp.get('name', '')} {comp.get('key', '')}".lower()
    for dim, rx in _KEYS:
        if dim in ks and re.search(rx, t): return dim
    w = weights(kind); return max(ks, key=lambda k: w[k])


def is_critical(comp):
    """A requirement the opportunity cannot do without: marked by the rubric, or weighted 8 or more of 10."""
    if isinstance(comp.get("critical"), bool): return comp["critical"]
    try: return int(comp.get("weight", 5)) >= 8
    except (TypeError, ValueError): return False


def criteria_score(criteria):
    """One competency's score from its criteria: sum(score x weight) / sum(weight), over the criteria that were actually assessed.
    Returns (score or None, coverage 0 to 1). A criterion the interview never established is left out, not counted as zero."""
    tot = sum(c["weight"] for c in criteria) or 0
    got = [c for c in criteria if isinstance(c.get("score"), (int, float))]
    gw = sum(c["weight"] for c in got)
    if not got or not tot: return None, 0.0
    return sum(c["score"] * c["weight"] for c in got) / gw, gw / tot


ROLE_PROFILES = [   # (name, pattern on the position and job description, multiplier per dimension). Dimensions a type of interview does not have are ignored.
    ("founder", r"\bfound(er|ing)\b|\bco-?founder\b|\bceo\b|\bentrepreneur|\bowner\b|\bstartup (lead|builder)\b",
     {"market": 1.25, "traction": 1.25, "execution": 1.2, "judgment": 1.25, "technical": 0.9, "communication": 1.0, "professional": 0.9}),
    ("engineering", r"\b(back-?end|front-?end|full[- ]?stack|software|devops|sre|site reliability|platform|data engineer|machine learning|ml engineer|ai engineer|developer|programmer|engineer(ing)?)\b",
     {"technical": 1.35, "reasoning": 1.25, "execution": 1.05, "communication": 0.8, "judgment": 1.0, "professional": 0.8, "potential": 1.0}),
    ("data", r"\b(data scientist|data analyst|analyst|statistic|research scientist|bi developer)\b",
     {"technical": 1.25, "reasoning": 1.35, "communication": 1.0, "judgment": 1.1, "execution": 0.95}),
    ("sales", r"\b(sales|account executive|business development|customer success|account manager|growth)\b",
     {"communication": 1.45, "execution": 1.2, "judgment": 1.0, "motivation": 1.1, "technical": 0.6, "reasoning": 0.9}),
    ("product", r"\b(product manager|product owner|program manager|project manager|operations|strategy)\b",
     {"judgment": 1.4, "communication": 1.2, "reasoning": 1.1, "execution": 1.1, "technical": 0.7}),
    ("design", r"\b(designer|ux|ui|creative|brand)\b", {"execution": 1.3, "communication": 1.2, "technical": 0.9, "reasoning": 0.9}),
    ("leadership", r"\b(director|head of|vp\b|vice president|manager|lead)\b", {"professional": 1.3, "judgment": 1.3, "communication": 1.15, "technical": 0.8}),
]


def role_profile(position="", description=""):
    """Which role archetype this opportunity is, from the position first and the description second. '' when nothing matches (the type's own weights then apply unchanged)."""
    pos, desc = str(position or "").lower(), str(description or "")[:1200].lower()
    for text in (pos, desc):
        if not text.strip(): continue
        for name, rx, _ in ROLE_PROFILES:
            if re.search(rx, text): return name
    return ""


def _normalise(raw):
    """Scale to exactly 100 with whole numbers (largest remainder), so the weights shown are the weights used."""
    tot = sum(raw.values()) or 1.0; exact = {k: v * 100.0 / tot for k, v in raw.items()}
    fl = {k: int(v) for k, v in exact.items()}; left = 100 - sum(fl.values())
    for k in sorted(exact, key=lambda k: exact[k] - fl[k], reverse=True)[:left]: fl[k] += 1
    return fl


def weights_for(kind, position="", description=""):
    """The weights are exactly the published scoring table for the interview type (each adds to 100). They are NOT shifted by role: the same table is used for every position."""
    return dict(weights(kind))


_CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def _dim_conf(group, cov):
    if not group: return "low"
    ranks = [_CONF_RANK.get(c.get("confidence"), 0) for c in group]; avg = sum(ranks) / len(ranks)
    ev = sum(len(c.get("evidence") or []) for c in group) / len(group)
    if cov < 0.5 or avg < 0.6: return "low"
    return "high" if avg >= 1.6 and ev >= 1.5 and cov >= 0.75 else "medium"


def compute(comps, kind, answered=0, asked_n=0, penalties=None, position="", description="", excluded_turns=0):
    """comps: the validated competency rows (key, name, weight, rating, score, evidence, missing, confidence, dimension, critical, coverage).
    penalties: the dict from findings.penalty_policy (its "items" are the only deductions that exist; anything else, including the old integer arguments, is ignored).
    Returns the full breakdown. overall is None when the interview gave nothing to score: that is inconclusive, never zero."""
    w = weights_for(kind, position, description); info = dim_info(kind); keys = dims_for(kind)
    scored = [c for c in comps if isinstance(c.get("score"), (int, float))]
    by_dim = {d: [] for d in keys}
    for c in scored: by_dim[dimension_for(c, kind)].append(c)

    dims = []
    for d in keys:
        group = by_dim[d]; allc = [c for c in comps if dimension_for(c, kind) == d]
        base = {"key": d, "name": info[d][0], "meaning": info[d][1], "weight": w[d], "competencies": [c["name"] for c in allc]}
        if not group:   # nothing scored here: either the rubric never covered it (not assessed) or it did and the interview gave too little (insufficient evidence). Neither is a score.
            dims.append(dict(base, score=None, level="", assessed=False, state="insufficient_evidence" if allc else "not_assessed", confidence="low", coverage=0, evidence=[],
                             missing=[m for c in allc for m in (c.get("missing") or [])][:3])); continue
        cw = sum(c["weight"] for c in group) or 1
        sc = sum(c["score"] * c["weight"] for c in group) / cw
        cov = sum(c["weight"] * (c.get("coverage") if isinstance(c.get("coverage"), (int, float)) else 1.0) for c in group) / cw
        dims.append(dict(base, score=round(sc), level=level_for(sc), assessed=True, state="assessed", confidence=_dim_conf(group, cov), coverage=int(round(cov * 100)),
                         evidence=[e for c in group for e in (c.get("evidence") or [])][:3], missing=[m for c in group for m in (c.get("missing") or [])][:3]))

    used = [x for x in dims if x["assessed"] and x["weight"] > 0]
    role_covered = sum(x["weight"] for x in used)   # the share of the role (by weight) the interview actually assessed
    overall = None
    if used:   # rescaled over the dimensions that were assessed, so a dimension the interview never reached is not a zero
        overall = sum(x["score"] * x["weight"] for x in used) / (role_covered or 1)
    ratio = min(1.0, answered / asked_n) if asked_n else (1.0 if scored else 0.0)
    cap = None
    if overall is not None and asked_n:
        if ratio < 0.3: cap = 40       # the candidate WAS asked and gave nothing: that is evidence too, but the score cannot be high
        elif ratio < 0.5: cap = 60
        if cap is not None: overall = min(overall, cap)
    pen = penalties if isinstance(penalties, dict) else {"items": [], "total": 0, "skipped": []}
    penalty = int(pen.get("total", 0) or 0) if overall is not None else 0
    before = overall
    if overall is not None: overall = max(0.0, min(98.0, overall - penalty))

    # coverage: the share of the opportunity's competency weight that was really assessed (a competency counts by how many of its criteria were)
    tw = sum(c["weight"] for c in comps) or 0
    cov = (sum(c["weight"] * (c.get("coverage") if isinstance(c.get("coverage"), (int, float)) else 1.0) for c in scored) / tw) if tw else 0.0
    ev_n = [len(c.get("evidence") or []) for c in scored]
    low_conf = sum(1 for c in scored if c.get("confidence") == "low")
    if len(scored) < 2 or cov < 0.4 or ratio < 0.5 or role_covered < 40: conf = "low"
    elif cov >= 0.75 and ratio >= 0.7 and role_covered >= 70 and (sum(ev_n) / len(ev_n)) >= 1.5 and low_conf <= len(scored) // 3: conf = "high"
    else: conf = "medium"

    crit = []
    for c in comps:
        if not is_critical(c): continue
        s = c.get("score")
        if not isinstance(s, (int, float)): st = "not_assessed"
        elif s >= MET: st = "met"
        elif c.get("confidence") == "low" and (c.get("coverage") or 0) < 0.5 and c.get("rating") != "not_demonstrated": st = "not_assessed"   # too little evidence of failure to call it failure
        else: st = "not_met"
        crit.append({"key": c["key"], "name": c["name"], "score": s, "status": st, "label": {"met": "Demonstrated", "not_met": "Not demonstrated", "not_assessed": "Not assessed"}[st],
                     "confidence": c.get("confidence", "low"), "evidence": (c.get("evidence") or [])[:2], "missing": (c.get("missing") or [])[:2]})
    return {"version": 3, "overall": None if overall is None else int(round(overall)), "level": "" if overall is None else level_for(overall),
            "dimensions": dims, "coverage": int(round(cov * 100)), "role_covered": role_covered, "confidence": conf, "provisional": conf == "low" and overall is not None,
            "answered_ratio": round(ratio, 2), "capped_at": cap, "penalty": penalty, "penalties": pen.get("items", []), "penalties_skipped": pen.get("skipped", []),
            "before_penalty": None if before is None else int(round(before)), "role_profile": role_profile(position, description), "weights": w, "excluded_turns": excluded_turns,
            "critical": {"met": sum(1 for x in crit if x["status"] == "met"), "total": len(crit), "not_met": sum(1 for x in crit if x["status"] == "not_met"),
                         "not_assessed": sum(1 for x in crit if x["status"] == "not_assessed"), "items": crit},
            "kind": kind_key(kind)}
