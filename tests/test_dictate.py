"""Speak-to-fill endpoint. Not yet executed in the authoring environment (no Django there)."""
from django.core.files.uploadedfile import SimpleUploadedFile
from core.services import stt
from tests.test_flow import client_in  # noqa: F401

def test_dictate_requires_login_and_returns_transcript(client, client_in, monkeypatch):
    seen = {}
    monkeypatch.setattr(stt, "transcribe", lambda data, mime="", language="en", prompt="": seen.update(prompt=prompt) or {"text": "Python and SQL", "heard": True, "reason": ""})
    r = client_in.post("/stt/", {"audio": SimpleUploadedFile("f.webm", b"x" * 3000, content_type="audio/webm"), "label": "Skills"}).json()
    assert r["text"] == "Python and SQL" and seen["prompt"] == ""
    assert client_in.post("/stt/", {}).status_code == 400
    assert client.post("/stt/", {}).status_code in (302, 403)

def test_forms_load_the_dictation_script(client_in):
    for url in ("/profile/", "/w/new/"):
        assert "js/dictate.js" in client_in.get(url).content.decode()
