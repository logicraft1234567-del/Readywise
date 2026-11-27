"""Plain Python services (no LLM): Memory Agent and Scheduler Agent."""
from datetime import date, timedelta
from ..models import *

def update_memory(user, scores, notes, confidence=None):
    """Fold one interview's category scores into the long-term record. The weight of the new result follows how well the interview was evidenced:
    a result built on thin evidence moves the record only a little, so one short or unlucky session cannot rewrite it."""
    a = {"high": 0.4, "medium": 0.3, "low": 0.15}.get(confidence, 0.4)
    for cat, sc in (scores or {}).items():
        if cat not in CAT_LABEL or sc is None: continue
        m, created = MemoryItem.objects.get_or_create(user=user, category=cat, defaults={"score": float(sc)})
        if not created: m.score = round((1 - a) * m.score + a * float(sc), 1)
        m.observations += 1; m.note = (notes or {}).get(cat, m.note)[:300]; m.save()

def adjust_plan(ws):
    """Recalculate priorities from memory + role weights. Never silently drops tasks."""
    log = []; today = date.today(); w = ws.weights()
    mem = {m.category: m.score for m in MemoryItem.objects.filter(user=ws.user)}
    need = {c: w[c] * (100 - mem.get(c, 50)) / 100 for c, _ in CATS}
    last_day = ws.date if (ws.date and not ws.general and ws.date > today) else today + timedelta(days=max(2, ws.prep_days))
    # 1. reorganise missed tasks
    missed = list(ws.tasks.filter(done=False, due__lt=today).order_by("-priority"))
    span = max(1, (last_day - today).days)
    for i, t in enumerate(missed):
        t.due = today + timedelta(days=min(span, i // 2)); t.save(); log.append(f"Rescheduled missed task: {t.title}")
    # 2. de-emphasise mastered topics, keep them on the list
    for t in ws.tasks.filter(done=False):
        if mem.get(t.category, 0) >= 85 and t.kind != "mock":
            t.priority = 2; t.save(); log.append(f"Lowered priority (already strong): {t.title}")
    # 3. add targeted work for the biggest gaps
    for cat in [c for c, _ in sorted(need.items(), key=lambda x: -x[1])][:2]:
        if mem.get(cat, 50) >= 70: continue
        if ws.tasks.filter(category=cat, auto_added=True, done=False).exists(): continue
        d = min(last_day, today + timedelta(days=1))
        PrepTask.objects.create(workspace=ws, due=today, title=f"Targeted drill: {CAT_LABEL[cat]}", detail=f"Recurring weak area (currently {round(mem.get(cat, 50))}/100). Practise 3 focused questions and write a structured answer for each.", category=cat, kind="practice", priority=10, auto_added=True)
        PrepTask.objects.create(workspace=ws, due=d, title=f"Focused panel session: {CAT_LABEL[cat]}", detail="Run a short panel interview with the interviewers responsible for this area, then compare the score.", category=cat, kind="mock", priority=9, auto_added=True)
        log.append(f"Added drill and focused panel session for {CAT_LABEL[cat]}")
    return log or ["Plan already matches your latest results."]

def readiness(ws):
    mem = {m.category: m for m in MemoryItem.objects.filter(user=ws.user)}
    rows = [{"key": c, "label": l, "score": round(mem[c].score) if c in mem else None, "weight": ws.weights()[c], "note": mem[c].note if c in mem else ""} for c, l in CATS]
    tasks = ws.tasks.all(); done = tasks.filter(done=True).count()
    return {"rows": rows, "tasks_done": done, "tasks_total": tasks.count(), "strong": [r for r in rows if r["score"] and r["score"] >= 75],
            "weak": sorted([r for r in rows if r["score"] is not None and r["score"] < 65], key=lambda r: r["score"]), "unassessed": [r for r in rows if r["score"] is None],
            "sessions": ws.sessions.filter(status="done").count()}

SEED = [
 ("Tom","Chief Executive Officer","Strategic, direct, composed and demanding.","Formal","Leadership, strategy, business","Leadership and decision-making. Long-term thinking. Business understanding. Motivation and ambition. Handling difficult situations.","Assess leadership potential","advanced","img/i06.png","m",0.85,0.95,"strategic,company"),
 ("Mask","Department Manager","Analytical, practical, detail-oriented and challenging.","Direct","Role-specific delivery, problem solving","Role-specific knowledge. Problem-solving. Practical experience. Working under pressure. Team collaboration.","Test practical depth","advanced","img/i07.png","m",1.0,1.0,"technical,behavioural"),
 ("Sarah","HR Director","Warm, observant, professional and probing.","Warm","People, communication, culture","Communication. Behavioural questions (STAR). Conflict resolution. Work ethic. Cultural and role expectations.","Assess teamwork and communication","standard","img/i08.png","f",1.05,1.0,"communication,behavioural"),
 ("Alex","Technical Lead","Highly technical, curious and precise.","Precise","Programming, architecture, debugging","Programming. System design. Technical reasoning. Architecture. Debugging.","Probe technical reasoning","advanced","img/i09.png","m",0.95,1.05,"technical,system_design"),
 ("David","Senior Engineer","Calm, curious, thorough.","Conversational","Engineering practice","Code quality. Trade-offs. Testing. Past project details.","Verify hands-on experience","standard","img/i10.png","m",0.9,1.0,"technical,system_design"),
 ("Michael","Visa Officer","Formal, brisk, consistent, fair.","Direct","Consular interviews, document checks","Purpose of travel. Funding. Ties to home country. Consistency of answers. Short closed questions.","Practise concise, honest answers","standard","img/i11.png","m",0.8,1.0,"communication,behavioural"),
 ("Elena","Scholarship and Fellowship Panelist","Thoughtful, fair, values purpose.","Warm","Academic merit, leadership, impact","Academic goals. Leadership. Community impact. Why this programme. Research significance.","Understand motivation and impact","standard","img/i12.png","f",1.0,0.95,"strategic,communication"),
 ("Peter","Finance Director","Numbers-driven, skeptical, concise.","Direct","Finance, planning, risk","Financial reasoning. Business cases. Unit economics. Risk and ROI.","Check commercial judgement","advanced","img/i13.png","m",0.9,1.05,"strategic,company"),
 ("Nia","University Admissions Officer","Friendly, curious, attentive.","Warm","Admissions, academic fit","Academic background. Fit with the course. Personal growth. Plans after graduation.","Assess academic fit","standard","img/i19.png","f",1.1,1.0,"communication,strategic"),
 ("Victoria","Venture Partner","Sharp, sceptical, fast, fair.","Direct","Venture investing, markets, traction","Problem and market. Traction and metrics. Business model. Competition. Use of funds. Team.","Stress-test the pitch like an investor","advanced","img/i01.png","f",1.0,1.05,"strategic,company"),
]
BANKS = {
 "Tom": ("Why this organisation, and why now?\nWhere do you want to be in five years and what is your plan?\nTell me about a decision you made with incomplete information.\nHow would you handle a top priority failing under pressure?\nWhy should we choose you over an equally qualified candidate?", "Clear strategic thinking. Evidence of ownership. Honest ambition. Stays calm under pushback. Concise."),
 "Mask": ("Walk me through a project you delivered end to end.\nHow did you debug the hardest problem you faced?\nHow do you prioritise when everything is urgent?\nTell me about disagreeing with a teammate on approach.", "Concrete detail. Real personal contribution, not team credit. Sound problem-solving steps. Learns from mistakes."),
 "Sarah": ("Tell me about a conflict and how you resolved it.\nGive an example of when you missed a deadline.\nHow do you take feedback?\nDescribe working with someone very different from you.", "STAR structure. Self-awareness. Ownership without blame. Clear communication."),
 "Alex": ("Design a service for thousands of concurrent users.\nWhat happens when your cache goes stale?\nHow would you debug intermittent production failures?\nExplain a trade-off you made between speed and correctness.", "States trade-offs. Reasons from first principles. Checks edge cases. Says assumptions out loud."),
 "David": ("Walk me through code you are proud of and what you would change.\nHow do you test it?\nWhat would you do about a flaky test?\nHow do you review other people's code?", "Practical detail. Real testing habits. Honest about weaknesses."),
 "Michael": ("What is the purpose of your visit?\nWho is paying for your trip?\nWhat will you do after your studies or stay?\nWhere do you have family and work ties?\nHave you travelled abroad before?", "Short, truthful answers. Consistent facts. Clear funding. Credible plans to return. No rehearsed monologues."),
 "Elena": ("Why do you deserve this award or place?\nTell me about the biggest impact you have had on others.\nWhat challenge shaped you most?\nHow will you give back?\nWhat is your research question and why does it matter?", "Specific evidence of impact. Authentic purpose. Long-term vision. Humility with substance."),
 "Peter": ("How do you make money, and what are the unit economics?\nHow big is the market and how do you know?\nWhat happens if your biggest cost doubles?\nWhat is your cash runway?", "Numbers backed by sources. Honest about risks. Sensible assumptions. Clear use of funds."),
 "Nia": ("Why this course?\nWhat recent idea in your subject fascinated you?\nTell me about a problem you could not solve at first.\nWhat do you plan after graduating?", "Curiosity. Reasoning aloud. Depth over memorised facts. Fit with the course."),
 "Victoria": ("What problem are you solving, and who has it badly enough to pay?\nWhat traction proves demand?\nWho are your competitors and why will you win?\nWhy is now the right time?\nWhat is the biggest risk?", "Customer evidence. Crisp metrics. Direct answers to objections. Conviction without exaggeration."),
}
VOICES = ["troy", "austin", "daniel", "hannah", "diana", "autumn"]  # Groq Orpheus voices: three male, three female
SEED_VOICE = {"Tom": "troy", "Mask": "austin", "Sarah": "hannah", "Alex": "daniel", "David": "austin", "Michael": "troy", "Elena": "diana", "Peter": "daniel", "Nia": "autumn", "Victoria": "diana"}
def ensure_seed():
    q = Interviewer.objects.filter(owner=None)
    if q.count() == len(SEED) and q.filter(name="Michael", position="Visa Officer").exclude(rubric="").exists() and q.filter(name="Tom", voice_name="troy").exists(): return
    for r in SEED:
        Interviewer.objects.update_or_create(owner=None, name=r[0], defaults=dict(position=r[1], personality=r[2], style=r[3], expertise=r[4], responsibilities=r[5], objectives=r[6], difficulty=r[7], image=r[8], gender=r[9], pitch=r[10], rate=r[11], focus=r[12], voice_name=SEED_VOICE.get(r[0], "troy"), question_bank=BANKS[r[0]][0], rubric=BANKS[r[0]][1]))
