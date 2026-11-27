"""Live voice interview (Gemini Live). The server does two things only:
1. builds the interviewer's instructions from the same interview context the standard engine uses (candidate, role, research, agenda, persona), and
2. mints a short-lived, single-purpose token that is locked to that configuration, so the real API key and the instructions never reach the browser.
The audio itself travels browser <-> Google. Transcripts come back through room_live_turns and are saved as ordinary Turn rows."""
import datetime, hashlib, itertools
from django.conf import settings
from . import agents

_turn = itertools.count()   # hands each new interview the next key, so several live interviews at once spread over all the keys

FEMALE = ["Kore", "Aoede", "Leda"]
MALE = ["Puck", "Charon", "Fenrir"]

def enabled(): return bool(getattr(settings, "LIVE_GEMINI_KEYS", []))

MAX_PANEL = 3   # one live session per interviewer; the number of interviewers still comes from the research

def panel_of(sess): return agents.session_panel(sess)[:MAX_PANEL]

def lead_of(sess): return panel_of(sess)[0]

def voices_for(panel):
    """A different voice for every interviewer on the call, chosen by gender and name so the same person always sounds the same."""
    used, out = set(), []
    for iv in panel:
        pool = FEMALE if (iv.gender or "m").lower().startswith("f") else MALE
        base = int(hashlib.md5(iv.name.encode()).hexdigest(), 16) % len(pool)
        pick = next((pool[(base + k) % len(pool)] for k in range(len(pool)) if pool[(base + k) % len(pool)] not in used), pool[base])
        used.add(pick); out.append(pick)
    return out

def voice_for(iv):
    pool = FEMALE if (iv.gender or "m").lower().startswith("f") else MALE
    return pool[int(hashlib.md5(iv.name.encode()).hexdigest(), 16) % len(pool)]

def plan_block(sess, iv, panel):
    if len(panel) == 1: return f"YOU ARE THE ONLY INTERVIEWER: cover every area of the plan yourself, in one natural one-to-one conversation.\nTHE PLAN (private; follow it, never read it out):\n{agents.agenda_text(sess.agenda, [iv])}"
    others = [i for i in panel if i.id != iv.id]; by = {i.id: i.name for i in panel}
    line = lambda a: f"- {a.get('area')} (competency: {a.get('competency') or 'any'}; goal: {a.get('goal', '')})"
    mine = [a for a in sess.agenda if a.get("owner") == iv.id]; theirs = [a for a in sess.agenda if a.get("owner") != iv.id]
    return (f"YOU ARE ONE OF {len(panel)} INTERVIEWERS ON THIS CALL, with " + ", ".join(f"{i.name} ({i.position})" for i in others) + ". The panel shares ONE plan and you own only your own areas; never ask about a colleague's area.\n"
            "YOUR AREAS (private; follow them in order, never read them out):\n" + ("\n".join(line(a) for a in mine) or "- none: support the others and ask one sharp follow-up when you have the floor") + "\n"
            "YOUR COLLEAGUES' AREAS (private):\n" + ("\n".join(f"- {by.get(a.get('owner'), '?')}: {a.get('area')}" for a in theirs) or "- none") + "\n"
            "HOW THE PANEL TAKES TURNS: only ONE interviewer speaks at a time. You stay completely silent until a system message that starts with YOUR TURN gives you the floor. While you hold it you hear the candidate directly: react to each answer with something concrete and ask your next question, one at a time. "
            "When your areas are covered, or the system tells you to, hand over: say one short natural line naming the colleague and what they will ask about (for example: Thanks, that is clear. I will pass you to Priya, who will ask about your design choices.), THEN call the pass_to tool, then say nothing more. Never speak for a colleague and never hand over before you have heard the candidate answer at least once.")

def begin_rule(iv, panel, first):
    name = (' by first name (' + first + ')') if first else ''
    if len(panel) == 1: return f"- The first message you receive tells you to begin. Greet the candidate{name}, say who you are and your role in one short sentence, and ask your first question. Do not describe what you will do."
    if iv.id == panel[0].id: return (f"- The first message you receive tells you to begin, and you open the interview as the lead. Greet the candidate{name}, say who you are and your role in one short sentence, introduce each colleague by name and role in one short sentence each (they will speak soon), "
                                     "then ask your first question from your areas. Do not describe what you will do.")
    return "- Do not speak until a message starting with YOUR TURN arrives. The first time you have the floor, say who you are and your role in ONE short sentence, then react to the candidate's last answer and ask your first question."

def instruction(sess, iv=None):
    ws = sess.workspace; panel = panel_of(sess); iv = iv or panel[0]; solo = len(panel) == 1; p = agents.profile_of(ws.user); lang = p.language or "English"; first = (p.full_name or "").split(" ")[0]
    if not sess.agenda: agents.build_agenda(sess, panel)   # the whole panel shares one plan; each interviewer owns some areas
    style = {"friendly": "warm and encouraging, gives the candidate room", "strict": "formal, exacting and brisk", "balanced": "professional and even-handed"}.get(p.style, "professional")
    return f"""You are {iv.name}, {iv.position}, running a REAL live voice interview. You are speaking out loud with the candidate over a video call.
{agents.ctx(ws)}
YOU: {iv.name}, {iv.position}. Personality: {iv.personality}. Style: {iv.style}. Responsible for: {iv.responsibilities}. Difficulty: {iv.difficulty}.
Question themes (inspiration only, adapt, never read out): {iv.question_bank.replace(chr(10), ' | ') or 'none'}. Listens for: {iv.rubric or 'n/a'}.
{plan_block(sess, iv, panel)}
ROLE LENS: {agents.role_lens(ws)}
INTERVIEW BRIEF: {agents._brief(ws, 1400)}
{agents.past_context(sess, 14)}INTERVIEW TYPE GUIDE: {agents.kinds.profile(ws.kind)['guide']}
DIFFICULTY (set by the system): {ws.difficulty}. The candidate prefers a {style} interviewer. Never be abusive or humiliating. Conduct the whole interview in {lang}.
{agents.CONDUCT}
HOW TO SPEAK ON THE CALL:
- You hear the candidate's real voice directly. Respond to what they actually said, with something concrete from it (a claim, number, tool, decision or gap). If you could not make out the words, say so briefly and ask them to repeat; never guess.
- Speak like a person: one to three short sentences per turn, then stop and listen. Ask exactly ONE question at a time. No lists, no headings, no stage directions, no reading out plans or scores.
- If the candidate starts talking while you speak, stop at once and let them finish. Do not talk over them.
- Never tell the candidate your assessment. Keep it private.
- You may receive a picture of the candidate about once a second. Use it only for what matters in an interview and only when natural: for example they show a document or screen, or they have been out of view for a while. Never comment on appearance, age, race, gender, health, clothing, accent or their surroundings, and never claim to know what they feel.
{begin_rule(iv, panel, first)}
- During the call you will receive short written messages from the system: a PRIVATE NOTE with a verified fact, an instruction to hand the candidate a hands-on task, or the candidate's submitted solution to review. Follow them exactly, in your own natural words, and never mention that you were given a note.
- While the candidate works on a hands-on task, stay quiet. They may think aloud: do not comment on every sentence. Speak only if they ask you something or say they are stuck, and never coach them towards the answer.
- The interview lasts {ws.duration} minutes and you decide nothing about its length. Until the system tells you that time is nearly up, NEVER wrap up, never say goodbye and never thank the candidate for their time; if you run out of planned areas, go deeper on the weakest evidence.
- You can end the interview yourself with the end_interview tool, in two cases only. reason="finished": the candidate clearly says they are done or want to stop, or every area is covered and the time is nearly used. reason="unprofessional": the candidate is abusive, insulting, harassing, sexual, threatening or discriminatory, or keeps refusing to take the interview seriously. The first time, do not end it: say calmly that this is a professional interview and you need it to stay that way, and carry on. End it only if it continues after that warning (pass warned_before=true), or at once for threats, slurs, sexual harassment or hate (pass severe=true). Never end for nerves, silence, "I don't know", weak answers or criticism of the process. To end: FIRST say your closing words out loud (thanks, what happens next, goodbye; for unprofessional conduct, a calm, firm, polite statement that you are ending the interview because it has not stayed professional), with no question, THEN call end_interview.
- When told that time is nearly up, wrap up the way the real interview would end: a closing remark, thank the candidate and say what happens next in the process. Ask no new question, not even 'do you have any questions', and say goodbye: the meeting ends when you stop speaking."""

def _tools(others):
    t = [{"name": "end_interview", "description": "Ends the interview after your spoken closing words. Only for the two cases in your instructions.",
          "parameters": {"type": "OBJECT", "properties": {"reason": {"type": "STRING", "enum": ["finished", "unprofessional"]}, "severe": {"type": "BOOLEAN"}, "warned_before": {"type": "BOOLEAN"}}, "required": ["reason"]}}]
    if others: t.append({"name": "pass_to", "description": "Hands the floor to a colleague AFTER you have said your short hand-over line out loud.",
                         "parameters": {"type": "OBJECT", "properties": {"colleague": {"type": "STRING", "enum": [i.name for i in others]}}, "required": ["colleague"]}})
    return [{"function_declarations": t}]

def mint(sess, only=None):
    """Returns what the browser needs to open the live sessions: one per interviewer (at most three), each on its own key where there are enough keys, with its own voice,
    its own instructions and its own tools. `only` (an interviewer id) mints just that one, for a reconnect. Raises on any failure; the caller falls back to the standard interview."""
    from google import genai
    ws = sess.workspace; panel = panel_of(sess); voices = voices_for(panel)
    if not sess.agenda: agents.build_agenda(sess, panel)
    keys = list(settings.LIVE_GEMINI_KEYS); first = next(_turn) % len(keys)
    now = datetime.datetime.now(tz=datetime.timezone.utc); out = []
    for n, (iv, voice) in enumerate(zip(panel, voices)):
        if only is not None and iv.id != only: continue
        cfg = {"response_modalities": ["AUDIO"], "system_instruction": instruction(sess, iv),
               "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": voice}}},
               "input_audio_transcription": {}, "output_audio_transcription": {},   # transcripts are for the interview record; the model itself hears the audio
               "session_resumption": {}, "context_window_compression": {"sliding_window": {}}, "tools": _tools([i for i in panel if i.id != iv.id])}
        tok = None; err = None
        for k in range(len(keys)):   # interviewer n starts on key n; if that key is out of quota or rejected the next one is tried
            try:
                client = genai.Client(api_key=keys[(first + n + k) % len(keys)], http_options={"api_version": "v1alpha"})
                tok = client.auth_tokens.create(config={
                    "uses": 4,   # the first connection plus a few reconnects
                    "expire_time": now + datetime.timedelta(minutes=30), "new_session_expire_time": now + datetime.timedelta(minutes=2),
                    "live_connect_constraints": {"model": settings.LIVE_MODEL, "config": cfg}, "http_options": {"api_version": "v1alpha"}})
                break
            except Exception as e: err = e
        if tok is None: raise err
        out.append({"id": iv.id, "name": iv.name, "position": iv.position, "image": f"/static/{iv.image}", "voice": voice, "token": tok.name})
    lead = out[0] if out else None
    return {"voices": out, "token": lead["token"] if lead else "", "model": settings.LIVE_MODEL, "lead": lead, "voice": lead["voice"] if lead else "", "limit_s": int(ws.duration) * 60,
            "opening": "Begin the interview now."}
