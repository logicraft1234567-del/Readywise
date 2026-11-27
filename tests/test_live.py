"""Live voice interview (Gemini Live): instruction building, token endpoint, transcript saving. Gemini itself is never called here."""
import json
from django.test import override_settings
from core.models import *
from core.services import live
from tests.test_flow import client_in  # noqa: F401
from tests.test_room_live import _session

def _open(c):
    ws, s = _session(c, 3)
    s.started_at = s.started_at; s.save(); return ws, s

def test_instruction_is_one_interviewer_with_the_real_interview_context(client_in):
    c = client_in; ws, s = _open(c); iv = live.lead_of(s); text = live.instruction(s)
    assert iv.name in text and "REAL" in text and "ONLY INTERVIEWER" in text and "Never comment on appearance" in text
    assert live.voice_for(iv) in live.FEMALE + live.MALE

def test_token_endpoint_needs_a_key_and_returns_no_secret(client_in, monkeypatch):
    c = client_in; ws, s = _open(c)
    with override_settings(LIVE_GEMINI_KEYS=[]):
        assert c.post(f"/room/{s.pk}/live/token/", content_type="application/json", data="{}").status_code == 400
    monkeypatch.setattr(live, "mint", lambda sess: {"token": "auth_tokens/abc", "model": "m", "lead": {"id": 1}, "limit_s": 600, "opening": "go"})
    with override_settings(LIVE_GEMINI_KEYS=["SECRET-KEY"]):
        r = c.post(f"/room/{s.pk}/live/token/", content_type="application/json", data="{}")
    assert r.status_code == 200 and "SECRET-KEY" not in r.content.decode() and r.json()["token"].startswith("auth_tokens/")

def test_token_failure_is_a_clean_error_so_the_browser_falls_back(client_in, monkeypatch):
    c = client_in; ws, s = _open(c)
    def boom(sess): raise RuntimeError("google down")
    monkeypatch.setattr(live, "mint", boom)
    with override_settings(LIVE_GEMINI_KEYS=["k"]):
        assert c.post(f"/room/{s.pk}/live/token/", content_type="application/json", data="{}").status_code == 502

def test_turns_are_saved_as_ordinary_turns(client_in):
    c = client_in; ws, s = _open(c)
    body = {"turns": [{"role": "interviewer", "text": "Tell me about  your last project."}, {"role": "candidate", "text": "I built a   cache."}, {"role": "candidate", "text": "   "}]}
    r = c.post(f"/room/{s.pk}/live/turns/", content_type="application/json", data=json.dumps(body))
    assert r.json()["saved"] == 2
    t = list(s.turns.order_by("id")); assert [x.role for x in t] == ["interviewer", "candidate"] and t[0].speaker == live.lead_of(s) and t[1].text == "I built a cache." and t[0].text == "Tell me about your last project."

def test_turns_refused_after_the_interview_ended(client_in):
    c = client_in; ws, s = _open(c); s.status = "done"; s.save()
    assert c.post(f"/room/{s.pk}/live/turns/", content_type="application/json", data=json.dumps({"turns": [{"role": "candidate", "text": "x"}]})).status_code == 400

# ---- fact-check and hands-on task in live mode ----
from core.services import agents, factcheck

def _talk(s, n=4):
    iv = live.lead_of(s)
    for k in range(n): Turn.objects.create(session=s, speaker=iv, role="interviewer", text=f"Question {k}?")

def test_wrong_claim_becomes_a_private_note_once(client_in):
    c = client_in; ws, s = _open(c); _talk(s, 1)
    t = Turn.objects.create(session=s, role="candidate", text="I cut latency by 900%.", factcheck={"claims": [{"claim": "cut latency by 900%", "verdict": "wrong", "truth": "A reduction cannot exceed 100%.", "source": "arithmetic"}]})
    r = c.post(f"/room/{s.pk}/live/facts/", content_type="application/json", data="{}").json()["text"]
    assert "PRIVATE NOTE" in r and "cut latency by 900%" in r and "A reduction cannot exceed 100%." in r
    assert c.post(f"/room/{s.pk}/live/facts/", content_type="application/json", data="{}").json()["text"] == ""   # handed over once

def test_supported_claims_produce_no_note(client_in):
    c = client_in; ws, s = _open(c)
    Turn.objects.create(session=s, role="candidate", text="I used Redis.", factcheck={"claims": [{"claim": "used Redis", "verdict": "supported", "truth": "", "source": ""}]})
    assert c.post(f"/room/{s.pk}/live/facts/", content_type="application/json", data="{}").json()["text"] == ""

def test_task_is_set_only_after_enough_conversation_and_only_once(client_in, monkeypatch):
    c = client_in; ws, s = _open(c); ws.duration = 30; ws.save()
    ch = {"title": "Sum", "brief": "Add numbers", "format": "code", "language": "javascript", "starter": "", "tests": [], "minutes": 10, "spoken": "Try this."}
    monkeypatch.setattr(agents, "build_format", lambda w: "code"); monkeypatch.setattr(agents, "make_challenge", lambda sess: ch)
    post = lambda: c.post(f"/room/{s.pk}/live/challenge/", content_type="application/json", data="{}").json()
    r = post(); assert r["challenge"] is None and r["final"] is False   # too early
    _talk(s, 4); r = post(); assert r["challenge"]["title"] == "Sum" and r["final"] is True
    s.refresh_from_db(); assert s.challenge["title"] == "Sum"
    r = post(); assert r["challenge"] is None and r["final"] is True      # never a second task

def test_task_is_skipped_for_roles_without_one(client_in, monkeypatch):
    c = client_in; ws, s = _open(c); _talk(s, 4); monkeypatch.setattr(agents, "build_format", lambda w: None)
    r = c.post(f"/room/{s.pk}/live/challenge/", content_type="application/json", data="{}").json(); assert r == {"challenge": None, "final": True}

def test_submitted_solution_keeps_its_line_breaks_and_the_standard_tag(client_in):
    c = client_in; ws, s = _open(c); code = "function solve(a){\n  return a;\n}"
    c.post(f"/room/{s.pk}/live/turns/", content_type="application/json", data=json.dumps({"turns": [{"role": "candidate", "text": code, "build": True}]}))
    t = s.turns.get(role="candidate"); assert t.text == agents.BUILD_TAG + code and "\n" in t.text

# ---- speed: voice in pieces, evaluation started early, no second model call ----
from core.services import tts
import core.jobs as jobs

def test_reply_is_spoken_first_sentence_first_and_pieces_keep_their_order():
    p = tts.parts("Thanks for that. You said you cut latency by two thirds, and I would like to understand how you measured it before and after the change. What did you compare?")
    assert p[0] == "Thanks for that." and " ".join(p) == "Thanks for that. You said you cut latency by two thirds, and I would like to understand how you measured it before and after the change. What did you compare?"
    assert tts.parts("Short one.") == ["Short one."] and tts.parts("") == []

def test_pieces_are_made_at_the_same_time_and_joined_in_order(monkeypatch):
    import io, wave, time
    def wav(tag):
        b = io.BytesIO(); w = wave.open(b, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(bytes([tag]) * 200); w.close(); return b.getvalue()
    def one(c, voice): time.sleep(.3); return wav(len(c) % 250 + 1)
    monkeypatch.setattr(tts, "_one", one); t0 = time.time()
    out = tts.synth("Sentence number one is here. " + "Another long sentence goes on and on. " * 6, "troy")
    assert time.time() - t0 < .3 * 3 and out[:4] == b"RIFF"   # four or more pieces in well under their summed time

def test_tts_part_endpoint_returns_one_piece_and_the_count(client_in, monkeypatch):
    c = client_in; ws, s = _open(c); _talk(s, 1); turn = s.turns.filter(role="interviewer").first()
    monkeypatch.setattr(tts, "_one", lambda c_, v: b"RIFF....WAVE")
    r = c.post(f"/room/{s.pk}/tts/", content_type="application/json", data=json.dumps({"turn_id": turn.id, "part": 0}))
    assert r.status_code == 200 and r["X-Parts"] == "1" and r.content[:4] == b"RIFF"

def _sync(monkeypatch):
    """Run the background evaluation in the test's own thread, so the test is deterministic and uses the test database."""
    from concurrent.futures import Future
    class Sync:
        def __init__(self, *a, **k): pass
        def submit(self, fn, *a):
            f = Future()
            try: f.set_result(fn(*a))
            except Exception as e: f.set_exception(e)
            return f
        def shutdown(self, wait=True): pass
    monkeypatch.setattr("concurrent.futures.ThreadPoolExecutor", Sync)
    class Conn:
        def close(self): pass
    monkeypatch.setattr(jobs, "connection", Conn())

def test_evaluation_started_at_the_closing_words_is_reused_not_run_twice(client_in, monkeypatch):
    c = client_in; ws, s = _open(c); _talk(s, 2); Turn.objects.create(session=s, role="candidate", text="I built a cache with a thirty second ttl and measured hit rate.")
    _sync(monkeypatch); calls = []
    class Ev: scores = {}
    monkeypatch.setattr(agents, "evaluate", lambda sess: (calls.append(1), (Ev(), {}))[1])
    monkeypatch.setattr(jobs.logic, "update_memory", lambda *a, **k: None); monkeypatch.setattr(jobs.logic, "adjust_plan", lambda *a, **k: None); monkeypatch.setattr(jobs.panelplan, "adapt_after_session", lambda *a, **k: None)
    jobs.prefetch_evaluation(s.pk); jobs.finalize_task(s.pk, [], None)
    s.refresh_from_db(); assert s.status == "done" and len(calls) == 1

def test_new_words_after_the_early_evaluation_make_it_run_again(client_in, monkeypatch):
    c = client_in; ws, s = _open(c); _talk(s, 2); Turn.objects.create(session=s, role="candidate", text="First answer with enough words to count here.")
    _sync(monkeypatch); calls = []
    class Ev: scores = {}
    monkeypatch.setattr(agents, "evaluate", lambda sess: (calls.append(1), (Ev(), {}))[1])
    monkeypatch.setattr(jobs.logic, "update_memory", lambda *a, **k: None); monkeypatch.setattr(jobs.logic, "adjust_plan", lambda *a, **k: None); monkeypatch.setattr(jobs.panelplan, "adapt_after_session", lambda *a, **k: None)
    jobs.prefetch_evaluation(s.pk); Turn.objects.create(session=s, role="candidate", text="One more thing I forgot to say before the end."); jobs.finalize_task(s.pk, [], None)
    assert len(calls) == 2   # the early result was discarded because the transcript changed

# ---- a panel of live interviewers: one session each, one voice at a time ----
def test_each_panelist_gets_their_own_brief_voice_and_a_handover_tool(client_in):
    c = client_in; ws, s = _open(c); panel = list(Interviewer.objects.filter(owner=None)[:3]); assert len(panel) == 3
    chair, other = live.instruction(s, panel[0], panel), live.instruction(s, panel[1], panel)
    assert "ONLY INTERVIEWER" not in chair and "You are the chair" in chair and panel[1].name in chair and "hand_over" in chair and "introduce your colleagues" not in chair   # the opening line is sent as a message, not repeated here
    assert "NOT the chair" in other and "YOU HAVE THE FLOOR" in other and "Say nothing until a message tells you" in other and "ONLY INTERVIEWER" not in other
    v = live.voices_for(panel); assert len(set(v.values())) == 3 and all(x in live.FEMALE + live.MALE for x in v.values())   # three different voices
    names = [f["name"] for f in live._tools(panel, panel[0])[0]["function_declarations"]]; assert names == ["end_interview", "hand_over"]
    assert live._tools(panel[:1], panel[0])[0]["function_declarations"][0]["name"] == "end_interview" and len(live._tools(panel[:1], panel[0])[0]["function_declarations"]) == 1   # alone: nobody to hand over to

def test_turns_keep_who_spoke(client_in):
    c = client_in; ws, s = _open(c); panel = agents.session_panel(s); who = panel[-1]
    c.post(f"/room/{s.pk}/live/turns/", content_type="application/json", data=json.dumps({"turns": [{"role": "interviewer", "text": "Over to my side.", "speaker": who.id}, {"role": "interviewer", "text": "Anyone.", "speaker": 999999}]}))
    t = list(s.turns.order_by("id")); assert t[0].speaker == who and t[1].speaker == live.lead_of(s)   # an unknown speaker falls back to the chair

# ---- repeat interviews explore new ground; the live interviewer cannot end it early ----
def test_a_repeat_interview_is_told_what_was_already_asked(client_in):
    c = client_in; ws, s = _open(c); assert agents.prior_block(s) == ""   # first attempt: nothing to avoid
    iv = live.lead_of(s); Turn.objects.create(session=s, speaker=iv, role="interviewer", text="Welcome, I am Sam.", topic="introductions")
    Turn.objects.create(session=s, speaker=iv, role="interviewer", text="Thanks for that. Walk me through the caching layer you built?")
    s.status = "done"; s.agenda = [{"area": "Caching project", "owner": iv.id}]; s.save()
    c.post(f"/w/{ws.pk}/session/", {}); s2 = Session.objects.exclude(pk=s.pk).get()
    b = agents.prior_block(s2)
    assert "Walk me through the caching layer you built?" in b and "Caching project" in b and "Welcome, I am Sam" not in b and "Do not ask any of these questions again" in b
    assert "EARLIER INTERVIEWS" in live.instruction(s2) and "at most one question in five" in b

def test_live_brief_forbids_ending_early(client_in):
    c = client_in; ws, s = _open(c); text = live.instruction(s)
    assert "refuses to end it early" in text and "candidate_stopped" in text and "never try before the last part" in text
