"""The AI answer parser: a long answer that is cut off (token limit) must be repaired, not thrown away.
This is what caused "The AI answer could not be read" at the end of research. Runs without Django installed."""
import importlib.util, json, sys, types
if importlib.util.find_spec("django") is None:
    dj = types.ModuleType("django"); conf = types.ModuleType("django.conf"); conf.settings = types.SimpleNamespace(); dj.conf = conf; sys.modules.update({"django": dj, "django.conf": conf})
from core.services import ai

FULL = json.dumps({"summary": "x", "topics": [{"label": "a", "importance": 5}, {"label": "b", "importance": 6}], "sections": [{"key": "k", "items": [{"point": "hello world"}]}]})

def test_complete_fenced_and_wrapped_answers():
    for t in (FULL, "```json\n" + FULL + "\n```", "Sure! " + FULL + " Hope that helps"): assert ai.parse_json(t)["summary"] == "x"

def test_cut_off_answers_keep_what_was_written():
    for t in (FULL[:-35], FULL[:-8], FULL[:FULL.index('"b"') - 3], FULL[:FULL.index('"importance": 6') + 8]):
        d = ai.parse_json(t); assert isinstance(d, dict) and d["summary"] == "x" and len(d["topics"]) >= 1

def test_garbage_still_raises_and_lists_still_parse():
    assert ai.parse_json("[1,2,3]") == [1, 2, 3]
    try: ai.parse_json("no json at all"); assert False
    except ai.AIError: pass
