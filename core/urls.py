from django.urls import path
from . import views as v
urlpatterns = [
 path("", v.landing, name="landing"), path("guide/", v.guide, name="guide"), path("contact/", v.contact, name="contact"),
 path("register/", v.register, name="register"), path("login/", v.login_view, name="login"), path("logout/", v.logout_view, name="logout"),
 path("dashboard/", v.dashboard, name="dashboard"), path("analytics/", v.analytics, name="analytics"), path("search/", v.search, name="search"), path("tasks/", v.tasks_page, name="tasks"), path("profile/", v.profile, name="profile"), path("welcome/", v.welcome, name="welcome"),
 path("w/new/", v.workspace_new, name="ws_new"), path("w/<int:pk>/", v.workspace, name="ws"),
 path("w/<int:pk>/research/", v.do_research, name="ws_research"), path("w/<int:pk>/allocate/", v.do_allocate, name="ws_allocate"),
 path("w/<int:pk>/plan/", v.do_plan, name="ws_plan"), path("w/<int:pk>/adjust/", v.do_adjust, name="ws_adjust"),
 path("w/<int:pk>/delete/", v.ws_delete, name="ws_delete"), path("w/<int:pk>/docs/", v.ws_docs, name="ws_docs"), path("task/<int:pk>/toggle/", v.toggle_task, name="task_toggle"), path("calendar/", v.calendar_page, name="calendar"), path("notifications/", v.notifications, name="notifications"),
 path("w/<int:pk>/session/", v.new_session, name="session_new"),
 path("room/<int:pk>/", v.room, name="room"), path("room/<int:pk>/turn/", v.room_turn, name="room_turn"),
 path("room/<int:pk>/finish/", v.room_finish, name="room_finish"), path("stt/", v.dictate, name="dictate"), path("w/adapt/", v.wizard_adapt, name="wizard_adapt"), path("w/doc/", v.wizard_doc, name="wizard_doc"), path("w/docs/", v.wizard_docs, name="wizard_docs"), path("room/<int:pk>/stt/", v.room_stt, name="room_stt"), path("room/<int:pk>/recording/", v.room_recording, name="room_rec"),
 path("report/<int:pk>/", v.report, name="report"),
 path("w/<int:pk>/job/", v.ws_job, name="ws_job"), path("room/<int:pk>/job/", v.room_job, name="room_job"), path("room/<int:pk>/tts/", v.room_tts, name="room_tts"), path("room/<int:pk>/live/token/", v.room_live_token, name="room_live_token"), path("room/<int:pk>/live/turns/", v.room_live_turns, name="room_live_turns"), path("room/<int:pk>/live/facts/", v.room_live_facts, name="room_live_facts"), path("room/<int:pk>/live/challenge/", v.room_live_challenge, name="room_live_challenge"),
 path("w/<int:pk>/plan.ics", v.plan_ics, name="plan_ics"), path("w/<int:pk>/readiness/", v.readiness_page, name="readiness"),
 path("interviewers/<int:pk>/publish/", v.interviewer_publish, name="iv_publish"), path("interviewers/<int:pk>/clone/", v.interviewer_clone, name="iv_clone"),
 path("interviewers/", v.interviewers, name="interviewers"), path("interviewers/new/", v.interviewer_new, name="interviewer_new"),
]
