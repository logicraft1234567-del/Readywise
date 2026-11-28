# ReadyWise: your personal AI interview department

Django + Groq. Panel of up to 5 AI interviewers, sourced research, adaptive plan, live voice/camera room, evidence-based reports, skills memory.

## Run
Quickest: double-click `run.bat` (Windows) or run `./run.sh` (Mac/Linux). It installs packages, creates the database and starts the server.

If you see `no such table: django_session`, the database hasn't been created yet: run `python manage.py migrate`, then start the server again. If you update the code later and get column errors, run `python manage.py migrate` again (or delete `db.sqlite3` if you don't need your test data).

Manual steps:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add GROQ_RESEARCH_KEYS and GROQ_INTERVIEW_KEYS
python manage.py migrate
python manage.py runserver
```
Open http://127.0.0.1:8000 . Use Chrome or Edge for voice recognition (typing works everywhere). Camera/mic need localhost or HTTPS.

## How the agents share data (core/services)
- `research.run` (`services/research.py`, `services/evidence.py`)  a different research plan per interview type (`services/kinds.py`). Six searches run side by side: the type's four angles, what real candidates report (forums, reviews, Reddit threads, which are fetched and read), and interview videos (YouTube captions are read, summarised with timestamps, and only the notes are kept). A synthesis step writes that type's briefing. Evidence rules are enforced in code: a finding resting on a forum, review or video is never `confirmed`, sources older than three years are flagged and demoted, and the page shows how many separate sources agree and how many videos were actually heard
- `agents.prepare`   research + CV + panel + past scores -> `PrepTask` rows
- `agents.next_turn` Panel Orchestrator: picks the speaker, avoids repeats, tracks covered topics and time, filters memory per interviewer focus
- `agents.evaluate`  transcript -> scores, timestamped observations
- `logic.update_memory` (plain Python) blends scores into `MemoryItem`
- `scoring.compute` (plain Python, no AI) is the scoring engine. The AI only judges evidence: it scores each criterion of each competency (fixed in the rubric before the interview) or says there was not enough evidence. Python then calculates competency scores, dimension scores, and the overall score, using the dimensions and weights of that interview type in `scoring.KIND_DIMS`. Every type has its own dimensions (a visa interview has purpose, consistency, funds and ties, and no technical dimension; a pitch has market and traction; a certification has only knowledge, application and judgment). Each type's weights add to 100; add an entry when you add a type. Skills the interview never reached are left out and the weights rescaled, never counted as zero. It also reports coverage, evidence confidence, and which critical requirements were met. The result is stored in `Evaluation.breakdown`. `agents.final_score` is only a fallback when too few competencies could be rated.
- `logic.adjust_plan`  (plain Python) reschedules missed tasks, lowers mastered topics, adds drills + focused panel sessions
- `services/ai.py` and `services/tts.py` are the only files that talk to Groq; swap them to change provider.

## Interview types: one place to change everything (services/kinds.py)
Each of the 10 types defines its own: form questions (grouped into The opportunity, Your story, The interview, with example answers), a 4-step research plan, the briefing sections (for example the pitch briefing has Market numbers, Competitors, Benchmarks and Likely objections; the visa briefing has Official requirements and a Consistency checklist), the interviewer behaviour, the scoring weights, and the research animation (a blurred orb with its own colours and motion: sparks, rings, ripples, orbiting nodes, dust, stars, a scan line, a network, growing bars, hexagons). To add a type, add one entry there; the form, research, page and animation follow from it.

Research runs in a background thread when Redis is not set (`RESEARCH_IN_THREAD=1`, the default), so the page can show real progress. Set `RESEARCH_IN_THREAD=0` to run it inline.

## Guided flows and the journey
- **Sign-up leads to `/welcome/`**: a one-question-at-a-time profile set-up with an animated guide orb, word-by-word questions, tags for skills, drag-and-drop CV, a progress bar and confetti. Every question can be skipped, and "Skip setup" jumps straight to the dashboard. `/profile/` is still the full form.
- **New interview (`/w/new/`)** uses the same engine (`static/js/wizard.js`, `static/css/wizard.css`): pick the type, then that type's own questions one at a time. Only the essentials (name, role, and for pitches the problem and the ask) cannot be skipped. Answers go into the same form fields as before, so the server did not change how it reads them. The questions live in `services/kinds.py`.
- **The workspace is one connected journey** (`static/js/journey.js`, `static/css/journey.css`): Research, Panel, Prep plan, Practice, Readiness, joined by one animated track with a "Next up" marker. The page opens on the right step, and the sticky bar at the bottom always holds the one button that does the next thing (run research, continue, generate the plan, enter the interview room). Completing a step celebrates it the next time the page loads. The main buttons (Continue, Finish, Create my workspace and the big journey button) have no idle animation: they only react when clicked, by shattering into glass shards that fly out and re-form (`static/js/shatter.js`; reduced-motion users get a quick fade instead).

## What the research can and cannot reach
- **Web search** (Groq browser_search) finds the pages. **Pages and Reddit threads** are then fetched by the server itself, only from URLs the search returned, never private addresses, and respecting robots.txt. Login-walled sites (LinkedIn, Facebook, X, Glassdoor, Indeed, Blind) are not fetched; for those only the search snippet is used.
- **YouTube** videos are found with the YouTube Data API when `YOUTUBE_API_KEY` is set (two searches per research run, 100 quota units each, so about 50 runs on the free 10,000 units a day; recent videos first). Without a key, or if the quota runs out, web search finds them instead. Their captions are read with `youtube-transcript-api` (in `requirements.txt`, no key needed). Videos without captions are listed but not heard. YouTube often blocks cloud servers (Render, AWS) from reading captions; if transcripts fail in production but work on your laptop, set `YOUTUBE_PROXY` to a residential or rotating proxy URL. Restrict the API key to the YouTube Data API v3 in Google Cloud so a leaked key cannot be used for anything else.
- Only short notes are stored, never full transcripts or pages. Quotes are limited and sources are linked.
- Interviewers also ask one question at a time, balance who speaks, and probe vague answers. The report ignores speech-recognition typos and shows a stronger version of each weak answer.

## Not built yet (next steps)
Realtime streaming voice, WebRTC, Django Channels, Celery/Redis, Supabase storage, and lip-sync (MuseTalk / Wav2Lip / LivePortrait). Today avatars are still photos with a speaking highlight; voice uses the browser's speech APIs. DRF is not wired in: endpoints are plain JSON views.

## Tests and deploy
`pytest` runs the full flow with Groq mocked. **Deploying to Render with PostgreSQL: see `DEPLOY_ON_RENDER.md`** (`render.yaml` creates the web service and the database).

## What ReadyWise does
- **Interviewers and difficulty are chosen by the system** (max 3, `services/panelplan.py`), per interview type (`services/kinds.py`).
- **Introductions:** every panel member introduces themselves before the first question.
- **Personal settings:** interview language, preferred style (friendly, balanced, strict), CV analysed into a structured profile, optional names of your real interviewers.
- **Interviewer depth:** each interviewer has question themes (inspiration only) and a rubric of what they listen for.
- **Room checks:** camera resolution, live microphone level meter, and a connection check before you start.
- **Groq voices (Orpheus), camera snapshot feedback (Llama 4 vision), reminders, calendar export, printable readiness report, read-only API** (see code).

## Parked for now (not needed, some cost money)
Celery/Redis background jobs and Supabase recording storage are in the code but switched off unless you set `REDIS_URL` or the `SUPABASE_*` variables. Realtime streaming voice, WebRTC, Channels, true lip-sync (needs a GPU service) and any paid features are not built.

## API keys and models
Two groups of Groq keys, by job. `GROQ_RESEARCH_KEYS` (comma separated) serves research, panel assignment, prep plans and CV analysis. `GROQ_INTERVIEW_KEYS` serves the live interview, voices, evaluation and camera feedback. Calls rotate round-robin across the keys in their group, and a key that hits its rate limit falls over to the next one. `GROQ_API_KEY` is an optional single fallback. Never commit `.env`.

| Job | Default model (override in `.env`) |
|---|---|
| Text and JSON | `openai/gpt-oss-120b`, then `openai/gpt-oss-20b` (`GROQ_MODEL`) |
| Web research | `openai/gpt-oss-120b`, then `openai/gpt-oss-20b` with Groq's built-in `browser_search` tool (`GROQ_RESEARCH_MODEL`). Groq shut down its `groq/compound` models on 2026-09-21. Browser search cannot return JSON directly, so the answer is converted to JSON by a second call when needed |
| Camera snapshots | `qwen/qwen3.8-27b`, then `qwen/qwen3.6-27b` (`GROQ_VISION_MODEL`), max 5 images |
| Voices | `canopylabs/orpheus-v1-english` (`GROQ_TTS_MODEL`) |

Groq retires models often (llama-3.3-70b-versatile and the Llama 4 vision models are already gone). Each model setting accepts a comma-separated list and a retired model falls through to the next. Run `python manage.py groq_models --test` after setup: it checks every key, lists the models your keys can use, and runs one live request through text, research, camera and voice, printing PASS or FAIL for each. Run it again any time something stops working.

**Voices:** Orpheus has six English voices (troy, austin, daniel, hannah, diana, autumn), so some interviewers share a voice. Long turns are split at sentence ends and joined, because Orpheus takes short inputs. Voice audio is English only: for other interview languages the browser voice is used. Before the first voice request, accept the Orpheus terms once in the Groq console (Playground, text-to-speech), otherwise Groq returns a terms error.

## Interviewers: photos only (Nov 22 2026)
The interview room uses the interviewer photos (`core/static/img/i01.png` to `i19.png`). The 3D avatars, TalkingHead, three.js and the lip-sync code were removed. A speaking interviewer is shown by a highlighted tile, a gentle zoom on the photo and a small level meter that follows the voice.

## How the interviewers behave
- `core/services/agents.py` holds `CONDUCT`, the rules every interviewer follows: formal and neutral, no flattery, one question per turn, every question grounded in the candidate's own details from the wizard, the research or the job description, implausible claims challenged with a request for evidence, arithmetic checked, unethical or unprofessional statements named once and calmly, and no question ever repeated.
- `polish()` removes flattery openers and exclamation marks from whatever the model returns. `too_similar()` catches a repeated question and the question is regenerated once on a different area.
- Interruptions: the microphone only interrupts an interviewer when the option is ticked in the setup screen (off by default), after 1.8 s of the interviewer's sentence, and only for 1.5 s of clearly loud speech. The Interrupt button always works. A noise that cuts an interviewer off just replays the same question.
- Notes such as "(interrupted ...)" or "(didn't hear you)" are no longer written into the transcript.

## Design system (Nov 2026 redesign)
- Tokens live at the top of `core/static/css/app.css` (`--paper`, `--surface`, `--ink`, `--b1` brand, `--line`, radii `--r1..--r4`). Light and dark share the same names.
- Type: Newsreader (headlines) and Geist (interface), self-hosted in `core/static/fonts/` and declared in `css/fonts.css`.
- No runtime CDNs. Tailwind is compiled to `css/tailwind.css`; Lucide, GSAP and Chart.js are vendored in `static/vendor/`. After adding new Tailwind classes to templates or JS, rebuild with `npx tailwindcss -i in.css -o core/static/css/tailwind.css --minify` (config content paths: `core/templates/**/*.html`, `core/static/js/*.js`).
- Landing styles: `css/landing.css`. Workspace journey: `css/journey.css`. Guided wizard: `css/wizard.css`.

## Research stage and the story
- `core/static/js/research.js` + the `.rs-stage` markup in `workspace.html`: while research runs, the overlay plays a scene for the step that is active (official pages, candidate accounts, interview videos, writing the briefing, choosing the panel). The accent colour and the pages-it-reads text change with the interview type.
- `core/static/js/story.js` + `css/story.css`: the "See story" film on the landing page (9 chapters, 65 seconds, GSAP timeline). Open it directly with `/#story`. Picture and sound are both generated in the browser: the score is synthesized live with Web Audio (heartbeat, risers, impacts, pads, a major-key lift for the finale), with a sound toggle and an optional narration toggle that uses the browser's own voices. No media files. To use real footage instead, replace the overlay with a `<video>`.

## Guide page
`/guide/` (`templates/core/guide.html`, styles in `css/landing.css`, `js/guide.js`) explains how to use the site, what is asked and why, why research comes first, how scores work, what data is kept and what the user controls. A short version sits on the landing page (`#guide`). If you change what the app stores or which AI provider it uses, update the "Your data and your control" section so it stays true.

## Films (story and walkthrough)
`core/static/js/film.js` is the shared engine (GSAP timeline, particles, live Web Audio score, controls). Each film is a config: `story.js` (the 65 second motivational story, `/#story`) and `guide-film.js` (the 11-chapter walkthrough of how to use the site, why the questions matter, why research comes first and how data is handled, `/#walkthrough`). Markup comes from `templates/core/_film.html`; buttons use `data-story-open` or `data-film-open="walk"`. To add a film, add a config file and include `_film.html` with a new id.

## Buttons on small screens

A button label is never clipped on a phone (560px and narrower). Every button has one of three forms:

| Form | Markup | Use when |
|---|---|---|
| Full label, then short label | `<span class="bl">Create my interview workspace</span><span class="bs">Create workspace</span>` inside the button | the label is longer than 17 characters |
| Icon only | add `ico-m` to the button, put the label in `<span class="bl">`, and give the button `aria-label` and `title` | the icon alone is clear (for example Leave room) |
| Wraps | nothing to add | short labels; `.btn` wraps to two lines and keeps a 44px touch height on phones |

The same pattern covers buttons built in JavaScript: the journey "Next up" button (`.jbtn`, labels in `journey.js` each have a `short`), the planner cards and pop-up, the wizard (`.wz-btn` wraps and its main choices stack full width) and the story film end card (`.st-btn`). When you build a button in JavaScript, write both spans too.

Rules: the short label keeps the same verb as the full one, in sentence case. Both `.btn` and the interview room's `.rm-btn` use the pattern. `tests/test_buttons.py` fails if a label longer than 17 characters has no short form, or an icon-only button has no accessible name.
