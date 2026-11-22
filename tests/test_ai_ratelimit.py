"""Groq rate limits: cool the key down, use the next key or model, wait only when everything is limited, never wait for a hopeless request.
Runs against a local fake Groq server, without Django installed or any network."""
import importlib.util, json, sys, threading, types
from http.server import BaseHTTPRequestHandler, HTTPServer
if importlib.util.find_spec("django") is None:
    dj = types.ModuleType("django"); conf = types.ModuleType("django.conf")
    conf.settings = types.SimpleNamespace(GROQ_RESEARCH_KEYS=["k1", "k2"], GROQ_INTERVIEW_KEYS=["k1", "k2"], GROQ_API_KEY="", GROQ_MODELS=["big", "small"]); dj.conf = conf; sys.modules.update({"django": dj, "django.conf": conf})
import pytest
from core.services import ai

@pytest.fixture(autouse=True)
def _clean_state():
    """These tests replace ai._keys / ai.BASE and fill the cool-down tables; put everything back so other test files see the real thing."""
    keys, base, send = ai._keys, ai.BASE, ai._send; yield
    ai._keys, ai.BASE, ai._send = keys, base, send; ai._cool.clear(); ai._lim.clear(); ai._dead.clear()

SCRIPT = {}   # (key, model) -> list of replies, consumed in order; a reply is ("ok",) or (429, message)
CALLS = []
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); key = self.headers["Authorization"].split()[-1]; CALLS.append((key, body["model"]))
        q = SCRIPT.get((key, body["model"]), []); r = q.pop(0) if q else ("ok",)
        if r[0] == "ok": out = {"choices": [{"message": {"content": "hello from " + body["model"]}}]}; code = 200
        else: code = r[0]; out = {"error": {"message": r[1]}}
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(out).encode())
    def log_message(self, *a): pass

def setup(script):
    SCRIPT.clear(); SCRIPT.update(script); CALLS.clear(); ai._cool.clear(); srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    ai.BASE = f"http://127.0.0.1:{srv.server_port}"; slept.clear(); return srv
slept = []; ai.time.sleep = lambda s: slept.append(s)   # no real waiting in tests
MSG = lambda t: f"Rate limit reached for model `x`. Limit 8000, Used 7000, Requested 3000. Please try again in {t}."
def chat(): return ai._chat(["big", "small"], [{"role": "user", "content": "hi"}], 0.5, False, "research")["content"]

def test_retry_seconds_parsing():
    assert ai.retry_seconds("Please try again in 2.5s.") == 2.5 and ai.retry_seconds("try again in 350ms") == 0.35
    assert abs(ai.retry_seconds("try again in 1m5.3s") - 65.3) < 1e-6 and ai.retry_seconds("try again in 14m24s") == 864 and ai.retry_seconds("nothing here") == 8.0

def test_a_limited_key_is_skipped_and_stays_cooled_down():
    srv = setup({("k1", "big"): [(429, MSG("1.5s"))], ("k2", "big"): []}); ai._keys = lambda p: ["k1", "k2"]   # k1 is tried first, is refused and cools down
    assert chat() == "hello from big"
    CALLS.clear(); assert chat() == "hello from big" and all(k == "k2" for k, _ in CALLS)   # k1 is cooling down: no wasted request on it
    srv.shutdown()

def test_all_keys_limited_on_one_model_falls_back_to_the_other_model_without_waiting():
    srv = setup({("k1", "big"): [(429, MSG("20s"))], ("k2", "big"): [(429, MSG("20s"))]}); ai._keys = lambda p: ["k1", "k2"]
    assert chat() == "hello from small" and slept == []; srv.shutdown()

def test_everything_limited_waits_for_the_soonest_then_succeeds():
    msgs = {(k, m): [(429, MSG("2s"))] for k in ("k1", "k2") for m in ("big", "small")}; srv = setup(msgs); ai._keys = lambda p: ["k1", "k2"]
    real = ai.time.time; clock = [real()]; ai.time.time = lambda: clock[0]; ai.time.sleep = lambda s: (slept.append(s), clock.__setitem__(0, clock[0] + s))
    try: assert chat().startswith("hello") and slept and 2 <= slept[0] <= 3
    finally: ai.time.time = real; srv.shutdown()

def test_a_daily_limit_fails_fast_with_a_clear_message():
    d = {(k, m): [(429, "Rate limit reached for model `x` on tokens per day (TPD): Limit 200000, Used 199990, Requested 3000. Please try again in 14m24s.")] for k in ("k1", "k2") for m in ("big", "small")}
    srv = setup(d); ai._keys = lambda p: ["k1", "k2"]
    try: chat(); assert False
    except ai.AIError as e: assert "rate limiting" in str(e) and "add more keys" in str(e) and slept == []
    srv.shutdown()

def test_a_request_bigger_than_the_per_minute_limit_is_reported_at_once():
    srv = setup({("k1", "big"): [(429, "Rate limit reached. Limit 8000, Used 0, Requested 21000. Please try again in 5s.")], ("k1", "small"): [(429, "Limit 8000, Used 0, Requested 21000.")]}); ai._keys = lambda p: ["k1"]
    try: chat(); assert False
    except ai.AIError as e: assert "request_too_large" in str(e) or "413" in str(e)
    assert slept == []; srv.shutdown()


# ---- the "once and for all" part: use other models, learn from Groq's headers, wait only where waiting is allowed ----
def test_groq_headers_make_us_wait_for_a_refill_instead_of_being_refused():
    ai._lim.clear(); ai._learn("k1", "big", {"x-ratelimit-remaining-tokens": "300", "x-ratelimit-reset-tokens": "3s"})
    assert 2 < ai._short_wait("k1", "big", 2000) <= 3 and ai._short_wait("k1", "big", 100) == 0 and ai._short_wait("k2", "big", 2000) == 0
    import time as _t; ai._lim[("k1", "big")] = (300, _t.time() - 1)
    assert ai._short_wait("k1", "big", 2000) == 0                                 # the reset time has passed, the allowance is back: go ahead
    ai._learn("k1", "big", None); ai._learn("k1", "big", {})                      # missing headers never break a call

def test_a_busy_key_is_skipped_before_sending_not_after_a_429():
    srv = setup({}); ai._keys = lambda p: ["k1", "k2"]; ai._lim.clear(); ai._learn("k1", "big", {"x-ratelimit-remaining-tokens": "5", "x-ratelimit-reset-tokens": "9s"})
    try: assert chat() == "hello from big" and all(k == "k2" for k, _ in CALLS)    # k1 is known to be empty, so no request is wasted on it
    finally: ai._lim.clear(); srv.shutdown()

def test_a_retired_model_is_not_asked_again():
    srv = setup({("k1", "big"): [(404, "The model `big` does not exist or has been decommissioned: model_not_found")]}); ai._keys = lambda p: ["k1"]; ai._dead.clear()
    try:
        assert chat() == "hello from small"; CALLS.clear(); assert chat() == "hello from small" and all(m == "small" for _, m in CALLS)
    finally: ai._dead.clear(); srv.shutdown()

def test_patience_is_opt_in_per_thread_and_a_short_wait_gives_up_quickly():
    assert ai._max_wait() == ai.MAX_WAIT and ai._max_wait(3) == 3
    with ai.patient(150): assert ai._max_wait() == 150 and ai.current_wait() == 150
    assert ai._max_wait() == ai.MAX_WAIT
    d = {(k, m): [(429, MSG("20s"))] for k in ("k1", "k2") for m in ("big", "small")}; srv = setup(d); ai._keys = lambda p: ["k1", "k2"]
    try:
        ai._chat(["big", "small"], [{"role": "user", "content": "hi"}], 0.5, False, "research", wait=2); assert False
    except ai.AIError as e: assert "busy" in str(e) and "rate limiting" in str(e) and "add more keys" in str(e) and slept == []
    finally: srv.shutdown()

def test_light_jobs_try_the_cheap_models_first(monkeypatch):
    srv = setup({}); ai._keys = lambda p: ["k1"]; monkeypatch.setattr(ai.settings, "GROQ_LIGHT_MODELS", ["small", "big"], raising=False); monkeypatch.setattr(ai.settings, "GROQ_MODELS", ["big", "small"], raising=False)
    try:
        assert ai.call("hi", light=True)[0] == "hello from small" and CALLS[-1][1] == "small"
        assert ai.call("hi")[0] == "hello from big" and CALLS[-1][1] == "big"
    finally: srv.shutdown()

def test_search_only_runs_on_models_that_have_it_and_other_models_never_get_gpt_oss_options():
    srv = setup({}); ai._keys = lambda p: ["k1"]; seen = []
    real = ai._send; ai._send = lambda body, purpose: (seen.append(body), real(body, purpose))[1]
    try:
        ai._chat(["llama-x", "openai/gpt-oss-120b"], [{"role": "user", "content": "hi"}], 0.3, False, "research", tools=[{"type": "browser_search"}], reasoning_effort="medium")
        assert [b["model"] for b in seen] == ["openai/gpt-oss-120b"] and seen[0]["reasoning_effort"] == "medium"          # the web-search tool only goes to a model that has it
        seen.clear(); ai._chat(["llama-x"], [{"role": "user", "content": "hi"}], 0.3, False, "research", reasoning_effort="medium")
        assert "reasoning_effort" not in seen[0]
    finally: ai._send = real; srv.shutdown()
