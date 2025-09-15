from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-viewer-key")
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "apps.notifications",
    "apps.cards",
    "apps.scheduling",
    "apps.media",
    "apps.metering",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
]

ROOT_URLCONF = "config.urls_viewer"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.request",
        ]},
    }
]

WSGI_APPLICATION = None

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Reserved nicknames
RESERVED_NICKNAMES = {"admin","api","static","media","img","assets","robots","sitemap"}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Base URL of this viewer instance (used by main app to link here)
VIEWER_BASE_URL = os.getenv("VIEWER_BASE_URL", "http://localhost:9000")

# Use distinct cookie names so the viewer (port 9000) doesn't clash with the
# main app session/CSRF cookies running on the same domain (localhost).
SESSION_COOKIE_NAME = os.getenv("VIEWER_SESSION_COOKIE", "viewer_sessionid")
CSRF_COOKIE_NAME = os.getenv("VIEWER_CSRF_COOKIE", "viewer_csrftoken")

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

# Celery for Viewer: run tasks eagerly to avoid broker requirement in dev
CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = True  # execute .delay() inline in this process

# Ensure notifications stay in DEV mode on viewer unless overridden
os.environ.setdefault("NOTIF_DEV_MODE", "1")
