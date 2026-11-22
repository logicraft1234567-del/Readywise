"""Speech-to-text for the interview room (Groq Whisper).

Why this exists: browser dictation (webkitSpeechRecognition) only exists in Chrome-family browsers, sends audio to a
third party, silently stops, and gives no signal when it hears nothing. The room now records the candidate's own
microphone and sends it here, so every browser gets the same transcript and the interviewer only ever reacts to words
that were really transcribed.

transcribe() returns {"text": str, "heard": bool, "reason": str}. heard is False when the clip was silence/noise,
which stops Whisper's well-known habit of inventing "Thank you." or "Thanks for watching!" for an empty recording.
"""
import json, re, uuid, urllib.request, urllib.error
from django.conf import settings
from . import ai

MAX_BYTES = 8 * 1024 * 1024
EXT = {"webm": "webm", "ogg": "ogg", "mp4": "mp4", "m4a": "m4a", "mpeg": "mp3", "mp3": "mp3", "wav": "wav", "x-wav": "wav", "flac": "flac"}
# Phrases Whisper tends to produce from silence or room noise. Only treated as phantom when the clip is also very short.
PHANTOM = re.compile(r"^\W*(thank you(?: so much| very much)?|thanks(?: for watching)?|thanks for watching|bye(?:-bye)?|you|okay|ok|\.+|um+|uh+|hmm+|so|yeah)\W*$", re.I)

def _ext(mime):
    sub = (mime or "").split(";")[0].split("/")[-1].strip().lower()
    return EXT.get(sub, "webm")

def _multipart(fields, filename, content, mime):
    b = uuid.uuid4().hex; out = []
    for k, v in fields.items():
        out.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    out.append(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
    out.append(content); out.append(f"\r\n--{b}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={b}"

def _post(model, data, filename, mime, language, prompt):
    fields = {"model": model, "response_format": "verbose_json", "temperature": "0"}
    if language: fields["language"] = language
    if prompt: fields["prompt"] = prompt[:600]
    body, ctype = _multipart(fields, filename, data, mime)
    last = None
    for k in ai._keys("interview"):
        req = urllib.request.Request(ai.BASE + "/audio/transcriptions", body, {"Content-Type": ctype, "Authorization": "Bearer " + k, "User-Agent": "ReadyWise/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            last = ai.AIError(f"Groq returned {e.code}: {e.read().decode()[:300]}")
            if e.code not in (401, 429, 500, 502, 503): raise last
        except Exception as e:
            last = ai.AIError(f"Could not reach Groq: {e}")
    raise last or ai.AIError("No Groq key is set for the interview. Add GROQ_INTERVIEW_KEYS to .env.")

def judge(result):
    """Decide from Whisper's own confidence numbers whether real speech was heard. Pure function, unit-tested."""
    text = " ".join(str(result.get("text") or "").split())
    segs = [s for s in (result.get("segments") or []) if isinstance(s, dict)]
    if not text: return {"text": "", "heard": False, "reason": "silence"}
    if segs:
        speech = [s for s in segs if s.get("no_speech_prob", 0) < 0.6 or s.get("avg_logprob", 0) > -1.0]
        if not speech: return {"text": "", "heard": False, "reason": "no_speech"}
        dur = sum(max(0.0, s.get("end", 0) - s.get("start", 0)) for s in speech)
    else:
        dur = None
    if PHANTOM.match(text) and (dur is None or dur < 1.6): return {"text": "", "heard": False, "reason": "phantom"}
    return {"text": text, "heard": True, "reason": ""}

def transcribe(data, mime="audio/webm", language="en", prompt=""):
    if not data or len(data) < 800: return {"text": "", "heard": False, "reason": "empty"}
    if len(data) > MAX_BYTES: raise ai.AIError("That recording is too long to transcribe. Answer in shorter parts.")
    models = list(getattr(settings, "GROQ_STT_MODELS", None) or ["whisper-large-v3", "whisper-large-v3-turbo"])
    last = None
    for m in models:
        try: return judge(_post(m, data, "answer." + _ext(mime), mime or "audio/webm", (language or "en").split("-")[0].lower(), prompt))
        except ai.AIError as e:
            last = e
            if "429" in str(e) and ai.retry_seconds(e, 99) <= 12:   # a short rate limit: wait it out once, then try this model again
                import time; time.sleep(ai.retry_seconds(e) + 0.3)
                try: return judge(_post(m, data, "answer." + _ext(mime), mime or "audio/webm", (language or "en").split("-")[0].lower(), prompt))
                except ai.AIError as e2: last = e2
            if ai._skip(last): continue  # retired model or rate limited: try the next one
            raise last
    raise ai.AIError(f"No Groq speech model could transcribe this. Run `python manage.py groq_models` and set GROQ_STT_MODEL. Last error: {last}")
