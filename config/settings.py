import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
_env = BASE_DIR / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "*").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
# Render sets these automatically, so the live site works without extra host settings.
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
if _render_host:
    if "*" not in ALLOWED_HOSTS and _render_host not in ALLOWED_HOSTS: ALLOWED_HOSTS.append(_render_host)
    if f"https://{_render_host}" not in CSRF_TRUSTED_ORIGINS: CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")
def _env_keys(plural, prefix):
    """Keys can be given as one comma-separated variable (GROQ_RESEARCH_KEYS=a,b,c) and/or numbered ones (GROQ_RESEARCH_KEY_1, _2 ...)."""
    raw = [os.environ.get(plural, "")] + [os.environ.get(f"{prefix}_{n}", "") for n in range(1, 10)]
    out = []
    for k in ",".join(raw).split(","):
        if k.strip() and k.strip() not in out: out.append(k.strip())
    return out
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")  # optional: makes video discovery far more reliable than web search alone
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")  # optional single fallback for everything
GROQ_RESEARCH_KEYS = _env_keys("GROQ_RESEARCH_KEYS", "GROQ_RESEARCH_KEY")  # research, panel assignment, prep plans, CV analysis
GROQ_INTERVIEW_KEYS = _env_keys("GROQ_INTERVIEW_KEYS", "GROQ_INTERVIEW_KEY")  # live interview, voices, evaluation, camera feedback
def _models(name, default): return [m.strip() for m in os.environ.get(name, default).split(",") if m.strip()]
# Groq limits tokens PER MODEL (and per organisation, so extra keys from the same account share them). Listing models from different
# families gives the app several separate allowances to draw on: when one is used up the next answers straight away instead of waiting.
# A model Groq has retired is skipped automatically, so extra names are harmless.
_FALLBACKS = "llama-3.3-70b-versatile,llama-3.1-8b-instant,meta-llama/llama-4-scout-17b-16e-instruct,qwen/qwen3-32b,moonshotai/kimi-k2-instruct-0905"
GROQ_MODELS = _models("GROQ_MODEL", "openai/gpt-oss-120b,openai/gpt-oss-20b," + _FALLBACKS)  # text and JSON; first available one is used
GROQ_LIGHT_MODELS = _models("GROQ_LIGHT_MODEL", "openai/gpt-oss-20b,llama-3.1-8b-instant,llama-3.3-70b-versatile,openai/gpt-oss-120b")  # small quick jobs (follow-up questions): cheap models first so the big ones keep their allowance
GROQ_RESEARCH_MODELS = _models("GROQ_RESEARCH_MODEL", "openai/gpt-oss-120b,openai/gpt-oss-20b")  # models that support Groq's built-in browser_search tool
# Backup provider, used only when every Groq model is rate limited. Any OpenAI-compatible service. Leave empty to turn it off.
BACKUP_AI_BASE_URL = os.environ.get("BACKUP_AI_BASE_URL", "")
BACKUP_AI_KEYS = _env_keys("BACKUP_AI_KEYS", "BACKUP_AI_KEY")
BACKUP_AI_MODELS = _models("BACKUP_AI_MODELS", "")
GROQ_STT_MODELS = _models("GROQ_STT_MODEL", "whisper-large-v3,whisper-large-v3-turbo")  # speech to text for the interview room
GROQ_VISION_MODELS = _models("GROQ_VISION_MODEL", "qwen/qwen3.8-27b,qwen/qwen3.6-27b")  # camera snapshots (must accept images)
INSTALLED_APPS = ["django.contrib.admin","django.contrib.auth","django.contrib.contenttypes","django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles","rest_framework","core"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware","whitenoise.middleware.WhiteNoiseMiddleware","django.contrib.sessions.middleware.SessionMiddleware","django.middleware.common.CommonMiddleware","django.middleware.csrf.CsrfViewMiddleware","django.contrib.auth.middleware.AuthenticationMiddleware","django.contrib.messages.middleware.MessageMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND":"django.template.backends.django.DjangoTemplates","DIRS":[],"APP_DIRS":True,"OPTIONS":{"context_processors":["django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages","core.context.shell"]}}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {"default":{"ENGINE":"django.db.backends.sqlite3","NAME":BASE_DIR/"db.sqlite3"}}
if os.environ.get("DATABASE_URL"):  # Render PostgreSQL (the blueprint fills this in from the readywise-db database)
    from urllib.parse import urlparse, unquote, parse_qs
    u = urlparse(os.environ["DATABASE_URL"]); q = parse_qs(u.query)
    DATABASES["default"] = {"ENGINE":"django.db.backends.postgresql","NAME":unquote(u.path[1:]),"USER":unquote(u.username or ""),"PASSWORD":unquote(u.password or ""),
                            "HOST":u.hostname,"PORT":u.port or 5432,"CONN_MAX_AGE":int(os.environ.get("DB_CONN_MAX_AGE", "60")),"CONN_HEALTH_CHECKS":True}
    _ssl = (q.get("sslmode") or [os.environ.get("DB_SSLMODE", "")])[0]
    if not _ssl and u.hostname and "." in u.hostname: _ssl = "require"  # Render's external address needs SSL; the internal one has no dots and does not
    if _ssl: DATABASES["default"]["OPTIONS"] = {"sslmode": _ssl}
if not DEBUG:  # production behind Render's HTTPS proxy
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True; CSRF_COOKIE_SECURE = True
LANGUAGE_CODE = "en-us"; TIME_ZONE = "Africa/Lagos"; USE_TZ = True
STATIC_URL = "/static/"; STATIC_ROOT = BASE_DIR / "staticfiles"; MEDIA_URL = "/media/"; MEDIA_ROOT = BASE_DIR/"media"
import mimetypes
mimetypes.add_type("text/javascript", ".mjs"); mimetypes.add_type("text/javascript", ".js"); mimetypes.add_type("model/gltf-binary", ".glb")
WHITENOISE_MIMETYPES = {".mjs": "text/javascript", ".glb": "model/gltf-binary"}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login/"; LOGIN_REDIRECT_URL = "/dashboard/"
DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024

GROQ_TTS_MODEL = os.environ.get("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
REDIS_URL = os.environ.get("REDIS_URL", "")
RESEARCH_IN_THREAD = os.environ.get("RESEARCH_IN_THREAD", "1") == "1"  # run research in a background thread so the page shows live progress (needs no Redis)
CELERY_BROKER_URL = REDIS_URL or "memory://"; CELERY_ENABLED = bool(REDIS_URL)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/"); SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", ""); SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "recordings")
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", ""); EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587")); EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", ""); EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "ReadyWise <noreply@readywise.local>")
REST_FRAMEWORK = {"DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"], "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"]}
