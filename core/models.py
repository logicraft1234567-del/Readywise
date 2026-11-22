from django.db import models
from django.contrib.auth.models import User

CATS = [("technical","Technical"),("system_design","System design"),("communication","Communication"),
        ("behavioural","Behavioural"),("strategic","Strategic thinking"),("company","Company knowledge")]
CAT_LABEL = dict(CATS)
KINDS = [("startup","Startup job"),("employment","Corporate job"),("internship","Internship"),("graduate","Graduate programme"),("admission","University admission"),
         ("scholarship","Scholarship"),("visa","Visa practice"),("fellowship","Fellowship"),("pitch","Investor pitch"),("certification","Certification")]
LEVELS = [("standard","Standard"),("advanced","Advanced"),("expert","Expert")]

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    education = models.TextField(blank=True); experience = models.TextField(blank=True)
    skills = models.TextField(blank=True); interests = models.TextField(blank=True)
    language = models.CharField(max_length=40, default="English"); cv_text = models.TextField(blank=True)
    full_name = models.CharField(max_length=120, blank=True); style = models.CharField(max_length=12, default="balanced"); cv_profile = models.JSONField(default=dict, blank=True)

class Interviewer(models.Model):
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=60); position = models.CharField(max_length=80)
    personality = models.CharField(max_length=200); style = models.CharField(max_length=80, default="Formal")
    expertise = models.CharField(max_length=200, blank=True); responsibilities = models.TextField()
    objectives = models.CharField(max_length=200, blank=True)
    difficulty = models.CharField(max_length=20, choices=LEVELS, default="advanced")
    image = models.CharField(max_length=120, default="img/i06.png")
    gender = models.CharField(max_length=1, default="m"); pitch = models.FloatField(default=1.0); rate = models.FloatField(default=1.0)
    focus = models.CharField(max_length=120, default="communication")  # comma-separated CATS keys
    voice_name = models.CharField(max_length=30, default="Kore"); public = models.BooleanField(default=False)
    question_bank = models.TextField(blank=True); rubric = models.TextField(blank=True); avatar = models.CharField(max_length=80, blank=True)
    def focus_list(self): return [f for f in self.focus.split(",") if f]
    def __str__(self): return f"{self.name} ({self.position})"

class Workspace(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=160); kind = models.CharField(max_length=20, choices=KINDS, default="employment")
    company = models.CharField(max_length=120, blank=True); position = models.CharField(max_length=120, blank=True)
    date = models.DateField(null=True, blank=True); general = models.BooleanField(default=False)
    duration = models.PositiveIntegerField(default=30); fmt = models.CharField(max_length=80, default="Technical + Behavioural")
    difficulty = models.CharField(max_length=20, choices=LEVELS, default="standard")
    location = models.CharField(max_length=60, default="Online"); prep_days = models.PositiveIntegerField(default=7)
    job_description = models.TextField(blank=True)
    panel = models.ManyToManyField(Interviewer, blank=True)
    research = models.JSONField(default=dict, blank=True); sources = models.JSONField(default=list, blank=True)
    researched_at = models.DateTimeField(null=True, blank=True)
    job_state = models.CharField(max_length=10, default="idle"); job_error = models.TextField(blank=True); job_progress = models.JSONField(default=dict, blank=True)
    research_cache = models.JSONField(default=dict, blank=True)   # notes of the research angles already finished, so a run that hit a rate limit resumes instead of starting over
    details = models.JSONField(default=dict, blank=True); documents = models.JSONField(default=dict, blank=True); allocation = models.JSONField(default=dict, blank=True); known_interviewers = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    def weights(self):
        from .services import kinds
        w = (self.research or {}).get("category_weights", {}) or {}; d = kinds.profile(self.kind)["weights"]
        return {k: float(w.get(k) if w.get(k) is not None else d.get(k, 5)) for k, _ in CATS}

class Finding(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="findings")
    claim = models.TextField(); kind = models.CharField(max_length=24, default="inferred")  # confirmed / candidate_reported / inferred
    confidence = models.CharField(max_length=12, default="medium"); relevance = models.CharField(max_length=200, blank=True)
    source_hint = models.CharField(max_length=300, blank=True); source_date = models.CharField(max_length=40, blank=True)
    retrieved = models.DateField(auto_now_add=True)

class PrepTask(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="tasks")
    due = models.DateField(); title = models.CharField(max_length=160); detail = models.TextField(blank=True)
    category = models.CharField(max_length=20, default="technical"); kind = models.CharField(max_length=12, default="learn")
    done = models.BooleanField(default=False); priority = models.IntegerField(default=5); auto_added = models.BooleanField(default=False)
    class Meta: ordering = ["due", "-priority", "id"]

class Session(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="sessions")
    mode = models.CharField(max_length=20, default="normal")  # normal/challenging/high_pressure/executive/unknown
    started_at = models.DateTimeField(auto_now_add=True); ended_at = models.DateTimeField(null=True, blank=True)
    recording = models.FileField(upload_to="recordings/", null=True, blank=True)
    covered = models.JSONField(default=list, blank=True); status = models.CharField(max_length=12, default="open")
    vision = models.JSONField(default=dict, blank=True); recording_url = models.CharField(max_length=400, blank=True)
    challenge = models.JSONField(default=dict, blank=True)  # the hands-on task the panel set in this session, if any
    panel_ids = models.JSONField(default=list, blank=True)  # interviewer ids the candidate chose for this session (1 to 3); empty = the workspace panel

class Turn(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="turns")
    speaker = models.ForeignKey(Interviewer, null=True, blank=True, on_delete=models.SET_NULL)
    role = models.CharField(max_length=12, default="interviewer"); text = models.TextField()
    topic = models.CharField(max_length=120, blank=True); followup = models.BooleanField(default=False)
    offset = models.PositiveIntegerField(default=0); created = models.DateTimeField(auto_now_add=True)

class Evaluation(models.Model):
    session = models.OneToOneField(Session, on_delete=models.CASCADE, related_name="evaluation")
    scores = models.JSONField(default=dict); summary = models.TextField(blank=True)
    observations = models.JSONField(default=list); improvements = models.JSONField(default=list); strengths = models.JSONField(default=list)

class MemoryItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE); category = models.CharField(max_length=20)
    score = models.FloatField(default=50); observations = models.PositiveIntegerField(default=0)
    note = models.TextField(blank=True); updated = models.DateTimeField(auto_now=True)
    class Meta: unique_together = ("user", "category")

class Contact(models.Model):
    name = models.CharField(max_length=80); email = models.EmailField(); message = models.TextField(); created = models.DateTimeField(auto_now_add=True)
