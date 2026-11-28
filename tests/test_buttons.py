"""Buttons on phones: a label is never clipped. Every long label has a short form (.bl full / .bs short) or becomes an icon (.ico-m with an aria-label)."""
import glob, re
from .test_planner import setup   # noqa: F401

BTN = re.compile(r'<(a|button)\b([^>]*\bclass="[^"]*\b(?:btn|rm-btn)\b[^"]*"[^>]*)>(.*?)</\1>', re.S)
LIMIT = 17   # a label longer than this does not fit a small phone button

def buttons():
    for f in sorted(glob.glob("core/templates/core/*.html")):
        for m in BTN.finditer(open(f).read()):
            yield f.split("/")[-1], m.group(2), m.group(3)

def visible(inner):
    t = re.sub(r"<span class=\"bs\">.*?</span>", "", inner, flags=re.S)   # the full label, as shown on larger screens
    t = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", "", re.sub(r"<[^>]+>", "", t)); return " ".join(t.split())

def test_every_long_button_label_has_a_short_form_or_becomes_an_icon():
    bad = [(f, visible(i)) for f, a, i in buttons() if len(visible(i)) > LIMIT and 'class="bs"' not in i and "ico-m" not in a
           and not re.search(r"\bw-full\b|rm-ctl", a) and "{% if mode ==" not in i]
    assert not bad, f"labels too long for a phone, add a short form: {bad}"

def test_a_full_label_always_has_something_to_show_on_a_phone():
    for f, a, i in buttons():
        if 'class="bl"' in i:
            assert 'class="bs"' in i or ("ico-m" in a and "data-lucide" in i and "aria-label=" in a), (f, a)   # short label, or an icon with a name for screen readers

def test_icon_only_buttons_have_an_accessible_name():
    for f, a, i in buttons():
        if "ico-m" in a: assert "aria-label=" in a and "title=" in a, (f, a)
        if "rm-ctl" not in a and "<span" not in i and "data-lucide" in i and not visible(i): assert "aria-label=" in a, (f, a)

def test_pages_with_the_new_labels_still_render(client, setup):
    u, ws = setup
    for url in ("/guide/", "/dashboard/", f"/w/{ws.pk}/", "/interviewers/", "/profile/"):
        r = client.get(url); assert r.status_code == 200, (url, r.status_code)
    assert 'class="bs"' in client.get("/guide/").content.decode() and 'class="bs"' in client.get(f"/w/{ws.pk}/").content.decode()
    assert ".btn .bs{display:none}" in open("core/static/css/app.css").read()


# ---- buttons that JavaScript builds (journey bar, planner, story film, wizard) follow the same rule ----
def test_journey_next_up_labels_all_have_a_short_form():
    js = open("core/static/js/journey.js").read()
    found = re.findall(r'label: "([^"]+)"(, short: "([^"]+)")?', js)
    assert len(found) >= 7
    for label, _, short in found:
        assert short and len(short) <= LIMIT, f"journey label needs a short form (17 characters or fewer): {label!r}"
    assert 'class="bl"' in js and 'class="bs"' in js and 'setAttribute("aria-label", c.label)' in js   # the full label stays the accessible name


def test_buttons_written_in_javascript_have_no_long_unshortened_label():
    for f in glob.glob("core/static/js/*.js"):
        for m in re.finditer(r'class="(?:st-)?btn[^"]*"[^>]*>([^<]{18,})<', open(f).read()):
            raise AssertionError(f"{f}: long button label without a short form: {m.group(1)!r}")


def test_the_phone_rules_exist_for_every_button_family():
    css = lambda n: open(f"core/static/css/{n}.css").read()
    assert re.search(r"@media\(max-width:560px\)\{\.btn\{white-space:normal", css("app"))
    assert re.search(r"@media\(max-width:560px\)\{\.jbtn\{white-space:normal", css("journey"))
    assert re.search(r"@media\(max-width:560px\)\{\.wz-btn\{white-space:normal", css("wizard"))
    assert ".st-btn .bs{display:inline}" in css("story") and ".rm-btn .bs{display:inline}" in css("room")
