import pytest


@pytest.fixture(autouse=True)
def _inline_research(settings, monkeypatch):
    settings.RESEARCH_IN_THREAD = False  # tests run research inline so results are ready when the request returns
    from core.services import evidence
    monkeypatch.setattr(evidence, "fetch_text", lambda url, limit=6000: "")  # no real web pages or Reddit threads in tests
    monkeypatch.setattr(evidence, "transcript", lambda vid, langs=(): None)  # no real YouTube captions in tests
    monkeypatch.setattr(evidence, "youtube_search", lambda q, key, n=10, years=4: (None, "disabled in tests"))  # no real YouTube API calls in tests
    settings.YOUTUBE_API_KEY = ""
