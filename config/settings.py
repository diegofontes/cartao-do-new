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
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Tailwind integration (django-tailwind)
    "tailwind",
    "theme",  # Nome do app Tailwind
    "django_htmx",
    "apps.accounts",
    "apps.billing",
    "apps.dashboard",
    "apps.cards",
    "apps.scheduling",
    "apps.delivery",
    "apps.metering",
    "apps.notifications",
    "apps.pages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
            "libraries": {
                # Ensure custom template tags are always registered
                "currency": "apps.delivery.templatetags.currency",
            },
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

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

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
# Allow timezone override via environment (e.g., TIME_ZONE=America/Sao_Paulo)
TIME_ZONE = os.getenv("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Tailwind (django-tailwind)
# Após executar `python manage.py tailwind init theme`,
# adicione também "theme" em INSTALLED_APPS.
TAILWIND_APP_NAME = "theme"

# Media (uploads)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Upload constraints (configurable)
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2MB

# Custom user model
AUTH_USER_MODEL = "accounts.User"

# Cache (Redis)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": "paygo",
    }
}

# Celery
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND") or CELERY_BROKER_URL
# Celery will use Django's TIME_ZONE by default; allow override via CELERY_TIMEZONE env
CELERY_TIMEZONE = os.getenv("CELERY_TIMEZONE", TIME_ZONE)
CELERY_TASK_ALWAYS_EAGER = False

# Stripe
import stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
stripe.api_key = STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Billing settings
UNIT_PRICE_CENTS = int(os.getenv("UNIT_PRICE_CENTS", "25"))
DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "usd")

# Public viewer base URL (for "view card" button)
VIEWER_BASE_URL = os.getenv("VIEWER_BASE_URL", "http://localhost:9000")

# Dashboard base URL for links in notifications
DASHBOARD_BASE_URL = os.getenv("DASHBOARD_BASE_URL", "http://localhost:8000")

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
LOGIN_URL = "/auth/login"

# Nickname reservations (also used in viewer settings)
RESERVED_NICKNAMES = {"admin", "api", "static", "media", "img", "assets", "robots", "sitemap"}

# Logging (prints our app logs at INFO level to console)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[%(levelname)s] %(asctime)s %(name)s: %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        }
    },
    "loggers": {
        # Capture all our project app logs (e.g., apps.billing.services)
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Optionally, lower Django’s own verbosity
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# Basic production security (configurable via env)
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "true").lower() == "true"
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))


FORCE_SCRIPT_NAME = os.getenv("DJANGO_FORCE_SCRIPT_NAME")
if FORCE_SCRIPT_NAME:
    if not FORCE_SCRIPT_NAME.startswith("/"):
        FORCE_SCRIPT_NAME = f"/{FORCE_SCRIPT_NAME}"
    STATIC_URL = f"{FORCE_SCRIPT_NAME}/static/"
    MEDIA_URL = f"{FORCE_SCRIPT_NAME}/media/"
    LOGIN_URL = f"{FORCE_SCRIPT_NAME}/auth/login"
    #CSRF_COOKIE_PATH = FORCE_SCRIPT_NAME or '/' 
    #SESSION_COOKIE_PATH = FORCE_SCRIPT_NAME or '/'
    USE_X_FORWARDED_HOST = True

# Delivery limits (per card)
DELIVERY_LIMITS = {
    "groups_per_card": int(os.getenv("DELIVERY_GROUPS_PER_CARD", "20")),
    "items_per_card": int(os.getenv("DELIVERY_ITEMS_PER_CARD", "200")),
    "modifier_groups_per_item": int(os.getenv("DELIVERY_MODIFIER_GROUPS_PER_ITEM", "20")),
    "options_per_modifier_group": int(os.getenv("DELIVERY_OPTIONS_PER_MODIFIER_GROUP", "50")),
}
