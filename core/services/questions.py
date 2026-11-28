"""Question quality for the interview panel. Pure Python.

The panel must not ask the same thing twice. The model is told what was already asked, but a model can still rephrase an earlier question, so the check is also made in
code: a new question that is too close to one already asked (or already answered) is rejected and the panel is asked once more with the offending question named.
A follow-up that digs into the SAME answer is fine; it must add something new (a number, a reason, a mechanism) rather than restate the question."""
import re

from . import identity

_FILLER = set("tell me about please could you would can walk through what how why do does did is are was were your you the a an of to in on for and or with that this it explain describe "
              "give example specific specifically exactly more detail details little bit also then so now next okay ok well just really actually".split())


def tokens(q):
    """Content words of a question, with the commonest endings folded so 'costs' and 'cost' match."""
    out = []
    for w in re.findall(r"[a-z][a-z0-9']+", str(q or "").lower()):
        if w in _FILLER or len(w) < 3: continue
        for suf in ("ing", "ed", "es", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 4: w = w[:-len(suf)]; break
        out.append(w)
    return out


def similarity(a, b):
    """0 to 1: how much of the SMALLER question's content is in the other. Identical or reworded questions score high; questions that share a topic but ask different things stay low."""
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb: return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def duplicate_of(new, earlier, threshold=0.75):
    """The earlier question the new one repeats, or None. earlier: list of question strings."""
    best, hit = 0.0, None
    for q in earlier or []:
        s = similarity(new, q)
        if s > best: best, hit = s, q
    return hit if best >= threshold and len(tokens(new)) >= 3 else None


def is_duplicate(new, earlier, threshold=0.75):
    return duplicate_of(new, earlier, threshold) is not None


def unique(candidates, earlier, threshold=0.75):
    """The first candidate question that repeats nothing already asked (or, failing that, None)."""
    asked = list(earlier or [])
    for c in candidates or []:
        if not is_duplicate(c, asked, threshold): return c
    return None


def already_covered_note(earlier, limit=12):
    """A line for the prompt: the questions already asked, so the model can avoid them."""
    qs = [re.sub(r"\s+", " ", str(q)).strip()[:140] for q in (earlier or []) if str(q).strip()][-limit:]
    return ("QUESTIONS ALREADY ASKED (never repeat or merely reword any of these; ask something new, or dig into a specific detail of the answer given): " + " | ".join(qs)) if qs else ""


def candidate_questions(question_texts):
    """Questions in an interviewer turn: the sentences ending with a question mark (or the whole text if it has none)."""
    qs = [s.strip() for s in re.findall(r"[^?.!]*\?", str(question_texts or "")) if s.strip()]
    return qs or ([str(question_texts).strip()] if str(question_texts or "").strip() else [])


def clarification_for_claim(p, claim_text):
    """A fair follow-up for an unsupported or ambiguous claim: ask, do not accuse. p: the identity profile."""
    from . import findings
    kind = findings.claim_kind(claim_text)
    if kind in (findings.ESTIMATE, findings.FINANCIAL): return "How did you arrive at that figure, and what assumptions does it rest on?"
    if kind == findings.OWNERSHIP: return identity.clarification_question(p, claim_text)
    return "What is that based on, and can you point me to where I could check it?"


_STEMS = ["What was the hardest part of that, and how did you deal with it?", "What did you personally do there, as opposed to the people around you?",
          "What would you do differently if you did it again?", "What result did that produce, and how did you know it worked?",
          "What did you rule out, and why?", "What is the biggest risk in what you just described?"]


def fallback_followups(last_answer=""):
    """Neutral follow-ups that dig into the answer just given, for the rare case where the model repeats a question twice. They add no facts of their own."""
    return list(_STEMS)
