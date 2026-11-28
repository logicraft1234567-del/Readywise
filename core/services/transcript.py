"""Transcript quality: deciding whether the words a candidate's answer was turned into can be trusted as EVIDENCE. Pure Python: no database, network or AI.

WHY THIS EXISTS
The evaluator judges the words in the transcript. When speech recognition guesses the wrong language (English speech printed as Vietnamese or German), the evaluator
judges words the candidate never said, and the score is corrupted by READYWISE, not by the candidate. Two things were letting that happen:
  1. the live voice path asked Gemini for transcription with no language at all, so it auto-detected per fragment;
  2. nothing checked a transcript before it was saved, scored or quoted.
Now every candidate turn is assessed here. A turn that is in the wrong language, in the wrong script, low confidence or a repeat is flagged `reliable: False`.
The evaluator never sees its words; it is not counted as an unanswered question; and the room asks the candidate to repeat or type instead of scoring it."""
import re

# Interview language name (as stored on Profile.language) -> ISO 639-1 code used by Whisper and Gemini.
ISO = {"English": "en", "French": "fr", "Spanish": "es", "Portuguese": "pt", "German": "de", "Arabic": "ar", "Hausa": "ha", "Yoruba": "yo", "Igbo": "ig",
       "Swahili": "sw", "Hindi": "hi", "Chinese (Mandarin)": "zh"}
BCP47 = {"English": "en-US", "French": "fr-FR", "Spanish": "es-ES", "Portuguese": "pt-PT", "German": "de-DE", "Arabic": "ar-SA", "Hausa": "ha-NG", "Yoruba": "yo-NG",
         "Igbo": "ig-NG", "Swahili": "sw-KE", "Hindi": "hi-IN", "Chinese (Mandarin)": "zh-CN"}
# Whisper's verbose_json reports the detected language by English name.
WHISPER_NAME = {"english": "en", "french": "fr", "spanish": "es", "portuguese": "pt", "german": "de", "arabic": "ar", "hausa": "ha", "yoruba": "yo", "igbo": "ig", "swahili": "sw",
                "hindi": "hi", "chinese": "zh", "vietnamese": "vi", "italian": "it", "dutch": "nl", "russian": "ru", "turkish": "tr", "indonesian": "id", "polish": "pl", "japanese": "ja", "korean": "ko"}
LATIN_LANGS = {"en", "fr", "es", "pt", "de", "ha", "yo", "ig", "sw", "it", "nl", "id", "tr", "pl", "vi"}

_STOPWORDS = {
    "en": "the and to of a in that is it for was on are with as be this have from or an by not but what all were when your can said there use each which she do how their if will up other about out many then them these so some her would make like him into time has look two more write go see number no way could people my than first water been call who oil its now find long down day did get come made may part i you we they he me he's i'm it's don't".split(),
    "de": "der die das und ist nicht ich du wir sie ein eine einen mit von zu den dem des auf für ist sind war auch es im an als aber oder wie wenn noch nur schon mein dein hier dass was wird kann haben hat bei nach aus über sehr".split(),
    "vi": "và của là có không được một những cho với trong này đó các để người tôi chúng khi đã sẽ như từ về ra cũng nhưng rất nhiều bạn anh chị em ông bà".split(),
    "fr": "le la les de des du un une et est que qui dans pour pas sur au avec ce il elle nous vous ils ne se plus par mais ou comme je tu mon ma mes son sa ses très être avoir fait".split(),
    "es": "el la los las de del un una y es que en por con para no se su sus al lo como más pero ya yo tú mi mis este esta muy ser tiene hacer todo también".split(),
    "pt": "o a os as de do da dos das um uma e é que em por com para não se seu sua ao como mais mas já eu você meu minha muito ser tem fazer também".split(),
}
_VI_CHARS = re.compile(r"[ạảãấầẩẫậắằẳẵặẹẻẽếềểễệỉĩịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹđơư]", re.I)
_DE_CHARS = re.compile(r"[äöüßÄÖÜ]")
_SCRIPTS = {"cjk": re.compile(r"[一-鿿぀-ヿ가-힯]"), "arabic": re.compile(r"[؀-ۿ]"), "cyrillic": re.compile(r"[Ѐ-ӿ]"),
            "devanagari": re.compile(r"[ऀ-ॿ]"), "thai": re.compile(r"[฀-๿]"), "hebrew": re.compile(r"[֐-׿]")}
_SCRIPT_FOR = {"zh": "cjk", "ja": "cjk", "ko": "cjk", "ar": "arabic", "ru": "cyrillic", "hi": "devanagari"}


def iso_for(language):
    """ISO code for a language name or code. Unknown names fall back to English: the interview language is always explicit, never auto-detected."""
    s = str(language or "").strip()
    if s in ISO: return ISO[s]
    low = s.lower().split("-")[0]
    return low if low in LATIN_LANGS or low in ISO.values() else "en"


def _words(text): return re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)?", str(text or "").lower())


def detect(text):
    """Best-effort language of a transcript: (iso, strength 0-1). Script first, then stopword and diacritic evidence. Short texts are 'unknown' on purpose."""
    t = str(text or ""); w = _words(t)
    if len(w) < 4 and len(t) < 12: return "unknown", 0.0
    for sc, rx in _SCRIPTS.items():
        n = len(rx.findall(t))
        if n >= max(3, 0.3 * len(re.sub(r"\s", "", t))): return {"cjk": "zh", "arabic": "ar", "cyrillic": "ru", "devanagari": "hi"}.get(sc, sc), min(1.0, n / max(1, len(t)) * 2)
    if len(w) < 4: return "unknown", 0.0
    score = {}
    for lang, sw in _STOPWORDS.items():
        hit = sum(1 for x in w if x in sw); score[lang] = hit / len(w)
    score["vi"] += 0.25 * min(1.0, len(_VI_CHARS.findall(t)) / max(1, len(w)) * 3)
    score["de"] += 0.12 * min(1.0, len(_DE_CHARS.findall(t)) / max(1, len(w)) * 3)
    best = max(score, key=score.get); ordered = sorted(score.values(), reverse=True)
    margin = ordered[0] - ordered[1]
    if ordered[0] < 0.12: return "unknown", ordered[0]
    return best, round(min(1.0, margin * 3 + ordered[0]), 2)


def language_ok(text, expected):
    """False only when the text is clearly in a DIFFERENT language from the one the interview is conducted in. Proper nouns, code and short answers pass."""
    exp = iso_for(expected); w = _words(text)
    if len(w) < 5: return True
    lang, strength = detect(text)
    if lang == "unknown" or lang == exp: return True
    if exp in ("ha", "yo", "ig", "sw") : return lang not in ("vi", "de", "zh", "ru", "ar") or strength < 0.5   # these have no stopword list here; only reject unmistakable other-script/language
    if exp in _SCRIPT_FOR and lang != exp: return strength < 0.4
    return strength < 0.35 or (lang in ("vi", "de", "fr", "es", "pt") and exp == "en" and strength < 0.45)


def assess(text, expected_language="English", whisper=None, requested=None):
    """Is this transcript usable as evidence? Returns {"reliable": bool, "confidence": 0-1, "issues": [codes], "language": iso detected}.
    whisper: the provider's own verbose_json dict (language, segments with avg_logprob, no_speech_prob, compression_ratio). Issue codes: language_mismatch, wrong_script,
    low_confidence, repetition, too_short, provider_language_mismatch."""
    exp = iso_for(expected_language); issues = []; conf = 1.0
    t = " ".join(str(text or "").split()); lang, strength = detect(t)
    if not t: return {"reliable": False, "confidence": 0.0, "issues": ["empty"], "language": "unknown"}
    if not language_ok(t, expected_language): issues.append("language_mismatch"); conf = min(conf, 0.2)
    if exp in ("en", "fr", "es", "pt", "de") and any(rx.search(t) and len(rx.findall(t)) >= 2 for k, rx in _SCRIPTS.items() if k != _SCRIPT_FOR.get(exp)): issues.append("wrong_script"); conf = min(conf, 0.15)
    if exp == "en" and len(_VI_CHARS.findall(t)) >= 3: issues.append("language_mismatch"); conf = min(conf, 0.2)
    if re.search(r"(\b\w+\b)(?:\W+\1\b){4,}", t.lower()) or re.search(r"(.{6,}?)(?:\W+\1){3,}", t.lower()): issues.append("repetition"); conf = min(conf, 0.3)
    if whisper:
        segs = [s for s in (whisper.get("segments") or []) if isinstance(s, dict)]
        got = WHISPER_NAME.get(str(whisper.get("language") or "").lower(), str(whisper.get("language") or "").lower()[:2])
        if got and got != exp and requested != exp: issues.append("provider_language_mismatch"); conf = min(conf, 0.3)
        elif got and got != exp: issues.append("provider_language_mismatch"); conf = min(conf, 0.5)   # we forced the language yet the provider still heard another
        if segs:
            lp = sorted(float(s.get("avg_logprob", 0)) for s in segs); med = lp[len(lp) // 2]
            if med < -1.0: issues.append("low_confidence"); conf = min(conf, max(0.0, 1.0 + med) * 0.6)
            elif med < -0.7: conf = min(conf, 0.7)
            if any(float(s.get("compression_ratio", 0)) > 2.4 for s in segs): issues.append("repetition"); conf = min(conf, 0.3)
    if len(_words(t)) < 2 and len(t) < 8: issues.append("too_short"); conf = min(conf, 0.6)
    hard = {"language_mismatch", "wrong_script", "low_confidence", "repetition", "provider_language_mismatch"}
    reliable = not (set(issues) & hard)
    return {"reliable": reliable, "confidence": round(conf, 2), "issues": sorted(set(issues)), "language": lang}


# ---------- duplicates and merging ----------
def _sent(t): return [s.strip() for s in re.split(r"(?<=[.!?])\s+", str(t or "").strip()) if s.strip()]


def squash_repeats(text):
    """Remove sentences that immediately repeat (a chunk transcribed twice). Order and first occurrences are kept."""
    out, last = [], ""
    for s in _sent(text):
        k = re.sub(r"\W+", " ", s.lower()).strip()
        if k and k == last: continue
        out.append(s); last = k
    return " ".join(out)


def merge_fragments(prev, new):
    """Append `new` to `prev` without duplicating overlapping words. Live transcription and chunked audio overlap at the seams; naive concatenation doubles words."""
    prev, new = " ".join(str(prev or "").split()), " ".join(str(new or "").split())
    if not prev: return new
    if not new: return prev
    pw, nw = prev.split(), new.split()
    for n in range(min(len(pw), len(nw), 12), 0, -1):
        if [w.lower().strip(".,!?") for w in pw[-n:]] == [w.lower().strip(".,!?") for w in nw[:n]]: return " ".join(pw + nw[n:])
    return prev + " " + new


def is_duplicate_turn(text, previous, window=3):
    """True when this candidate turn repeats one of the last few already saved (a retry or a double upload). previous: list of earlier candidate turn texts, newest last."""
    k = re.sub(r"\W+", " ", str(text or "").lower()).strip()
    if len(k.split()) < 4: return False
    return any(re.sub(r"\W+", " ", str(p or "").lower()).strip() == k for p in previous[-window:])


# ---------- what the evaluator is allowed to read ----------
UNRELIABLE_MARK = "[audio not transcribed reliably; these words are excluded from the evaluation]"


def usable(turn_asr):
    """A turn is evidence unless its saved assessment says it is not reliable. Turns saved before this feature have no assessment and are trusted as before."""
    return not (isinstance(turn_asr, dict) and turn_asr.get("reliable") is False)


def summarise(turns_asr):
    """(n_candidate_turns, n_unreliable, share) for the report's transcription-quality note."""
    n = len(turns_asr); bad = sum(1 for a in turns_asr if not usable(a))
    return n, bad, (bad / n if n else 0.0)
