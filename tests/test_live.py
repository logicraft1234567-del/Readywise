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

def test_each_interviewer_gets_their_own_instruction_voice_and_tools(client_in):
    c = client_in; ws, s = _open(c); panel = live.panel_of(s); assert 2 <= len(panel) <= live.MAX_PANEL
    voices = live.voices_for(panel); assert len(set(voices)) == len(panel) and all(v in live.FEMALE + live.MALE for v in voices)   # nobody shares a voice
    texts = [live.instruction(s, iv) for iv in panel]
    for iv, text in zip(panel, texts):
        assert iv.name in text and "REAL" in text and "Never comment on appearance" in text and "YOUR TURN" in text and "pass_to" in text and "ONLY INTERVIEWER" not in text
        assert all(o.name in text for o in panel if o.id != iv.id)   # each knows who the colleagues are
    assert "you open the interview as the lead" in texts[0] and "Do not speak until a message starting with YOUR TURN" in texts[1]
    owned = {a.get("owner") for a in s.agenda}; assert owned <= {i.id for i in panel}   # one shared plan, areas split by interviewer

def test_a_solo_panel_is_one_interviewer_with_the_whole_plan(client_in, monkeypatch):
    c = client_in; ws, s = _open(c); solo = live.panel_of(s)[:1]; monkeypatch.setattr(live, "panel_of", lambda sess: solo)
    text = live.instruction(s); assert solo[0].name in text and "ONLY INTERVIEWER" in text and "pass_to" not in text.split("HOW TO SPEAK")[0]
    assert [t["function_declarations"][0]["name"] for t in live._tools([])] == ["end_interview"]

def test_panel_is_capped_at_three_and_every_member_has_a_hand_over_tool(client_in):
    c = client_in; ws, s = _open(c); panel = live.panel_of(s); names = [i.name for i in panel]
    fn = live._tools(panel[1:])[0]["function_declarations"]; assert [f["name"] for f in fn] == ["end_interview", "pass_to"] and fn[1]["parameters"]["properties"]["colleague"]["enum"] == names[1:]

def test_mint_gives_every_interviewer_a_token_on_a_different_key(client_in, monkeypatch):
    import sys, types
    c = client_in; ws, s = _open(c); used = []
    class Tokens:
        def __init__(self, key): self.key = key
        def create(self, config): used.append((self.key, config["live_connect_constraints"]["config"]["system_instruction"])); return types.SimpleNamespace(name=f"auth_tokens/{len(used)}")
    class Client:
        def __init__(self, api_key, http_options=None): self.auth_tokens = Tokens(api_key)
    fake = types.ModuleType("google"); fake.genai = types.SimpleNamespace(Client=Client); monkeypatch.setitem(sys.modules, "google", fake); monkeypatch.setitem(sys.modules, "google.genai", fake.genai)
    with override_settings(LIVE_GEMINI_KEYS=["k1", "k2", "k3"], LIVE_MODEL="m"):
        out = live.mint(s); n = len(live.panel_of(s))
        assert len(out["voices"]) == n and len({k for k, _ in used}) == n and len({v["token"] for v in out["voices"]}) == n and out["token"] == out["voices"][0]["token"]
        assert len({text for _, text in used}) == n   # each session has its own instruction
        used.clear(); one = live.mint(s, only=out["voices"][1]["id"]); assert len(one["voices"]) == 1 and one["voices"][0]["id"] == out["voices"][1]["id"] and len(used) == 1   # a reconnect mints one

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
    monkeypatch.setattr(agents, "build_plan", lambda sess: "code"); monkeypatch.setattr(agents, "make_challenge", lambda sess: ch)
    post = lambda: c.post(f"/room/{s.pk}/live/challenge/", content_type="application/json", data="{}").json()
    r = post(); assert r["challenge"] is None and r["final"] is False   # too early
    _talk(s, 4); r = post(); assert r["challenge"]["title"] == "Sum" and r["final"] is True
    s.refresh_from_db(); assert s.challenge["title"] == "Sum"
    r = post(); assert r["challenge"] is None and r["final"] is True      # never a second task

def test_task_is_skipped_for_roles_without_one(client_in, monkeypatch):
    c = client_in; ws, s = _open(c); _talk(s, 4); monkeypatch.setattr(agents, "build_plan", lambda sess: None)
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


def test_each_interviewers_words_are_saved_under_their_own_name(client_in):
    c = client_in; ws, s = _open(c); panel = live.panel_of(s)
    body = {"turns": [{"role": "interviewer", "text": "First question.", "speaker": panel[1].id}, {"role": "candidate", "text": "My answer."}, {"role": "interviewer", "text": "Second question.", "speaker": 999999}]}
    c.post(f"/room/{s.pk}/live/turns/", content_type="application/json", data=json.dumps(body))
    t = list(s.turns.order_by("id")); assert t[0].speaker == panel[1] and t[1].speaker is None and t[2].speaker == panel[0]   # an unknown speaker falls back to the lead

def test_reconnect_token_request_is_for_one_interviewer(client_in, monkeypatch):
    c = client_in; ws, s = _open(c); seen = {}
    monkeypatch.setattr(live, "mint", lambda sess, only=None: seen.setdefault("only", only) or {"voices": [], "token": "t"})
    with override_settings(LIVE_GEMINI_KEYS=["k"]):
        c.post(f"/room/{s.pk}/live/token/", content_type="application/json", data=json.dumps({"iv": 7}))
    assert seen["only"] == 7
