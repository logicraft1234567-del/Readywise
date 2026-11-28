"""The real-interview panel: shared agenda, fact-check key, panel size from research, required documents, score out of 100."""
import json, pytest
from django.contrib.auth.models import User
from core.models import *
from core.services import ai, logic, agents, panelplan, factcheck

@pytest.fixture
def ws(db):
    logic.ensure_seed(); u = User.objects.create_user("u", password="p")
    w = Workspace.objects.create(user=u, title="usa student visa", kind="visa", company="United States", position="F-1 student visa", duration=20,
                                 research={"role_level": "entry", "competitiveness": "medium", "summary": "s", "topics": [{"label": "Funding", "importance": 9, "status": "confirmed"}, {"label": "Ties to home country", "importance": 8, "status": "confirmed"}],
                                           "panel": {"found": True, "count": 1, "roles": ["Consular officer"], "why": "Student visa interviews are conducted by one consular officer.", "status": "confirmed"},
                                           "required_documents": [{"key": "i20", "label": "I-20 form", "why": "Proves admission", "must": True}, {"key": "funds", "label": "Proof of funds", "why": "Who pays", "must": True}]})
    return w

def test_panel_size_comes_from_research(ws):
    panelplan.allocate(ws); ws.refresh_from_db()
    assert ws.panel.count() == 1 and ws.allocation["size_source"] == "research" and ws.allocation["needs_choice"] is False
    assert ws.panel.get().position == "Visa Officer"   # the best fit for the role the research named

def test_candidate_chooses_only_when_research_cannot_say(ws):
    ws.research = dict(ws.research, panel={"found": False, "count": None, "roles": [], "why": "", "status": "inferred"}); ws.save()
    panelplan.allocate(ws); ws.refresh_from_db(); assert ws.allocation["needs_choice"] is True
    panelplan.allocate(ws, size=2); ws.refresh_from_db()
    assert ws.panel.count() == 2 and ws.allocation["size_source"] == "candidate" and ws.allocation["needs_choice"] is False

def test_research_size_wins_over_candidate_choice(ws):
    panelplan.allocate(ws, size=3); ws.refresh_from_db(); assert ws.panel.count() == 1

def test_fallback_score_out_of_100():
    w = {"technical": 5, "communication": 5}
    assert agents.final_score(80, {"technical": 80, "communication": 80}, w, 8, 8) == 80
    assert agents.final_score(80, {"technical": 80}, w, 2, 8) <= 40            # most questions unanswered: capped
    assert agents.final_score(80, {"technical": 80}, w, 8, 8, 6) == 80 - 6          # a documented verified penalty costs points
    assert agents.final_score(None, {}, w, 0, 0) == 0
    assert agents.final_score(30, {"technical": 30}, w, 8, 8) == 30             # no artificial floor: a weak performance is scored as weak
    assert agents.final_score(99, {"technical": 99}, w, 8, 8) == 98             # the very top of the scale is almost never reached
    assert agents.final_score(75, {"technical": 75}, w, 3, 8) == 60             # many questions skipped: held at 60
    assert agents.verdict_for(88) == "Outstanding" and agents.verdict_for(30) == "Not ready"

def test_factcheck_parses_and_downgrades(monkeypatch, ws):
    monkeypatch.setattr(ai, "call", lambda *a, **k: (json.dumps({"claims": ["GPU price is $3,100", "I never said that"]}), []))     # step 1: pick the claims
    def look(prompt, system=None, wait=8):                                                                                              # step 2: one lookup per claim
        if "3,100" in prompt: return json.dumps({"verdict": "wrong", "truth": "Flagship data-centre GPUs sell for about $25,000 to $40,000 (2026)", "source": "nvidia.com"}), []
        return json.dumps({"verdict": "wrong", "truth": "", "source": ""}), []
    monkeypatch.setattr(ai, "factcheck_search", look)
    r = factcheck.check(ws, "How much does it cost?", "The price is around 3100 dollars for the top GPU")
    assert [c["verdict"] for c in r["claims"]] == ["wrong", "unverifiable"]
    assert factcheck.check(ws, "q", "yes")["skipped"] is True and not factcheck.worth_checking("I am a hard worker and love people")

def test_factcheck_uses_its_own_key(settings, monkeypatch):
    settings.GROQ_FACTCHECK_KEYS = ["fc-key"]; settings.GROQ_RESEARCH_KEYS = ["r1"]; settings.GROQ_INTERVIEW_KEYS = ["i1"]; settings.GROQ_API_KEY = ""
    assert sorted(ai._keys("factcheck")) == ["fc-key", "r1"] and ai._keys("research") == ["r1"]     # the fact checker works from ALL the research keys plus its own

def _session(ws):
    panelplan.allocate(ws); return Session.objects.create(workspace=ws, mode="normal")

def test_agenda_decides_the_speaker_and_verified_facts_reach_the_panel(ws, monkeypatch):
    ws.research = dict(ws.research, panel={"found": True, "count": 3, "roles": [], "why": "", "status": "confirmed"}); ws.save()
    s = _session(ws); panel = agents.session_panel(s); assert len(panel) == 3
    prompts = []
    def fake(prompt, system=None, json_mode=False, search=False, temperature=0.8, images=None, purpose="research", **kw):
        prompts.append(prompt)
        if "You chair the briefing" in prompt: return json.dumps({"items": [{"owner": panel[0].id, "area": "Motivation", "goal": "why"}, {"owner": panel[1].id, "area": "Funding", "goal": "who pays"}, {"owner": panel[2].id, "area": "Ties", "goal": "return"}]}), []
        if "at the start of a REAL interview" in prompt: return json.dumps({"text": "Good morning."}), []
        # the model tries to let the WRONG person speak: the plan must override it
        return json.dumps({"speaker_id": panel[2].id, "move": "advance", "interject": False, "text": "How much will your parents pay, exactly?", "heard": "", "topic": "x", "followup": False, "end": False, "notes": {"claims": ["parents will pay one million dollars"], "gaps": []}}), []
    monkeypatch.setattr(ai, "call", fake)
    for _ in panel: agents.next_turn(s, 5)          # introductions
    s.refresh_from_db(); assert [a["area"] for a in s.agenda] == ["Motivation", "Funding", "Ties"]
    Turn.objects.create(session=s, role="candidate", text="I want to study computer science because I love building things and I plan to return home after.", offset=30,
                        factcheck={"claims": [{"claim": "tuition is 1 million dollars", "verdict": "wrong", "truth": "Typical US master's tuition is $30,000 to $60,000 a year (2026)", "source": "studyportals"}]})
    t, end, intro = agents.next_turn(s, 40)
    assert t.speaker_id == panel[1].id                  # advance -> owner of the NEXT agenda item (Funding), not who the model named
    assert "VERIFIED FACTS" in prompts[-1] and "$30,000 to $60,000" in prompts[-1]
    s.refresh_from_db(); assert s.agenda[0]["done"] is True and "parents will pay one million dollars" in s.board["claims"]
    assert Turn.objects.filter(session=s, role="candidate").get().factcheck["used"] is True   # a correction is used once, not repeated forever

def test_unclear_answer_is_not_built_on(ws, monkeypatch):
    s = _session(ws); panel = agents.session_panel(s); seen = {}
    def fake(prompt, system=None, json_mode=False, search=False, temperature=0.8, images=None, purpose="research", **kw):
        if "You chair the briefing" in prompt: return json.dumps({"items": []}), []
        if "at the start of a REAL interview" in prompt: return json.dumps({"text": "Good morning. Why are you going to the US?"}), []
        seen["p"] = prompt; return json.dumps({"speaker_id": panel[0].id, "move": "advance", "text": "Sorry, I did not catch that. Could you say it again?", "heard": "", "topic": "x", "end": False}), []
    monkeypatch.setattr(ai, "call", fake)
    agents.next_turn(s, 3); Turn.objects.create(session=s, role="candidate", text="Wood.", offset=10)
    s.refresh_from_db(); before = [a["done"] for a in s.agenda]
    t, _, _ = agents.next_turn(s, 12); s.refresh_from_db()
    assert "NO USABLE ANSWER" in seen["p"] and [a["done"] for a in s.agenda] == before and t.followup is False

def test_unclear_answer_rules():
    assert agents.unclear_answer("Wood.", "Who pays?") is True and agents.unclear_answer("Wood.", "Is it a bank statement?") is True   # one stray word is never an answer
    assert agents.unclear_answer("My father.", "Who is paying?") is False and agents.unclear_answer("My father pays.", "Who is paying?") is False
    assert agents.unclear_answer("Role", "Who is paying for your studies?") is True
    assert agents.unclear_answer("Yes.", "Are you married?") is False

def test_conduct_is_a_real_interview_not_a_coach():
    c = agents.CONDUCT
    assert "REAL INTERVIEW" in c and "not practice" in c and "You do not coach" in c and "never ask the candidate to upload" in c

def test_documents_are_collected_outside_the_interview(ws, client):
    c = client; c.login(username="u", password="p")
    assert [d["have"] for d in agents.doc_checklist(ws)] == [False, False]
    r = c.post(f"/w/{ws.pk}/docs/", {"key": "funds", "text": "Bank statement: balance 52,000 USD, account holder Mr A. Doe, dated 1 Nov 2026"}); assert r.status_code == 200
    assert c.post(f"/w/{ws.pk}/docs/", {"key": "nonsense", "text": "x" * 40}).status_code == 400
    ws.refresh_from_db(); got, miss = agents.doc_status(ws); assert got == ["Proof of funds"] and miss == ["I-20 form"]
    assert "DOCUMENTS NOT PROVIDED (this process expects them): I-20 form" in agents.ctx(ws) and "52,000 USD" in agents.ctx(ws)

def test_stt_hint_has_no_instruction_words(ws, client, monkeypatch):
    from core.services import stt
    c = client; c.login(username="u", password="p"); panelplan.allocate(ws); s = Session.objects.create(workspace=ws); seen = {}
    monkeypatch.setattr(stt, "transcribe", lambda data, mime, lang, hint: seen.setdefault("hint", hint) and {"text": "hi", "heard": True, "reason": ""})
    from django.core.files.uploadedfile import SimpleUploadedFile
    c.post(f"/room/{s.pk}/stt/", {"audio": SimpleUploadedFile("a.webm", b"x" * 900, "audio/webm")})
    assert "Role" not in seen["hint"] and "answer" not in seen["hint"].lower()
