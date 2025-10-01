from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Django env vars (with backward-compatible fallbacks)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or os.getenv("SECRET_KEY", "dev-key")
_dj_debug = os.getenv("DJANGO_DEBUG")
if _dj_debug is not None:
    DEBUG = _dj_debug.lower() in {"1", "true", "yes", "on"}
else:
    DEBUG = bool(int(os.getenv("DEBUG", "1")))

_allowed_hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "").strip()
if _allowed_hosts:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(",") if h.strip()]
else:
    ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "http://localhost:8000").split(",")

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "apps.accounts",
    "apps.notifications",
    "apps.cards",
    "apps.scheduling",
    "apps.media",
    "apps.metering",
    "apps.pages",
    "apps.delivery",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # Sessions must load before CSRF
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "config.urls_viewer"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
            "libraries": {
                # Ensure viewer knows our custom tags
                "currency": "apps.delivery.templatetags.currency",
            },
        },
    }
]

WSGI_APPLICATION = None

# Database: Prefer DATABASE_URL, else use POSTGRES_* vars (UTF-8 client + UTC)
POSTGRES_DB = os.getenv("POSTGRES_DB", "app")
POSTGRES_USER = os.getenv("POSTGRES_USER", "app")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "app")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    from urllib.parse import urlparse

    u = urlparse(DATABASE_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": u.path.lstrip("/"),
            "USER": u.username,
            "PASSWORD": u.password,
            "HOST": u.hostname,
            "PORT": u.port or "5432",
            "CONN_MAX_AGE": 600,
            "OPTIONS": {"options": "-c client_encoding=UTF8 -c timezone=UTC"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": POSTGRES_DB,
            "USER": POSTGRES_USER,
            "PASSWORD": POSTGRES_PASSWORD,
            "HOST": POSTGRES_HOST,
            "PORT": POSTGRES_PORT,
            "CONN_MAX_AGE": 600,
            "OPTIONS": {"options": "-c client_encoding=UTF8 -c timezone=UTC"},
        }
    }

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Reserved nicknames
RESERVED_NICKNAMES = {"admin","api","static","media","img","assets","robots","sitemap"}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Base URL of this viewer instance (used by main app to link here)
VIEWER_BASE_URL = os.getenv("VIEWER_BASE_URL", "http://localhost:9000")
DASHBOARD_BASE_URL = os.getenv("DASHBOARD_BASE_URL", "http://localhost:8000")

# Use distinct cookie names so the viewer (port 9000) doesn't clash with the
# main app session/CSRF cookies running on the same domain (localhost).
SESSION_COOKIE_NAME = os.getenv("VIEWER_SESSION_COOKIE", "viewer_sessionid")
CSRF_COOKIE_NAME = os.getenv("VIEWER_CSRF_COOKIE", "viewer_csrftoken")

# Custom user model
AUTH_USER_MODEL = "accounts.User"

# Logging for viewer profile
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[%(levelname)s] %(asctime)s %(name)s: %(message)s"}
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"}
    },
    "loggers": {
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# Celery for Viewer: default to Redis; can be overridden by explicit vars
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND") or CELERY_BROKER_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = False

# Ensure notifications stay in DEV mode on viewer unless overridden
os.environ.setdefault("NOTIF_DEV_MODE", "1")

# Basic production security (configurable via env)
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "true").lower() == "true"
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
