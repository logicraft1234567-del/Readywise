"""New-interview flow endpoints. Needs Django (not run in the authoring environment)."""
import json
from core.models import Workspace
from core.services import ai
from tests.test_flow import client_in, post_json  # noqa: F401

def test_adapt_endpoint_returns_a_plan_and_survives_ai_failure(client_in, monkeypatch):
    monkeypatch.setattr(ai, "call", lambda *a, **k: (json.dumps({"order": ["why"], "ask": [{"q": "What drove the career change?", "short": "Career change"}], "say": "Interesting."}), []))
    r = post_json(client_in, "/w/adapt/", {"kind": "startup", "answers": {"company": "Acme"}, "remaining": ["position", "why"], "custom": []}).json()
    assert r["ask"][0]["key"] == "x1" and "position" in r["order"]
    def boom(*a, **k): raise ai.AIError("rate limit")
    monkeypatch.setattr(ai, "call", boom); r = post_json(client_in, "/w/adapt/", {"kind": "startup", "answers": {}, "remaining": ["position"], "custom": []}).json()
    assert r["fallback"] and r["order"] == ["position"]
    assert post_json(client_in, "/w/adapt/", {"kind": "nope"}).status_code == 400

def test_followup_answers_are_saved_with_their_question(client_in):
    client_in.post("/w/new/", {"kind": "startup", "startup__company": "Acme", "startup__position": "Engineer", "startup__x1": "Burnout in finance", "startup__xq1": "Career change", "startup__x2": "ignored without a label"})
    d = Workspace.objects.get().details; assert d["Career change"] == "Burnout in finance" and "ignored" not in json.dumps(d)
