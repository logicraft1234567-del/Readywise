"""The evidence-driven interviewer: assessment record, adaptive follow-ups, strict validation, per-competency final evaluation."""
import json, pytest
from django.contrib.auth.models import User
from core.models import *
from core.services import ai, logic, agents, panelplan

RUBRIC = [{"key": "tech_depth", "name": "Technical depth", "looks_like": "explains why, not just what", "weight": 9},
          {"key": "ownership", "name": "Personal ownership", "looks_like": "says what I did", "weight": 6},
          {"key": "judgment", "name": "Judgment under uncertainty", "looks_like": "trade-offs with reasons", "weight": 5}]

def mkws(user, **kw):
    d = dict(user=user, title="backend engineer", kind="employment", company="Acme", position="Senior Backend Engineer", duration=20, research={"topics": [{"label": "System design", "importance": 9}], "panel": {"found": True, "count": 1, "roles": ["Engineering manager"], "why": "x", "status": "confirmed"}})
    d.update(kw); w = Workspace.objects.create(**d); panelplan.allocate(w); return w

@pytest.fixture
def env(db):
    logic.ensure_seed(); u = User.objects.create_user("u", password="p"); w = mkws(u); s = Session.objects.create(workspace=w); panel = agents.session_panel(s)
    return w, s, panel

def reply(panel, **kw):
    d = {"speaker_id": panel[0].id, "move": "followup", "interject": False, "text": "Why did you pick that design?", "heard": "", "topic": "x", "followup": True, "end": False, "notes": {"claims": [], "gaps": []},
         "assessment": {"said": "I built the queue", "demonstrates": "built a queue", "evidence": ["built the queue"], "unknown": ["why this design"], "sufficient": False, "competency": "tech_depth", "status": "partial", "contradiction": ""}}
    d.update(kw); return d

def script(monkeypatch, panel, replies, rubric=RUBRIC, log=None):
    """Replies are handed out to the interviewer-turn prompts in order; the briefing and introduction have fixed replies."""
    q = list(replies); log = log if log is not None else []
    def fake(prompt, system=None, json_mode=False, search=False, temperature=0.8, images=None, purpose="research", **kw):
        log.append(prompt)
        if "You chair the briefing" in prompt: return json.dumps({"competencies": rubric, "items": [{"owner": panel[0].id, "area": "System design", "competency": "tech_depth", "goal": "g1"}, {"owner": panel[0].id, "area": "Incident handling", "competency": "judgment", "goal": "g2"}, {"owner": panel[0].id, "area": "Team contribution", "competency": "ownership", "goal": "g3"}]}), []
        if "at the start of a REAL interview" in prompt: return json.dumps({"text": "Good morning. Tell me about the system you are proudest of."}), []
        r = q.pop(0) if q else reply(panel)
        return (r if isinstance(r, str) else json.dumps(r)), []
    monkeypatch.setattr(ai, "call", fake); return log

def start(s, panel, monkeypatch, replies, **kw):
    log = script(monkeypatch, panel, replies, **kw); agents.next_turn(s, 3); s.refresh_from_db(); return log

def answer(s, text, at=30): return Turn.objects.create(session=s, role="candidate", text=text, offset=at)

LONG = "I designed the queue myself, because ordering mattered for payments, and I chose Kafka over SQS after we measured the latency."

def test_insufficient_answer_gets_a_followup_and_the_record_shows_why(env, monkeypatch):
    w, s, panel = env; start(s, panel, monkeypatch, [reply(panel)]); answer(s, "We built a queue and it worked well for the team in the end.")
    t, _, _ = agents.next_turn(s, 40); s.refresh_from_db()
    assert t.followup is True and s.agenda[0]["done"] is False                    # stays on the area: the evidence is not there yet
    c = s.assessment["competencies"]["tech_depth"]
    assert c["status"] == "partial" and c["evidence"] == ["built the queue"] and c["missing"] == ["why this design"] and c["confidence"] == "low"

def test_sufficient_answer_is_not_followed_up(env, monkeypatch, settings):
    settings.PANEL_RECHECK = True   # the second look at its own assessment is an extra model call and is off by default; this test covers it when switched on
    w, s, panel = env
    suff = reply(panel, move="followup", text="And what about the design?", assessment=dict(reply(panel)["assessment"], sufficient=True, status="established", unknown=[]))
    adv = reply(panel, move="advance", text="Tell me about an incident you handled.", followup=False, assessment=dict(suff["assessment"]))
    log = start(s, panel, monkeypatch, [suff, adv]); answer(s, LONG)
    t, _, _ = agents.next_turn(s, 40); s.refresh_from_db()
    assert "SUFFICIENT" in log[-1] and t.text == "Tell me about an incident you handled."   # the panel was told once, and advanced
    assert s.agenda[0]["done"] is True and t.topic == "Incident handling" and "System design" in s.assessment["objectives_done"]

def test_repeated_question_is_never_sent(env, monkeypatch):
    w, s, panel = env
    log = start(s, panel, monkeypatch, [reply(panel, text="Why did you pick Kafka over SQS for the payment queue?"), reply(panel, text="What would you change if the volume tripled?")])
    Turn.objects.create(session=s, speaker=panel[0], role="interviewer", text="Why did you pick Kafka over SQS for the payment queue?", topic="System design", offset=10); answer(s, "We measured it.", 20)
    t, _, _ = agents.next_turn(s, 40)
    assert "REPEATED" in log[-1] and t.text == "What would you change if the volume tripled?"

def test_unsupported_claim_is_recorded_for_verification_and_probed(env, monkeypatch):
    w, s, panel = env
    log = start(s, panel, monkeypatch, [reply(panel, text="How was that 40 percent measured?", notes={"claims": ["cut latency by 40 percent"], "gaps": ["no measurement given"]})]); answer(s, "We cut latency by forty percent after the rewrite, everyone saw it.")
    t, _, _ = agents.next_turn(s, 40); s.refresh_from_db()
    assert s.board["claims"] == ["cut latency by 40 percent"] and s.board["gaps"] == ["no measurement given"]
    assert "An unsupported claim: probe it without accusing" in log[-1] and "accus" not in t.text.lower()

def test_contradiction_is_recorded_and_put_to_the_panel_next_turn(env, monkeypatch):
    w, s, panel = env
    con = reply(panel, assessment=dict(reply(panel)["assessment"], contradiction="Said the team of 3 built it, earlier said they built it alone", status="concern"))
    log = start(s, panel, monkeypatch, [con, reply(panel)]); answer(s, "Actually my team of three built that part together with me.")
    agents.next_turn(s, 40); s.refresh_from_db()
    assert s.board["contradictions"] == ["Said the team of 3 built it, earlier said they built it alone"] and s.assessment["competencies"]["tech_depth"]["status"] == "concern"
    answer(s, "Well, it was mostly me, I just had some help with deployment.", 60); agents.next_turn(s, 70)
    assert "Contradictions found: Said the team of 3" in log[-1]

def test_unusable_transcript_is_not_assessed(env, monkeypatch):
    w, s, panel = env; start(s, panel, monkeypatch, [reply(panel, text="Sorry, I did not catch that. Could you repeat it?")]); answer(s, "Wood.")
    t, _, _ = agents.next_turn(s, 40); s.refresh_from_db()
    assert s.assessment["log"] == [] and all(c["evidence"] == [] for c in s.assessment["competencies"].values())   # nothing was invented from noise

def test_assessment_is_never_spoken_and_candidate_response_has_no_internal_fields(env, monkeypatch, client):
    w, s, panel = env; start(s, panel, monkeypatch, [reply(panel)]); client.login(username="u", password="p"); answer(s, LONG)
    r = client.post(f"/room/{s.pk}/turn/", data=json.dumps({"answer": None}), content_type="application/json").json()
    assert "assessment" not in r and "notes" not in r and "evidence" not in json.dumps(r) and r["text"] == "Why did you pick that design?"

def test_role_specific_rubric_and_lens(db, monkeypatch):
    logic.ensure_seed(); u = User.objects.create_user("v", password="p")
    eng = mkws(u); ceo = mkws(u, title="nvidia ceo", position="Chief Executive Officer", kind="employment"); visa = mkws(u, title="usa student visa", kind="visa", position="F-1 student visa", company="United States")
    a, b, c = agents.role_lens(eng), agents.role_lens(ceo), agents.role_lens(visa)
    assert "TECHNICAL" in a and "LEADERSHIP" not in a and "LEADERSHIP" in b and "ELIGIBILITY" in c and "TECHNICAL" not in c
    s = Session.objects.create(workspace=ceo); panel = agents.session_panel(s); log = script(monkeypatch, panel, [], rubric=RUBRIC); agents.build_agenda(s, panel)
    assert "LEADERSHIP" in log[0] and "RUBRIC" in log[0] and [c["key"] for c in s.assessment["rubric"]] == ["tech_depth", "ownership", "judgment"]
    assert [i["competency"] for i in s.agenda] == ["tech_depth", "judgment", "ownership"]

def test_rubric_fallback_uses_the_research_not_a_fixed_list(env):
    w, s, panel = env; r = agents.clean_rubric("garbage", w)
    assert [c["name"] for c in r] == ["System design"] and r[0]["weight"] == 9

def test_malformed_reply_gets_one_corrective_retry_then_fails_cleanly(env, monkeypatch, client):
    w, s, panel = env; log = start(s, panel, monkeypatch, ["this is not json", reply(panel)])
    t, _, _ = agents.next_turn(s, 10)
    assert t.text == "Why did you pick that design?" and "NOT VALID" in log[-1]
    n = Turn.objects.filter(session=s).count(); agenda_before = list(Session.objects.get(pk=s.pk).agenda)
    monkeypatch.setattr(ai, "call", lambda *a, **k: ("still not json", []))
    with pytest.raises(ai.AIError): agents.next_turn(s, 20)
    assert Turn.objects.filter(session=s).count() == n and Session.objects.get(pk=s.pk).agenda == agenda_before   # nothing invented, nothing advanced

def test_ai_failure_keeps_the_interview_alive_and_does_not_duplicate_the_answer(env, monkeypatch, client):
    w, s, panel = env; start(s, panel, monkeypatch, []); client.login(username="u", password="p")
    def boom(*a, **k): raise ai.AIError("rate limited")
    good = ai.call; monkeypatch.setattr(ai, "call", boom)
    r = client.post(f"/room/{s.pk}/turn/", data=json.dumps({"answer": LONG}), content_type="application/json"); assert r.status_code == 400
    monkeypatch.setattr(ai, "call", good)
    r = client.post(f"/room/{s.pk}/turn/", data=json.dumps({"answer": None}), content_type="application/json"); assert r.status_code == 200   # the room's retry
    assert Turn.objects.filter(session=s, role="candidate").count() == 1

def test_clean_update_is_strict():
    keys = {"a"}
    assert agents.clean_update({"sufficient": "yes"}, keys) is None and agents.clean_update("x", keys) is None
    u = agents.clean_update({"sufficient": True, "competency": "zzz", "status": "great", "evidence": "one thing", "unknown": []}, keys)
    assert u["competency"] is None and u["status"] is None and u["evidence"] == ["one thing"]

def _finished(env, monkeypatch, comps, **top):
    w, s, panel = env; start(s, panel, monkeypatch, [])
    Turn.objects.create(session=s, speaker=panel[0], role="interviewer", text="Why Kafka?", topic="System design", offset=20)
    c = answer(s, LONG, 40)
    d = {"overall": 70, "summary": "ok", "strengths": [], "improvements": [], "scores": {}, "observations": [{"turn_id": c.id, "tone": "positive", "quote": "I chose Kafka over SQS", "note": "specific", "better": ""}], "competencies": comps, "unverified_claims": ["said the team trusted the design"]}
    d.update(top); monkeypatch.setattr(ai, "call", lambda *a, **k: (json.dumps(d), [])); return agents.evaluate(s)[0]

def test_final_evaluation_separates_demonstrated_ability_from_missing_evidence(env, monkeypatch):
    comps = [{"key": "tech_depth", "rating": "demonstrated", "score": 82, "evidence": ["chose Kafka over SQS after measuring latency"], "missing": [], "confidence": "medium", "reason": "Explained why with a measurement."},
             {"key": "ownership", "rating": "not_demonstrated", "score": 10, "evidence": [], "missing": ["what they personally did"], "confidence": "high", "reason": "Not covered."}]   # no cited inability: must not stand
    ev = _finished(env, monkeypatch, comps); by = {c["key"]: c for c in ev.competencies}
    assert by["tech_depth"]["rating"] == "demonstrated" and by["tech_depth"]["score"] == 82 and by["tech_depth"]["evidence"]
    assert by["ownership"]["rating"] == "insufficient_evidence" and by["ownership"]["score"] is None      # no evidence of inability is not inability
    assert by["judgment"]["rating"] == "insufficient_evidence" and by["judgment"]["score"] is None         # the evaluator skipped it: not silently zero
    assert ev.unverified == ["said the team trusted the design"] and 0 <= ev.overall <= 100

def test_not_demonstrated_needs_cited_evidence_and_counts_against_the_score(env, monkeypatch):
    comps = [{"key": "tech_depth", "rating": "not_demonstrated", "score": 15, "evidence": ["could not say why Kafka rather than SQS"], "missing": [], "confidence": "high", "reason": "Could not explain."},
             {"key": "judgment", "rating": "demonstrated", "score": 80, "evidence": ["named a trade-off"], "missing": [], "confidence": "medium", "reason": "ok"}]
    ev = _finished(env, monkeypatch, comps, overall=70); by = {c["key"]: c for c in ev.competencies}
    assert by["tech_depth"]["rating"] == "not_demonstrated" and by["tech_depth"]["score"] == 15
    # the evaluator's own "overall" of 70 does not decide the score: technical (30%) at 15 and judgment (10%) at 80 -> (15*30 + 80*10) / 40 = 31
    assert ev.overall == 31 and ev.verdict == "Not ready"
    assert ev.breakdown["critical"]["not_met"] == 1 and ev.breakdown["critical"]["items"][0]["key"] == "tech_depth"   # the failed requirement is named
