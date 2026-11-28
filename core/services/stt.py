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
from . import transcript as tsq

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

WHISPER_LANGS = {"en", "fr", "es", "pt", "de", "ar", "ha", "yo", "sw", "hi", "zh"}   # Igbo is not a Whisper language: for it the language is not forced and the transcript is checked afterwards

def judge(result, expected="en"):
    """Decide from Whisper's own confidence numbers whether real speech was heard, and then whether the words can be trusted as evidence. Pure function, unit-tested.
    Returns text, heard, reason, plus reliable / confidence / issues / language (services/transcript.py): a transcript in the wrong language or with low confidence is heard but NOT reliable."""
    text = " ".join(str(result.get("text") or "").split())
    segs = [s for s in (result.get("segments") or []) if isinstance(s, dict)]
    if not text: return {"text": "", "heard": False, "reason": "silence", "reliable": False, "confidence": 0.0, "issues": ["empty"], "language": "unknown"}
    if segs:
        speech = [s for s in segs if s.get("no_speech_prob", 0) < 0.6 or s.get("avg_logprob", 0) > -1.0]
        if not speech: return {"text": "", "heard": False, "reason": "no_speech", "reliable": False, "confidence": 0.0, "issues": ["no_speech"], "language": "unknown"}
        dur = sum(max(0.0, s.get("end", 0) - s.get("start", 0)) for s in speech)
    else:
        dur = None
    if PHANTOM.match(text) and (dur is None or dur < 1.6): return {"text": "", "heard": False, "reason": "phantom", "reliable": False, "confidence": 0.0, "issues": ["phantom"], "language": "unknown"}
    text = tsq.squash_repeats(text)   # a chunk transcribed twice must not count twice
    q = tsq.assess(text, expected, whisper=result, requested=expected)
    return {"text": text, "heard": True, "reason": "" if q["reliable"] else "unreliable", "reliable": q["reliable"], "confidence": q["confidence"], "issues": q["issues"], "language": q["language"]}

def transcribe(data, mime="audio/webm", language="en", prompt=""):
    """language is the interview's language (a code such as en or en-US, from the session). It is ALWAYS sent to the provider for the languages it supports, so English speech is never
    guessed to be Vietnamese or German. If the result still comes back in another language or with low confidence it is retried once on the next model with no vocabulary prompt; if it is still
    not reliable it is returned flagged (reliable False) so the room asks the candidate to repeat instead of scoring words they never said."""
    if not data or len(data) < 800: return {"text": "", "heard": False, "reason": "empty", "reliable": False, "confidence": 0.0, "issues": ["empty"], "language": "unknown"}
    if len(data) > MAX_BYTES: raise ai.AIError("That recording is too long to transcribe. Answer in shorter parts.")
    iso = tsq.iso_for(language); force = iso if iso in WHISPER_LANGS else ""
    models = list(getattr(settings, "GROQ_STT_MODELS", None) or ["whisper-large-v3", "whisper-large-v3-turbo"])
    last, best = None, None
    for n, m in enumerate(models):
        err = None
        for attempt in (0, 1):
            try: r = judge(_post(m, data, "answer." + _ext(mime), mime or "audio/webm", force, "" if best is not None else prompt), iso)   # the retry after a doubtful result drops the vocabulary prompt, which can itself bias the guess
            except ai.AIError as e:
                err = last = e
                if attempt == 0 and "429" in str(e) and ai.retry_seconds(e, 99) <= 12:   # a short rate limit: wait it out once, then try this model again
                    import time; time.sleep(ai.retry_seconds(e) + 0.3); continue
                break
            err = None
            if r["reliable"] or not r["heard"]: return r
            if best is None or r["confidence"] > best["confidence"]: best = r   # heard but doubtful: the next model gets a chance to do better
            break
        if err is not None and not ai._skip(err): raise err   # a retired or rate-limited model falls through to the next; any other error stops
    if best is not None: return best
    raise ai.AIError(f"No Groq speech model could transcribe this. Run `python manage.py groq_models` and set GROQ_STT_MODEL. Last error: {last}")
