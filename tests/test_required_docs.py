"""Required documents in the new-interview flow: every type asks for the one thing the AI cannot guess (a CV for jobs, the deck for a pitch...),
the text is read and shown, it reaches the prompts, and it is stored on the workspace."""
import json
from django.core.files.uploadedfile import SimpleUploadedFile
from core.models import Workspace
from core.services import agents, ai, kinds, wizard, logic
from tests.test_flow import client_in, post_json  # noqa: F401  (fixtures)

CV = "Ada Obi. Backend engineer, 3 years at Paystack building payment APIs in Python and Postgres. BSc Computer Science, University of Ibadan. Led a migration that cut latency by 40 percent."

def test_every_interview_type_asks_in_three_parts_and_documents_come_last_after_a_document_check(client_in):
    cfg = client_in.get("/w/new/").context["cfg"]
    for k, kc in cfg["kinds"].items():
        d = kinds.doc(k); ids = [x["id"] for x in kc["steps"]]; ds = kc["docSteps"]; st = ds[1]
        assert [x["id"] for x in ds] == ["docscan", d["key"]] and ds[0]["type"] == "research" and ds[0]["noSkip"] and kc["docKey"] == d["key"], k
        assert st["type"] == "doc" and st["req"] and st["name"] == f"{k}__{d['key']}" and st["file"] == "doc_" + d["key"] and st["reqMsg"] and not st.get("adapt"), k
        assert d["key"] not in ids and "jd" in ids                                                           # the main document is no longer among the personal questions
        why = kinds.WHY_KEYS[k]; assert why and all(w in ids for w in why) and ids.index("jd") < min(ids.index(w) for w in why), k   # part 2 follows the application
        chap = {x["id"]: x.get("chapter") for x in kc["steps"]}
        assert chap["company"] == "Your application" and all(chap[w] == "Why you chose it" for w in why) and {x["chapter"] for x in ds} == {"Your documents"}, k
    assert {kinds.doc(k)["key"] for k in ("startup", "employment", "internship", "graduate", "admission", "scholarship", "fellowship", "certification")} == {"cv"}
    assert kinds.doc("visa")["key"] == "application" and kinds.doc("pitch")["key"] == "deck"       # not only jobs
    assert cfg["docUrl"] == "/w/doc/" and cfg["docsUrl"] == "/w/docs/"

def test_a_cv_saved_in_the_profile_is_offered_so_nobody_uploads_it_twice(client_in):
    cfg = client_in.get("/w/new/").context["cfg"]; assert "employment__cv" not in cfg["values"]
    p = agents.profile_of(client_in.session and __import__("django.contrib.auth").contrib.auth.get_user(client_in)); p.cv_text = CV; p.save()
    cfg = client_in.get("/w/new/").context["cfg"]; st = next(x for x in cfg["kinds"]["employment"]["docSteps"] if x["id"] == "cv")
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


def test_document_check_finds_the_documents_asks_for_each_and_saves_them(client_in, monkeypatch):
    from core.services import wizard, ai
    wizard._dcache.clear()
    def fake_call(prompt, **kw): return json.dumps({"docs": [{"key": "funds", "label": "Proof of funds", "why": "They check who pays.", "must": True}, {"key": "cv", "label": "Your CV", "why": "x", "must": True}, {"key": "pp", "label": "Passport number", "why": "x", "must": True}]}), []
    monkeypatch.setattr(ai, "call", fake_call); monkeypatch.setattr(ai, "search", lambda *a, **k: (fake_call("")[0], []))
    r = client_in.post("/w/docs/", data=json.dumps({"kind": "employment", "company": "Acme", "position": "Engineer"}), content_type="application/json").json()
    assert r["source"] == "web" and [d["key"] for d in r["docs"]] == ["funds"]                          # the CV has its own question and a passport number is never asked for
    assert client_in.post("/w/docs/", data=json.dumps({"kind": "nope"}), content_type="application/json").status_code == 400
    manifest = json.dumps(r["docs"]); r2 = client_in.post("/w/new/", {"kind": "employment", "employment__company": "Acme", "employment__position": "Engineer", "employment__cv": CV, "employment__doc_funds": "Bank letter: balance 12,000", "docs_manifest": manifest})
    ws = Workspace.objects.get(company="Acme"); assert r2.status_code == 302
    assert ws.docs_plan[0]["key"] == "funds" and ws.documents["doc_funds"].startswith("Bank letter")
    assert [d["key"] for d in agents.doc_checklist(ws)] == ["funds"] and agents.doc_checklist(ws)[0]["have"] is True   # the workspace checklist shows it before any research has run


def test_document_check_falls_back_to_a_short_list_and_never_raises(monkeypatch):
    from core.services import wizard, ai
    wizard._dcache.clear(); boom = lambda *a, **k: (_ for _ in ()).throw(ai.AIError("down"))
    monkeypatch.setattr(ai, "call", boom); monkeypatch.setattr(ai, "search", boom)
    r = wizard.docs_research("visa", "United Kingdom", "Student visa"); assert r["source"] == "default" and any(d["key"] == "funds" for d in r["docs"])
