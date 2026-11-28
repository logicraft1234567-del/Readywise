"""Scoring integrity: identity resolution, research evidence, penalties, role weights, transcript quality, duplicate questions.
Pure Python (no Django, network or AI). Run: python -m pytest tests/test_integrity.py --noconftest -c /dev/null"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date
from core.services import identity as ident, findings as fnd, scoring, transcript as tsq, questions as qq

# --- the Orbit case: a hackathon project named like a commercial company ---
def orbit(**kw):
    d = {"Project name": "Orbit", "What it does": "Turns uploaded study notes into interactive lessons for students with an AI pipeline", "Hackathon": "Local Hackathon"}; d.update(kw)
    return ident.build_profile(name="Orbit", kind="hackathon", details=d, candidate_name="Ada Obi")
SRC_OTHER = {"url": "https://orbit.love/about-us", "title": "About Orbit", "entity": "Orbit (community analytics company)", "domain": "orbit.love", "founders": ["Patrick Woods", "Josh Dzielak"],
             "description": "Orbit is a community growth platform for developer relations teams", "type": "commercial_company", "pricing": "$10 per workspace"}

def test_name_alone_never_verifies_or_matches():
    p = orbit(); assert p["status"] == ident.UNVERIFIED and "domain" not in p["signals"]
    m = ident.match_source(p, SRC_OTHER); assert m["verdict"] != ident.SAME
    assert ident.match_source(ident.build_profile(name="Orbit", kind="employment", company="Orbit"), {"url": "https://orbit.love", "title": "Orbit"})["verdict"] == ident.UNKNOWN

def test_verified_identity_needs_a_hard_signal_and_a_second_one():
    p = orbit(Website="https://orbitlearn.app", Repository="https://github.com/ada/orbit")
    assert p["status"] == ident.VERIFIED and "domain" in p["signals"]
    assert ident.match_source(p, {"url": "https://orbitlearn.app/pricing", "title": "Pricing"})["verdict"] == ident.SAME
    assert ident.match_source(p, SRC_OTHER)["verdict"] == ident.DIFFERENT      # another domain, other founders

def test_shared_hosts_do_not_identify():
    p = orbit(Repo="https://github.com/ada/orbit")
    assert ident.match_source(p, {"url": "https://github.com/someoneelse/orbit", "title": "orbit"})["verdict"] != ident.SAME
    assert ident.match_source(p, {"url": "https://github.com/ada/orbit/blob/main/README.md", "title": "readme"})["same"] == ["repository"]

def test_founder_claim_is_never_challenged_without_verified_same_entity():
    p = orbit(); m = ident.match_source(p, SRC_OTHER)
    ok, why = ident.ownership_challengeable(p, "founder", m, SRC_OTHER["founders"], "Ada Obi"); assert not ok and "unverified" in why
    pv = orbit(Website="https://orbitlearn.app", Repository="https://github.com/ada/orbit")
    same = ident.match_source(pv, {"url": "https://orbitlearn.app/about", "title": "About", "founders": ["Chidi Eze"]})
    assert ident.ownership_challengeable(pv, "founder", same, ["Chidi Eze"], "Ada Obi")[0] is True
    assert ident.ownership_challengeable(pv, "founder", same, ["Ada Obi", "Chidi Eze"], "Ada Obi")[0] is False   # she is listed
    assert "role" in ident.clarification_question(p, "I am the founder").lower()

def test_roles_are_parsed():
    assert ident.role_claim("I am the founder of Orbit") == "founder" and ident.role_claim("I'm a co-founder") == "co_founder"
    assert ident.role_claim("I led the team") == "team_leader" and ident.role_claim("I built everything myself") == "project_creator"

# --- research findings ---
def test_other_companys_pricing_is_wrong_entity_not_false():
    f = fnd.classify("The cost per user is $10 for token usage", "wrong", dict(SRC_OTHER, unit="per_workspace"), orbit(), truth="Orbit charges $10 per workspace")
    assert f["classification"] in (fnd.WRONG_ENTITY, fnd.UNVERIFIED, fnd.PARTIALLY_VERIFIED) and not f["penalty_eligible"]
    assert fnd.penalty_policy([f])["total"] == 0

def test_founder_claim_against_other_company_is_wrong_entity_and_free():
    f = fnd.classify("I am the founder of Orbit", "wrong", SRC_OTHER, orbit(), truth="Founders are Patrick Woods and Josh Dzielak")
    assert f["classification"] == fnd.WRONG_ENTITY and fnd.penalty_policy([f])["total"] == 0

def test_estimates_are_never_false():
    f = fnd.classify("Our token cost is around $10 per user per month", "wrong", {"url": "https://x.com/p", "title": "Pricing", "date": "2026"}, ident.build_profile(name="X", kind="pitch"), truth="$0.40")
    assert f["classification"] == fnd.UNVERIFIED and f["needs_assumptions"] and fnd.penalty_policy([f])["total"] == 0

def test_unit_mismatch_is_not_a_contradiction():
    assert fnd.units_conflict("per_user", "per_workspace") and not fnd.units_conflict("per_user", "per_user") and not fnd.units_conflict("", "per_user")
    assert fnd.financial_unit("$10 per user") == "per_user" and fnd.financial_unit("$10 per workspace") == "per_workspace"

def test_verified_false_public_fact_costs_points_once_and_is_explained():
    src = {"url": "https://www.who.int/x", "title": "WHO", "date": "2026-02-01"}
    f = fnd.classify("The Eiffel Tower is in Berlin", "wrong", src, ident.build_profile(name="Acme", kind="employment", company="Acme"), truth="It is in Paris")
    assert f["classification"] == fnd.VERIFIED_FALSE and f["penalty_eligible"]
    dup = dict(f, claim="the eiffel tower is in berlin")
    pol = fnd.penalty_policy([f, dup]); assert len(pol["items"]) == 1 and 1 <= pol["total"] <= fnd.MAX_TOTAL and pol["skipped"][0]["why"].startswith("the same statement")
    assert pol["items"][0]["source_url"] and pol["items"][0]["reason"]

def test_penalties_are_capped_and_proportional():
    p = ident.build_profile(name="Acme", kind="employment", company="Acme"); fs = []
    for i in range(8):
        fs.append(fnd.classify(f"I worked at company{i} for {i+3} years", "wrong", {"url": f"https://e.com/{i}", "title": "t", "date": "2026-01-01"}, p, truth=f"actually {i}"))
    assert fnd.penalty_policy(fs)["total"] <= fnd.MAX_TOTAL
    minor = fnd.classify("The library has 40 contributors", "wrong", {"url": "https://e.com/l", "title": "t", "date": "2026-01-01"}, p, truth="52")
    assert fnd.penalty_policy([minor])["total"] < fnd.penalty_policy([fs[0]])["total"]

def test_outdated_and_conflicting_and_legacy_never_penalise():
    p = ident.build_profile(name="Acme", kind="employment", company="Acme")
    old = fnd.classify("The price is $20 per user", "wrong", {"url": "https://e.com", "title": "t", "date": "2019"}, p, today=date(2026, 11, 28), truth="$15")
    conf = fnd.classify("Water boils at 90C at sea level", "conflicting", {"url": "https://e.com", "title": "t"}, p)
    assert old["classification"] == fnd.OUTDATED and conf["classification"] == fnd.CONFLICTING
    legacy = {"claim": "the earth is flat", "verdict": "wrong", "truth": "round", "source": "nasa"}
    assert fnd.migrate_legacy(legacy)["classification"] == fnd.UNVERIFIED and fnd.penalty_policy([old, conf, legacy])["total"] == 0

def test_orbit_report_end_to_end_scores_no_penalty():
    claims = [("I am the founder of Orbit", "wrong"), ("The cost per user is $10", "wrong"), ("Orbit's token cost is about $10 per user", "wrong"), ("Movie memory lasts years", "partial")]
    fs = [fnd.classify(c, v, SRC_OTHER, orbit(), truth="x") for c, v in claims]
    assert fnd.penalty_policy(fs)["total"] == 0 and fnd.summarise(fs)[fnd.VERIFIED_FALSE] == 0

# --- scoring ---
def row(key, dim, score, w=5, conf="medium", crit=False, rating="partial", cov=1.0):
    return {"key": key, "name": key, "weight": w, "rating": rating if score is not None else "insufficient_evidence", "score": score, "evidence": ["e1", "e2"] if score is not None else [], "missing": [],
            "confidence": conf, "dimension": dim, "critical": crit, "coverage": cov}

PUBLISHED = {
    "employment": [("Technical", 30), ("Reasoning", 20), ("Execution", 20), ("Communication", 15), ("Judgment", 10), ("Professional", 5)],
    "startup": [("Technical", 25), ("Reasoning", 15), ("Ownership and shipping", 25), ("Communication", 10), ("Judgment under constraints", 15), ("Why this startup", 10)],
    "internship": [("Skills and foundations", 20), ("Learning ability and potential", 25), ("Experience and projects", 10), ("Communication", 20), ("Motivation and fit", 15), ("Reliability and attitude", 10)],
    "graduate": [("Skills and foundations", 20), ("Reasoning", 20), ("Learning ability and potential", 20), ("Communication", 15), ("Motivation and fit", 10), ("Teamwork and attitude", 15)],
    "admission": [("Academic ability", 25), ("Critical thinking", 25), ("Motivation and fit with the programme", 20), ("Communication", 15), ("Character and maturity", 15)],
    "scholarship": [("Academic ability", 15), ("Achievement and impact", 25), ("Goals and plan", 15), ("Communication", 20), ("Character and values", 25)],
    "fellowship": [("Expertise", 25), ("Vision and originality", 20), ("Track record and impact", 20), ("Communication", 15), ("Plan for the fellowship", 10), ("Character and collaboration", 10)],
    "pitch": [("Market and business case", 20), ("Traction and proof", 20), ("Product knowledge", 10), ("Pitch and story", 25), ("Judgment on risk", 20), ("Honesty and coachability", 5)],
    "hackathon": [("Technical depth", 30), ("Working result", 25), ("Reasoning", 10), ("Demo and story", 20), ("Judgment", 10), ("Teamwork", 5)],
    "certification": [("Knowledge of the subject", 55), ("Applying the knowledge", 30), ("Judgment in practice", 15)],
}

def test_weights_and_labels_are_exactly_the_published_table():
    for kind, rows in PUBLISHED.items():
        info, w = scoring.dim_info(kind), scoring.weights_for(kind, "Backend Engineer", "write Go services")
        assert sorted((info[d][0], w[d]) for d in scoring.dims_for(kind)) == sorted(rows), kind
        assert sum(w.values()) == 100 and w == scoring.weights_for(kind, "Sales Executive")   # the role never changes the weights

def test_not_assessed_is_never_zero_and_never_penalised():
    full = scoring.compute([row("t", "technical", 70), row("r", "reasoning", 70)], "employment")
    assert full["overall"] == 70
    dims = {d["key"]: d for d in full["dimensions"]}; assert dims["execution"]["state"] == "not_assessed" and dims["execution"]["score"] is None
    assert scoring.compute([], "employment")["overall"] is None

def test_no_score_floor_and_provisional_when_little_was_assessed():
    r = scoring.compute([row("t", "technical", 12)], "employment"); assert r["overall"] == 12 and r["confidence"] == "low" and r["provisional"] is True

def test_critical_requirement_states_and_no_failure_without_evidence():
    cs = [row("a", "technical", 85, crit=True, conf="high"), row("b", "reasoning", 40, crit=True, rating="not_demonstrated", conf="high"), row("c", "execution", None, crit=True),
          row("d", "judgment", 30, crit=True, conf="low", cov=0.2, rating="partial")]
    st = {c["key"]: c["status"] for c in scoring.compute(cs, "employment")["critical"]["items"]}
    assert st == {"a": "met", "b": "not_met", "c": "not_assessed", "d": "not_assessed"}

def test_penalty_is_the_only_deduction_and_is_shown():
    cs = [row(d, d, 80) for d in scoring.dims_for("employment")]
    pol = {"items": [{"points": 5, "claim": "x", "reason": "r"}], "total": 5, "skipped": []}
    r = scoring.compute(cs, "employment", 8, 8, pol); assert r["overall"] == 75 and r["before_penalty"] == 80 and r["penalty"] == 5 and r["penalties"][0]["claim"] == "x"
    assert scoring.compute(cs, "employment", 8, 8, 99)["overall"] == 80   # a bare number is not a policy: ignored

def test_overall_is_computed_from_dimensions_not_supplied():
    cs = [row("t", "technical", 90, w=5), row("c", "communication", 50, w=5)]
    r = scoring.compute(cs, "employment", position="Backend Engineer"); w = r["weights"]; assert w == scoring.weights("employment")
    assert r["overall"] == round((90 * w["technical"] + 50 * w["communication"]) / (w["technical"] + w["communication"]))

# --- transcripts ---
def test_english_expected_vietnamese_or_german_is_unreliable():
    vi = "Tôi đã xây dựng một hệ thống cho phép học sinh tải lên ghi chú và nhận bài học tương tác"
    de = "Ich habe ein System gebaut, das die Notizen der Schüler hochlädt und daraus interaktive Lektionen macht"
    en = "I built a system that takes student notes and turns them into interactive lessons"
    assert not tsq.assess(vi, "English")["reliable"] and not tsq.assess(de, "English")["reliable"] and tsq.assess(en, "English")["reliable"]
    assert tsq.assess(de, "German")["reliable"]

def test_short_names_and_code_are_not_false_alarms():
    for t in ("Postgres and Redis", "Yes, about six years.", "I used FastAPI with a Postgres database and Celery workers for the queue"): assert tsq.assess(t, "English")["reliable"], t

def test_whisper_signals_flag_unreliable():
    w = {"language": "vietnamese", "segments": [{"avg_logprob": -1.4, "compression_ratio": 1.2}]}
    assert not tsq.assess("I built a pipeline for lessons from notes", "English", whisper=w)["reliable"]
    assert tsq.assess("I built a pipeline for lessons from notes", "English", whisper={"language": "english", "segments": [{"avg_logprob": -0.2, "compression_ratio": 1.4}]})["reliable"]
    assert not tsq.assess("thank you thank you thank you thank you thank you thank you", "English")["reliable"]

def test_language_is_explicit_never_guessed():
    assert tsq.iso_for("English") == "en" and tsq.iso_for("en-US") == "en" and tsq.iso_for("German") == "de" and tsq.iso_for("") == "en" and tsq.BCP47["English"] == "en-US"

def test_merge_and_duplicate_fragments():
    assert tsq.merge_fragments("I built the pipeline and", "and then I tested it") == "I built the pipeline and then I tested it"
    assert tsq.squash_repeats("We shipped it. We shipped it. Users liked it.") == "We shipped it. Users liked it."
    assert tsq.is_duplicate_turn("I built the pipeline and tested it", ["x", "I built the pipeline and tested it"]) and not tsq.is_duplicate_turn("ok", ["ok"])
    assert tsq.usable({}) and tsq.usable(None) and not tsq.usable({"reliable": False})

# --- questions ---
def test_repeated_questions_are_detected_and_new_ones_pass():
    asked = ["How did you calculate the cost per user for your pipeline?", "What happens when a student uploads a very large file?"]
    assert qq.is_duplicate("Can you walk me through how you calculated the per-user cost of the pipeline?", asked)
    assert not qq.is_duplicate("Who else worked on the project with you?", asked)
    assert qq.unique(["How did you calculate the cost per user for your pipeline?", "Who tested the lessons?"], asked) == "Who tested the lessons?"
    assert "ALREADY ASKED" in qq.already_covered_note(asked)

def test_clarification_asks_for_assumptions_instead_of_accusing():
    q = qq.clarification_for_claim(orbit(), "Our token cost is around $10 per user"); assert "assumption" in q.lower()
