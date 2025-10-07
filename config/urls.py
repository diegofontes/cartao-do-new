from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from django.urls import path, include
from django.views.generic import RedirectView
from django.urls import re_path
from apps.cards import views_public as card_public
from apps.media import urls as media_urls
from apps.notifications import urls as notif_urls
from apps.pages import views as pages_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.dashboard.urls")),
    path("img/", include((media_urls, "media"), namespace="media")),
    path("cards/", include("apps.cards.urls")),
    path("api/", include("apps.scheduling.urls")),
    path("api/", include((notif_urls, "notifications"), namespace="notifications")),
    path("api/lead", pages_views.lead, name="api_lead"),
    # Healthcheck endpoint
    path("healthz", lambda _request: HttpResponse("ok")),
    # Legal pages
    path("", include("apps.pages.urls")),
    path("auth/", include("apps.accounts.auth_urls")),
    path("accounts/", include("apps.accounts.urls")),
    # Global alias to satisfy `{% url 'logout' %}` if used without namespace
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Aliases for legacy or un-namespaced reverses
    path(
        "signup/",
        RedirectView.as_view(pattern_name="accounts:auth_signup", permanent=False),
        name="signup",
    ),
    path("billing/", include("apps.billing.urls")),
    path("delivery/", include("apps.delivery.urls")),
    path("metering/", include("apps.metering.urls")),
    path("stripe/", include("apps.billing.webhooks")),  # /stripe/webhook/
    path("search/dashboard/", include(("apps.search.urls_dashboard", "search_dashboard"), namespace="search_dashboard")),
    path("search/", include(("apps.search.urls", "search_public"), namespace="search")),
    path("", RedirectView.as_view(pattern_name="dashboard:index", permanent=False)),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/?$", card_public.card_public, name="card_public_main"),
]

# Custom error handlers
handler404 = "config.views_errors.handler404"
