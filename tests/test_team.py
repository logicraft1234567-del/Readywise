import json
from datetime import date, timedelta
from django.test import Client
from django.contrib.auth.models import User
from django.utils import timezone
from core.models import *
from core.services import team, kinds, competitors, agents
from .test_planner import setup, mk   # noqa: F401

def pitch(u, **kw): return Workspace.objects.create(user=u, title="Orbit pitch", kind="pitch", company="Orbit", position="Seed round", **kw)
def member(ws, email, name="Ada", part=""):
    u = User.objects.create_user(email.split("@")[0], email, "pw"); m = TeamMember.objects.create(workspace=ws, email=email, invited_by=ws.user, user=u, status="accepted", name=name, part=part, responded_at=timezone.now()); c = Client(); c.force_login(u); return u, m, c

def test_invites_are_checked_and_the_team_is_capped_at_five(client, setup):
    u, _ = setup; ws = pitch(u)
    ok, bad = team.invite(ws, "ada@gmail.com, KOLA@gmail.com\nada@gmail.com\nnot-an-email\np@x.co", u)
    assert [m.email for m in ok] == ["ada@gmail.com", "kola@gmail.com"] and any("that is you" in b for b in bad)
    ok2, bad2 = team.invite(ws, "a@x.com b@x.com c@x.com d@x.com", u)
    assert len(ok2) == 2 and any("at most 5" in b for b in bad2) and team.size(ws) == 5   # coordinator + four
    assert team.invite(ws, "ada@gmail.com", u)[0] == [] 

def test_invitation_shows_in_the_notifications_and_can_be_accepted(client, setup):
    u, _ = setup; ws = pitch(u); team.invite(ws, "kola@gmail.com", u)
    k = User.objects.create_user("kola", "kola@gmail.com", "pw"); c = Client(); c.force_login(k)
    n = c.get("/notifications/").json(); inv = [i for i in n["items"] if i["type"] == "invite"]; assert inv and n["count"] >= 1 and "invited you to present together" in inv[0]["title"]
    wrong = User.objects.create_user("zed", "zed@x.co", "pw"); c2 = Client(); c2.force_login(wrong); assert c2.post(f"/team/invite/{inv[0]['invite']}/accept/").status_code in (403, 404)
    r = c.post(f"/team/invite/{inv[0]['invite']}/accept/"); assert r.status_code == 200 and r.json()["url"] == f"/w/{ws.pk}/team/"
    assert TeamMember.objects.get(workspace=ws).status == "accepted" and not [i for i in c.get("/notifications/").json()["items"] if i["type"] == "invite"]
    assert c.get(f"/w/{ws.pk}/").status_code == 200 and ws in team.workspaces_for(k)   # the teammate now shares the workspace
    me = c.get("/dashboard/").content.decode(); assert "Orbit pitch" in me
    n = client.get("/notifications/").json(); assert any("joined your team" in i["title"] for i in n["items"])   # the coordinator is told

def test_a_decline_keeps_the_person_out(client, setup):
    u, _ = setup; ws = pitch(u); team.invite(ws, "kola@gmail.com", u); k = User.objects.create_user("kola", "kola@gmail.com", "pw"); c = Client(); c.force_login(k)
    m = TeamMember.objects.get(workspace=ws); assert c.post(f"/team/invite/{m.pk}/decline/").status_code == 200
    assert c.get(f"/w/{ws.pk}/").status_code == 404 and team.size(ws) == 1

def test_only_the_coordinator_runs_the_plan_and_deletes(client, setup):
    u, _ = setup; ws = pitch(u); k, m, c = member(ws, "kola@gmail.com")
    assert c.get(f"/w/{ws.pk}/team/").status_code == 200 and c.get(f"/w/{ws.pk}/").status_code == 200
    assert c.post(f"/w/{ws.pk}/plan/").status_code in (400, 404) and c.post(f"/w/{ws.pk}/delete/").status_code in (302, 404) and c.post(f"/w/{ws.pk}/team/invite/", {"emails": "x@y.com"}).status_code == 404
    assert Workspace.objects.filter(pk=ws.pk).exists() and not ws.team.filter(email="x@y.com").exists()   # nothing happened
    outsider = User.objects.create_user("o", "o@x.co", "pw"); c3 = Client(); c3.force_login(outsider); assert c3.get(f"/w/{ws.pk}/").status_code == 404 and c3.get(f"/w/{ws.pk}/team/").status_code == 404

def test_the_plan_is_split_by_what_each_person_presents(client, setup):
    u, _ = setup; ws = pitch(u, details={"team": "x", "coordinator_part": "market size pricing and go-to-market"}); k, m, c = member(ws, "kola@gmail.com", "Kola", "the technical demo and the architecture")
    mk(ws, 0, title="Size the market and pricing"); mk(ws, 0, title="Rehearse the technical demo"); mk(ws, 1, title="Write the architecture answer"); mk(ws, 1, title="Prepare unit economics for pricing")
    mock = mk(ws, 2, title="Panel practice", kind="mock"); team.split_tasks(ws)
    by = {t.title: t.assignee_id for t in ws.tasks.all()}
    assert by["Size the market and pricing"] == u.id and by["Rehearse the technical demo"] == k.id and by["Write the architecture answer"] == k.id and by["Prepare unit economics for pricing"] == u.id
    assert by["Panel practice"] is None   # practice interviews belong to everyone
    mine_ = {t.title for t in team.tasks_for(k)}; assert "Rehearse the technical demo" in mine_ and "Panel practice" in mine_ and "Size the market and pricing" not in mine_
    tid = ws.tasks.get(title="Size the market and pricing").pk; assert c.post(f"/task/{tid}/toggle/").status_code == 403   # a teammate cannot tick someone else's task
    assert client.get("/tasks/").status_code == 200 and "Whole team" in client.get("/tasks/").content.decode()
    ws.team.update(status="declined"); team.split_tasks(ws); assert not ws.tasks.exclude(assignee=None).exists()   # alone again: everything is the coordinator's

def test_a_time_is_confirmed_when_everyone_says_yes(client, setup):
    u, _ = setup; ws = pitch(u); k, m, c = member(ws, "kola@gmail.com"); day = (timezone.localtime() + timedelta(days=3)).date().isoformat()
    r = client.post(f"/w/{ws.pk}/team/slot/", {"date": day, "time": "16:30"}); assert r.status_code == 302
    s = ws.slots.get(); assert not s.chosen and not Workspace.objects.get(pk=ws.pk).scheduled_at
    assert any("Vote on a time" in i["title"] for i in c.get("/notifications/").json()["items"])   # the teammate is asked
    c.post(f"/w/{ws.pk}/team/vote/{s.pk}/", {"vote": "yes"}); ws.refresh_from_db(); s.refresh_from_db()
    assert s.chosen and ws.scheduled_at and ws.date.isoformat() == day
    assert "is confirmed" in client.get(f"/w/{ws.pk}/team/").content.decode()

def test_the_new_interview_flow_asks_about_teammates_for_pitch_and_hackathon_only(client, setup):
    from core.views import interview_config
    cfg = interview_config()["kinds"]
    for k in ("pitch", "hackathon"): assert cfg[k]["docSteps"][-1]["id"] == "teammates" and cfg[k]["docSteps"][-1]["type"] == "textarea"
    assert all(s["id"] != "teammates" for s in cfg["employment"]["docSteps"])
    r = client.post("/w/new/", {"kind": "hackathon", "hackathon__company": "Orbit", "hackathon__position": "ETHGlobal", "hackathon__teammates": "ada@gmail.com\nkola@gmail.com"})
    ws = Workspace.objects.get(kind="hackathon"); assert r.status_code == 302 and ws.team.count() == 2 and ws.user.username == "p"

def test_hackathon_is_a_full_interview_type():
    assert "hackathon" in kinds.ORDER and kinds.profile("hackathon")["label"] == "Hackathon presentation" and "hackathon" in kinds.DOCS and "hackathon" in kinds.TEAM_KINDS and len(kinds.profile("hackathon")["plan"]) == 5

def test_the_interviewers_know_who_is_on_the_team(client, setup):
    u, _ = setup; ws = pitch(u, details={"coordinator_part": "the market"}); assert "TEAM OF" not in agents.ctx(ws)
    member(ws, "kola@gmail.com", "Kola", "the demo"); c = agents.ctx(ws); assert "TEAM OF 2" in c and "Kola" in c and "the demo" in c

def test_competitors_are_verified_one_by_one_and_non_competitors_are_dropped(client, setup, monkeypatch):
    from core.services import ai
    u, _ = setup; ws = pitch(u, details={"problem": "Students cannot find safe night rides", "solution": "A shared ride app for campuses"})
    monkeypatch.setattr(ai, "call", lambda prompt, **kw: (json.dumps({"product": "A ride-sharing app for students", "customer": "university students", "problem": "safe rides at night", "category": "ride sharing", "must_overlap": "rides for students", "substitutes": ["walking"],
                                                                      "items": [{"name": "Uber", "url": "https://uber.com", "what": "ride hailing"}, {"name": "Slack", "url": "https://slack.com", "what": "chat"}, {"name": "Bolt", "url": "https://bolt.eu", "what": "rides"}]}), {}))
    def search(q, **kw):
        if "Slack" in q.split("Check, using the web, whether")[-1][:20]: return (json.dumps({"verdict": "not_competitor", "why": "chat tool"}), [])
        if "Uber" in q.split("Check, using the web, whether")[-1][:20]: return (json.dumps({"verdict": "direct", "why": "same riders", "how_they_differ": "campus only", "their_strength": "huge supply", "evidence_url": "https://uber.com/about"}), [])
        if "Bolt" in q.split("Check, using the web, whether")[-1][:20]: return (json.dumps({"verdict": "direct", "why": "same riders", "how_they_differ": "safety focus", "their_strength": "cheap"}), [{"url": "https://bolt.eu/en"}])
        return ("Uber, Slack and Bolt are named", [])
    monkeypatch.setattr(ai, "search", search)
    out = competitors.run(ws); names = [i["name"] for i in out["items"]]
    assert names == ["Uber", "Bolt"] and out["dropped"] == ["Slack"] and out["items"][0]["source"] == "https://uber.com/about" and out["product"]["customer"] == "university students"
    ws.research = {"competitors": out}; assert "Uber (direct)" in competitors.brief_line(ws)

def test_the_workspace_page_shows_verified_competitors_and_the_team_button(client, setup):
    u, _ = setup; comp = {"product": {"product": "A ride app for students", "customer": "students"}, "dropped": ["Slack"], "items": [{"name": "Uber", "url": "https://uber.com", "what": "ride hailing", "type": "direct", "why": "same riders", "differ": "campus only", "strength": "supply", "source": "https://uber.com/about"}]}
    ws = Workspace.objects.create(user=u, title="Orbit", kind="hackathon", company="Orbit", position="ETHGlobal", researched_at=timezone.now(), research={"summary": "Summary text", "sections": [], "topics": [], "competitors": comp})
    h = client.get(f"/w/{ws.pk}/").content.decode()
    assert "Competitors that really compete" in h and "Uber" in h and "Direct competitor" in h and "Checked and left out" in h and "Slack" in h and f"/w/{ws.pk}/team/" in h
    t = client.get(f"/w/{ws.pk}/team/").content.decode(); assert "Invite teammates" in t and "Propose a time" in t and "Your part" in t
