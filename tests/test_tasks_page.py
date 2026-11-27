from datetime import timedelta
from core.models import *
from core.services import planner
from .test_planner import setup, mk   # noqa: F401

def test_tasks_have_their_own_page_with_today_upcoming_and_done(client, setup):
    u, ws = setup; mk(ws, 0, title="Do now"); mk(ws, 2, title="Later one"); d = mk(ws, 0, title="Already done"); d.done = True; d.save()
    r = client.get("/tasks/"); h = r.content.decode(); assert r.status_code == 200
    assert "Do now" in h and "Later one" in h and "Already done" in h and 'id="l-today"' in h and 'id="l-later"' in h and 'id="l-done"' in h
    assert '"Do now"' in h   # drawn from one data block, like the rest of the planner
    assert client.get(f"/tasks/?w={ws.pk}").status_code == 200

def test_tasks_page_is_private_and_needs_login(client, setup):
    u, ws = setup; other = User.objects.create_user("o2", "o2@x.co", "pw"); w2 = Workspace.objects.create(user=other, title="Other"); mk(w2, 0, title="Secret task")
    assert "Secret task" not in client.get("/tasks/").content.decode()
    client.logout(); assert client.get("/tasks/").status_code == 302

def test_dashboard_and_calendar_no_longer_list_tasks_but_link_to_the_tasks_page(client, setup):
    u, ws = setup; mk(ws, 0, title="Unique task title xyz")
    dash = client.get("/dashboard/").content.decode(); assert "Unique task title xyz" not in dash and 'id="focus-list"' not in dash and 'href="/tasks/"' in dash
    cal = client.get("/calendar/").content.decode(); assert "Unique task title xyz" not in cal and "Tasks page" in cal
    assert 'href="/tasks/"' in dash and "Tasks" in dash   # sidebar entry
