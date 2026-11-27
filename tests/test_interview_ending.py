"""The panel may end the interview itself, but only for a finished interview or after unprofessional conduct, and never in the middle of a question."""
from core.services import agents
from .test_brain import env, reply, start, answer   # noqa: F401

GOOD = "I built the queue myself and chose Kafka after measuring latency."

def test_a_weak_answer_or_a_model_mistake_never_ends_the_interview(env, monkeypatch):
    w, s, panel = env
    start(s, panel, monkeypatch, [reply(panel, end_reason="finished", text="Thank you, that is all. Goodbye.")]); answer(s, GOOD)
    t, end, _ = agents.next_turn(s, 200)
    assert end is False and t.end_reason == ""

def test_candidate_who_says_they_are_done_ends_it_with_a_closing_that_asks_nothing(env, monkeypatch):
    w, s, panel = env
    start(s, panel, monkeypatch, [reply(panel, end_reason="finished", text="Thank you for your time today. We will be in touch about next steps. Any last questions?")]); answer(s, "Okay, I am done now.")
    t, end, _ = agents.next_turn(s, 200)
    assert end is True and t.end_reason == "finished" and "?" not in t.text

def test_first_unprofessional_moment_is_a_warning_the_second_ends_it(env, monkeypatch):
    w, s, panel = env
    start(s, panel, monkeypatch, [reply(panel, end_reason="unprofessional", text="Let us keep this professional. Back to the design question."),
                                  reply(panel, end_reason="unprofessional", text="I am ending this interview because it has not stayed professional. Thank you. Goodbye.")])
    answer(s, "lol this is a stupid interview")
    t, end, _ = agents.next_turn(s, 100); s.refresh_from_db()
    assert end is False and s.assessment["conduct_warnings"] == 1
    answer(s, "you are an idiot", at=140)
    t, end, _ = agents.next_turn(s, 160); s.refresh_from_db()
    assert end is True and t.end_reason == "unprofessional" and s.assessment["ended_by"] == "unprofessional"

def test_severe_conduct_ends_it_at_once(env, monkeypatch):
    w, s, panel = env
    start(s, panel, monkeypatch, [reply(panel, end_reason="unprofessional", severe=True, text="I am ending this interview because it has not stayed professional. Goodbye.")]); answer(s, "a threat")
    t, end, _ = agents.next_turn(s, 100)
    assert end is True and t.end_reason == "unprofessional"

def test_unprofessional_ending_is_known_to_the_evaluator(env):
    w, s, panel = env; s.assessment = {"ended_by": "unprofessional"}
    assert "ENDED THE INTERVIEW EARLY" in agents.ended_note(s) and agents.ended_note(type("S", (), {"assessment": {}})()) == ""

def test_only_a_clear_short_request_counts_as_wanting_to_stop():
    for t in ("I'm done.", "Okay, I am done now", "Can we stop here?", "let's end the interview", "Please end this interview", "I would like to stop"): assert agents.asks_to_end(t), t
    for t in ("I finished the migration in two weeks and then handed it over to the data team.", "I need to go through the logs first", "We are done with the first phase and moved on to testing",
              "I want to stop the process when the queue is full", "", "I'm finished with university and now I work in payments"): assert not agents.asks_to_end(t), t
