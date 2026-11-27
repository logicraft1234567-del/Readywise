"""The evidence-based scoring engine: weights per interview type, criteria maths, missing evidence, critical requirements, known-score sample interviews."""
import pytest
from core.services import scoring, kinds, agents
from .test_planner import setup   # noqa: F401


def comp(key, name, dim, score, weight=5, critical=None, evidence=2, conf="medium", cov=1.0):
    return {"key": key, "name": name, "dimension": dim, "weight": weight, "score": score, "evidence": ["x"] * evidence if score is not None else [],
            "confidence": conf, "coverage": cov if score is not None else 0.0, "critical": weight >= 8 if critical is None else critical}


def six(kind="employment", **s):
    """One competency per dimension of this interview type, scored from the keyword arguments (None = not reached)."""
    assert set(s) <= set(scoring.dims_for(kind)), set(s) - set(scoring.dims_for(kind))
    return [comp(d, d, d, s.get(d), 5) for d in scoring.dims_for(kind)]


def test_every_interview_type_has_its_own_dimensions_that_add_to_100():
    assert set(scoring.KIND_DIMS) == set(kinds.ORDER)
    for k in kinds.ORDER:
        w = scoring.weights(k); assert sum(w.values()) == 100 and set(w) <= set(scoring.DIM_DEFAULT) and all(v > 0 for v in w.values()), k
        assert set(scoring.dim_info(k)) == set(w)
    assert len({tuple(scoring.dims_for(k)) + tuple(scoring.weights(k).values()) for k in kinds.ORDER}) == len(kinds.ORDER)   # no two kinds are assessed the same way
    assert scoring.weights("unknown_kind") == scoring.weights("employment")


def test_a_dimension_that_does_not_matter_for_a_type_is_not_part_of_it():
    assert "technical" not in scoring.dims_for("visa") and {"purpose", "consistency", "ties"} <= set(scoring.dims_for("visa"))   # visa: no technical test, but purpose, a consistent story, funds and ties
    assert {"market", "traction"} <= set(scoring.dims_for("pitch")) and "ties" not in scoring.dims_for("pitch")
    assert scoring.dims_for("certification") == ["technical", "reasoning", "judgment"]
    assert "impact" in scoring.dims_for("scholarship") and "motivation" in scoring.dims_for("admission") and "potential" in scoring.dims_for("internship")
    r = scoring.compute(six("visa", purpose=80, consistency=70, ties=75, communication=80, professional=85), "visa")
    assert [d["key"] for d in r["dimensions"]] == ["purpose", "consistency", "ties", "communication", "professional"] and r["overall"] == 77


def test_a_competency_can_only_land_in_a_dimension_of_its_own_type():
    assert scoring.dimension_for({"name": "Proof of funds", "dimension": "technical"}, "visa") == "ties"       # "technical" is not a visa dimension: re-read from the words
    assert scoring.dimension_for({"name": "Course knowledge"}, "visa") in scoring.dims_for("visa")
    assert scoring.dimension_for({"name": "Unmatched thing"}, "visa") == "purpose"                                # nothing matches: the type's heaviest dimension
    assert scoring.dimension_for({"name": "Market sizing"}, "pitch") == "market" and scoring.dimension_for({"name": "x", "dimension": "traction"}, "pitch") == "traction"


def test_the_same_strengths_score_differently_for_different_kinds():
    strong_tech = lambda k: [comp("t", "Technical depth", "technical", 90, 5), comp("j", "Judgment", "judgment", 50, 5)]
    assert scoring.compute(strong_tech("certification"), "certification")["overall"] > scoring.compute(strong_tech("pitch"), "pitch")["overall"] + 10   # depth is nearly everything in a certification


def test_overall_is_the_weighted_average_of_dimension_scores():
    r = scoring.compute(six("employment", technical=82, reasoning=78, execution=70, communication=85, judgment=72, professional=80), "employment")
    assert r["overall"] == 78 and r["level"] == "Strong"          # 0.30*82 + 0.20*78 + 0.20*70 + 0.15*85 + 0.10*72 + 0.05*80 = 78.15


def test_criteria_give_the_competency_score():
    crit = [{"name": n, "weight": w, "score": s} for n, w, s in [("a", 15, 90), ("b", 30, 90), ("c", 25, 70), ("d", 20, 40), ("e", 10, 60)]]
    sc, cov = scoring.criteria_score(crit); assert round(sc) == 72 and cov == 1.0       # the idempotency example: .15*90 + .30*90 + .25*70 + .20*40 + .10*60 = 72
    crit[3]["score"] = None                                                              # a criterion the interview never reached is left out, not zero
    sc2, cov2 = scoring.criteria_score(crit); assert round(sc2) == 80 and round(cov2, 2) == 0.8


def test_clean_competencies_calculates_the_score_from_criteria_not_from_the_evaluator():
    rub = [{"key": "api", "name": "API design", "weight": 9, "dimension": "technical", "critical": True,
            "criteria": [{"name": "Idempotency", "weight": 6}, {"name": "Failure handling", "weight": 4}]}]
    raw = [{"key": "api", "rating": "demonstrated", "score": 99, "evidence": ["used idempotency keys"], "confidence": "high", "reason": "ok",
            "criteria": [{"name": "Idempotency", "score": 90}, {"name": "Failure handling", "score": 50}]}]
    c = agents.clean_competencies(raw, rub)[0]
    assert c["score"] == 74 and c["level"] == "Competent" and c["dimension"] == "technical" and c["critical"] is True   # (90*6 + 50*4) / 10 = 74, not the evaluator's 99


def test_rating_and_score_must_agree():
    rub = [{"key": "a", "name": "A", "weight": 5}]
    mk = lambda rating, score: agents.clean_competencies([{"key": "a", "rating": rating, "score": score, "evidence": ["e"]}], rub)[0]["score"]
    assert mk("demonstrated", 30) == 65 and mk("not_demonstrated", 90) == 45 and mk("partial", 95) == 74


def test_missing_evidence_is_not_a_low_score():
    full = scoring.compute(six("employment", technical=80, reasoning=80), "employment")
    assert full["overall"] == 80                                               # communication etc. were never reached: left out, the rest rescaled
    unassessed = [d for d in full["dimensions"] if not d["assessed"]]; assert len(unassessed) == 4 and all(d["score"] is None for d in unassessed)
    assert scoring.compute(six("employment"), "employment")["overall"] is None             # nothing assessed: inconclusive, not zero


def test_confidence_follows_the_evidence_not_the_score():
    thin = scoring.compute(six("employment", technical=90), "employment", 8, 8)
    assert thin["confidence"] == "low" and thin["coverage"] < 40
    rich = scoring.compute([comp(d, d, d, 70, 5, evidence=3, conf="high") for d in scoring.dims_for("employment")], "employment", 8, 8)
    assert rich["confidence"] == "high" and rich["coverage"] == 100
    assert scoring.compute([comp(d, d, d, 70, 5, evidence=3, conf="high") for d in scoring.dims_for("employment")], "employment", 3, 8)["confidence"] == "low"   # most questions unanswered


def test_a_failed_critical_requirement_is_reported_even_when_the_average_is_good():
    cs = [comp("tech", "Backend engineering", "technical", 35, weight=9), comp("comm", "Communication", "communication", 95, weight=4),
          comp("lead", "Ownership", "execution", 90, weight=5), comp("judg", "Judgment", "judgment", 90, weight=5), comp("reason", "Reasoning", "reasoning", 85, weight=5)]
    r = scoring.compute(cs, "employment", 8, 8)
    assert r["critical"]["total"] == 1 and r["critical"]["not_met"] == 1 and r["critical"]["items"][0]["status"] == "not_met"
    missing = scoring.compute([comp("tech", "Backend", "technical", None, weight=9), comp("c", "C", "communication", 80)], "employment")
    assert missing["critical"]["not_assessed"] == 1 and missing["critical"]["not_met"] == 0   # not reached is not the same as failed


E80 = dict(technical=80, reasoning=80, execution=80, communication=80, judgment=80, professional=80); E100 = {k: 100 for k in E80}


def test_wrong_facts_and_unanswered_questions_are_penalised_with_evidence():
    base = scoring.compute(six("employment", **E80), "employment", 8, 8)
    assert base["overall"] == 80
    assert scoring.compute(six("employment", **E80), "employment", 8, 8, 2, 1)["overall"] == 67
    capped = scoring.compute(six("employment", **E80), "employment", 2, 8)
    assert capped["overall"] == 40 and capped["capped_at"] == 40
    assert scoring.compute(six("employment", **E100), "employment", 8, 8)["overall"] == 98


def test_dimension_is_inferred_for_older_rubrics():
    assert scoring.dimension_for({"name": "Communication of numbers"}) == "communication"
    assert scoring.dimension_for({"name": "System architecture"}) == "technical"
    assert scoring.dimension_for({"name": "Ownership of delivery"}) == "execution"
    assert scoring.dimension_for({"name": "x", "dimension": "judgment"}) == "judgment"


# ---- sample interviews with known reference levels: if the engine drifts, these fail ----
SAMPLES = {   # name: (kind, dimension scores, answered, asked, the range a fair reviewer would give)
    "weak engineer":      ("employment", dict(technical=30, reasoning=35, execution=40, communication=55, judgment=35, professional=60), 8, 8, (30, 45)),
    "average engineer":   ("employment", dict(technical=62, reasoning=60, execution=58, communication=65, judgment=55, professional=70), 8, 8, (55, 68)),
    "strong engineer":    ("employment", dict(technical=85, reasoning=82, execution=78, communication=80, judgment=75, professional=85), 8, 8, (76, 88)),
    "strong visa":        ("visa", dict(purpose=85, consistency=82, ties=78, communication=80, professional=88), 7, 7, (78, 88)),
    "inconsistent visa":  ("visa", dict(purpose=60, consistency=30, ties=40, communication=60, professional=35), 7, 7, (30, 48)),
    "average certification": ("certification", dict(technical=60, reasoning=55, judgment=50), 8, 8, (52, 64)),
    "average pitch":      ("pitch", dict(market=60, traction=55, technical=70, communication=65, judgment=50, professional=70), 6, 6, (55, 66)),
}


@pytest.mark.parametrize("name", list(SAMPLES))
def test_sample_interviews_land_in_the_range_a_fair_reviewer_would_give(name):
    kind, dims, ans, asked, (lo, hi) = SAMPLES[name]
    r = scoring.compute(six(kind, **dims), kind, ans, asked); assert lo <= r["overall"] <= hi, (name, r["overall"])


def test_report_shows_how_the_score_was_built_and_older_reports_still_render(client, setup):
    from core.models import Session, Evaluation
    u, ws = setup; s = Session.objects.create(workspace=ws, status="done")
    cs = [comp("tech", "Backend engineering", "technical", 35, weight=9), comp("comm", "Communication", "communication", 90, weight=4), comp("judg", "Judgment", "judgment", 80)]
    bd = scoring.compute(cs, "employment", 8, 8)
    Evaluation.objects.create(session=s, overall=bd["overall"], verdict="Weak", summary="Ok.", breakdown=bd)
    h = client.get(f"/report/{s.pk}/").content.decode()
    assert "How your score was built" in h and "Evidence confidence" in h and "Critical requirements met: 0 of 1" in h and "not yet demonstrated" in h and "Technical or domain competence" in h
    assert "not a prediction of a real hiring decision" in h
    none = Session.objects.create(workspace=ws, status="done"); Evaluation.objects.create(session=none, overall=None, verdict="Inconclusive", summary="Nothing.")
    h = client.get(f"/report/{none.pk}/").content.decode(); assert "Inconclusive" in h and "How your score was built" not in h
