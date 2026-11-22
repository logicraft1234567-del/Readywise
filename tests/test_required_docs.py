"""Required documents in the new-interview flow: every type asks for the one thing the AI cannot guess (a CV for jobs, the deck for a pitch...),
the text is read and shown, it reaches the prompts, and it is stored on the workspace."""
import json
from django.core.files.uploadedfile import SimpleUploadedFile
from core.models import Workspace
from core.services import agents, ai, kinds, wizard, logic
from tests.test_flow import client_in, post_json  # noqa: F401  (fixtures)

CV = "Ada Obi. Backend engineer, 3 years at Paystack building payment APIs in Python and Postgres. BSc Computer Science, University of Ibadan. Led a migration that cut latency by 40 percent."

def test_every_interview_type_has_a_required_document_question_before_the_personal_ones(client_in):
    cfg = client_in.get("/w/new/").context["cfg"]
    for k, kc in cfg["kinds"].items():
        d = kinds.doc(k); ids = [x["id"] for x in kc["steps"]]; st = next(x for x in kc["steps"] if x["id"] == d["key"])
        assert st["type"] == "doc" and st["req"] and st["adapt"] and st["name"] == f"{k}__{d['key']}" and st["file"] == "doc_" + d["key"], k
        assert ids.index(d["key"]) > ids.index("jd") and st["reqMsg"]
    assert {kinds.doc(k)["key"] for k in ("startup", "employment", "internship", "graduate", "admission", "scholarship", "fellowship", "certification")} == {"cv"}
    assert kinds.doc("visa")["key"] == "application" and kinds.doc("pitch")["key"] == "deck"       # not only jobs
    assert cfg["docUrl"] == "/w/doc/"

def test_a_cv_saved_in_the_profile_is_offered_so_nobody_uploads_it_twice(client_in):
    cfg = client_in.get("/w/new/").context["cfg"]; assert "employment__cv" not in cfg["values"]
    p = agents.profile_of(client_in.session and __import__("django.contrib.auth").contrib.auth.get_user(client_in)); p.cv_text = CV; p.save()
    cfg = client_in.get("/w/new/").context["cfg"]; st = next(x for x in cfg["kinds"]["employment"]["steps"] if x["id"] == "cv")
    assert cfg["values"]["employment__cv"] == CV and "loaded the CV from your profile" in st["help"] and st["req"]
    assert "visa__application" not in cfg["values"]                                                  # only CV-type documents come from the profile

def test_the_server_reads_an_uploaded_file_and_sends_the_text_back(client_in):
    r = client_in.post("/w/doc/", {"file": SimpleUploadedFile("cv.txt", CV.encode())}); assert r.status_code == 200 and r.json()["text"] == CV and r.json()["truncated"] is False
    big = SimpleUploadedFile("cv.txt", ("word " * 5000).encode()); d = client_in.post("/w/doc/", {"file": big}).json(); assert len(d["text"]) == 6000 and d["truncated"]
    assert client_in.post("/w/doc/", {"file": SimpleUploadedFile("e.txt", b"  \n ")}).status_code == 400   # nothing readable: say so
    assert client_in.post("/w/doc/", {}).status_code == 400 and client_in.get("/w/doc/").status_code == 405

def test_reading_a_document_needs_a_login(client):
    assert client.post("/w/doc/", {"file": SimpleUploadedFile("cv.txt", CV.encode())}).status_code == 302

BASE = {"kind": "employment", "duration": "45", "prep_days": "7", "employment__company": "Acme", "employment__position": "Backend engineer"}

def test_the_document_is_stored_on_the_workspace_and_first_cv_goes_to_the_profile(client_in):
    assert client_in.post("/w/new/", {**BASE, "employment__cv": CV}).status_code == 302
    ws = Workspace.objects.get(); assert ws.documents == {"cv": CV} and agents.profile_of(ws.user).cv_text == CV

def test_an_uploaded_file_is_used_when_no_text_came_with_it(client_in):
    client_in.post("/w/new/", {**BASE, "doc_cv": SimpleUploadedFile("cv.txt", CV.encode())}); assert Workspace.objects.get().documents == {"cv": CV}

def test_the_profile_cv_is_the_fallback_and_other_types_use_their_own_document(client_in):
    p = agents.profile_of(Workspace.objects.model.user.field.related_model.objects.get(username="t1")); p.cv_text = CV; p.save()
    client_in.post("/w/new/", BASE); assert Workspace.objects.get().documents == {"cv": CV}
    client_in.post("/w/new/", {"kind": "pitch", "duration": "20", "pitch__company": "Omega", "pitch__position": "Seed", "pitch__deck": "Slide 1: we fix payments"})
    assert Workspace.objects.get(kind="pitch").documents == {"deck": "Slide 1: we fix payments"}

def test_documents_reach_the_prompts_without_repeating_the_profile_cv(client_in):
    client_in.post("/w/new/", {"kind": "visa", "duration": "10", "visa__company": "UK", "visa__position": "Student visa", "visa__application": "Offer letter from Leeds; father sponsors"})
    ws = Workspace.objects.get(); c = agents.ctx(ws); assert "<untrusted_documents>" in c and "Offer letter from Leeds" in c
    from core.services import research; assert "Offer letter from Leeds" in research._ctx(ws)
    client_in.post("/w/new/", {**BASE, "employment__cv": CV}); w2 = Workspace.objects.get(kind="employment"); assert CV not in agents.docs_block(w2)   # already in the prompt through the profile

def test_the_guide_reads_the_document_and_can_never_skip_it(monkeypatch):
    cat = wizard.catalogue("employment"); assert cat["cv"]["req"] and cat["cv"]["type"] == "doc"
    seen = {}
    def fake(prompt, **kw): seen.update(prompt=prompt, **kw); return json.dumps({"order": ["why"], "ask": [{"q": "Your CV shows a move from banking. What drove it?", "short": "Career move"}]}), []
    monkeypatch.setattr(ai, "call", fake); wizard._cache.clear()
    r = wizard.adapt("employment", {"company": "Acme", "position": "Backend", "cv": CV}, ["cv", "why", "win"], [])
    assert "Ada Obi" in seen["prompt"] and "REQUIRED" in seen["prompt"] and "cv" in r["order"] and r["ask"][0]["q"].startswith("Your CV shows")
    assert seen["light"] is True and seen["wait"] <= 5                                               # cheap model, and it never makes the person wait long

def test_a_busy_ai_means_the_normal_order_at_once_and_identical_requests_are_not_asked_twice(monkeypatch):
    calls = []
    def boom(prompt, **kw): calls.append(1); raise ai.AIError("The AI is busy right now: Groq is rate limiting this app")
    monkeypatch.setattr(ai, "call", boom); wizard._cache.clear(); r = wizard.adapt("employment", {"company": "A"}, ["position", "cv"], [])
    assert r["fallback"] and r["order"] == ["position", "cv"] and r["ask"] == []
    monkeypatch.setattr(ai, "call", lambda p, **k: (calls.append(2) or json.dumps({"order": ["cv"]}), [])); wizard.adapt("employment", {"company": "A"}, ["position", "cv"], []); wizard.adapt("employment", {"company": "A"}, ["position", "cv"], [])
    assert calls.count(2) == 1
