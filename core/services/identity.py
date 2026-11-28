"""Company and project identity resolution. Pure Python: no database, no network, no AI, so every rule here is unit-tested.

WHY THIS EXISTS
Two businesses sharing a name are not the same business. Before this module, research and the live fact-check searched the web for a NAME ("Orbit"),
took whatever the first results said (another company's pricing, another company's founders) and used it to challenge what the candidate said about their own
project. A candidate was marked down for "lying" about being the founder of a hackathon project because a commercial company with the same name had different
founders. That is READYWISE's error, not the candidate's, and it must never lower a score.

HOW IT WORKS
1. build_profile() collects every identifying signal the candidate supplied: names, domains, repository, hackathon submission link, product description, founders.
2. status() says whether the identity is VERIFIED (a hard signal such as a domain, repository or submission link, plus a second independent signal) or UNVERIFIED.
3. match_source() compares one researched source against the profile and answers "same", "different" or "unknown". A shared NAME is never a signal.
4. Ownership claims ("I am the founder") are only ever challengeable when the source is the SAME verified entity and it directly names other owners.
   Otherwise clarification_question() gives the panel a relevant question to ask instead of an accusation."""
import re
from urllib.parse import urlparse

# What the thing being discussed is, relative to the candidate.
OWN_STARTUP, HACKATHON_PROJECT, ESTABLISHED_COMPANY, UNRELATED_SAME_NAME, SIMILAR_PRODUCT, RENAMED, UNKNOWN_ENTITY = (
    "own_startup", "hackathon_project", "established_company", "unrelated_same_name", "similar_product", "renamed_company", "unknown")
ENTITY_TYPES = (OWN_STARTUP, HACKATHON_PROJECT, ESTABLISHED_COMPANY, UNRELATED_SAME_NAME, SIMILAR_PRODUCT, RENAMED, UNKNOWN_ENTITY)

VERIFIED, UNVERIFIED = "verified", "unverified"
SAME, DIFFERENT, UNKNOWN = "same", "different", "unknown"

ROLES = ("founder", "co_founder", "project_creator", "team_leader", "developer", "contributor", "employee", "unknown")
ROLE_LABEL = {"founder": "Founder", "co_founder": "Co-founder", "project_creator": "Project creator", "team_leader": "Hackathon team leader",
              "developer": "Developer", "contributor": "Contributor", "employee": "Employee", "unknown": "Unclear role"}

# Kinds of interview where the candidate presents their OWN project or business. Everything else (jobs, programmes) is about an organisation they are applying to.
OWNER_KINDS = ("hackathon", "pitch")
# Hosts that hold many different projects: sharing one of these hosts says nothing about identity (only the full repository or submission path does).
SHARED_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "devpost.com", "devfolio.co", "dorahacks.io", "lablab.ai", "notion.site", "notion.so", "docs.google.com",
                "drive.google.com", "figma.com", "youtube.com", "youtu.be", "linkedin.com", "medium.com", "vercel.app", "netlify.app", "herokuapp.com", "onrender.com",
                "pages.dev", "web.app", "firebaseapp.com", "streamlit.app", "huggingface.co", "replit.app", "glitch.me")
# Hosts that are not a company's own site, so a page on them is not a "commercial company" page.
_NOT_COMMERCIAL = SHARED_HOSTS + ("wikipedia.org", "reddit.com", "news.ycombinator.com", "producthunt.com", "crunchbase.com", "pitchbook.com", "pmc.ncbi.nlm.nih.gov", "arxiv.org")

_URL = re.compile(r"https?://[^\s<>\"'()\]]+", re.I)
_BARE_DOMAIN = re.compile(r"\b((?:[a-z0-9-]+\.)+(?:com|io|so|ai|app|dev|co|org|net|love|xyz|tech|cloud|me|edu|gov|ng|uk|us|in))\b(?:/[^\s]*)?", re.I)
_STOP = set("a an the and or of for to in on at by with from is are was were be been it its this that these those as we our you your i my me they their he she his her "
            "will would can could should may might do does did done have has had not no yes so if then than into onto over under about up down out more most very just also "
            "using use used build built make made app platform tool product project startup company service system".split())


def _norm(s): return re.sub(r"\s+", " ", str(s or "")).strip()


def host_of(url):
    """Lower-case host without www and port. Accepts a bare domain too."""
    u = str(url or "").strip()
    if not u: return ""
    if "://" not in u: u = "http://" + u
    try: h = (urlparse(u).hostname or "").lower()
    except ValueError: return ""
    return h[4:] if h.startswith("www.") else h


def _path_of(url):
    u = str(url or "").strip()
    if "://" not in u: u = "http://" + u
    try: return urlparse(u).path.strip("/").lower()
    except ValueError: return ""


def same_host(a, b):
    """True for the same domain or a subdomain of it (docs.example.com is example.com). Shared hosts never match on host alone."""
    ha, hb = host_of(a), host_of(b)
    if not ha or not hb: return False
    if ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha):
        return not any(ha == s or ha.endswith("." + s) for s in SHARED_HOSTS)
    return False


def is_commercial_host(url):
    h = host_of(url)
    return bool(h) and not any(h == s or h.endswith("." + s) for s in _NOT_COMMERCIAL)


def keywords(text, limit=40):
    """Distinctive lower-case words, for comparing two descriptions."""
    out = []
    for w in re.findall(r"[a-z][a-z0-9+#.-]{2,}", _norm(text).lower()):
        w = w.strip(".-")
        if w and w not in _STOP and w not in out: out.append(w)
    return out[:limit]


def overlap(a, b):
    """Share of the SMALLER description's keywords found in the other (0 to 1). Two empty descriptions overlap 0, not 1."""
    ka, kb = set(keywords(a)), set(keywords(b))
    if not ka or not kb: return 0.0
    return len(ka & kb) / min(len(ka), len(kb))


def _name_tokens(name):
    return [t for t in re.findall(r"[a-z]{2,}", _norm(name).lower()) if t not in ("the", "and", "van", "von", "de", "dr", "mr", "mrs", "ms")]


def _people(v):
    """Names from a list or a comma / 'and' separated string."""
    if isinstance(v, (list, tuple)): items = [str(x) for x in v]
    else: items = re.split(r",|;|\band\b|&|\n", str(v or ""))
    return [_norm(x) for x in items if len(_name_tokens(x)) >= 1 and len(_norm(x)) <= 60]


def same_person(a, b):
    """Two names refer to the same person when every token of the shorter name is in the longer one (Josh Dzielak / Joshua Dzielak do not match on first name alone)."""
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb: return False
    if len(ta) == 1 or len(tb) == 1: return ta == tb
    short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return all(t in long for t in short) or (ta[0] == tb[0] and ta[-1] == tb[-1])


# ---------- the identity profile ----------
def _detail(details, *needles):
    """First non-empty value in the interview's details whose key contains one of the needles."""
    for k, v in (details or {}).items():
        if any(n in str(k).lower() for n in needles) and _norm(v): return _norm(v)
    return ""


def build_profile(name="", kind="", details=None, documents=None, job_description="", company="", candidate_name="", candidate_claims=""):
    """Everything known about WHAT is being discussed, built only from what the candidate and their documents supplied. Nothing is looked up here and nothing is invented.
    name: the project or company name. details / documents: the dicts the interview setup stores. Returns a plain dict (JSON-safe)."""
    details = {str(k): v for k, v in (details or {}).items() if isinstance(v, (str, int, float))}
    documents = {str(k): str(v) for k, v in (documents or {}).items() if isinstance(v, (str, int, float))}
    blob = " ".join([*details.values(), *documents.values(), str(job_description or "")])
    urls = []
    for m in _URL.findall(blob):
        u = m.rstrip(".,;:!?)")
        if u not in urls: urls.append(u)
    for k, v in details.items():   # a bare domain typed into a "website" or "link" field
        if any(n in k.lower() for n in ("website", "domain", "url", "link", "site", "repo", "github", "demo", "submission")):
            for m in _BARE_DOMAIN.finditer(str(v)):
                u = "https://" + m.group(0)
                if not any(host_of(u) == host_of(x) and _path_of(u) == _path_of(x) for x in urls): urls.append(u)
    repos = [u for u in urls if host_of(u) in ("github.com", "gitlab.com", "bitbucket.org") and len(_path_of(u).split("/")) >= 2]
    hackathon_name = _detail(details, "hackathon", "event", "competition")
    submission = [u for u in urls if host_of(u).endswith(("devpost.com", "devfolio.co", "dorahacks.io", "lablab.ai")) and _path_of(u)]
    own_domains = []
    for u in urls:
        h = host_of(u)
        if h and not any(h == s or h.endswith("." + s) for s in SHARED_HOSTS) and h not in own_domains: own_domains.append(h)
    explicit = host_of(_detail(details, "website", "domain", "url", "site"))   # a domain typed into a website field is the strongest statement of identity
    if explicit and explicit not in own_domains and not any(explicit == s or explicit.endswith("." + s) for s in SHARED_HOSTS): own_domains.insert(0, explicit)
    desc = _detail(details, "description", "what it does", "product", "problem", "idea", "pitch", "summary", "about") or ""
    docs_desc = " ".join(t[:600] for t in documents.values() if _norm(t))[:1500]
    founders = _people(_detail(details, "founder", "team members", "creator", "cofounder", "co-founder"))
    # Is the candidate presenting something of their own, or applying to an organisation that already exists?
    claims = _norm(candidate_claims).lower()
    owner = kind in OWNER_KINDS or bool(re.search(r"\b(my|our) (own )?(startup|project|company|product|app|business|idea)\b|\bi (founded|built|created|started)\b", claims + " " + _norm(blob[:600]).lower()))
    if kind == "hackathon" or hackathon_name or submission: etype = HACKATHON_PROJECT
    elif owner: etype = OWN_STARTUP
    elif company or name: etype = ESTABLISHED_COMPANY
    else: etype = UNKNOWN_ENTITY
    p = {"name": _norm(name or company)[:120], "aliases": _people(_detail(details, "former name", "previous name", "formerly", "aka", "also known")), "entity_type": etype, "candidate_owns": owner,
         "domains": own_domains[:6], "repositories": repos[:4], "submission_links": submission[:3], "hackathon": hackathon_name[:120], "description": _norm(desc or docs_desc)[:900],
         "industry": _detail(details, "industry", "sector", "category", "market")[:120], "country": _detail(details, "country", "region", "location", "based")[:80],
         "founders": founders[:6], "candidate_name": _norm(candidate_name)[:80], "has_documents": any(len(_norm(t)) >= 80 for t in documents.values()),
         "kind": kind, "company": _norm(company)[:120]}
    p["signals"] = signals(p); p["status"] = status(p)
    return p


def signals(p):
    """The independent identity signals present in a profile. A name is deliberately not one of them."""
    s = []
    if p.get("domains"): s.append("domain")
    if p.get("repositories"): s.append("repository")
    if p.get("submission_links"): s.append("submission_link")
    if len(p.get("description") or "") >= 40: s.append("description")
    if p.get("industry"): s.append("industry")
    if p.get("founders"): s.append("founders")
    if p.get("hackathon"): s.append("hackathon")
    if p.get("has_documents"): s.append("documentation")
    return s


HARD = ("domain", "repository", "submission_link")


def status(p):
    """VERIFIED needs a hard signal (domain, repository or submission link) AND a second, independent signal. Anything less is UNVERIFIED. A name alone never verifies."""
    s = signals(p)
    return VERIFIED if any(x in s for x in HARD) and len(s) >= 2 else UNVERIFIED


def confidence(p):
    """high / medium / low: how far research about this entity can be trusted to be about the right one."""
    s = signals(p)
    if status(p) == VERIFIED and len(s) >= 3: return "high"
    if status(p) == VERIFIED or (not p.get("candidate_owns") and len(s) >= 2): return "medium"   # an organisation applied to, described by a job posting and an industry, is a reasonable working identity
    return "low"


def prompt_block(p):
    """The identity as text for any prompt that researches or checks facts, with the rule that stops same-name confusion."""
    if not p or not p.get("name"): return ""
    lines = [f"IDENTITY OF THE SUBJECT (supplied by the candidate; status {str(p.get('status', UNVERIFIED)).upper()}, confidence {confidence(p)}):",
             f"- Name: {p['name']}" + (f" (also: {', '.join(p['aliases'])})" if p.get("aliases") else ""),
             f"- What it is: {p['entity_type'].replace('_', ' ')}" + (" owned by the candidate" if p.get("candidate_owns") else " the candidate is applying to or discussing")]
    for key, label in (("domains", "Official domain"), ("repositories", "Repository"), ("submission_links", "Hackathon submission"), ("founders", "Founders / creators given"), ("hackathon", "Hackathon"),
                       ("industry", "Industry"), ("country", "Country or region"), ("description", "Product description")):
        v = p.get(key)
        if v: lines.append(f"- {label}: {', '.join(v) if isinstance(v, list) else v}")
    lines.append("RULES: the same NAME is not the same entity. Use only sources that match this identity by domain, product, industry or founders. If a source describes a different company, product or founders with a similar name, "
                 "set \"source_entity\" to that other entity and report it as a different entity; never transfer its pricing, founders, funding or claims to this subject. If the identity is UNVERIFIED, do not state any "
                 "fact about the subject's ownership, pricing or finances as verified.")
    return "\n".join(lines)


# ---------- matching a researched source to the identity ----------
def match_source(p, src):
    """Does this source describe the same entity as the profile? src: {url, title, entity, domain, description, founders, industry, country, type}.
    Returns {"verdict": same|different|unknown, "same": [signals], "different": [signals], "reason": str}.
    SAME needs a hard signal (the candidate's own domain, repository or submission link) or three independent soft signals. A matching name contributes nothing.
    DIFFERENT needs one decisive difference (another domain when the profile has one, other founders when both have them) or two softer ones."""
    src = src or {}
    url = src.get("url") or ""; shost = host_of(src.get("domain") or url)
    same, diff = [], []
    # hard signals
    if any(same_host(shost, d) for d in p.get("domains", [])): same.append("domain")
    for r in p.get("repositories", []) + p.get("submission_links", []):
        pr = _path_of(r)
        if pr and host_of(url) == host_of(r) and _path_of(url).startswith(pr): same.append("repository" if r in p.get("repositories", []) else "submission_link")
    if p.get("domains") and shost and not same_host(shost, p["domains"][0]) and not any(same_host(shost, d) for d in p["domains"]) \
            and not any(shost == s or shost.endswith("." + s) for s in SHARED_HOSTS): diff.append("domain")
    # soft signals
    sd, pd = _norm(src.get("description") or src.get("snippet")), p.get("description") or ""
    if sd and pd:
        o = overlap(sd, pd)
        if o >= 0.45: same.append("description")
        elif o <= 0.12: diff.append("description")
    pf, sf = p.get("founders", []), _people(src.get("founders"))
    if pf and sf:
        (same if any(same_person(a, b) for a in pf for b in sf) else diff).append("founders")
    elif p.get("candidate_name") and sf and p.get("candidate_owns") and p.get("entity_type") in (OWN_STARTUP, HACKATHON_PROJECT) and not pf:
        pass   # the candidate's own name against a source's founders is handled by the ownership rules, not by identity
    pi, si = _norm(p.get("industry")).lower(), _norm(src.get("industry")).lower()
    if pi and si:
        (same if overlap(pi, si) >= 0.5 else diff).append("industry")
    pc, sc = _norm(p.get("country")).lower(), _norm(src.get("country")).lower()
    if pc and sc and pc != sc and pc not in sc and sc not in pc: diff.append("country")
    if p.get("entity_type") == HACKATHON_PROJECT and (src.get("type") == "commercial_company" or (is_commercial_host(url) and (src.get("pricing") or src.get("founders")))) and not any(x in same for x in HARD):
        diff.append("hackathon_vs_commercial")   # a hackathon submission is not an established commercial company just because the names match
    # a source on the candidate's own domain, repository or submission page IS that entity
    if any(x in same for x in HARD) or len(same) >= 3: verdict, why = SAME, "matched on " + ", ".join(same)
    elif "domain" in diff or "founders" in diff or len(diff) >= 2: verdict, why = DIFFERENT, "differs on " + ", ".join(diff) + (" (the name alone does not make it the same entity)" if p.get("name") else "")
    else: verdict, why = UNKNOWN, "not enough independent signals to tell; the name alone is not evidence"
    return {"verdict": verdict, "same": sorted(set(same)), "different": sorted(set(diff)), "reason": why}


def entity_class(p, match):
    """What the matched source is, relative to the candidate's subject (the six cases the product must tell apart)."""
    if match["verdict"] == SAME: return RENAMED if (p.get("aliases") and match["same"] == ["description"]) else p.get("entity_type", UNKNOWN_ENTITY)
    if match["verdict"] == DIFFERENT: return UNRELATED_SAME_NAME if "domain" in match["different"] or "founders" in match["different"] else SIMILAR_PRODUCT
    return UNKNOWN_ENTITY


# ---------- ownership and role claims ----------
_ROLE_RX = [("co_founder", r"\bco[- ]?found(er|ed|ing)\b"), ("founder", r"\b(i am|i'm|i was|as) (the |a |an )?(sole |solo |single )?(founder|ceo|owner)\b|\bi (founded|started|created) (the |this |my |our )?(startup|company|business|project|product)|\bi am the founder\b|\bfounder of\b"),
             ("team_leader", r"\b(team )?(lead|leader|captain)\b|\bi led\b"), ("employee", r"\bi (work|worked) (at|for)\b|\bemployee\b|\bintern(ed)? at\b"),
             ("project_creator", r"\bi (built|created|designed|made|developed) (it|this|the)\b|\bsole (builder|creator|developer)\b|\bi (built|made) everything\b|\bbuilt everything myself\b"),
             ("developer", r"\bi (developed|coded|programmed|engineered|implemented)\b|\bdeveloper\b|\bengineer\b"), ("contributor", r"\bcontribut(or|ed|ion)\b|\bi helped\b|\bi worked on\b")]


def role_claim(text):
    """The strongest role a candidate states for themselves in this text, or 'unknown'. Order matters: co-founder is matched before founder."""
    t = _norm(text).lower()
    for role, rx in _ROLE_RX:
        if re.search(rx, t): return role
    return "unknown"


def ownership_challengeable(p, claimed_role, match, source_founders=None, candidate_name=""):
    """May READYWISE challenge a founder or ownership claim? Only when ALL of these hold: the identity is verified, the source is the SAME entity,
    the source names its founders, and the candidate is not one of them. Returns (bool, reason)."""
    if claimed_role not in ("founder", "co_founder", "project_creator"): return False, "not an ownership claim"
    if p.get("status") != VERIFIED: return False, "the project's identity is unverified, so the claim cannot be checked against any source"
    if match.get("verdict") != SAME: return False, "the source is not shown to be the same entity (a shared name is not evidence)"
    founders = _people(source_founders)
    if not founders: return False, "the source does not name the founders"
    me = candidate_name or p.get("candidate_name") or ""
    if me and any(same_person(me, f) for f in founders): return False, "the candidate is named among the founders"
    if claimed_role == "project_creator": return False, "a project creator is not necessarily listed as a founder"
    return True, "a verified source for the same entity names different founders"


def clarification_question(p, claim_text="", claimed_role=None):
    """What a fair interviewer asks when the identity or the role is unclear. Never an accusation."""
    role = claimed_role or role_claim(claim_text); name = p.get("name") or "your project"
    if p.get("status") != VERIFIED and role in ("founder", "co_founder", "project_creator", "team_leader"):
        return f"Tell me about {name}: where can I see it (a website, repository or submission link), and what exactly was your role in it?"
    if role in ("founder", "co_founder"): return f"How did {name} start, and who else was involved from the beginning?"
    if role in ("project_creator", "developer", "contributor"): return f"Which parts of {name} did you personally build, and which did teammates or other tools provide?"
    return f"Which project or company do you mean by {name}, and what was your part in it?"


FOUNDER_AREAS = ["the problem it solves and who has it", "what has actually been built", "what makes it different", "how it earns revenue", "the evidence of demand",
                 "current operating costs and how each figure was calculated", "the technical architecture and why it was chosen", "the biggest risks", "what the candidate personally contributed", "plans for growth"]


def probe_block(p):
    """For a candidate presenting their OWN project or startup: what a fair, rigorous panel investigates, and how to challenge without inventing facts."""
    if not p or not p.get("candidate_owns"): return ""
    return ("AREAS TO PROBE FOR THIS CANDIDATE'S OWN PROJECT (ask from what they actually said, one at a time): " + "; ".join(FOUNDER_AREAS) + ". "
            "If they give a number, ask how they calculated it and what it assumes. If they say they built something, ask them to explain how it works. If they say they are the founder, find out which project they mean and their exact role "
            "(founder, co-founder, creator, team leader, developer, contributor). Challenge professionally, but never invent a fact, never use another company's facts as theirs, and never accuse: unsupported means ask.")
