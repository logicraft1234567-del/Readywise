import pytest
pw = pytest.importorskip("playwright.sync_api")  # pip install playwright && playwright install chromium, then run the server

def test_landing_loads():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch(); page = b.new_page(); page.goto("http://127.0.0.1:8000/", timeout=5000)
        except Exception as e:
            pytest.skip(f"needs a Chromium install and a running server: {str(e)[:60]}")
        assert "ReadyWise" in page.title(); page.click("text=Start free"); assert "/register" in page.url; b.close()
