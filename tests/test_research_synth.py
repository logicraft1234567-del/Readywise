"""Research synthesis is two smaller calls, and one bad answer must not lose the whole briefing. Needs Django (not run in the authoring environment)."""
import json
from tests.test_flow import client_in  # noqa: F401
from core.services import ai, research

def test_truncated_first_answer_is_retried_and_part_two_failure_keeps_the_briefing(monkeypatch):
    calls = []
    good = json.dumps({"summary": "s", "sections": [], "topics": [], "key_numbers": [{"label": "Market size", "value": "$4B", "year": "2025", "status": "confirmed", "source": "x.com"}]})
    def fake(prompt, **kw):
        calls.append(kw.get("max_tokens"))
        if "list what this candidate should expect" in prompt: raise ai.AIError("Groq returned 429")
        return (good if len(calls) > 1 else "no json here"), []
    monkeypatch.setattr(ai, "call", fake)
    ws = type("W", (), {"kind": "startup"})(); d = research._synthesise(ws, "ctx", "English", [("Market", "notes")])
    assert d["key_numbers"][0]["value"] == "$4B" and "partial" in d and all(c for c in calls)   # every call had an explicit output budget

def test_a_second_click_does_not_start_a_second_research_run(client_in, monkeypatch):
    import time
    from core import jobs
    from core.models import Workspace
    started = []; monkeypatch.setattr(jobs, "dispatch", lambda *a: started.append(a) or True)
    client_in.post("/w/new/", {"kind": "startup", "startup__company": "Acme", "startup__position": "Engineer"}); ws = Workspace.objects.get()
    Workspace.objects.filter(pk=ws.pk).update(job_state="running", job_progress={"t": int(time.time())})
    r = client_in.post(f"/w/{ws.pk}/research/").json(); assert r["already_running"] and started == []
