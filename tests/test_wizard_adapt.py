"""Adaptive creation questions: the model proposes, the code disposes. Runs without Django installed (ai.call is faked)."""
import importlib.util, json, sys, types
if importlib.util.find_spec("django") is None:
    dj = types.ModuleType("django"); conf = types.ModuleType("django.conf"); conf.settings = types.SimpleNamespace(); dj.conf = conf; sys.modules.update({"django": dj, "django.conf": conf})
import pytest
from core.services import ai, wizard, kinds

@pytest.fixture(autouse=True)
def _restore_ai(monkeypatch): monkeypatch.setattr(ai, "call", ai.call)   # these tests replace ai.call by assignment; this puts it back afterwards

KEYS = [f["key"] for f in kinds.profile("startup")["fields"]]
def fake(monkeypatch_or_none, reply):
    ai.call = lambda *a, **k: (reply if isinstance(reply, str) else json.dumps(reply), [])

def run(reply, remaining=None, custom=None, answers=None):
    wizard._cache.clear(); fake(None, reply); return wizard.adapt("startup", answers or {"company": "Acme", "position": "Backend engineer"}, remaining or ["position"] + KEYS, custom or [])

def test_skips_reorders_rewrites_and_adds_a_followup():
    r = run({"order": ["stack", "why", "ghost_key"], "rewrite": {"stack": "Which backend technologies have you used at work?"}, "ask": [{"q": "You mentioned a career change. What drove it?", "short": "Career change", "type": "textarea", "ph": "e.g. moved from finance"}], "say": "Backend, nice."})
    assert [k for k in r["order"] if k in KEYS][:2] == ["stack", "why"] and "ghost_key" not in r["order"]
    assert r["rewrite"]["stack"].startswith("Which backend") and r["ask"][0]["key"] == "x1" and r["ask"][0]["type"] == "textarea" and r["say"] == "Backend, nice."

def test_required_questions_can_never_be_skipped():
    r = run({"order": []}); assert "position" in r["order"] and all(k in r["order"] for k in KEYS if next(f for f in kinds.profile("startup")["fields"] if f["key"] == k)["req"])

def test_followups_are_capped_deduplicated_and_validated():
    ask = [{"q": "Question number one here?", "type": "text"}, {"q": "Question number two here?", "type": "select", "options": ["only one"]}, {"q": "Question number three?", "type": "text"}]
    r = run({"order": ["why"], "ask": ask}); assert len(r["ask"]) == 2 and r["ask"][1]["type"] == "text"   # max 2 per step; a select needs two options
    custom = [{"key": f"x{i}", "q": f"Earlier {i}?", "answered": True} for i in range(1, 6)]
    r = run({"order": ["why"], "ask": ask}, custom=custom); assert len(r["ask"]) == 1 and r["ask"][0]["key"] == "x6"     # 6 follow-ups over the whole flow
    r = run({"order": ["why"], "ask": [{"q": "Earlier 1?"}]}, custom=custom[:1]); assert r["ask"] == []                    # same question is not asked twice

def test_a_model_failure_never_breaks_the_form():
    def boom(*a, **k): raise ai.AIError("rate limit")
    ai.call = boom; r = wizard.adapt("startup", {}, ["position", "why"], []); assert r["order"] == ["position", "why"] and r["fallback"] and r["ask"] == []
    for bad in ("not json", "[]", '{"order": "nonsense", "ask": 5}'):
        r = run(bad); assert isinstance(r["order"], list) and r["ask"] == []

def test_company_and_position_are_always_kept():
    r = run({"order": ["why"]}, remaining=["company", "position", "why"]); assert r["order"][:0] == [] and {"company", "position"} <= set(r["order"])

def test_followups_never_repeat_the_catalogue_or_ask_for_a_document():
    ask = [{"q": "Could you paste your CV for me?", "type": "text"},                      # the CV has its own step
           {"q": "Why do you want to join this startup, and why now?", "type": "text"},   # reworded catalogue question ("why")
           {"q": "Which database have you scaled the furthest?", "type": "text"}]         # genuinely new
    r = run({"order": ["why"], "ask": ask}); assert [a["q"] for a in r["ask"]] == ["Which database have you scaled the furthest?"]

def test_two_followups_that_say_the_same_thing_become_one():
    r = run({"order": ["why"], "ask": [{"q": "Which database have you scaled the furthest?", "type": "text"}, {"q": "What is the furthest you have scaled a database?", "type": "text"}]})
    assert len(r["ask"]) == 1
