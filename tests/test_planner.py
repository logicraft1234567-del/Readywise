import json, pytest
from datetime import date, timedelta
from django.contrib.auth.models import User
from core.models import *

@pytest.fixture
def setup(client, db):
    u = User.objects.create_user("p", "p@x.co", "pw"); client.force_login(u)
    ws = Workspace.objects.create(user=u, title="Backend role", position="Engineer", date=date.today() + timedelta(days=2),
        sources=[{"url": "https://example.com/sql", "title": "SQL indexing guide", "snippet": "indexes"}, {"url": "https://www.youtube.com/watch?v=abc", "title": "SQL indexes explained", "video": True}])
    return u, ws

def mk(ws, days, **kw): return PrepTask.objects.create(workspace=ws, due=date.today() + timedelta(days=days), title=kw.pop("title", "SQL indexes"), **kw)

def test_future_locked_today_completes_and_undoes(client, setup):
    u, ws = setup; later, now = mk(ws, 2), mk(ws, 0, title="Today task")
    r = client.post(f"/task/{later.pk}/toggle/"); assert r.status_code == 400 and "opens on" in r.json()["error"]
    r = client.post(f"/task/{now.pk}/toggle/"); assert r.status_code == 200 and r.json()["done"] is True
    now.refresh_from_db(); assert now.done and now.completed_at
    assert client.post(f"/task/{now.pk}/toggle/").json()["done"] is False

def test_missed_task_moves_forward_and_reminds(client, setup):
    u, ws = setup; t = mk(ws, -2, title="Missed one")
    n = client.get("/notifications/").json(); t.refresh_from_db()
    assert t.due == date.today() and t.orig_due == date.today() - timedelta(days=2)
    item = [i for i in n["items"] if i["task"]][0]; assert "missed" in item["message"].lower() and item["task"]["moved"] and n["count"] == 1
    assert client.post(f"/task/{t.pk}/toggle/").json()["done"] is True

def test_overflow_spreads_and_never_passes_interview(client, setup):
    u, ws = setup
    for i in range(7): mk(ws, -1, title=f"m{i}")
    client.get("/notifications/"); days = sorted(PrepTask.objects.values_list("due", flat=True))
    assert max(days) <= ws.date and days.count(date.today()) == 4

def test_links_and_interview_button(client, setup):
    u, ws = setup; t = mk(ws, 0, title="SQL indexes", detail="indexing"); m = mk(ws, 0, title="Mock panel", kind="mock")
    cards = {c["title"]: c for c in [i["task"] for i in client.get("/notifications/").json()["items"] if i["task"]]}
    assert cards["SQL indexes"]["links"]["read"]["url"] == "https://example.com/sql" and "youtube.com/watch" in cards["SQL indexes"]["links"]["watch"]["url"]
    assert cards["Mock panel"]["links"]["interview"]["workspace"] == ws.pk and cards["SQL indexes"]["links"]["interview"] is None
    assert "youtube.com/results" in cards["Mock panel"]["links"]["watch"]["url"]

def test_pages_render(client, setup):
    u, ws = setup; mk(ws, 0); mk(ws, 3)
    c = client.get("/calendar/"); assert c.status_code == 200 and b'id="day-panel"' in c.content and b"Interview" in c.content
    assert client.get(f"/calendar/?m=2030-02&w={ws.pk}&d=2030-02-05").status_code == 200
    w = client.get(f"/w/{ws.pk}/").content.decode(); assert 'id="plan-list"' in w and 'id="plan-data"' in w
    d = client.get("/dashboard/").content.decode(); assert 'id="pg-score"' in d or 'No scores yet' in d; assert 'id="focus-list"' not in d and 'id="bell"' in d and "Calendar" in d and "/tasks/" in d and "Analytics" in d
    a = client.get("/analytics/"); assert a.status_code == 200 and b'id="pg-activity"' in a.content and b'id="radar"' in a.content

def test_progress_numbers(client, setup):
    u, ws = setup
    for sc, cat in ((60, 50), (72, 70), (65, 66)):
        s = Session.objects.create(workspace=ws, status="done"); Evaluation.objects.create(session=s, overall=sc, scores={"technical": cat})
    t = mk(ws, 0); client.post(f"/task/{t.pk}/toggle/")
    from core.services import planner
    p = planner.progress(u); assert [x["score"] for x in p["series"]] == [60, 72, 65] and p["trend"]["state"] == "up" and p["trend"]["delta"] == 5
    assert p["cats"][0]["first"] == 50 and p["cats"][0]["latest"] == 66 and p["streak"] == 1 and p["week_done"] == 1
