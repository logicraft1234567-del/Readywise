# Deploy ReadyWise on Render (with Render PostgreSQL)

Everything is already configured: `render.yaml` (web service + database), `build.sh`, `.python-version`, and production settings in `config/settings.py`.

## 1. Put the code on GitHub
`.env` and `.env.render` hold your real API keys and are in `.gitignore`, so they will NOT be pushed. That is intentional. Do not remove them from `.gitignore`.
```bash
git init && git add . && git commit -m "ReadyWise"
git branch -M main
git remote add origin https://github.com/<you>/readywise.git
git push -u origin main
```
(Check `git status` first: `.env` and `.env.render` must not be listed.)

## 2. Create everything from the blueprint
1. Render dashboard -> **New** -> **Blueprint** -> connect the GitHub repo.
2. Render reads `render.yaml` and creates the **readywise** web service and the **readywise-db** PostgreSQL database. It links the database automatically (`DATABASE_URL`) and generates `DJANGO_SECRET_KEY`.
3. It asks for the secret values: open `.env.render` on your computer and paste `GROQ_RESEARCH_KEYS`, `GROQ_INTERVIEW_KEYS`, `YOUTUBE_API_KEY`, `BACKUP_AI_BASE_URL`, `BACKUP_AI_KEYS`, `BACKUP_AI_MODELS`.
   Shortcut: after the service exists, go to it -> **Environment** -> **Add from .env** and paste the whole content of `.env.render`.
4. Click **Apply**. The first build installs packages, collects static files and creates all tables in PostgreSQL (`build.sh`).

## 3. Open and test
- Your site is at `https://readywise.onrender.com` (or the name Render gives you). Hosts and CSRF origins are set automatically from Render's own variables.
- Create an account and run an interview.
- Voice: accept the Orpheus terms once in the Groq console (Playground -> text-to-speech).
- Optional admin: Render service -> **Shell** -> `python manage.py createsuperuser`, then open `/admin/`.

## 4. Before launch day
- **Database plan:** the free Render PostgreSQL expires after 30 days. In `render.yaml` change `plan: free` to a paid plan (for example `basic-256mb`) or upgrade it in the dashboard, otherwise your data will be deleted.
- **Web plan:** the free web service sleeps after 15 minutes idle, so the first visit is slow. Use `starter` for a demo or launch.
- **Recordings:** the web disk is wiped on every deploy. Session recordings are not kept unless you set the `SUPABASE_*` variables (the code supports it).
- **Keys:** if a key was ever shared (chat, screenshot, public repo), create a new one in the Groq, Google and YouTube consoles and update it in Render.

## Variables reference
| Variable | Where it comes from |
|---|---|
| `DATABASE_URL` | Render, from `readywise-db` |
| `DJANGO_SECRET_KEY` | Render, generated |
| `DJANGO_DEBUG=0` | `render.yaml` |
| `GROQ_RESEARCH_KEYS`, `GROQ_INTERVIEW_KEYS` | you (`.env.render`) |
| `YOUTUBE_API_KEY` | you, optional |
| `BACKUP_AI_BASE_URL`, `BACKUP_AI_KEYS`, `BACKUP_AI_MODELS` | you, optional |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | only needed for a custom domain, comma separated (`ALLOWED_HOSTS=readywise.com,www.readywise.com`, `CSRF_TRUSTED_ORIGINS=https://readywise.com,https://www.readywise.com`) |

## Troubleshooting
- **Build fails on migrate:** check the database is "Available" in the dashboard, then redeploy.
- **400 Bad Request:** custom domain not in `ALLOWED_HOSTS`.
- **403 CSRF failed:** custom domain not in `CSRF_TRUSTED_ORIGINS` (must start with `https://`).
- **Research or voice errors:** run `python manage.py groq_models --test` in the Render Shell.
- **YouTube captions fail from Render:** set `YOUTUBE_PROXY` (see README).
