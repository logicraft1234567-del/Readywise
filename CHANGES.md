# Scoring, research and transcription integrity upgrade

## Root causes found
1. **Company identity by name.** Research and the live fact-check searched the web for a name ("Orbit") and applied whatever came back (another company's pricing and founders) to the candidate's own project.
2. **Flat penalties.** Every "wrong" claim cost 5 points and every "implausible" one 3, regardless of entity, seriousness or duplicates, so one repeated statement could cost 18 points.
3. **Live transcription had no language.** The Gemini Live path auto-detected the language per fragment, so English speech was printed as Vietnamese or German and then scored.
4. **No transcript quality check.** Wrong-language or low-confidence text went straight to the evaluator.
5. **Score floors.** `clean_competencies` forced scores up to fit the rating (demonstrated >= 65, partial 40 to 74, not demonstrated <= 45) and invented 80/55/20 defaults.

## What changed
- `services/identity.py` (new): identity profile from what the candidate supplied; VERIFIED needs a domain, repository or submission link plus a second signal; `match_source` returns same / different / unknown (a shared name is never a signal); ownership claims are challengeable only against a verified, same-entity source that names other founders; clarification questions instead of accusations.
- `services/findings.py` (new): every finding carries claim, source URL/title/date, entity, evidence, confidence, applies-to-candidate and one of 7 classes (verified true/false, partially verified, unverified, conflicting, wrong entity, outdated). Estimates and unit mismatches (per user vs per workspace) are never "false". `penalty_policy` is the only route to a deduction: verified-false + correct entity only, severity x confidence, de-duplicated, capped at 15, each with a reason.
- `services/scoring.py`: weights are exactly the published scoring table for each interview type (no role shifting), with the table's own area names; no floors, "not assessed" / "insufficient evidence" never zero, per-dimension confidence/coverage/evidence/missing, critical requirements as demonstrated / not demonstrated / not assessed, provisional flag, penalties itemised.
- `services/transcript.py` (new) + `stt.py`: language always sent, Whisper language/logprob/compression checks, one retry on the next model, unreliable turns flagged and excluded from evidence and from the answered/asked counts.
- `services/live.py`: `language_code` and instruction pin the live voice session to the interview language; `views.py` assesses every live and typed turn.
- `services/questions.py` (new) + `agents.py`: duplicate-question guard across the whole session, with a non-repeating fallback.
- `agents.py`: identity block and founder probe areas in the panel prompt, confront vs clarify fact handling, no score floors, evidence checked against the transcript.
- `research.py`: research scoped to the verified identity, findings stored with entity and classification, wrong-entity sources never used.
- Report page: score-by-area breakdown, not-assessed list, critical requirements in 3 groups, verified inaccuracies with points, external research kept separate from the score, transcription note.
- Migration `0019_identity_findings_asr` (Workspace.identity, Turn.asr, Finding classification/source/entity). Run `python manage.py migrate`.

## Tests
`tests/test_integrity.py` (26 tests, no Django needed) plus updated `test_scoring.py`, `test_real_panel.py`, `test_stt.py`.
Not run in the authoring environment (Django was not installed and there was no network): the Django-dependent tests, the migration, and template rendering. Please run `python -m pytest` and `python manage.py migrate` before deploying.

## Interview room layout and fixed shell
- `static/js/room.js` `layoutSquares`: the interviewers and the candidate are equal squares, never more than 2 across, as large as the screen allows (cap raised from 440px to 900px). On phones the squares shrink until everyone is on screen, and the name plates simplify at small sizes (`static/css/room.css`).
- `static/css/app.css`: the header and sidebar no longer scroll with the page. Root cause: `body{overflow-x:hidden}` made the body its own scroll box, so `position:sticky` had nothing to stick to. On desktop the app is one screen tall and the sidebar and main column scroll separately; on mobile the header is pinned to the top.
