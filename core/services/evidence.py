"""Evidence gathering beyond plain web search: read community pages and Reddit threads, and read YouTube transcripts.
Everything here is best-effort. Sites block bots and cloud servers, so every function returns an empty result instead of raising,
and the research falls back to the search snippets. Only URLs that came out of a search are ever fetched, private networks are refused,
robots.txt is respected, and nothing is stored except the short notes the research agent writes from it."""
import html, ipaddress, json, os, re, socket, urllib.error, urllib.parse, urllib.request, urllib.robotparser
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

UA = "Mozilla/5.0 (compatible; ReadyWiseBot/1.0; interview-preparation research)"
OFFICIAL_SUFFIXES = (".gov", ".edu", ".ac.uk", ".gov.uk", ".gov.ng", ".gov.au", ".gc.ca", ".int", ".mil", ".europa.eu", ".edu.au", ".ac.za", ".gov.in", ".edu.ng")
COMMUNITY = ("reddit.com", "glassdoor.", "teamblind.com", "indeed.com", "quora.com", "thestudentroom.co.uk", "linkedin.com", "medium.com", "dev.to", "news.ycombinator.com",
             "levels.fyi", "leetcode.com", "collegeconfidential", "wallstreetoasis", "nairaland.com", "youtube.com", "youtu.be", "tiktok.com", "facebook.com", "x.com", "twitter.com",
             "substack.com", "forum", "discuss", "community", "visajourney.com", "trustpilot.com", "ambitionbox.com", "careerbliss.com", "prepinsta.com")
NO_FETCH = ("linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com", "tiktok.com", "youtube.com", "youtu.be", "glassdoor.", "indeed.com", "teamblind.com")  # login walls, or handled separately
_robots = {}

def _host(url):
    try: return (urlparse(url).netloc or "").lower().split("@")[-1].split(":")[0].replace("www.", "")
    except Exception: return ""

def _match(h, c):
    """Full domains (reddit.com) match the domain and its subdomains only, so netflix.com is not mistaken for x.com. Fragments (glassdoor., forum) match anywhere."""
    c2 = c.strip(".")
    return (h == c2 or h.endswith("." + c2)) if "." in c.strip(".") and not c.endswith(".") else c2 in h

def tier(url, company=""):
    """official: government, university or the organisation's own site. community: forums, reviews, social, video. web: everything else (news, blogs)."""
    h = _host(url)
    slug = re.sub(r"[^a-z0-9]", "", (company or "").lower())
    if any(h.endswith(x) or h == x[1:] for x in OFFICIAL_SUFFIXES) or (len(slug) >= 4 and slug in re.sub(r"[^a-z0-9]", "", h)): return "official"
    if any(_match(h, c) for c in COMMUNITY): return "community"
    return "web"

_HINTS = ("reddit", "glassdoor", "teamblind", "blind.com", "quora", "studentroom", "linkedin", "youtube", "youtu.be", "forum", "anonymous", "candidate report", "candidate-reported",
          "nairaland", "levels.fyi", "indeed.com", "medium.com", "tiktok", "twitter", "facebook", "trustpilot", "ambitionbox", "visajourney")

def is_community_hint(text):
    """True if a source note mentions a forum, review site or video, so a finding based on it can never count as confirmed."""
    t = (text or "").lower(); return any(h in t for h in _HINTS)

# ---------- YouTube ----------
_VID = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:[^\s\"'<>]*&)?v=|shorts/|embed/|live/))([A-Za-z0-9_-]{11})")

def video_ids(texts):
    """Video ids in order of first appearance, from any mix of URLs and text."""
    out = []
    for t in texts:
        for m in _VID.finditer(t or ""):
            if m.group(1) not in out: out.append(m.group(1))
    return out

def youtube_search(query, key, n=10, years=4):
    """YouTube Data API v3 search. Returns (videos, error): videos is [{id, title, channel, published}] in relevance order, error is a short message or None.
    Costs 100 quota units per call (the free quota is 10,000 a day)."""
    after = (datetime.now(timezone.utc) - timedelta(days=365 * years)).strftime("%Y-%m-%dT%H:%M:%SZ")
    qs = urllib.parse.urlencode({"part": "snippet", "type": "video", "q": query, "maxResults": n, "relevanceLanguage": "en", "safeSearch": "moderate", "publishedAfter": after, "key": key})
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/search?" + qs, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r: data = json.load(r)
    except urllib.error.HTTPError as e:
        try: msg = json.loads(e.read().decode()).get("error", {}).get("message", "")
        except Exception: msg = ""
        return None, f"YouTube API {e.code}: {msg}"[:200].replace(key, "***")
    except Exception as e: return None, ("YouTube API unreachable: " + str(e))[:160].replace(key, "***")
    out = []
    for it in data.get("items", []):
        vid, sn = (it.get("id") or {}).get("videoId"), it.get("snippet") or {}
        if vid: out.append({"id": vid, "title": html.unescape(sn.get("title", "")), "channel": html.unescape(sn.get("channelTitle", "")), "published": (sn.get("publishedAt") or "")[:10]})
    return out, None

def transcript(video_id, langs=("en", "en-US", "en-GB")):
    """Captions as [(seconds, text)] or None when unavailable (no captions, blocked, or youtube-transcript-api not installed)."""
    try: from youtube_transcript_api import YouTubeTranscriptApi
    except Exception: return None
    try:
        if hasattr(YouTubeTranscriptApi, "get_transcript"): raw = YouTubeTranscriptApi.get_transcript(video_id, languages=list(langs))  # versions before 1.0
        else:
            proxy = os.environ.get("YOUTUBE_PROXY", "").strip(); kw = {}
            if proxy:
                from youtube_transcript_api.proxies import GenericProxyConfig
                kw["proxy_config"] = GenericProxyConfig(http_url=proxy, https_url=proxy)
            fetched = YouTubeTranscriptApi(**kw).fetch(video_id, languages=list(langs))
            raw = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else [{"start": x.start, "text": x.text} for x in fetched]
        rows = [(float(r["start"]), re.sub(r"\s+", " ", str(r["text"])).strip()) for r in raw if str(r.get("text", "")).strip()]
        return rows or None
    except Exception: return None

def transcript_text(rows, limit=9000, window=40):
    """Readable text with a [mm:ss] marker about every 40 seconds. Long videos keep the start and the end, where tips and conclusions usually are."""
    lines, cur, t0 = [], [], None
    for start, text in rows:
        if t0 is None or start - t0 >= window:
            if cur: lines.append(f"[{int(t0) // 60:02d}:{int(t0) % 60:02d}] " + " ".join(cur))
            cur, t0 = [], start
        cur.append(text)
    if cur: lines.append(f"[{int(t0) // 60:02d}:{int(t0) % 60:02d}] " + " ".join(cur))
    full = "\n".join(lines)
    if len(full) <= limit: return full
    head = int(limit * 0.65); return full[:head] + "\n[...]\n" + full[-(limit - head):]

# ---------- safe page fetching ----------
def _public(host):
    try: infos = socket.getaddrinfo(host, None)
    except Exception: return False
    for i in infos:
        ip = ipaddress.ip_address(i[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified: return False
    return True

class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlparse(newurl)
        if u.scheme not in ("http", "https") or not _public(u.hostname or ""): raise urllib.error.URLError("redirect to a non-public address refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def _get(url, accept="text/html,application/xhtml+xml", max_bytes=400_000, timeout=12):
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname or not _public(u.hostname): return None
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en"})
    try:
        with urllib.request.build_opener(_Redirect).open(req, timeout=timeout) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            if not any(k in ctype for k in ("html", "json", "text")): return None
            raw = r.read(max_bytes)
        m = re.search(r"charset=([\w-]+)", ctype); return raw.decode(m.group(1) if m else "utf-8", "replace")
    except Exception: return None

def _robots_ok(url):
    u = urlparse(url); base = f"{u.scheme}://{u.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser(); txt = _get(base + "/robots.txt", "text/plain", 100_000, 6)
        try: rp.parse((txt or "").splitlines()); _robots[base] = rp if txt else None
        except Exception: _robots[base] = None
    rp = _robots[base]; return True if rp is None else rp.can_fetch(UA, url)

class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "iframe", "button"}
    BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr", "blockquote", "section", "article"}
    def __init__(self): super().__init__(); self.out, self.skip = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP: self.skip += 1
        elif tag in self.BLOCK: self.out.append("\n")
    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip: self.skip -= 1
        elif tag in self.BLOCK: self.out.append("\n")
    def handle_data(self, data):
        if not self.skip: self.out.append(data)

def html_to_text(html, limit=6000):
    p = _Text()
    try: p.feed(html)
    except Exception: pass
    lines = [re.sub(r"\s+", " ", l).strip() for l in "".join(p.out).split("\n")]
    return "\n".join(l for l in lines if len(l) >= 25)[:limit]  # drop menus and one-word fragments

def reddit_text(url, limit=6000):
    """A Reddit thread as text: the post and its highest-scored comments."""
    m = re.search(r"reddit\.com(/r/[^/\s?#]+/comments/[^/\s?#]+)", url)
    if not m: return ""
    raw = _get("https://www.reddit.com" + m.group(1) + ".json?limit=40&depth=2&raw_json=1", "application/json")
    try:
        data = json.loads(raw); post = data[0]["data"]["children"][0]["data"]; found = []
        def walk(nodes, depth=0):
            for n in nodes:
                d = n.get("data", {})
                if n.get("kind") == "t1" and d.get("body"): found.append((d.get("score") or 0, d["body"]))
                rep = d.get("replies")
                if depth < 2 and isinstance(rep, dict): walk(rep.get("data", {}).get("children", []), depth + 1)
        walk(data[1]["data"]["children"]); found.sort(key=lambda x: -x[0])
        top = "\n".join(f"- ({s} votes) {re.sub(chr(10) + '+', ' ', b)[:420]}" for s, b in found[:12])
        return (f"POST: {post.get('title', '')}\n{(post.get('selftext') or '')[:1500]}\nTOP COMMENTS:\n{top}")[:limit]
    except Exception: return ""

def fetch_text(url, limit=6000):
    """Readable text of a public page, or '' if it cannot or should not be fetched."""
    h = _host(url)
    if not h: return ""
    if "reddit.com" in h:
        t = reddit_text(url, limit)
        if t: return t
        url = re.sub(r"//(www\.)?reddit\.com", "//old.reddit.com", url)  # the plain-HTML version, if the JSON one is blocked
    elif any(_match(h, n) for n in NO_FETCH): return ""
    if not _robots_ok(url): return ""
    html = _get(url)
    return html_to_text(html, limit) if html else ""
