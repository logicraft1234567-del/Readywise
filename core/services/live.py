"""Live voice interview (Gemini Live). The server does two things only:
1. builds the interviewer's instructions from the same interview context the standard engine uses (candidate, role, research, agenda, persona), and
2. mints a short-lived, single-purpose token that is locked to that configuration, so the real API key and the instructions never reach the browser.
The audio itself travels browser <-> Google. Transcripts come back through room_live_turns and are saved as ordinary Turn rows."""
import datetime, hashlib, random
from django.conf import settings
from . import agents

FEMALE = ["Kore", "Aoede", "Leda"]
MALE = ["Puck", "Charon", "Fenrir"]

def enabled(): return bool(getattr(settings, "LIVE_GEMINI_KEYS", []))

def lead_of(sess): return agents.session_panel(sess)[0]

def voice_for(iv):
    pool = FEMALE if (iv.gender or "m").lower().startswith("f") else MALE
    return pool[int(hashlib.md5(iv.name.encode()).hexdigest(), 16) % len(pool)]

def instruction(sess):
    ws = sess.workspace; iv = lead_of(sess); p = agents.profile_of(ws.user); lang = p.language or "English"; first = (p.full_name or "").split(" ")[0]
    if not sess.agenda: agents.build_agenda(sess, [iv])   # one interviewer in live mode, so the whole plan is his or hers
    style = {"friendly": "warm and encouraging, gives the candidate room", "strict": "formal, exacting and brisk", "balanced": "professional and even-handed"}.get(p.style, "professional")
    return f"""You are {iv.name}, {iv.position}, running a REAL live voice interview. You are speaking out loud with the candidate over a video call.
{agents.ctx(ws)}
YOU: {iv.name}, {iv.position}. Personality: {iv.personality}. Style: {iv.style}. Responsible for: {iv.responsibilities}. Difficulty: {iv.difficulty}.
Question themes (inspiration only, adapt, never read out): {iv.question_bank.replace(chr(10), ' | ') or 'none'}. Listens for: {iv.rubric or 'n/a'}.
YOU ARE THE ONLY INTERVIEWER: cover every area of the plan yourself, in one natural one-to-one conversation.
THE PLAN (private; follow it, never read it out):
{agents.agenda_text(sess.agenda, [iv])}
ROLE LENS: {agents.role_lens(ws)}
INTERVIEW BRIEF: {agents._brief(ws, 1400)}
INTERVIEW TYPE GUIDE: {agents.kinds.profile(ws.kind)['guide']}
DIFFICULTY (set by the system): {ws.difficulty}. The candidate prefers a {style} interviewer. Never be abusive or humiliating. Conduct the whole interview in {lang}.
{agents.CONDUCT}
HOW TO SPEAK ON THE CALL:
- You hear the candidate's real voice directly. Respond to what they actually said, with something concrete from it (a claim, number, tool, decision or gap). If you could not make out the words, say so briefly and ask them to repeat; never guess.
- Speak like a person: one to three short sentences per turn, then stop and listen. Ask exactly ONE question at a time. No lists, no headings, no stage directions, no reading out plans or scores.
- If the candidate starts talking while you speak, stop at once and let them finish. Do not talk over them.
- Never tell the candidate your assessment. Keep it private.
- You may receive a picture of the candidate about once a second. Use it only for what matters in an interview and only when natural: for example they show a document or screen, or they have been out of view for a while. Never comment on appearance, age, race, gender, health, clothing, accent or their surroundings, and never claim to know what they feel.
- The first message you receive tells you to begin. Greet the candidate{(' by first name (' + first + ')') if first else ''}, say who you are and your role in one short sentence, and ask your first question. Do not describe what you will do.
- During the call you will receive short written messages from the system: a PRIVATE NOTE with a verified fact, an instruction to hand the candidate a hands-on task, or the candidate's submitted solution to review. Follow them exactly, in your own natural words, and never mention that you were given a note.
- While the candidate works on a hands-on task, stay quiet. They may think aloud: do not comment on every sentence. Speak only if they ask you something or say they are stuck, and never coach them towards the answer.
- The interview lasts {ws.duration} minutes and you decide nothing about its length. Until the system tells you that time is nearly up, NEVER wrap up, never say goodbye and never thank the candidate for their time; if you run out of planned areas, go deeper on the weakest evidence.
- When told that time is nearly up, wrap up the way the real interview would end: a closing remark, thank the candidate and say what happens next in the process. Ask no new question, not even 'do you have any questions', and say goodbye: the meeting ends when you stop speaking."""

def mint(sess):
    """Returns what the browser needs to open one Live session. Raises on any failure; the caller falls back to the standard interview."""
    from google import genai
    ws = sess.workspace; iv = lead_of(sess); voice = voice_for(iv)
    key = random.choice(settings.LIVE_GEMINI_KEYS)
    client = genai.Client(api_key=key, http_options={"api_version": "v1alpha"})
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    cfg = {"response_modalities": ["AUDIO"], "system_instruction": instruction(sess),
           "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": voice}}},
           "input_audio_transcription": {}, "output_audio_transcription": {},   # transcripts are for the interview record; the model itself hears the audio
           "session_resumption": {}, "context_window_compression": {"sliding_window": {}}}
    tok = client.auth_tokens.create(config={
        "uses": 4,   # the first connection plus a few reconnects
        "expire_time": now + datetime.timedelta(minutes=30), "new_session_expire_time": now + datetime.timedelta(minutes=2),
        "live_connect_constraints": {"model": settings.LIVE_MODEL, "config": cfg}, "http_options": {"api_version": "v1alpha"}})
    lead = {"id": iv.id, "name": iv.name, "position": iv.position, "image": f"/static/{iv.image}"}
    return {"token": tok.name, "model": settings.LIVE_MODEL, "lead": lead, "voice": voice, "limit_s": int(ws.duration) * 60,
            "opening": "Begin the interview now."}
