from core.models import *
from core.services import agents
from .test_brain import env, reply, start, answer   # noqa: F401

def test_a_second_interview_knows_what_the_first_one_asked(env, monkeypatch):
    w, s, panel = env
    assert agents.past_context(s) == ""   # nothing earlier: no variety block
    s.status = "done"; s.agenda = [{"owner": panel[0].id, "area": "Scaling the queue", "done": True}]; s.save()
    Turn.objects.create(session=s, speaker=panel[0], role="interviewer", text="Tell me about yourself and your last project?", offset=5)
    Turn.objects.create(session=s, speaker=panel[0], role="interviewer", text="How did you choose Kafka over RabbitMQ?", offset=60)
    s2 = Session.objects.create(workspace=w); p = agents.past_context(s2)
    assert "Scaling the queue" in p and "Tell me about yourself" in p and "never repeat one word for word" in p and "NEW" in p

def test_the_agenda_and_the_next_question_both_get_the_variety_instructions(env, monkeypatch):
    w, s, panel = env; s.status = "done"; s.agenda = [{"owner": panel[0].id, "area": "Scaling the queue", "done": True}]; s.save()
    Turn.objects.create(session=s, speaker=panel[0], role="interviewer", text="How did you choose Kafka over RabbitMQ?", offset=60)
    s2 = Session.objects.create(workspace=w); seen = []
    from core.services import ai
    def fake(prompt, **kw): seen.append(prompt); return ('{"competencies": [], "items": []}', {})
    monkeypatch.setattr(ai, "call", fake); agents.build_agenda(s2, panel)
    assert any("Scaling the queue" in p and "Cover NEW areas" in p and "Inspiration for fresh angles" in p for p in seen)

def test_the_interview_clock_starts_once_and_the_room_clock_wins(client, django_user_model, db):
    from datetime import timedelta
    from django.utils import timezone
    from django.contrib.auth.models import User
    from core.views import _start_clock
    u = User.objects.create_user("c", "c@x.co", "pw"); w = Workspace.objects.create(user=u, title="x"); s = Session.objects.create(workspace=w)
    Session.objects.filter(pk=s.pk).update(started_at=timezone.now() - timedelta(minutes=7)); s.refresh_from_db()   # 7 minutes in the lobby
    s = _start_clock(s); assert (timezone.now() - s.started_at).total_seconds() < 5   # the clock restarts when the room first asks
    first = s.started_at; Session.objects.filter(pk=s.pk).update(started_at=first - timedelta(minutes=3)); s.refresh_from_db()
    s = _start_clock(s); assert (first - s.started_at).total_seconds() > 170   # and only once
