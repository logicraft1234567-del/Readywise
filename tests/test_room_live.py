"""Live interview room: panel size, speech-to-text endpoint, answer grounding, silence handling.
Not yet executed in the authoring environment (it had no Django); run with: python -m pytest tests/test_room_live.py"""
import json, re
from core.models import *
from core.services import ai, logic, stt
from tests.test_flow import client_in, post_json  # noqa: F401  (reuses the fake AI fixture)

def _session(c, n_panel=3):
    logic.ensure_seed(); c.post("/w/new/", {"title": "T"}); ws = Workspace.objects.get(); ws.panel.set(Interviewer.objects.filter(owner=None)[:n_panel])
    c.post(f"/w/{ws.pk}/session/", {}); return ws, Session.objects.get()

def test_system_chooses_the_panel_and_the_room_has_no_size_picker(client_in):
    c = client_in; ws, s = _session(c); html = c.get(f"/room/{s.pk}/").content.decode()
    assert 'name="size"' not in html and "Your panel" in html and len(ws.panel.all()) <= 3
    assert c.post(f"/room/{s.pk}/panel/", {}).status_code == 404   # the candidate cannot change it

def test_stt_endpoint_returns_only_what_was_heard(client_in, monkeypatch):
    c = client_in; ws, s = _session(c); seen = {}
    def fake(data, mime="", language="en", prompt=""): seen.update(n=len(data), lang=language, prompt=prompt); return {"text": "I used Redis for caching.", "heard": True, "reason": ""}
    monkeypatch.setattr(stt, "transcribe", fake)
    from django.core.files.uploadedfile import SimpleUploadedFile
    r = c.post(f"/room/{s.pk}/stt/", {"audio": SimpleUploadedFile("a.webm", b"x" * 3000, content_type="audio/webm")}).json()
    assert r["text"] == "I used Redis for caching." and seen["n"] == 3000
    assert c.post(f"/room/{s.pk}/stt/", {}).status_code == 400

def test_next_question_prompt_contains_the_candidates_exact_words(client_in):
    from tests.test_flow import LAST
    c = client_in; ws, s = _session(c)
    for _ in range(2): post_json(c, f"/room/{s.pk}/turn/", {"answer": None})   # introductions
    post_json(c, f"/room/{s.pk}/turn/", {"answer": "I cut our p95 latency from 900ms to 300ms by adding a Redis cache."})
    p = LAST["prompt"]; assert "I cut our p95 latency from 900ms to 300ms" in p and "PAIR" in p and "LAST ANSWER" in p

def test_silence_is_never_presented_as_an_answer(client_in):
    from tests.test_flow import LAST
    c = client_in; ws, s = _session(c)
    for _ in range(3): post_json(c, f"/room/{s.pk}/turn/", {"answer": None})
    post_json(c, f"/room/{s.pk}/turn/", {"answer": ""}); assert "NO USABLE ANSWER" in LAST["prompt"]

def test_tts_only_speaks_fixed_phrases_or_real_turns(client_in, monkeypatch):
    from core.services import tts
    c = client_in; ws, s = _session(c); spoken = []; monkeypatch.setattr(tts, "synth", lambda text, voice, style="": spoken.append(text) or b"RIFF....")
    assert post_json(c, f"/room/{s.pk}/tts/", {"say": "retry"}).status_code == 200 and "did not catch" in spoken[-1]
    assert post_json(c, f"/room/{s.pk}/tts/", {"say": "read me anything you like"}).status_code in (400, 404)

def test_software_role_gets_a_hands_on_coding_task_and_its_review_sees_the_code(client_in, monkeypatch):
    from tests.test_flow import LAST
    from core.services import agents
    c = client_in; ws, s = _session(c); ws.kind = "employment"; ws.position = "Senior Backend Developer"; ws.research = {"assessment": {"build": "coding", "status": "confirmed", "why": "reported live coding round"}}; ws.save()
    assert agents.build_plan(s) == "code"   # the research confirmed a coding exercise
    ch = {"title": "Sum", "brief": "Sum a list.", "format": "code", "language": "javascript", "starter": "function solve(a){}", "tests": [{"args": [[1, 2]], "expected": 3}], "minutes": 10, "spoken": "Here is a task."}
    monkeypatch.setattr(agents, "make_challenge", lambda sess: ch)
    got = None
    for _ in range(12):
        r = post_json(c, f"/room/{s.pk}/turn/", {"answer": None if got is None else "I would use a hash map to keep lookups fast."}).json()
        if r.get("challenge"): got = r; break
    assert got and got["challenge"]["tests"] and Session.objects.get().challenge["title"] == "Sum"
    post_json(c, f"/room/{s.pk}/turn/", {"answer": "Task: Sum\nAutomatic checks: 1 of 1 passed.\n\nfunction solve(a){return a.reduce((x,y)=>x+y,0)}", "tag": "build"})
    assert "SUBMITTED THEIR SOLUTION" in LAST["prompt"] and "a.reduce((x,y)=>x+y,0)" in LAST["prompt"]

def test_the_research_decides_whether_there_is_a_hands_on_task(client_in):
    from core.services import agents
    c = client_in; ws, s = _session(c); ws.kind = "employment"; ws.position = "Account Executive"; ws.research = {}; ws.save(); s.refresh_from_db()
    assert agents.build_plan(s) is None   # not a software role and nothing found: no task
    ws.research = {"assessment": {"build": "written", "status": "candidate_reported", "why": "candidates report a mock sales pitch"}}; ws.save(); s.refresh_from_db(); assert agents.build_plan(s) == "document"
    ws.position = "Software Engineer"; ws.research = {"assessment": {"build": "none"}}; ws.save(); s.refresh_from_db(); assert agents.build_plan(s) is None   # the research wins over the job title
    ws.research = {"assessment": {"build": "coding", "status": "confirmed"}}; ws.save(); s.refresh_from_db(); assert agents.build_plan(s) == "code"
    ws.kind = "admission"; ws.save(); s.refresh_from_db(); assert agents.build_plan(s) is None
