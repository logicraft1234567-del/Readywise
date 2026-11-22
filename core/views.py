import json, time
from datetime import date
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import *
from .services import agents, ai, logic, docs, tts, stt, storage, kinds, panelplan, langs, wizard
from . import jobs

AVATARS = ["img/i06.png","img/i07.png","img/i08.png","img/i09.png","img/i10.png","img/i11.png","img/i12.png","img/i13.png","img/i19.png"]
KIND_CARDS = kinds.cards()
LIMITS = {"normal":0,"challenging":120,"high_pressure":60,"executive":90,"unknown":90}

def ajax(fn):
    def w(*a, **k):
        try: return fn(*a, **k)
        except ai.AIError as e: return JsonResponse({"error": str(e)}, status=400)
    w.__name__ = fn.__name__; return w

def mine(model, request, pk):
    return get_object_or_404(model, pk=pk, user=request.user) if model is Workspace else get_object_or_404(model, pk=pk, workspace__user=request.user)

FAQS = [("Is ReadyWise a mock interview website?","No. It is a preparation department: it researches your opportunity, builds a panel, trains you, runs the interview and adjusts your plan."),
("Does it predict whether I will get the job, place or visa?","No. Visa, admission and scholarship simulations are practice only. ReadyWise shows a transparent readiness picture and never a hiring probability."),
("Where does the research come from?","Groq's web-search model. Each finding is marked confirmed, candidate-reported or inferred, with a confidence level. Forum posts are never treated as company policy."),
("Do I need a camera?","The camera is optional. You can answer by voice or by typing. Recording only starts if you tick the consent box."),
("Can I create my own interviewer?","Yes. Set a name, role, personality, focus areas and difficulty, then reuse that interviewer in any workspace."),
("What happens if I miss a day?","The scheduler moves missed tasks onto the days you have left. Nothing essential is dropped silently.")]
# ---------- public ----------
def guide(request):
    logic.ensure_seed()
    return render(request, "core/guide.html", {"team": Interviewer.objects.filter(owner=None)[:3]})

def landing(request):
    if request.user.is_authenticated: return redirect("dashboard")
    logic.ensure_seed()
    return render(request, "core/landing.html", {"team": Interviewer.objects.filter(owner=None)[:9], "faqs": FAQS})

@require_POST
def contact(request):
    Contact.objects.create(name=request.POST.get("name", "")[:80], email=request.POST.get("email", ""), message=request.POST.get("message", ""))
    messages.success(request, "Thanks. Your message has been received.")
    return redirect("/#contact")

def register(request):
    if request.user.is_authenticated: return redirect("dashboard")
    if request.method == "POST":
        u, e, p = request.POST.get("username", "").strip(), request.POST.get("email", ""), request.POST.get("password", "")
        if len(p) < 8: messages.error(request, "Use a password with at least 8 characters.")
        elif not u or User.objects.filter(username__iexact=u).exists(): messages.error(request, "That username is taken. Pick another one, or log in if it's yours.")
        else:
            try:
                with transaction.atomic(): user = User.objects.create_user(u, e, p)
            except IntegrityError:  # a double submit created it a moment ago
                messages.error(request, "That username was just taken. If it's yours, log in instead.")
            else: agents.profile_of(user); login(request, user); return redirect("welcome")
    return render(request, "core/auth.html", {"mode": "register", "team": Interviewer.objects.filter(owner=None)[:5]})

def login_view(request):
    if request.user.is_authenticated: return redirect("dashboard")
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username"), password=request.POST.get("password"))
        if user: login(request, user); return redirect(request.GET.get("next") or "dashboard")
        messages.error(request, "Wrong username or password.")
    return render(request, "core/auth.html", {"mode": "login", "team": Interviewer.objects.filter(owner=None)[:5]})

def logout_view(request): logout(request); return redirect("landing")

# ---------- app ----------
@login_required
def dashboard(request):
    logic.ensure_seed(); p = agents.profile_of(request.user); today = date.today()
    mem = {m.category: round(m.score) for m in MemoryItem.objects.filter(user=request.user)}
    rows = []
    for w in Workspace.objects.filter(user=request.user).order_by("-created"):
        t = w.tasks.count(); d = w.tasks.filter(done=True).count(); sess = w.sessions.filter(status="done").count()
        steps = [bool(w.researched_at), t > 0, sess > 0]
        nxt = ["Run research", "Generate your plan", "Sit your first interview"][steps.index(False)] if False in steps else "Keep practising"
        rows.append({"w": w, "pct": round(100 * d / t) if t else 0, "tasks": t, "done": d, "sessions": sess, "steps": steps, "next": nxt,
                     "left": (w.date - today).days if w.date and not w.general else None, "panel": list(w.panel.all()), "diff": w.get_difficulty_display(), "kind_icon": kinds.profile(w.kind)["icon"]})
    hour = timezone.localtime().hour; hello = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    scored = [v for v in mem.values()]
    due = PrepTask.objects.filter(workspace__user=request.user, done=False, due__lte=today).select_related("workspace")
    return render(request, "core/dashboard.html", {"rows": rows, "profile": p, "hello": hello, "display_name": (p.full_name.split()[0] if p.full_name else request.user.username), "cards": KIND_CARDS,
        "stats": {"active": len(rows), "due": due.count(), "sessions": Session.objects.filter(workspace__user=request.user, status="done").count(), "avg": round(sum(scored) / len(scored)) if scored else None},
        "mem": [(l, mem.get(c)) for c, l in CATS], "mem_json": json.dumps([mem.get(c, 0) for c, _ in CATS]), "labels": json.dumps([l for _, l in CATS]),
        "sessions": Session.objects.filter(workspace__user=request.user, status="done").select_related("workspace").order_by("-started_at")[:5], "due": due[:6], "ivs": Interviewer.objects.filter(owner=None)[:5]})

def _save_profile(request, p):
    """Save profile answers from either the full profile page or the guided welcome flow. Only fields that were sent are changed."""
    for f in ("full_name", "education", "experience", "skills", "interests"):
        if f in request.POST: setattr(p, f, request.POST.get(f, "")[:4000])
    if "language" in request.POST: p.language = request.POST.get("language") if request.POST.get("language") in dict(langs.LANGS) else "English"
    if "style" in request.POST: p.style = request.POST.get("style") if request.POST.get("style") in ("friendly", "balanced", "strict") else "balanced"
    new_cv = bool(request.FILES.get("cv"))
    if new_cv: p.cv_text = docs.extract_text(request.FILES["cv"])
    p.save()
    if (new_cv or request.POST.get("reanalyse")) and p.cv_text:
        try: agents.analyse_cv(p); messages.success(request, "Profile saved and your CV was analysed.")
        except ai.AIError as e: messages.error(request, f"Profile saved, but the CV analysis failed: {e}")
    else: messages.success(request, "Profile saved.")

@login_required
def profile(request):
    p = agents.profile_of(request.user)
    if request.method == "POST":
        _save_profile(request, p); return redirect("profile")
    return render(request, "core/profile.html", {"p": p, "langs": [n for n, _ in langs.LANGS]})

SKILL_IDEAS = ["Communication", "Teamwork", "Problem solving", "Leadership", "Excel", "Python", "Writing", "Public speaking", "Data analysis", "Project management"]
FIELD_IDEAS = ["Software engineering", "Data and AI", "Finance", "Marketing", "Product", "Design", "Consulting", "Healthcare", "Research", "Startups"]

def welcome_config(p):
    """The guided first-time profile flow: one question at a time, all skippable."""
    style = [{"value": "friendly", "label": "Friendly", "desc": "Warm and encouraging. Good for building confidence.", "icon": "smile"},
             {"value": "balanced", "label": "Balanced", "desc": "Professional, fair and realistic.", "icon": "scale"},
             {"value": "strict", "label": "Strict", "desc": "Exacting and challenging, like a tough panel.", "icon": "flame"}]
    steps = [
        {"id": "intro", "type": "intro", "q": "Hi, I'm your ReadyWise coach", "help": "Let's get to know you in about a minute, so every question I ask is about your real story. You can skip anything and fill it in later.", "cta": "Let's go", "say": "Welcome! This only takes a minute."},
        {"id": "name", "name": "full_name", "type": "text", "label": "Name", "q": "First things first: what should your interviewers call you?", "ph": "Your name", "eg": "Ada Okafor", "say": "I'll make sure the panel gets it right."},
        {"id": "lang", "name": "language", "type": "select", "label": "Language", "q": "Which language do you want to practise in, {name}?", "help": "I'll ask the questions and write your feedback in it.", "options": [{"value": n, "label": n} for n, _ in langs.LANGS], "say": "Nice to meet you, {name}!"},
        {"id": "style", "name": "style", "type": "select", "label": "Interviewer style", "q": "How tough should your interviewers be?", "help": "You can change this any time.", "options": style, "say": "Pick the vibe you want to train with."},
        {"id": "edu", "name": "education", "type": "textarea", "label": "Education", "q": "Tell me about your education.", "help": "School, degree, courses, anything you're proud of.", "ph": "", "eg": "BSc Computer Science, University of Lagos, 2024. Final project on fraud detection."},
        {"id": "exp", "name": "experience", "type": "textarea", "label": "Experience", "q": "What work or project experience do you have?", "help": "Jobs, internships, volunteering, side projects. Numbers help.", "eg": "Interned at a fintech for 3 months, built a dashboard used by 40 agents.", "say": "This is gold for realistic questions."},
        {"id": "skills", "name": "skills", "type": "tags", "label": "Skills", "q": "What are your strongest skills?", "help": "Type a skill and press Enter, or tap a suggestion.", "suggest": SKILL_IDEAS, "ph": "Type a skill and press Enter"},
        {"id": "interests", "name": "interests", "type": "tags", "label": "Career interests", "q": "What roles or fields are you aiming for?", "help": "This helps me recommend the right kind of practice.", "suggest": FIELD_IDEAS, "ph": "Type a field and press Enter"},
        {"id": "cv", "type": "file", "file": "cv", "accept": ".pdf,.docx,.txt", "label": "CV", "q": "Got a CV? Drop it here.", "help": "I'll read it and turn it into a profile, so interviewers ask about your real background. Skip if you don't have it handy.", "dropLabel": "Drop your CV here, or click to choose", "say": "Last one. Then you're done!"},
    ]
    return {"mode": "profile", "steps": steps, "user": "", "values": {"full_name": p.full_name, "language": p.language or "English", "style": p.style or "balanced", "education": p.education, "experience": p.experience, "skills": p.skills, "interests": p.interests},
            "skipAll": {"label": "Skip setup", "next": "dashboard"}, "launchTitle": "Setting up your space", "launch": ["Saving your answers…", "Reading your CV, if you added one…", "Getting your dashboard ready…"],
            "finish": {"title": "You're all set, {name}!", "text": "Your profile is ready. Let's create your first interview and I'll research it, pick your panel and build your plan.",
                       "buttons": [{"label": "Create my first interview →", "next": "interview", "primary": True}, {"label": "Take me to my dashboard", "next": "dashboard"}]}}

@login_required
def welcome(request):
    p = agents.profile_of(request.user)
    if request.method == "POST":
        _save_profile(request, p); return redirect("ws_new" if request.POST.get("next") == "interview" else "dashboard")
    return render(request, "core/welcome.html", {"cfg": welcome_config(p)})

@login_required
@require_POST
@ajax
def wizard_adapt(request):
    """After each answer in the new-interview flow: what should be asked next for this person?"""
    d = json.loads(request.body or b"{}"); kind = d.get("kind")
    if kind not in kinds.PROFILES: return JsonResponse({"error": "Unknown interview type."}, status=400)
    raw = d.get("answers") if isinstance(d.get("answers"), dict) else {}
    ans = {str(k)[:30]: str(v)[:wizard.DOC_CHARS + 200] for k, v in raw.items()}
    rem = [str(k)[:30] for k in (d.get("remaining") or [])][:40]
    cust = [{"key": str(c.get("key"))[:6], "q": str(c.get("q", ""))[:200], "answered": bool(c.get("answered"))} for c in (d.get("custom") or []) if isinstance(c, dict)][:wizard.MAX_EXTRA]
    return JsonResponse(wizard.adapt(kind, ans, rem, cust))

DOC_TEXT_MAX = 6000

@login_required
@require_POST
def wizard_doc(request):
    """Reads an uploaded CV or document and sends back its text, so the guide can see it, the person can check what was read, and the
    questions that follow are about what is really in it."""
    f = request.FILES.get("file")
    if not f: return JsonResponse({"error": "No file was sent."}, status=400)
    if f.size > 8 * 1024 * 1024: return JsonResponse({"error": "That file is too big. Use one under 8 MB, or paste the text."}, status=400)
    try: text = docs.extract_text(f)
    except Exception: return JsonResponse({"error": "I could not open that file. Use a PDF, Word or text file, or paste the text."}, status=400)
    text = "\n".join(l.strip() for l in text.replace("\r", "").split("\n")).strip()
    text = "\n".join(l for i, l in enumerate(text.split("\n")) if l or (i and text.split("\n")[i - 1]))   # collapse runs of blank lines
    if len(text) < 20: return JsonResponse({"error": "I could not find any text in that file (a scanned page, perhaps). Paste the text instead."}, status=400)
    return JsonResponse({"text": text[:DOC_TEXT_MAX], "truncated": len(text) > DOC_TEXT_MAX})

def _read_doc(P, FILES, text_name, file_name):
    """The text of a document question: what was typed or filled in wins; otherwise the uploaded file is read on the server."""
    txt = P.get(text_name, "").strip()
    f = FILES.get(file_name)
    if not txt and f:
        try: txt = docs.extract_text(f).strip()
        except Exception: txt = ""
    return txt

@login_required
def workspace_new(request):
    if request.method == "POST":
        P = request.POST; kind = P.get("kind") if P.get("kind") in kinds.PROFILES else "startup"; pf = kinds.profile(kind); pre = kind + "__"
        jd = _read_doc(P, request.FILES, pre + "jd", "jd")
        dk = kinds.doc(kind)["key"]; mydoc = _read_doc(P, request.FILES, pre + dk, "doc_" + dk)[:12000]   # the required document: CV, pitch deck...
        prof = agents.profile_of(request.user)
        if not mydoc and dk == "cv" and prof.cv_text: mydoc = prof.cv_text[:12000]                          # fall back on the CV saved in the profile
        details = {f["short"]: P.get(pre + f["key"], "").strip()[:900] for f in pf["fields"] if P.get(pre + f["key"], "").strip()}
        for n in range(1, wizard.MAX_EXTRA + 1):   # follow-up questions the guide added for this person: the answer and the label travel together
            a_, q_ = P.get(f"{pre}x{n}", "").strip(), P.get(f"{pre}xq{n}", "").strip()
            if a_ and q_: details[q_[:60]] = a_[:900]
        d = P.get("date") or None; company = P.get(pre + "company", ""); position = P.get(pre + "position", "")
        ws = Workspace.objects.create(user=request.user, title=P.get("title") or f"{company} {position}".strip() or pf["label"], kind=kind, company=company, position=position, date=d, general=not d,
            duration=int(P.get("duration") or pf["duration"]), fmt=pf["format"], known_interviewers=P.get("known_interviewers", "")[:500], prep_days=int(P.get("prep_days") or 7), job_description=jd, details=details,
            documents={dk: mydoc} if mydoc else {})
        if dk == "cv" and mydoc and not prof.cv_text: prof.cv_text = mydoc; prof.save()   # first CV ever given: keep it on the profile so the next interview starts with it
        logic.ensure_seed(); panelplan.allocate(ws)  # the system assigns the panel and difficulty
        return redirect("ws", pk=ws.pk)
    return render(request, "core/ws_new.html", {"cfg": interview_config(request.GET.get("kind", ""), agents.profile_of(request.user)), "doc_files": sorted({"doc_" + d["key"] for d in kinds.DOCS.values()})})

KIND_EMOJI = {"startup": "🚀", "employment": "💼", "internship": "🎒", "graduate": "🎓", "admission": "🏫", "scholarship": "🏅", "visa": "✈️", "fellowship": "🔬", "pitch": "📈", "certification": "✅"}
NAME_EG = {"startup": ("Flutterwave", "Backend engineer"), "employment": ("Microsoft", "Product manager"), "internship": ("Google", "Software engineering intern"), "graduate": ("Unilever", "Future Leaders Programme"),
           "admission": ("University of Edinburgh", "MSc Data Science"), "scholarship": ("Chevening", "Master's degree"), "visa": ("United Kingdom", "Student visa"), "fellowship": ("Fulbright at Harvard", "Public health research"),
           "pitch": ("Omega", "Y Combinator seed round"), "certification": ("AWS", "Solutions Architect Associate")}
CHAPTER_SAY = {kinds.OPP: "Let's start with the opportunity itself.", kinds.YOU: "Now a bit about you. This is what makes the practice personal.", kinds.INT: "Almost done. A few questions about the interview itself."}

def interview_config(preselect="", profile=None):
    """The guided new-interview flow. Every interview type has its own questions, one at a time; only the essential ones cannot be skipped."""
    kc = {}
    for k in kinds.ORDER:
        pf = kinds.profile(k); co, po = NAME_EG[k]; steps = []; seen = set()
        def chapter(sec):
            first = sec not in seen; seen.add(sec); return {"chapter": sec, "say": CHAPTER_SAY[sec]} if first else {"chapter": sec}
        steps.append(dict(id="company", name=f"{k}__company", type="text", label=pf["company_label"], q=("What's " + pf["company_label"].lower() + "?") if pf["company_label"].lower().startswith("your ") else f"What's the {pf['company_label'].lower()}?", eg=co, req=True, adapt=True, reqMsg="I need this to research the right thing.", **chapter(kinds.OPP)))
        steps.append(dict(id="position", name=f"{k}__position", type="text", label=pf["position_label"].split(",")[0], q=f"And the {pf['position_label'].split(',')[0].lower()}?", eg=po, req=True, adapt=True, reqMsg="I need this to research the right thing.", **chapter(kinds.OPP)))
        def add(f):
            st = dict(id=f["key"], name=f"{k}__{f['key']}", type=f["type"], label=f["short"], q=f["label"], eg=f["ph"], req=f["req"], adapt=True, reqMsg="This one matters for a good result. A few words is enough.", **chapter(f["sec"]))
            if f["type"] == "select": st["options"] = [{"value": o, "label": o} for o in f["options"]]
            if f["type"] == "text" and len(f["ph"]) > 60: st["type"] = "textarea"
            steps.append(st)
        opp = [f for f in pf["fields"] if f["sec"] == kinds.OPP]
        for f in opp: add(f)
        steps.append(dict(id="jd", name=f"{k}__jd", type="doc", file="jd", accept=".pdf,.docx,.txt", label=pf["doc_label"], q=f"Do you have the {pf['doc_label'].lower()}?", help="Paste the text or upload it, and I'll ask about what is really in it. Skip it if you don't have it yet.", eg="", dropLabel="Drop a file here, or click to choose", chapter=kinds.OPP, adapt=True))
        d = kinds.doc(k); have = bool(d["profile_cv"] and profile and (profile.cv_text or "").strip())
        steps.append(dict(id=d["key"], name=f"{k}__{d['key']}", type="doc", file="doc_" + d["key"], accept=".pdf,.docx,.txt", label=d["short"], q=d["q"], req=True, adapt=True, ph=d["ph"], dropLabel=d["drop"], eg="",
                          help=("I loaded the CV from your profile. Check it, replace it by pasting a different one, or upload a file." if have else d["help"]), reqMsg="I need this one so I can ask about your real background. Paste it or upload a file.", **chapter(kinds.YOU)))
        if d["key"] == "cv": steps[-1].update(pasteOnly=True, minLen=80, ph="Copy your CV and paste it here. Typing is switched off.")   # a CV is pasted or uploaded, never typed
        for f in pf["fields"]:
            if f["sec"] != kinds.OPP: add(f)
        kc[k] = {"label": pf["label"], "blurb": pf["blurb"], "emoji": KIND_EMOJI[k], "icon": pf["icon"], "duration": pf["duration"], "palette": pf["anim"]["c"], "plan": [x["label"] for x in pf["plan"]], "steps": steps,
                 "hello": f"A {pf['label'].lower()}. I know exactly how to research that."}
    head = [{"id": "intro", "type": "intro", "q": "Let's set up your interview", "help": "A few quick questions, one at a time. Then I'll research it, build your panel and your plan. Skip anything that isn't essential.", "cta": "Start", "say": "Ready when you are."},
            {"id": "kind", "name": "kind", "type": "kind", "req": True, "label": "Type", "q": "What are you preparing for?", "help": "Pick the closest match. Each one gets its own research and its own questions.", "say": "Every type is researched differently."}]
    tail = [{"id": "known", "name": "known_interviewers", "type": "textarea", "label": "Known interviewers", "chapter": kinds.INT, "q": "Do you know who will interview you?", "help": "Names and roles help. I only look at public professional information.", "eg": "Jane Doe, VP Engineering", "max": 500},
            {"id": "date", "name": "date", "type": "date", "label": "Interview date", "chapter": kinds.INT, "q": "When is the interview?", "help": "No date yet? No problem. I'll plan around the time you have.", "say": "Time to plan the countdown."},
            {"id": "dur", "name": "duration", "type": "range", "label": "Length", "chapter": kinds.INT, "q": "How long will the interview be?", "help": "Your practice interviews will match it.", "min": 5, "max": 90, "step": 5, "def": 30, "unit": " min", "presets": [10, 20, 30, 45, 60]}]
    return {"mode": "interview", "kinds": kc, "head": head, "tail": tail, "review": {"button": "Create my workspace"}, "values": dict({"kind": preselect} if preselect in kc else {}, **{f"{k}__cv": profile.cv_text[:6000] for k in kc if kinds.doc(k)["profile_cv"] and profile and (profile.cv_text or "").strip()}), "docUrl": "/w/doc/", "startAfterKind": preselect in kc,
            "adaptUrl": "/w/adapt/", "launchTitle": "Building your workspace", "launch": ["Creating your workspace…", "Choosing your interviewers…", "Laying out your journey…"]}

@login_required
def workspace(request, pk):
    logic.ensure_seed(); ws = mine(Workspace, request, pk)
    mode, mode_why = panelplan.choose_mode(ws); pf = kinds.profile(ws.kind)
    tasks = list(ws.tasks.all()); ready = logic.readiness(ws); sessions = list(ws.sessions.order_by("-started_at")); has_done = any(x.status == "done" for x in sessions)
    researched = bool(ws.researched_at)
    journey = [{"id": "research", "label": "Research", "tag": "Learn the terrain", "done": researched},
               {"id": "panel", "label": "Panel", "tag": "Meet your interviewers", "done": researched},
               {"id": "plan", "label": "Prep plan", "tag": "Your countdown", "done": bool(tasks)},
               {"id": "interview", "label": "Practice", "tag": "Face the panel", "done": has_done},
               {"id": "ready", "label": "Readiness", "tag": "See where you stand", "done": has_done and ready["tasks_total"] > 0 and ready["tasks_done"] >= ready["tasks_total"]}]
    nxt = next((j["id"] for j in journey if not j["done"]), "ready")
    jdata = {"ws": ws.pk, "next": nxt, "done": [j["id"] for j in journey if j["done"]], "order": [j["id"] for j in journey], "labels": {j["id"]: j["label"] for j in journey},
             "has_tasks": bool(tasks), "researched": researched, "plan_url": f"/w/{ws.pk}/plan/", "panel": [i.name for i in ws.panel.all()]}
    left = (ws.date - date.today()).days if ws.date and not ws.general else None
    return render(request, "core/workspace.html", {"ws": ws, "r": ws.research or {}, "findings": ws.findings.all(), "panel": ws.panel.all(), "mode": mode, "mode_why": mode_why, "kind_label": pf["label"],
        "journey": journey, "journey_next": nxt, "jdata": jdata, "days_left": left, "tasks": tasks, "ready": ready, "sessions": sessions, "today": date.today(),
        "rs_ui": {"kind": ws.kind, "title": pf["anim"]["title"], "sig": pf["anim"]["sig"], "colors": pf["anim"]["c"], "speed": pf["anim"]["speed"], "steps": kinds.research_steps(ws.kind), "name": ws.company or ws.title,
                  "job": f"/w/{ws.pk}/job/", "run": f"/w/{ws.pk}/research/", "running": ws.job_state == "running"}, "plan_steps": kinds.research_steps(ws.kind)[:-2]})

@login_required
@require_POST
@ajax
def do_research(request, pk):
    ws = mine(Workspace, request, pk); pr = ws.job_progress or {}
    if ws.job_state == "running" and time.time() - (pr.get("t") or 0) < 300:   # one run at a time: a second click (or tab) joins the running one instead of doubling the AI requests
        return JsonResponse({"ok": True, "job": f"/w/{pk}/job/", "already_running": True})
    q = jobs.dispatch(jobs.research_task, pk); return JsonResponse({"ok": True, "job": f"/w/{pk}/job/" if q else None})

@login_required
@require_POST
@ajax
def do_plan(request, pk): mine(Workspace, request, pk); q = jobs.dispatch(jobs.plan_task, pk); return JsonResponse({"ok": True, "job": f"/w/{pk}/job/" if q else None})

@login_required
@require_POST
def do_adjust(request, pk):
    return JsonResponse({"ok": True, "log": logic.adjust_plan(mine(Workspace, request, pk))})

@login_required
@require_POST
def do_allocate(request, pk):
    ws = mine(Workspace, request, pk); panelplan.allocate(ws, use_ai=bool(ws.research)); return JsonResponse({"ok": True})

@login_required
@require_POST
def ws_delete(request, pk): mine(Workspace, request, pk).delete(); return redirect("dashboard")

@login_required
@require_POST
def toggle_task(request, pk):
    t = mine(PrepTask, request, pk); t.done = not t.done; t.save(); return JsonResponse({"done": t.done})

# ---------- interview room ----------
@login_required
@require_POST
def new_session(request, pk):
    ws = mine(Workspace, request, pk)
    if not ws.panel.exists(): panelplan.allocate(ws)
    s = Session.objects.create(workspace=ws, mode=panelplan.choose_mode(ws)[0]); return redirect("room", pk=s.pk)

def _iv(i): return {"id": i.id, "name": i.name, "position": i.position, "image": f"/static/{i.image}", "gender": i.gender, "pitch": i.pitch, "rate": i.rate}

@login_required
def room(request, pk):
    s = mine(Session, request, pk); prof = agents.profile_of(request.user)
    if not s.workspace.panel.exists(): panelplan.allocate(s.workspace)   # ReadyWise, not the candidate, decides who is on the panel
    cands = agents.session_panel(s)
    return render(request, "core/room.html", {"s": s, "ws": s.workspace, "panel": cands, "limit": LIMITS.get(s.mode, 0), "rec_lang": langs.code(prof.language), "lang": prof.language,
        "panel_json": json.dumps([_iv(i) for i in cands])})

@login_required
@require_POST
@ajax
def dictate(request):
    """Speak-to-fill for any form field. Returns the transcript; the browser puts it in the field and the person can edit it."""
    f = request.FILES.get("audio")
    if not f: return JsonResponse({"error": "No audio was received."}, status=400)
    # no prompt: an instruction-like prompt can leak into the transcript or bias it. The language is the person's profile language, so accented speech is not guessed as another language.
    return JsonResponse(stt.transcribe(f.read(), f.content_type or "audio/webm", langs.code(agents.profile_of(request.user).language), ""))

@login_required
@require_POST
@ajax
def room_stt(request, pk):
    """Transcribe one recorded answer. The browser sends its own microphone audio; nothing is guessed if nothing was heard."""
    s = mine(Session, request, pk); f = request.FILES.get("audio")
    if not f: return JsonResponse({"error": "No audio was received."}, status=400)
    ws = s.workspace; hint = f"Job interview answer. Role: {ws.position or ws.title}. Company: {ws.company}. " + (agents.profile_of(ws.user).skills or "")[:200]
    r = stt.transcribe(f.read(), f.content_type or "audio/webm", langs.code(agents.profile_of(ws.user).language), hint)
    return JsonResponse(r)

@login_required
@require_POST
@ajax
def room_turn(request, pk):
    s = mine(Session, request, pk); d = json.loads(request.body); elapsed = int((timezone.now() - s.started_at).total_seconds())
    if d.get("answer") is not None:
        tag = {"interrupted": "[interrupting the interviewer] ", "build": agents.BUILD_TAG, "cut_off": "[the panel stopped the candidate because the answer ran long] "}.get(d.get("tag"), "")
        if s.status != "open": return JsonResponse({"error": "This interview has ended."}, status=400)
        Turn.objects.create(session=s, role="candidate", text=(tag + (d["answer"].strip() or "(no answer given)"))[:9000 if d.get("tag") == "build" else 3000], offset=elapsed)
    t, end, intro = agents.next_turn(s, elapsed)
    return JsonResponse({"speaker": _iv(t.speaker), "text": t.text, "end": end, "intro": intro, "limit": LIMITS.get(s.mode, 0), "turn_id": t.id, "grounded": getattr(t, "grounded", None), "challenge": getattr(t, "challenge", None), "n": s.turns.filter(role="interviewer").count()})

@login_required
@require_POST
def room_recording(request, pk):
    s = mine(Session, request, pk)
    f = request.FILES.get("rec")
    if f:
        try: url = storage.upload(f.read(), f"s{s.pk}.webm", "video/webm")
        except Exception: url = None
        if url: s.recording_url = url
        else: f.seek(0); s.recording = f
        s.save()
    return JsonResponse({"ok": True})

@login_required
@require_POST
@ajax
def room_finish(request, pk):
    s = mine(Session, request, pk)
    try: d = json.loads(request.body or b"{}")
    except ValueError: d = {}
    frames = [f for f in (d.get("frames") or [])[:5] if isinstance(f, str) and len(f) < 400000]
    if not s.ended_at: s.ended_at = timezone.now()
    s.status = "evaluating"; s.save()
    cam = d.get("camera") if isinstance(d.get("camera"), dict) else None
    if cam:  # only plain numbers from the browser are kept
        cam = {k: (round(float(v), 1) if isinstance(v, (int, float)) else {str(a)[:12]: int(b) for a, b in list(v.items())[:8] if isinstance(b, (int, float))}) for k, v in list(cam.items())[:8] if isinstance(v, (int, float, dict))}
    q = jobs.dispatch(jobs.finalize_task, s.pk, frames, cam)
    return JsonResponse({"url": f"/report/{s.pk}/", "job": f"/room/{s.pk}/job/" if q else None})

@login_required
def ws_job(request, pk):
    ws = mine(Workspace, request, pk); pr = ws.job_progress or {}; stale = ws.job_state == "running" and bool(pr.get("t")) and time.time() - pr["t"] > 300  # no progress for 5 minutes: the run was interrupted
    return JsonResponse({"state": ws.job_state, "error": ws.job_error, "progress": pr, "stale": stale})

@login_required
def room_job(request, pk):
    s = mine(Session, request, pk); return JsonResponse({"state": s.status, "url": f"/report/{s.pk}/", "error": "Evaluation failed. Open the room again to retry." if s.status == "error" else ""})

SAY = {"retry": "I did not catch an answer. Please go ahead when you are ready.", "nudge": "Take your time. Whenever you are ready."}

@login_required
@require_POST
@ajax
def room_tts(request, pk):
    s = mine(Session, request, pk); d = json.loads(request.body or b"{}")
    if d.get("say") in SAY:  # fixed phrases only, spoken by an interviewer of this session: nobody can use this endpoint to voice arbitrary text
        iv = next((i for i in agents.session_panel(s) if i.id == d.get("speaker_id")), None) or agents.session_panel(s)[0]; text = SAY[d["say"]]
    else:
        t = get_object_or_404(Turn, pk=d.get("turn_id"), session=s); iv, text = t.speaker, t.text
    if (agents.profile_of(s.workspace.user).language or "English") != "English": return JsonResponse({"error": "Voice audio is English only for now; your browser voice is used instead."}, status=400)
    return HttpResponse(tts.synth(text, iv.voice_name), content_type="audio/wav")

@login_required
def plan_ics(request, pk):
    ws = mine(Workspace, request, pk); esc = lambda x: x.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ReadyWise//EN"]
    for t in ws.tasks.filter(done=False):
        L += ["BEGIN:VEVENT", f"UID:rw-{t.pk}@readywise", f"DTSTAMP:{timezone.now():%Y%m%dT%H%M%SZ}", f"DTSTART;VALUE=DATE:{t.due:%Y%m%d}", f"SUMMARY:{esc(t.title)}", f"DESCRIPTION:{esc(t.detail)}", "END:VEVENT"]
    r = HttpResponse("\r\n".join(L + ["END:VCALENDAR"]), content_type="text/calendar"); r["Content-Disposition"] = 'attachment; filename="readywise-plan.ics"'; return r

@login_required
def readiness_page(request, pk):
    ws = mine(Workspace, request, pk)
    return render(request, "core/readiness.html", {"ws": ws, "r": ws.research or {}, "ready": logic.readiness(ws), "panel": ws.panel.all(), "revise": ws.tasks.filter(done=False, category__in=["technical", "system_design"])[:8],
        "left": (ws.date - date.today()).days if ws.date and not ws.general else None, "today": date.today()})

@login_required
@require_POST
def interviewer_publish(request, pk):
    i = get_object_or_404(Interviewer, pk=pk, owner=request.user); i.public = not i.public; i.save(); return redirect("interviewers")

@login_required
@require_POST
def interviewer_clone(request, pk):
    i = get_object_or_404(Interviewer, pk=pk, public=True)
    if i.owner_id != request.user.id: i.pk = None; i.owner = request.user; i.public = False; i.save(); messages.success(request, f"{i.name} was added to your library.")
    return redirect("interviewers")

@login_required
def report(request, pk):
    s = mine(Session, request, pk); ev = getattr(s, "evaluation", None)
    return render(request, "core/report.html", {"s": s, "ws": s.workspace, "ev": ev, "turns": s.turns.select_related("speaker"),
        "labels": json.dumps([l for _, l in CATS]), "data": json.dumps([(ev.scores.get(c) or 0) if ev else 0 for c, _ in CATS])})

# ---------- interviewer marketplace ----------
@login_required
def interviewers(request):
    logic.ensure_seed()
    return render(request, "core/interviewers.html", {"builtin": Interviewer.objects.filter(owner=None), "mine": Interviewer.objects.filter(owner=request.user), "community": Interviewer.objects.filter(public=True).exclude(owner=request.user).exclude(owner=None)})

@login_required
def interviewer_new(request):
    if request.method == "POST":
        P = request.POST
        Interviewer.objects.create(owner=request.user, name=P.get("name", "Interviewer")[:60], position=P.get("position", "")[:80], personality=P.get("personality", ""), style=P.get("style", "Formal"),
            expertise=P.get("expertise", ""), responsibilities=P.get("responsibilities", ""), objectives=P.get("objectives", ""), difficulty=P.get("difficulty", "advanced"), image=P.get("image", AVATARS[0]),
            question_bank=P.get("question_bank", ""), rubric=P.get("rubric", ""), gender=P.get("gender", "m"), voice_name=P.get("voice_name") or ("hannah" if P.get("gender") == "f" else "daniel"), focus=",".join(P.getlist("focus")) or "communication")
        messages.success(request, "Interviewer created."); return redirect("interviewers")
    return render(request, "core/interviewer_new.html", {"avatars": AVATARS, "cats": CATS, "levels": LEVELS, "voices": logic.VOICES})
