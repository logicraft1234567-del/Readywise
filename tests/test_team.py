"""Team workspaces: a pitch or hackathon prepared by up to five people who share one workspace."""
import json
import pytest
from datetime import timedelta
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from core.models import Workspace, WorkspaceMember, PrepTask, TeamSlot, Session
from core.services import ai, kinds, team, logic, planner
from tests.test_flow import fake, fake_search, SEARCHED


@pytest.fixture
def two(monkeypatch, db):
    monkeypatch.setattr(ai, "call", fake); monkeypatch.setattr(ai, "search", fake_search); SEARCHED.clear()
    a, b = Client(), Client()
    a.post("/register/", {"username": "coord", "password": "password123", "email": "coord@gmail.com"})
    b.post("/register/", {"username": "mate", "password": "password123", "email": "Mate@Gmail.com"})
    return a, b

def _pitch(a, emails="mate@gmail.com"):
    logic.ensure_seed(); a.post("/w/new/", {"kind": "pitch", "pitch__company": "Omega", "pitch__position": "Seed", "pitch__team_emails": emails})
    return Workspace.objects.get(kind="pitch")

def test_hackathon_is_a_team_type_and_the_wizard_asks_for_teammates_last():
    assert "hackathon" in kinds.ORDER and set(kinds.TEAM_KINDS) == {"pitch", "hackathon"} and kinds.doc("hackathon")["key"] == "deck"
    from core.views import interview_config
    for k in kinds.TEAM_KINDS:
        last = interview_config()["kinds"][k]["docSteps"][-1]; assert last["name"] == f"{k}__team_emails" and not last.get("req")   # optional, and the very last question
    assert not any(s["id"] == "team" for s in interview_config()["kinds"]["visa"]["docSteps"])

def test_creating_a_pitch_with_a_teammate_makes_you_the_coordinator_and_invites_them(two):
    a, b = two; ws = _pitch(a)
    co = WorkspaceMember.objects.get(workspace=ws, role="coordinator"); inv = WorkspaceMember.objects.get(workspace=ws, role="member")
    assert co.user == ws.user and co.status == "accepted" and inv.status == "invited" and inv.email == "mate@gmail.com" and inv.user.username == "mate"
    assert b.get(f"/w/{ws.pk}/").status_code == 404   # not yet: they have to accept
    n = b.get("/notifications/").json(); assert n["items"][0]["type"] == "invite" and n["count"] >= 1 and "coord" in n["items"][0]["title"]
    assert "invited you to join" in b.get("/dashboard/").content.decode()

def test_accepting_shares_everything_and_the_coordinator_is_told(two):
    a, b = two; ws = _pitch(a); inv = WorkspaceMember.objects.get(role="member")
    assert b.post(f"/team/invite/{inv.pk}/accept/", HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()["status"] == "accepted"
    assert b.get(f"/w/{ws.pk}/").status_code == 200 and b.get(f"/w/{ws.pk}/team/").status_code == 200   # the same workspace
    assert any(r["workspace"] == ws.title for r in [{"workspace": x.title} for x in Workspace.objects.filter(team.ws_q(User.objects.get(username="mate"))).distinct()])
    assert any("joined" in i["title"] for i in a.get("/notifications/").json()["items"])
    assert Client().get(f"/w/{ws.pk}/team/").status_code == 302   # strangers are sent to log in
    c = Client(); c.post("/register/", {"username": "other", "password": "password123", "email": "o@gmail.com"}); assert c.get(f"/w/{ws.pk}/team/").status_code == 404

def test_only_the_invited_person_can_answer(two):
    a, b = two; _pitch(a); inv = WorkspaceMember.objects.get(role="member")
    assert a.post(f"/team/invite/{inv.pk}/accept/").status_code == 404   # even the coordinator cannot accept for them
    b.post(f"/team/invite/{inv.pk}/decline/"); inv.refresh_from_db(); assert inv.status == "declined"

def test_a_team_has_at_most_five_people(two):
    a, b = two; ws = _pitch(a, "a@x.com b@x.com c@x.com d@x.com e@x.com")
    assert ws.members.exclude(status="declined").count() == 5 and ws.members.filter(role="member").count() == 4   # the coordinator counts as one
    sent, skipped = team.invite(ws, ws.user, ["f@x.com"]); assert not sent and "full" in skipped[0][1]
    ws2 = Workspace.objects.create(user=ws.user, title="Solo", kind="visa"); assert team.invite(ws2, ws.user, ["a@x.com"])[0] == []   # not for every type

def test_the_prep_plan_is_split_between_members_and_practice_is_copied(two):
    a, b = two; ws = _pitch(a); inv = WorkspaceMember.objects.get(role="member"); b.post(f"/team/invite/{inv.pk}/accept/")
    b.post(f"/w/{ws.pk}/team/part/", {"part": "The demo and the tech questions"}); a.post(f"/w/{ws.pk}/team/part/", {"part": "Market and the ask"})
    day = planner.today()
    for i in range(6): PrepTask.objects.create(workspace=ws, due=day, title=f"Read about topic {i}", category="strategic")
    PrepTask.objects.create(workspace=ws, due=day, title="Mock interview with the panel", kind="mock")
    assert a.post(f"/w/{ws.pk}/team/split/").status_code == 302
    mine_, theirs = (ws.tasks.filter(assignee__username=n) for n in ("coord", "mate"))
    assert mine_.count() >= 3 and theirs.count() >= 3 and not ws.tasks.filter(assignee__isnull=True, done=False).exists()   # shared fairly, nothing left over
    assert mine_.filter(kind="mock").count() == 1 and theirs.filter(kind="mock", team_copy=True).count() == 1               # each sits their own practice
    assert b.post(f"/task/{theirs.exclude(kind='mock').first().pk}/toggle/").status_code in (200, 400)                     # their own task: allowed (or just not due)
    assert b.post(f"/task/{mine_.exclude(kind='mock').first().pk}/toggle/").status_code == 403                            # a teammate's task: not theirs to tick
    ids = {t["id"] for t in b.get("/tasks/").context["data"]["today"]}; assert ids == set(theirs.values_list("pk", flat=True)) - set(theirs.filter(done=True).values_list("pk", flat=True)) or ids <= set(theirs.values_list("pk", flat=True))

def test_everyone_marks_when_they_are_free_and_the_coordinator_confirms(two):
    a, b = two; ws = _pitch(a); inv = WorkspaceMember.objects.get(role="member"); b.post(f"/team/invite/{inv.pk}/accept/")
    when = (timezone.localtime() + timedelta(days=3)).replace(hour=15, minute=0).strftime("%Y-%m-%dT%H:%M")
    a.post(f"/w/{ws.pk}/team/slots/add/", {"when": when}); s = TeamSlot.objects.get()
    assert not team.slots(ws, ws.user)[0]["all"]; b.post(f"/w/{ws.pk}/team/slots/{s.pk}/vote/")
    assert team.slots(ws, ws.user)[0]["all"] and team.slots(ws, ws.user)[0]["count"] == 2   # both are free
    assert b.post(f"/w/{ws.pk}/team/slots/{s.pk}/confirm/").status_code == 404                  # only the coordinator confirms
    a.post(f"/w/{ws.pk}/team/slots/{s.pk}/confirm/"); ws.refresh_from_db()
    assert ws.date == timezone.localtime(s.start).date() and ws.details["team_time"].endswith("15:00")
    assert any("Interview time set" in i["title"] for i in b.get("/notifications/").json()["items"])
    a.post(f"/w/{ws.pk}/team/slots/add/", {"when": "2001-01-01T10:00"}); assert TeamSlot.objects.count() == 1   # not in the past

def test_each_member_sits_their_own_interview_and_the_team_reads_the_reports(two):
    a, b = two; ws = _pitch(a); inv = WorkspaceMember.objects.get(role="member"); b.post(f"/team/invite/{inv.pk}/accept/")
    b.post(f"/w/{ws.pk}/session/"); s = Session.objects.get(); assert s.user.username == "mate"
    assert b.get(f"/room/{s.pk}/").status_code == 200 and a.get(f"/room/{s.pk}/").status_code == 404   # the room is theirs alone
    assert a.get(f"/report/{s.pk}/").status_code == 200                                              # the report is shared with the team
    from core.services import agents; assert agents.candidate_of(s).username == "mate" and "TEAM (presenting together as one team of 2" in agents.ctx(ws)   # the interviewers know it is a team


# ---- research for a pitch or hackathon: understand the product, then find competitors that really compete ----
def test_only_the_competitor_steps_of_team_types_are_deep():
    deep = {k: [s["label"] for s in kinds.profile(k)["plan"] if s.get("deep")] for k in kinds.ORDER}
    assert deep["pitch"] == ["Competitors and alternatives"] and deep["hackathon"] == ["Similar projects and tools"]
    assert not [k for k in kinds.ORDER if k not in kinds.TEAM_KINDS and deep[k]]

def test_competitors_are_found_from_the_product_then_checked(two, monkeypatch):
    from core.services import research
    a, b = two; ws = _pitch(a); ws.details = {"problem": "Buyers of used phones get scammed", "market": "Nigerian resellers"}; ws.save()
    calls = []
    def fake_search(prompt):
        calls.append(prompt)
        if "Check this competitor list" in prompt: return ("Acme Escrow (DIRECT, confirmed). " + "Same customer, same job. " * 12, [{"url": "https://checked.example/acme", "title": "Acme"}])
        return ("Acme Escrow (DIRECT); Random Bank (not a competitor)", [{"url": "https://acme.example", "title": "Acme"}])
    monkeypatch.setattr(research, "_search", fake_search)
    monkeypatch.setattr(ai, "call", lambda *a, **k: (json.dumps({"what": "Escrow that holds payment until a used phone is received", "customer": "Nigerian phone resellers", "job": "get paid without being scammed", "search_terms": ["phone escrow Nigeria"]}), {}))
    step = next(s for s in kinds.profile("pitch")["plan"] if s.get("deep"))
    out = research._task_competitors(ws, research._ctx(ws), "English", step)
    assert out["product"]["customer"] == "Nigerian phone resellers" and len(calls) == 2
    assert "phone escrow Nigeria" in calls[0] and "DIRECT" in calls[0] and "NOT competitors" in calls[0]   # searched with the product's own words, with a clear rule for who counts
    assert "same customer for the same job" in calls[1] and "Random Bank" in calls[1]                       # then every candidate is checked
    assert out["text"].startswith("PRODUCT AS UNDERSTOOD") and "Acme Escrow (DIRECT, confirmed)" in out["text"] and {s["url"] for s in out["sources"]} == {"https://acme.example", "https://checked.example/acme"}
    ws.research = {"summary": "s", "product": out["product"], "sections": [{"key": "competition", "title": "Competitors", "items": [{"point": f"Rival {i} (DIRECT): x"} for i in range(6)]}]}
    br = research.brief(ws, 3000); assert "THE PRODUCT: Escrow that holds payment" in br and "Rival 5" in br   # the interviewers press on the real rivals
