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

def instruction(sess, iv=None, panel=None):
    """The private brief for one live interviewer. Alone: the only interviewer. On a panel: one member who speaks only when handed the floor."""
    ws = sess.workspace; panel = panel or [lead_of(sess)]; iv = iv or panel[0]; p = agents.profile_of(ws.user); lang = p.language or "English"; first = (p.full_name or "").split(" ")[0]
    if not sess.agenda: agents.build_agenda(sess, panel)   # a solo interviewer owns the whole plan; a panel shares it
    first_line = f"Greet the candidate{(' by first name (' + first + ')') if first else ''}, say who you are and your role in one short sentence"
    if len(panel) == 1:
        who = f"YOU ARE THE ONLY INTERVIEWER: cover every area of the plan yourself, in one natural one-to-one conversation.\nTHE PLAN (private; follow it, never read it out):\n{agents.agenda_text(sess.agenda, [iv])}"
        opening_rule = f"- The first message you receive tells you to begin. {first_line}, and ask your first question. Do not describe what you will do."
    else:
        roster = "; ".join(f"{x.name} ({x.position})" for x in panel); chair = iv.id == panel[0].id
        who = (f"YOU ARE ONE OF {len(panel)} INTERVIEWERS ON THIS PANEL: {roster}. Each of you has a different voice and you speak one at a time on the same video call. "
               + ("You are the chair: you open the interview." if chair else "You are NOT the chair: stay completely silent until a message tells you YOU HAVE THE FLOOR.")
               + f"\nTHE PLAN (private; each area names the interviewer who owns it; yours are marked {iv.name}; never read it out):\n{agents.agenda_text(sess.agenda, panel)}\n"
               "TAKING TURNS: speak only while you have the floor. When your areas are done, or the next area belongs to a colleague, hand over: say one short natural line to that colleague by name (for example: Sarah, over to you), then call the function hand_over with their exact name, then say nothing more. "
               "If the candidate directs a question at a colleague, say so briefly and hand over to them. When you receive the floor you are told what was said since you last spoke: pick up naturally from it in a sentence, then carry on with your own areas. On your first turn, introduce yourself in one short sentence. Never speak for a colleague.")
        opening_rule = (f"- The first message you receive tells you to begin. {first_line}, name your colleagues in one sentence (for example: With me today are Sarah from HR and Alex, our technical lead), and ask your first question. Do not describe what you will do." if chair
                        else "- You will not be asked to begin. Say nothing until a message tells you YOU HAVE THE FLOOR.")
    style = {"friendly": "warm and encouraging, gives the candidate room", "strict": "formal, exacting and brisk", "balanced": "professional and even-handed"}.get(p.style, "professional")
    return f"""You are {iv.name}, {iv.position}, running a REAL live voice interview. You are speaking out loud with the candidate over a video call.
{agents.ctx(ws)}
YOU: {iv.name}, {iv.position}. Personality: {iv.personality}. Style: {iv.style}. Responsible for: {iv.responsibilities}. Difficulty: {iv.difficulty}.
Question themes (inspiration only, adapt, never read out): {iv.question_bank.replace(chr(10), ' | ') or 'none'}. Listens for: {iv.rubric or 'n/a'}.
{who}
ROLE LENS: {agents.role_lens(ws)}
INTERVIEW BRIEF: {agents._brief(ws, 1400)}
{agents.prior_block(sess)}
INTERVIEW TYPE GUIDE: {agents.kinds.profile(ws.kind)['guide']}
DIFFICULTY (set by the system): {ws.difficulty}. The candidate prefers a {style} interviewer. Never be abusive or humiliating. Conduct the whole interview in {lang}.
{agents.CONDUCT}
HOW TO SPEAK ON THE CALL:
- You hear the candidate's real voice directly. Respond to what they actually said, with something concrete from it (a claim, number, tool, decision or gap). If you could not make out the words, say so briefly and ask them to repeat; never guess.
- Speak like a person: one to three short sentences per turn, then stop and listen. Ask exactly ONE question at a time. No lists, no headings, no stage directions, no reading out plans or scores.
- If the candidate starts talking while you speak, stop at once and let them finish. Do not talk over them.
- Never tell the candidate your assessment. Keep it private.
- You may receive a picture of the candidate about once a second. Use it only for what matters in an interview and only when natural: for example they show a document or screen, or they have been out of view for a while. Never comment on appearance, age, race, gender, health, clothing, accent or their surroundings, and never claim to know what they feel.
{opening_rule}
- During the call you will receive short written messages from the system: a PRIVATE NOTE with a verified fact, an instruction to hand the candidate a hands-on task, or the candidate's submitted solution to review. Follow them exactly, in your own natural words, and never mention that you were given a note.
- While the candidate works on a hands-on task, stay quiet. They may think aloud: do not comment on every sentence. Speak only if they ask you something or say they are stuck, and never coach them towards the answer.
- The interview lasts {ws.duration} minutes. Do not wrap up just because you have asked a few questions: if you run out of planned areas, go deeper on the weakest evidence. You can end the interview yourself by calling the function end_interview, in exactly three situations. (1) It has genuinely run its course: every area is covered with enough evidence AND most of the interview time has passed (the system refuses to end it early, so never try before the last part of the time). Use reason "completed". (2) The candidate says they want to stop: do not end at once; say how much time is left and ask once if they really want to stop, and only if they confirm, use reason "candidate_stopped". (3) The candidate is unprofessional: abusive, insulting, discriminatory, sexually inappropriate, clearly not taking the interview seriously, refusing to engage, or deliberately wasting time. First say once, calmly, what you expect; if it continues, end it. For severe abuse or harassment, end it at once. Use reason "unprofessional". Always say your closing words out loud FIRST (completed or candidate_stopped: thank the candidate and say what happens next; unprofessional: one calm, professional sentence that you are ending the interview because of the candidate's conduct), THEN call end_interview, then say nothing more. Never end it for nervousness, a pause to think, a weak answer or a technical problem.
- When told that time is nearly up, wrap up the way the real interview would end: a closing remark, thank the candidate and say what happens next in the process. Ask no new question, not even 'do you have any questions', and say goodbye: the meeting ends when you stop speaking."""

def voices_for(panel):
    """A different voice for every panelist (the pools hold three per gender, the most a panel has)."""
    used = set(); out = {}
    for iv in panel:
        pool = FEMALE if (iv.gender or "m").lower().startswith("f") else MALE; pref = voice_for(iv)
        out[iv.id] = next((v for v in [pref] + pool if v not in used), pref); used.add(out[iv.id])
    return out

def _tools(panel, iv):
    fns = [{"name": "end_interview", "description": "Ends the live interview now. Say your closing words out loud before calling it.",
            "parameters": {"type": "OBJECT", "properties": {"reason": {"type": "STRING", "enum": ["completed", "candidate_stopped", "unprofessional"]}}, "required": ["reason"]}}]
    others = [x.name for x in panel if x.id != iv.id]
    if others: fns.append({"name": "hand_over", "description": "Hands the floor to a colleague on the panel. Say a short handover line to them first, then call this, then say nothing more.",
                           "parameters": {"type": "OBJECT", "properties": {"to": {"type": "STRING", "enum": others}}, "required": ["to"]}})
    return [{"function_declarations": fns}]

def mint(sess, only=None):
    """Everything the browser needs to open one Live session per panelist (each on its own key where there are enough keys). `only` returns just that interviewer, for a reconnect.
    Raises on any failure; the caller falls back to the standard interview."""
    from concurrent.futures import ThreadPoolExecutor
    from google import genai
    ws = sess.workspace; panel = agents.session_panel(sess); voices = voices_for(panel); now = datetime.datetime.now(tz=datetime.timezone.utc)
    if not sess.agenda: agents.build_agenda(sess, panel)
    pick = [x for x in panel if only is None or x.id == only] or panel[:1]; keys = list(settings.LIVE_GEMINI_KEYS)
    if not keys: raise RuntimeError("No live key is set.")
    jobs = []
    for iv in pick:
        k = panel.index(iv)
        cfg = {"response_modalities": ["AUDIO"], "system_instruction": instruction(sess, iv, panel),
               "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": voices[iv.id]}}},
               "input_audio_transcription": {}, "output_audio_transcription": {},   # transcripts are for the interview record; the model itself hears the audio
               "session_resumption": {}, "context_window_compression": {"sliding_window": {}}, "tools": _tools(panel, iv)}
        order = keys[k % len(keys):] + keys[:k % len(keys)]   # each panelist starts on their own key; if it fails the next key is tried
        jobs.append((iv, cfg, order))
    def make(job):
        iv, cfg, order = job; err = None
        for key in order:
            try:
                client = genai.Client(api_key=key, http_options={"api_version": "v1alpha"})
                tok = client.auth_tokens.create(config={
                    "uses": 4,   # the first connection plus a few reconnects
                    "expire_time": now + datetime.timedelta(minutes=30), "new_session_expire_time": now + datetime.timedelta(minutes=2),
                    "live_connect_constraints": {"model": settings.LIVE_MODEL, "config": cfg}, "http_options": {"api_version": "v1alpha"}})
                return tok.name
            except Exception as e: err = e
        raise err or RuntimeError("No live key worked.")
    with ThreadPoolExecutor(max_workers=len(jobs)) as ex: tokens = list(ex.map(make, jobs))
    members = [{"id": iv.id, "name": iv.name, "position": iv.position, "image": f"/static/{iv.image}", "voice": voices[iv.id], "token": t} for (iv, _, _), t in zip(jobs, tokens)]
    multi = len(panel) > 1
    return {"token": members[0]["token"], "model": settings.LIVE_MODEL, "lead": {k: members[0][k] for k in ("id", "name", "position", "image")}, "voice": members[0]["voice"], "members": members,
            "limit_s": int(ws.duration) * 60, "opening": "Begin the interview now." + (" You are the chair: greet the candidate, introduce your colleagues in one sentence, and ask your first question." if multi else "")}
