"""Speech-to-text service tests. They run a local fake Groq server, so no key or network is needed.
Run: python -m pytest tests/test_stt.py   (also runs without Django installed, using a stub settings object)."""
import importlib.util, json, sys, threading, types
from http.server import BaseHTTPRequestHandler, HTTPServer
if importlib.util.find_spec("django") is None:
    dj = types.ModuleType("django"); conf = types.ModuleType("django.conf")
    conf.settings = types.SimpleNamespace(GROQ_RESEARCH_KEYS=[], GROQ_INTERVIEW_KEYS=["k1"], GROQ_API_KEY="", GROQ_STT_MODELS=["m-gone", "m-ok"])
    dj.conf = conf; sys.modules.update({"django": dj, "django.conf": conf})
from core.services import ai, stt

SEEN = []
class H(BaseHTTPRequestHandler):
    reply = {}
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])); SEEN.append((self.headers["Content-Type"], self.headers["Authorization"], body))
        model = body.split(b'name="model"\r\n\r\n')[1].split(b"\r\n")[0].decode()
        if model == "m-gone": self.send_response(404); self.end_headers(); self.wfile.write(b'{"error":{"code":"model_not_found"}}'); return
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(H.reply).encode())
    def log_message(self, *a): pass

def serve(reply):
    H.reply = reply; SEEN.clear(); srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    ai.BASE = f"http://127.0.0.1:{srv.server_port}"; return srv

AUDIO = b"x" * 5000
def test_real_speech_is_returned_and_request_is_well_formed():
    srv = serve({"text": " I led the migration of our billing service to Postgres.", "segments": [{"start": 0, "end": 4, "no_speech_prob": 0.01, "avg_logprob": -0.2}]})
    r = stt.transcribe(AUDIO, "audio/webm;codecs=opus", "en-US", "Role: backend engineer"); srv.shutdown()
    assert r["text"] == "I led the migration of our billing service to Postgres." and r["heard"] is True and r["reason"] == "" and r["reliable"] is True
    ctype, auth, body = SEEN[-1]
    assert ctype.startswith("multipart/form-data; boundary=") and auth == "Bearer k1"
    assert b'name="language"\r\n\r\nen' in body and b'filename="answer.webm"' in body and b"Role: backend engineer" in body and AUDIO in body

def test_retired_model_falls_through_to_next():
    srv = serve({"text": "Hello there, my name is Sam.", "segments": []}); r = stt.transcribe(AUDIO); srv.shutdown()
    assert r["heard"] and len(SEEN) == 2   # m-gone (404) then m-ok

def test_silence_hallucination_is_not_passed_to_the_interviewer():
    srv = serve({"text": "Thank you.", "segments": [{"start": 0, "end": 1.0, "no_speech_prob": 0.9, "avg_logprob": -1.8}]}); r = stt.transcribe(AUDIO); srv.shutdown()
    assert r["heard"] is False and r["text"] == ""

def test_short_phantom_without_segments_is_dropped_but_real_short_answer_kept():
    assert stt.judge({"text": "Thanks for watching!"})["heard"] is False
    assert stt.judge({"text": "Yes, about six years."})["heard"] is True
    assert stt.judge({"text": ""})["reason"] == "silence"

def test_tiny_clip_never_reaches_the_network():
    assert stt.transcribe(b"x" * 100)["reason"] == "empty"
