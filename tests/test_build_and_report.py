from core.models import *
from core.services import agents
from .test_planner import setup   # noqa: F401

def sess(ws, research=None, **kw):
    ws.research = research or {}; ws.save(); return Session.objects.create(workspace=ws, **kw)

def test_coding_task_needs_research_evidence_otherwise_the_candidate_is_asked(client, setup):
    u, ws = setup; ws.kind = "employment"; ws.position = "Backend Engineer"; ws.save()
    assert agents.build_plan(sess(ws)) == "ask"   # nothing known: ask, never assume
    assert agents.build_plan(sess(ws, {"assessment": {"build": "coding", "status": "inferred"}})) == "ask"   # a guess is not verification
    assert agents.build_plan(sess(ws, {"assessment": {"build": "coding", "status": "confirmed"}})) == "code"
    assert agents.build_plan(sess(ws, {"assessment": {"build": "coding", "status": "candidate_reported"}})) == "code"
    assert agents.build_plan(sess(ws, {"assessment": {"build": "none", "status": "confirmed"}})) is None
    assert agents.build_plan(sess(ws, {"assessment": {"build": "unknown", "status": "inferred"}})) == "ask"
    ws.position = "Marketing Manager"; ws.title = "Marketing Manager at Acme"; ws.save(); assert agents.build_plan(sess(ws)) is None   # not a software role: no coding question at all

def test_the_answer_to_the_question_is_a_yes_only_when_it_is_clear(client, setup):
    for t in ("yes please", "Sure, why not", "yeah let's do it"): assert agents.wants_build(t)
    for t in ("no thanks", "I'd rather not", "um", "", "yes... actually no, skip it"): assert not agents.wants_build(t)

def test_choice_is_remembered(client, setup):
    u, ws = setup; ws.kind = "employment"; ws.position = "Data Engineer"; ws.save(); s = sess(ws)
    agents.set_build_choice(s, "asked"); assert agents.build_plan(s) == "asked"
    agents.set_build_choice(s, "yes"); assert agents.build_plan(s) == "code"
    agents.set_build_choice(s, "no"); assert agents.build_plan(s) is None

def test_report_leads_with_plain_language_and_keeps_detail_collapsed(client, setup):
    u, ws = setup; s = Session.objects.create(workspace=ws, status="done")
    plain = agents.clean_plain({"headline": "You explained well but gave no numbers.", "good": [{"title": "Clear structure", "detail": "You answered in order."}], "next_steps": ["Write three numbers."],
                                "priorities": [{"title": "Give a real number", "what_happened": "You said it was faster.", "why_it_matters": "Panels cannot judge it.", "try_this": "Say 'cut load time from 4s to 1.5s'."}]})
    Evaluation.objects.create(session=s, overall=62, verdict="Borderline", summary="Ok. More.", scores={"technical": 70}, plain=plain)
    h = client.get(f"/report/{s.pk}/").content.decode()
    assert "What to improve first" in h and "Give a real number" in h and "Try this" in h and "What went well" in h and "Your next 3 practice steps" in h and "More detail" in h and "<details" in h
    old = Session.objects.create(workspace=ws, status="done"); Evaluation.objects.create(session=old, overall=40, verdict="Weak", summary="Weak answers. Bad.", improvements=["Be concrete"], strengths=["Polite"])
    h = client.get(f"/report/{old.pk}/").content.decode(); assert "Be concrete" in h and "Weak answers." in h   # older reports still render
