import os

from .settings import *  # noqa: F401,F403

ROOT_URLCONF = "config.urls_search"
WSGI_APPLICATION = "config.wsgi.application"

# Distinct cookies so the standalone service can coexist alongside dashboard/viewer.
SESSION_COOKIE_NAME = os.getenv("SEARCH_SESSION_COOKIE", "search_sessionid")
CSRF_COOKIE_NAME = os.getenv("SEARCH_CSRF_COOKIE", "search_csrftoken")

# The search service is read-mostly and stateless; drop admin UI and Tailwind build app.
for extra in ("django.contrib.admin", "tailwind", "theme"):
    if extra in INSTALLED_APPS:
        INSTALLED_APPS.remove(extra)

if "apps.search.apps.SearchConfig" not in INSTALLED_APPS:
    INSTALLED_APPS.append("apps.search.apps.SearchConfig")
