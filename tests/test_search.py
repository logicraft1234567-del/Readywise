from datetime import date
from django.contrib.auth.models import User
from core.models import *
from .test_planner import setup, mk   # noqa: F401

def groups(r): return {g["label"]: g["items"] for g in r.json()["groups"]}

def test_search_finds_interviews_tasks_and_reports(client, setup):
    u, ws = setup; ws.company = "Acme Bank"; ws.save(); mk(ws, 0, title="Practise SQL window functions")
    s = Session.objects.create(workspace=ws, status="done"); Evaluation.objects.create(session=s, overall=72, scores={}, summary="Strong on indexing")
    g = groups(client.get("/search/?q=acme")); assert g["Interviews"][0]["url"] == f"/w/{ws.pk}/" and g["Reports"][0]["url"] == f"/report/{s.pk}/" and "score 72" in g["Reports"][0]["sub"]
    t = groups(client.get("/search/?q=window"))["Prep tasks"][0]; assert t["url"].startswith("/tasks/?w=") and f"w={ws.pk}" in t["url"]
    assert groups(client.get("/search/?q=zzzzqq")) == {}

def test_search_is_private_and_needs_login(client, setup, django_user_model):
    u, ws = setup; other = User.objects.create_user("o", "o@x.co", "pw"); Workspace.objects.create(user=other, title="Secret panel at Globex")
    assert "Interviews" not in groups(client.get("/search/?q=globex"))
    client.logout(); assert client.get("/search/?q=acme").status_code == 302

def test_empty_search_offers_recent_work_and_page_has_the_box(client, setup):
    u, ws = setup; mk(ws, 0, title="Due now")
    g = groups(client.get("/search/")); assert g["Recent interviews"] and g["Due today"][0]["title"] == "Due now"
    h = client.get("/dashboard/").content.decode(); assert 'id="hs-list"' in h and "js/search.js" in h
