"""Thin Groq client. Swap this file (and tts.py) to change AI providers without touching the rest of the app.

Jobs and the Groq models behind them (all overridable in .env):
  text / JSON ........ GROQ_MODEL          (default openai/gpt-oss-120b)
  web research ....... GROQ_RESEARCH_MODEL (default openai/gpt-oss-120b with Groq's built-in browser_search tool;
                       the old groq/compound models were shut down on 2026-09-21)
  camera snapshots ... GROQ_VISION_MODEL   (default qwen/qwen3.8-27b)
  voices ............. GROQ_TTS_MODEL      (see tts.py)
Each model setting can be a comma-separated list: if Groq says the first one no longer exists, or its allowance is used up, the next is tried.
Rate limits (the part that used to fail): Groq limits tokens per model, and keys from one account share that allowance. So the app
  - spreads work over several models (GROQ_MODEL / GROQ_LIGHT_MODEL), small quick jobs on the cheap ones first;
  - reads Groq's own "tokens left" headers and waits a few seconds for a refill instead of sending a request that would be refused;
  - waits out a limit (45 s on screens people are watching, 150 s in background jobs, see patient()) before ever giving up;
  - never makes the new-interview guide wait: it falls back to the normal question order at once.
Groq retires models regularly. Run `python manage.py groq_models` to see what your keys can use right now.
"""
import json, re, threading, time, urllib.request, urllib.error
from django.conf import settings

class AIError(Exception): pass

BASE = "https://api.groq.com/openai/v1"
_rr = {"research": 0, "interview": 0}

def _keys(purpose):
    """Research uses the research keys, everything live (interview, voices, evaluation, camera) uses the interview keys.
    Calls rotate round-robin across the keys of that group, and a key that hits its quota falls over to the next one."""
    if purpose == "factcheck": ks = list(dict.fromkeys(list(getattr(settings, "GROQ_FACTCHECK_KEYS", []) or []) + list(settings.GROQ_RESEARCH_KEYS)))   # one pool: a dedicated fact-check key (if any) and ALL the research keys, so many checks run side by side
    else: ks = list(settings.GROQ_RESEARCH_KEYS if purpose == "research" else settings.GROQ_INTERVIEW_KEYS)
    pn = getattr(_ctx, "pin", None)
    if ks and pn is not None and purpose == "research": r = pn % len(ks); ks = ks[r:] + ks[:r]   # this block of research has its own key
    elif ks:
        _rr[purpose] = (_rr.get(purpose, 0) + 1) % len(ks); r = _rr[purpose]; ks = ks[r:] + ks[:r]
    if settings.GROQ_API_KEY and settings.GROQ_API_KEY not in ks: ks.append(settings.GROQ_API_KEY)
    return ks

class RateLimited(AIError):
    """Every key is cooling down for this model. retry = seconds until the soonest one is free again."""
    def __init__(self, msg, retry): super().__init__(msg); self.retry = retry

MAX_WAIT = 45                                  # longest we will wait for a rate limit to clear before telling the person (live screens)
_ctx = threading.local()                       # background jobs (research, plans) are allowed to be patient: see patient()
_dead = {}                                     # model -> time until which it is skipped because Groq says it no longer exists
_lim = {}                                      # (key, model) -> (tokens left, when they are back) as reported by Groq's own response headers

class patient:
    """`with ai.patient(150):` lets AI calls in this thread wait up to 150 s for a rate limit to clear (background jobs nobody is staring at)."""
    def __init__(self, seconds): self.s = seconds
    def __enter__(self): self.old = getattr(_ctx, "wait", None); _ctx.wait = self.s; return self
    def __exit__(self, *a): _ctx.wait = self.old
class pin:
    """`with ai.pin(2):` research calls in this thread try the 3rd research key first (the others only as a fallback), so each block of research has its own key."""
    def __init__(self, i): self.i = i
    def __enter__(self): self.old = getattr(_ctx, "pin", None); _ctx.pin = self.i; return self
    def __exit__(self, *a): _ctx.pin = self.old

class budget:
    """`with ai.budget(45):` AI calls in this thread give up (raise AIError) once 45 seconds have passed, so one slow search never holds everything up."""
    def __init__(self, seconds): self.s = seconds
    def __enter__(self): self.old = getattr(_ctx, "until", None); _ctx.until = time.time() + self.s; return self
    def __exit__(self, *a): _ctx.until = self.old
class gemini:
    """`with ai.gemini(1):` web searches in this thread are done by Gemini (Google Search) with the 2nd Gemini key instead of Groq's browser search."""
    def __init__(self, i): self.i = i
    def __enter__(self): self.old = getattr(_ctx, "gem", None); _ctx.gem = self.i; return self
    def __exit__(self, *a): _ctx.gem = self.old

def _gemini_search(prompt, system, temperature, keys=None, models=None):
    """One web-grounded research step done by Gemini with its Google Search tool. Returns (text, sources) or raises AIError (the caller then falls back to Groq).
    keys/models default to the backup provider's; the fact checker passes its own."""
    keys = list(keys) if keys is not None else list(getattr(settings, "BACKUP_AI_KEYS", []))
    models = list(models) if models is not None else list(getattr(settings, "BACKUP_AI_MODELS", []))
    if not keys or not models: raise AIError("No Gemini key is set.")
    k = keys[(getattr(_ctx, "gem", None) or 0) % len(keys)]; last = None
    for model in models:
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "tools": [{"google_search": {}}], "generationConfig": {"temperature": temperature}}
        if system: body["systemInstruction"] = {"parts": [{"text": system}]}
        left = _left()
        if left is not None and left <= 1: raise AIError("This step took too long and was skipped.")
        req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", json.dumps(body).encode(), {"Content-Type": "application/json", "x-goog-api-key": k, "User-Agent": "ReadyWise/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=90 if left is None else max(5, min(90, left))) as r: d = json.load(r)
            c = (d.get("candidates") or [{}])[0]; text = "".join(p.get("text", "") for p in (c.get("content") or {}).get("parts", [])).strip()
            src, seen = [], set()
            for g in (c.get("groundingMetadata") or {}).get("groundingChunks", []):
                w = g.get("web") or {}; u, t = w.get("uri", ""), w.get("title", "")
                if "vertexaisearch" in u and "." in t: u = "https://" + t   # Google hides the page behind a redirect; its title is the site's name
                if u.startswith("http") and u not in seen: seen.add(u); src.append({"url": u, "title": t})
            if text: return text, src[:20]
            last = AIError("Gemini returned no answer.")
        except urllib.error.HTTPError as e: last = AIError(f"Gemini returned {e.code}: {_plain(e.read().decode()[:300])}"); _rr["backup_err"] = str(last)[:200]
        except Exception as e: last = AIError(f"Could not reach Gemini: {e}")
    raise last or AIError("Gemini could not answer.")

def _left():
    u = getattr(_ctx, "until", None); return None if u is None else u - time.time()
def current_wait(): return getattr(_ctx, "wait", None)   # so a thread pool can pass the patience on to its workers
def _max_wait(wait=None): return wait if wait is not None else (getattr(_ctx, "wait", None) or MAX_WAIT)
_cool = {}                                     # (key, model) -> time until which Groq said that key is rate limited for that model
_gate = {"research": threading.BoundedSemaphore(12), "interview": threading.BoundedSemaphore(4), "factcheck": threading.BoundedSemaphore(10)}   # at most this many requests in flight at once, whatever the number of threads

def retry_seconds(text, default=8.0):
    """Groq says how long to wait: 'Please try again in 2.5s', '1m5.3s', '350ms' (or a retry-after header)."""
    t = str(text)
    m = re.search(r"try again in\s+(?:(\d+)h)?(?:(\d+)m(?!s))?(?:(\d+(?:\.\d+)?)(ms|s))?", t)
    if m and any(m.groups()[:3]):
        h, mi, sec, unit = m.groups(); v = int(h or 0) * 3600 + int(mi or 0) * 60 + (float(sec) / (1000 if unit == "ms" else 1) if sec else 0)
        if v: return v
    m = re.search(r"retry-after[:=\s]+(\d+(?:\.\d+)?)", t, re.I)
    return float(m.group(1)) if m else default

def _learn(k, model, headers):
    """Groq reports what is left of the per-minute allowance on every answer. Remember it, so the next request waits a few seconds
    for the allowance to refill instead of being sent just to be refused with a 429."""
    if headers is None: return
    try:
        rt, rr = headers.get("x-ratelimit-remaining-tokens"), headers.get("x-ratelimit-remaining-requests")
        if rt is not None: _lim[(k, model)] = (float(rt), time.time() + retry_seconds("try again in " + str(headers.get("x-ratelimit-reset-tokens") or "1s"), 1.0))
        if rr is not None and float(rr) < 1: _cool[(k, model)] = max(_cool.get((k, model), 0), time.time() + retry_seconds("try again in " + str(headers.get("x-ratelimit-reset-requests") or "2s"), 2.0))
    except Exception: pass

def _need(body):
    """A rough count of the tokens this request will use: the text going in plus the room reserved for the answer."""
    return len(json.dumps(body.get("messages", []))) / 3.2 + (body.get("max_completion_tokens") or body.get("max_tokens") or 1500)

def _short_wait(k, model, need):
    """Seconds until this key has room for a request of `need` tokens according to the last headers seen (0 = go ahead)."""
    left, back = _lim.get((k, model), (None, 0)); now = time.time()
    return 0 if left is None or back <= now or left >= need else back - now

def request(path, body, purpose="research", raw=False):
    """POST to Groq. Returns parsed JSON, or the raw bytes when raw=True (used for audio).
    A key that hits a rate limit is put on cooldown for that model (for as long as Groq says) and the next key is used; when every key
    is cooling down this raises RateLimited so the caller can try another model or wait."""
    keys = _keys(purpose)
    if not keys:
        raise AIError("No Groq key is set for " + purpose + ". Add " + ("GROQ_RESEARCH_KEYS" if purpose == "research" else "GROQ_INTERVIEW_KEYS") + " to your .env file and restart the server.")
    model = body.get("model", ""); now = time.time(); need = _need(body) if path.endswith("/chat/completions") else 0
    ready = [k for k in keys if _cool.get((k, model), 0) <= now and not _short_wait(k, model, need)]
    if not ready:
        soon = min(max(_cool.get((k, model), 0) - now, _short_wait(k, model, need)) for k in keys)
        raise RateLimited(f"Groq returned 429: every key is rate limited for {model}. Try again in {soon:.0f}s.", max(0.5, soon))
    last = None
    for k in ready:
        # A real User-Agent matters: Groq's edge rejects the default Python-urllib one with a 403.
        req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": "Bearer " + k, "User-Agent": "ReadyWise/1.0"})
        try:
            with _gate.get(purpose, _gate["interview"]):
                left = _left()
                if left is not None and left <= 1: raise AIError("This step took too long and was skipped.")
                with urllib.request.urlopen(req, timeout=120 if left is None else max(5, min(120, left))) as r:
                    _learn(k, model, getattr(r, "headers", None)); return r.read() if raw else json.load(r)
        except urllib.error.HTTPError as e:
            txt = e.read().decode()[:400]; last = AIError(f"Groq returned {e.code}: {txt}")
            if e.code == 429:
                m = re.search(r"Limit (\d+), Used (\d+), Requested (\d+)", txt)
                if m and int(m.group(3)) > int(m.group(1)):   # asking for more than the per-minute allowance in ONE request: waiting never helps, the request must be smaller
                    raise AIError(f"Groq returned 413: request_too_large. This request needs {m.group(3)} tokens but the limit is {m.group(1)} per minute for {model}.")
                wait = retry_seconds(txt + " retry-after " + str(e.headers.get("retry-after", "")) if e.headers.get("retry-after") else txt)
                _cool[(k, model)] = time.time() + min(wait, 3600) + 0.3; continue
            if e.code not in (401, 500, 502, 503): raise last  # bad request, too large etc.: another key won't help
        except Exception as e:
            last = AIError(f"Could not reach Groq: {e}")
    if last and "429" in str(last):
        soon = min((_cool.get((k, model), 0) for k in keys), default=0) - time.time()
        raise RateLimited(str(last), max(0.5, soon))
    raise last

def _gone(e): m = str(e); return "model_not_found" in m or "model_decommissioned" in m or "does not exist" in m or "decommissioned" in m

def _skip(e):  # reasons to try the next model: retired, rate limited on every key, or the request is too big for this model's limit
    m = str(e); return _gone(e) or "Groq returned 429" in m or "Groq returned 413" in m or "rate_limit" in m or "request_too_large" in m

def _send(body, purpose):
    """One chat request. If Groq rejects JSON mode for this model, retry once without it (parse_json copes with plain text)."""
    try: return request("/chat/completions", body, purpose)
    except AIError as e:
        m = str(e).lower()
        if "response_format" in body and ("json_validate" in m or "response_format" in m or "json mode" in m or "json_object" in m):
            body = {k: v for k, v in body.items() if k != "response_format"}; return request("/chat/completions", body, purpose)
        raise

def _plain(e):
    """The reason in plain words, without Groq's raw JSON."""
    m = str(e); j = re.search(r'"message"\s*:\s*"([^"]+)', m)
    return (j.group(1) if j else m)[:220]

def _backup_chat(messages, temperature, json_mode, extra):
    """Second provider for when every Groq model is rate limited. Any OpenAI-compatible service works (Cerebras, OpenRouter, Google Gemini, Together...).
    Set BACKUP_AI_BASE_URL, BACKUP_AI_KEYS and BACKUP_AI_MODELS in .env. Returns the message dict, or None if no backup is set up or it failed too."""
    base, keys, models = getattr(settings, "BACKUP_AI_BASE_URL", ""), list(getattr(settings, "BACKUP_AI_KEYS", [])), list(getattr(settings, "BACKUP_AI_MODELS", []))
    if not (base and keys and models) or extra.get("tools"): return None
    _rr["backup_err"] = ""
    for model in models:
        for k in keys:
            body = {"model": model, "messages": messages, "temperature": temperature, **{x: v for x, v in extra.items() if x in ("max_completion_tokens", "max_tokens")}}
            if "max_completion_tokens" in body: body["max_tokens"] = body.pop("max_completion_tokens")
            if json_mode: body["response_format"] = {"type": "json_object"}
            for attempt in (0, 1):
                req = urllib.request.Request(base.rstrip("/") + "/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": "Bearer " + k, "User-Agent": "ReadyWise/1.0"})
                try:
                    with urllib.request.urlopen(req, timeout=120) as r: msg = dict(json.load(r)["choices"][0]["message"])
                    msg["content"] = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S).strip()
                    if msg["content"]: return msg
                    break
                except urllib.error.HTTPError as e:
                    txt = e.read().decode()[:300]; _rr["backup_err"] = f"{e.code} {_plain(txt)}"[:200]
                    if e.code == 400 and "response_format" in body and "response_format" in txt + "json": body.pop("response_format", None); continue   # this provider has no JSON mode: parse_json copes with plain text
                    break
                except Exception as e: _rr["backup_err"] = str(e)[:200]; break
    return None

def _chat(models, messages, temperature, json_mode, purpose, wait=None, **extra):
    """`models` is one model id or a list. A retired model falls through to the next one (and is not asked again for an hour); a rate-limited
    one too, and if every model is rate limited we wait for the soonest to clear instead of failing straight away: up to `wait` seconds
    (default 45, or whatever ai.patient() allows for background jobs)."""
    ml = [models] if isinstance(models, str) else list(models)
    if not extra.get("tools") and getattr(settings, "BACKUP_AI_BASE_URL", "") and getattr(settings, "BACKUP_AI_KEYS", []):   # work is shared: every other plain request goes to the backup provider first, so no single provider carries it all
        _rr["spread"] = _rr.get("spread", 0) + 1
        if _rr["spread"] % 2 == 0:
            bk = _backup_chat(messages, temperature, json_mode, extra)
            if bk is not None: return bk
    deadline = time.time() + _max_wait(wait); last = None; limited = False
    while True:
        soonest = None
        if _left() is not None and _left() <= 1: raise AIError("This step took too long and was skipped.")
        for model in ml:
            if _dead.get(model, 0) > time.time(): continue
            gpt = model.startswith("openai/gpt-oss")
            if extra.get("tools") and not gpt: continue                         # Groq's built-in web search only exists on the gpt-oss models
            ex = {k: v for k, v in extra.items() if gpt or k != "reasoning_effort"}   # other model families reject reasoning_effort
            body = {"model": model, "messages": messages, "temperature": temperature, **ex}
            if gpt: body.setdefault("reasoning_effort", "low")  # these models reason first; low keeps interview turns quick and saves tokens
            if json_mode: body["response_format"] = {"type": "json_object"}
            try: data = _send(body, purpose)
            except RateLimited as e: last = e; limited = True; soonest = e.retry if soonest is None else min(soonest, e.retry); continue
            except AIError as e:
                last = e
                if _gone(e): _dead[model] = time.time() + 3600
                if "Groq returned 429" in str(e): limited = True
                if _skip(e): continue
                raise
            try: msg = dict(data["choices"][0]["message"])
            except Exception: raise AIError("Groq returned no answer. Try again.")
            msg["content"] = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S).strip()  # some reasoning models inline their thinking
            return msg
        if soonest is not None and time.time() + soonest <= deadline and (_left() is None or soonest + 1 < _left()): time.sleep(soonest + 0.3); continue
        if soonest is not None or limited:
            bk = _backup_chat(messages, temperature, json_mode, extra)   # Groq's allowance is used up: answer from the backup provider instead of making the person wait
            if bk is not None: return bk
            n = max(1, round(soonest if soonest is not None else 30)); when = f"{n} seconds" if n < 90 else f"about {round(n / 60)} minutes"
            raise AIError(f"The AI is busy right now: Groq's usage limit has been reached for this app ({', '.join(ml)}). It should clear in {when}, so please try again then. If this keeps happening, add keys from DIFFERENT Groq accounts (keys from one account share one allowance) to GROQ_RESEARCH_KEYS or GROQ_INTERVIEW_KEYS in .env, or upgrade the Groq plan.{(' The backup AI also failed: ' + _rr['backup_err'] + '.') if _rr.get('backup_err') else (' No backup AI is set up.' if not getattr(settings, 'BACKUP_AI_BASE_URL', '') else '')} Last error: {_plain(last)}")
        raise AIError(f"No Groq model in your settings could answer ({', '.join(ml)}). If a model was retired, run `python manage.py groq_models` and update .env. Last error: {_plain(last)}")

def list_models(purpose="interview"):
    """Model ids your keys can use right now (GET /models)."""
    last = None
    for k in _keys(purpose):
        req = urllib.request.Request(BASE + "/models", headers={"Authorization": "Bearer " + k, "User-Agent": "ReadyWise/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r: return sorted(m["id"] for m in json.load(r).get("data", []))
        except Exception as e: last = e
    raise AIError(f"Could not list Groq models: {last}")

def _sources(msg):
    """Pull web sources out of a search answer: executed_tools -> search_results, then any citation annotations, then URLs written in the text."""
    out, seen = [], set()
    def add(u, t="", snip=""):
        if isinstance(u, str) and u.startswith("http") and u not in seen:
            seen.add(u); e = {"url": u, "title": t or ""}
            if snip: e["snippet"] = str(snip)[:600]  # the page text the search saw, used when the page itself cannot be fetched
            out.append(e)
    for tool in msg.get("executed_tools") or []:
        for r in ((tool.get("search_results") or {}).get("results") or []): add(r.get("url"), r.get("title"), r.get("content"))
    for an in msg.get("annotations") or []:
        c = an.get("url_citation") or an.get("document_citation") or an; add(c.get("url"), c.get("title"))
    if not out:
        for u in re.findall(r"https?://[^\s)\]>\"']+", msg.get("content") or ""): add(u.rstrip(".,;"))
    return out[:20]

def search(prompt, system=None, temperature=0.3, purpose="research", wait=None):
    """One web-grounded research step. Returns (notes_text, sources). Falls back to the model's own knowledge (no sources) if search is unavailable."""
    if getattr(_ctx, "gem", None) is not None:   # this step belongs to a Gemini key
        try: return _gemini_search(prompt, system, temperature)
        except AIError: pass                       # Gemini could not do it: Groq tries
    msgs = [{"role": "system", "content": system}] if system else []
    msgs.append({"role": "user", "content": prompt})
    try:
        msg = _chat(settings.GROQ_RESEARCH_MODELS, msgs, temperature, False, purpose, wait=min(_max_wait(wait), 20), tools=[{"type": "browser_search"}], reasoning_effort="low")  # browser_search runs server-side and cannot be combined with JSON mode; if the search models are busy for more than ~20 s, move on rather than stall the whole run
    except AIError:  # search unavailable right now: answer from the model's own knowledge (no web sources) rather than fail
        msg = _chat(settings.GROQ_MODELS, msgs, temperature, False, purpose)
    return msg.get("content") or "", _sources(msg)

def factcheck_search(prompt, system=None, wait=8):
    """Web-grounded lookup for the live fact checker. Groq browser search on the pooled keys goes first (quick, and every research key can work at once);
    Gemini + Google Search is the fallback, or goes first when FACTCHECK_ENGINE=gemini. Returns (text, sources). Raises AIError when nothing answered in time."""
    gk = list(getattr(settings, "FACTCHECK_GEMINI_KEYS", []) or [])
    def gem(): return _gemini_search(prompt, system, 0.1, keys=gk, models=list(getattr(settings, "FACTCHECK_GEMINI_MODELS", []) or ["gemini-2.5-flash"]))
    def groq():
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        msg = _chat(settings.GROQ_RESEARCH_MODELS, msgs, 0.1, False, "factcheck", wait=min(wait, 6), tools=[{"type": "browser_search"}], reasoning_effort="low")
        return msg.get("content") or "", _sources(msg)
    order = [gem, groq] if (gk and getattr(settings, "FACTCHECK_ENGINE", "groq") == "gemini") else [groq] + ([gem] if gk else [])
    last = None
    for f in order:
        try: return f()
        except AIError as e: last = e
    raise last or AIError("The fact check could not be done.")

_search = search  # call() has a parameter named `search`, so keep an alias to the function

def call(prompt, system=None, json_mode=False, search=False, temperature=0.8, images=None, purpose="research", max_tokens=None, light=False, wait=None, effort=None, models=None):
    """Returns (text, sources). effort="low"|"medium"|"high" sets how long a reasoning model thinks (ignored by other model families): high for assessment decisions, low for routine turns. With search=True the answer is grounded by Groq's built-in web search and `sources` lists the pages used.
    light=True is for small quick jobs: the cheaper models are tried first. wait=N caps how long a rate limit may be waited out (N seconds)."""
    if search:
        text, sources = _search(prompt, system, temperature, purpose, wait)
        try: parse_json(text)
        except AIError:  # the search answered in prose: have the normal model turn it into the JSON that was asked for
            fix = [{"role": "user", "content": "Convert the research notes below into the JSON requested by the original instructions. Return JSON only. Keep every claim and source as written; do not add facts.\n\nORIGINAL INSTRUCTIONS:\n" + prompt[:6000] + "\n\nRESEARCH NOTES:\n" + text[:12000]}]
            text = _chat(settings.GROQ_MODELS, fix, 0.1, True, purpose, wait=wait).get("content") or ""
        return text, sources
    msgs = [{"role": "system", "content": system}] if system else []
    if images:
        content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + im}} for im in images[:5]]  # Groq accepts up to 5 images per request
        msgs.append({"role": "user", "content": content})
        return (_chat(settings.GROQ_VISION_MODELS, msgs, temperature, json_mode, purpose, wait=wait).get("content") or ""), []
    msgs.append({"role": "user", "content": prompt})
    extra = {"max_completion_tokens": max_tokens} if max_tokens else {}
    if effort in ("low", "medium", "high"): extra["reasoning_effort"] = effort   # reasoning models spend part of the budget thinking; a long JSON answer needs room or it is cut off mid-way
    models = list(models) if models else (getattr(settings, "GROQ_LIGHT_MODELS", None) or settings.GROQ_MODELS if light else settings.GROQ_MODELS)
    return (_chat(models, msgs, temperature, json_mode, purpose, wait=wait, **extra).get("content") or ""), []

def repair_json(t):
    """Close a JSON text that was cut off (token limit) or has trailing commas: end the open string, drop a dangling key or comma, close brackets in order."""
    stack, in_s, esc, out = [], False, False, []
    for ch in t:
        out.append(ch)
        if in_s:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == '"': in_s = False
            continue
        if ch == '"': in_s = True
        elif ch in "{[": stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack: stack.pop()
    s = "".join(out)
    if in_s: s += '"'
    s = re.sub(r',\s*$', "", s)
    s = re.sub(r',\s*"[^"]*"\s*:\s*$', "", s)            # a key whose value never arrived
    s = re.sub(r'"[^"]*"\s*:\s*$', "", s)
    s = re.sub(r',\s*$', "", s)
    return s + "".join(reversed(stack))

def parse_json(text):
    t = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    pairs = sorted((("{", "}"), ("[", "]")), key=lambda p: (t.find(p[0]) if t.find(p[0]) != -1 else 10**9))   # the outermost bracket first, so a cut-off object is not mistaken for one of its own lists
    for opener, closer in pairs[:1]:
        a, b = t.find(opener), t.rfind(closer)
        if a != -1 and b > a:
            try: return json.loads(t[a:b + 1])
            except Exception: pass
    a = min([x for x in (t.find("{"), t.find("[")) if x != -1] or [-1])
    if a != -1:   # truncated answer: keep everything that was written, close what was left open
        for cut in (t[a:], re.sub(r',\s*[^,\]}]*$', "", t[a:])):
            try:
                d = json.loads(repair_json(cut))
                if d: return d
            except Exception: pass
    raise AIError("The AI answer could not be read. Try again.")
