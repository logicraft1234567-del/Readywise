"""Groq text-to-speech (Orpheus): one voice per interviewer. Returns WAV bytes.
Orpheus accepts short inputs, so longer turns are split at sentence ends and the WAV pieces are joined."""
import io, re, wave
from django.conf import settings
from . import ai

VOICES = ["troy", "austin", "daniel", "hannah", "diana", "autumn"]  # Orpheus English voices: three male, three female
MALE = ["troy", "austin", "daniel"]; FEMALE = ["hannah", "diana", "autumn"]
LEGACY = {"Orus": "troy", "Fenrir": "austin", "Charon": "daniel", "Puck": "austin", "Rasalgethi": "troy", "Iapetus": "daniel",  # old Gemini voice names saved in existing databases
          "Aoede": "hannah", "Leda": "diana", "Kore": "autumn", "Zephyr": "diana", "Algieba": "troy"}
MAX_CHARS = 190

def voice_for(name): 
    n = (name or "").strip(); low = n.lower()
    return low if low in VOICES else LEGACY.get(n, "troy")

def chunks(text, limit=MAX_CHARS):
    out, cur = [], ""
    for s in re.split(r"(?<=[.!?;:])\s+", " ".join(text.split())):
        while len(s) > limit:  # a very long sentence: cut at the last space
            cut = s.rfind(" ", 0, limit); cut = cut if cut > 40 else limit; piece, s = s[:cut], s[cut:].strip()
            if cur: out.append(cur); cur = ""
            out.append(piece)
        if cur and len(cur) + 1 + len(s) > limit: out.append(cur); cur = s
        else: cur = (cur + " " + s).strip()
    if cur: out.append(cur)
    return out

def join_wavs(parts):
    if len(parts) == 1: return parts[0]
    buf = io.BytesIO(); w = None
    for p in parts:
        with wave.open(io.BytesIO(p), "rb") as r:
            if w is None: w = wave.open(buf, "wb"); w.setparams(r.getparams())
            w.writeframes(r.readframes(r.getnframes()))
    w.close(); return buf.getvalue()

def synth(text, voice, style=""):
    parts = []
    for c in chunks(text):
        body = {"model": settings.GROQ_TTS_MODEL, "input": c, "voice": voice_for(voice), "response_format": "wav"}
        try: wav = ai.request("/audio/speech", body, "interview", raw=True)
        except ai.AIError as e:
            if "terms" in str(e).lower(): raise ai.AIError("Groq needs you to accept the Orpheus voice terms once (console.groq.com, Playground, text-to-speech). " + str(e)[:150])
            raise
        if wav[:4] != b"RIFF": raise ai.AIError("Groq returned no audio.")
        parts.append(wav)
    if not parts: raise ai.AIError("Groq returned no audio.")
    return join_wavs(parts)
