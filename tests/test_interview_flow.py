"""A whole interview through the real HTTP endpoints and the real orchestration; only the language model and the web lookup are scripted."""
import json, pytest
from django.contrib.auth.models import User
from core.models import *
from core.services import ai, logic, agents, panelplan, factcheck
from core import jobs

def test_whole_interview_from_first_word_to_report(db, client, monkeypatch, settings):
    settings.FACTCHECK_SECONDS = 5
    logic.ensure_seed(); u = User.objects.create_user("u", password="p"); client.login(username="u", password="p")
    w = Workspace.objects.create(user=u, title="senior backend engineer", kind="employment", company="Acme", position="Senior Backend Engineer", duration=20,
                                 research={"assessment": {"build": "none", "status": "confirmed"}, "topics": [{"label": "System design", "importance": 9}], "panel": {"found": True, "count": 1, "roles": ["Engineering manager"], "why": "x", "status": "confirmed"},
                                           "required_documents": [{"key": "cv_extra", "label": "Portfolio", "why": "work samples", "must": True}]})
    panelplan.allocate(w); s = Session.objects.create(workspace=w); panel = agents.session_panel(s); assert len(panel) == 1
    rub = [{"key": "tech_depth", "name": "Technical depth", "looks_like": "why not just what", "weight": 9}, {"key": "ownership", "name": "Ownership", "looks_like": "what I did", "weight": 6}, {"key": "judgment", "name": "Judgment", "looks_like": "trade-offs", "weight": 5}]
    items = [{"owner": panel[0].id, "area": a, "competency": c, "goal": "g"} for a, c in (("System design", "tech_depth"), ("Team contribution", "ownership"), ("Incident handling", "judgment"))]
    A = lambda **k: dict({"said": "s", "demonstrates": "d", "evidence": ["e"], "unknown": [], "sufficient": True, "competency": "tech_depth", "status": "established", "contradiction": ""}, **k)
    turn_replies = [
        {"speaker_id": panel[0].id, "move": "followup", "text": "How many engineers worked on it with you?", "notes": {"claims": ["ledger on Postgres 9"], "gaps": []}, "assessment": A(sufficient=False, status="partial", unknown=["scale", "team"])},
        {"speaker_id": panel[0].id, "move": "advance", "text": "What happened when the primary failed?", "notes": {"claims": ["worked alone"], "gaps": []}, "assessment": A(competency="ownership", status="partial", sufficient=True)},
        {"speaker_id": panel[0].id, "move": "followup", "text": "Earlier you said nobody else touched it. Who was on the failover?", "notes": {"claims": [], "gaps": []}, "assessment": A(competency="ownership", contradiction="said alone, then said a team of three helped", status="concern", sufficient=False)},
        {"speaker_id": panel[0].id, "move": "advance", "text": "Tell me about the last incident you handled.", "notes": {"claims": [], "gaps": []}, "assessment": A(competency="ownership", status="partial", sufficient=True)},
    ]
    seen = {"prompts": []}; failures = {"left": 1}
    evaluation = {"overall": 62, "verdict_reason": "x", "summary": "Mixed.", "strengths": ["Chose Kafka with a measurement"], "improvements": ["Be consistent about who did what"], "scores": {},
                  "observations": [], "unverified_claims": ["ledger on Postgres 9"],
                  "competencies": [{"key": "tech_depth", "rating": "partial", "score": 55, "evidence": ["named Kafka with latency numbers"], "missing": ["why not SQS at scale"], "confidence": "medium", "reason": "Some depth, gaps on scale."},
                                   {"key": "ownership", "rating": "not_demonstrated", "score": 25, "evidence": ["said alone, then described a team of three"], "missing": [], "confidence": "medium", "reason": "Inconsistent account of personal contribution."}]}
    def fake(prompt, system=None, json_mode=False, search=False, temperature=0.8, images=None, purpose="research", **kw):
        seen["prompts"].append(prompt)
        if "You chair the briefing" in prompt: return json.dumps({"competencies": rub, "items": items}), []
        if "at the start of a REAL interview" in prompt: return json.dumps({"text": "Good morning. Tell me about the system you are proudest of."}), []
        if "Pick at most 3 PUBLIC" in prompt: return json.dumps({"claims": ["I built the ledger on Postgres 9"]}), []
        if "You run a REAL interview" in prompt:
            if failures["left"] and len(Turn.objects.filter(session=s, role="candidate")) == 3: failures["left"] -= 1; raise ai.AIError("rate limited")
            return json.dumps(turn_replies.pop(0)), []
        if "Evaluate this REAL interview" in prompt: return json.dumps(evaluation), []
        return "{}", []
    monkeypatch.setattr(ai, "call", fake)
    monkeypatch.setattr(ai, "factcheck_search", lambda prompt, system=None, wait=8: (json.dumps({"verdict": "wrong", "truth": "Postgres 9 reached end of life in 2021; current major is 18", "source": "postgresql.org"}), []))
    post = lambda body: client.post(f"/room/{s.pk}/turn/", data=json.dumps(body), content_type="application/json")

    r = post({"answer": None}).json(); assert r["intro"] is False and "Good morning" in r["text"]                       # the solo interviewer opens with a real question
    r = post({"answer": "I built the ledger on Postgres 9 and kept it consistent with a single writer for two years."}).json()
    assert r["text"] == "How many engineers worked on it with you?"
    ck = Turn.objects.filter(session=s, role="candidate").first().factcheck; assert ck["claims"][0]["verdict"] == "wrong"   # checked online before the next question
    r = post({"answer": "I was alone on it, the whole ledger was my work and nobody else touched it at all."}).json()
    assert any("VERIFIED FACTS" in p and "end of life in 2021" in p for p in seen["prompts"])                              # the panel was told the real figure when it asked the next question
    bad = post({"answer": "Postgres nine, on two big machines, with a streaming replica; my team of three helped me fail it over once."}); assert bad.status_code == 400   # the model call failed mid-interview
    assert Turn.objects.filter(session=s, role="candidate").count() == 3
    ok = post({"answer": None}); assert ok.status_code == 200 and "Earlier you said" in ok.json()["text"]                  # the room retried: the answer was kept, the panel continues, nothing is duplicated
    assert Turn.objects.filter(session=s, role="candidate").count() == 3
    s.refresh_from_db(); assert s.board["contradictions"] == ["said alone, then said a team of three helped"] and s.assessment["competencies"]["ownership"]["status"] == "concern"
    post({"answer": "The failover itself was my call, my colleagues only did the cabling and the monitoring changes."})
    s.refresh_from_db(); assert [i["done"] for i in s.agenda][:2] == [True, True]

    jobs.finalize_task(s.pk, [], None); s.refresh_from_db(); assert s.status == "done"
    ev = s.evaluation; assert ev.overall is not None and 0 <= ev.overall <= 100 and ev.verdict
    assert {c["key"]: c["rating"] for c in ev.competencies} == {"tech_depth": "partial", "ownership": "not_demonstrated", "judgment": "insufficient_evidence"}
    assert ev.checks[0]["truth"].startswith("Postgres 9 reached end of life") and ev.overall <= 62 - 5                      # the wrong fact cost points
    page = client.get(f"/report/{s.pk}/").content.decode()
    assert f'<b>{ev.overall}</b>' in page and "Skill-by-skill assessment" in page and "Not enough evidence" in page and "end of life in 2021" in page
