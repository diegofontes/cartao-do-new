from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import RedirectView
from django.urls import re_path
from apps.cards import views_public as card_public
from apps.media import urls as media_urls
from apps.notifications import urls as notif_urls

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.dashboard.urls")),
    path("img/", include((media_urls, "media"), namespace="media")),
    path("cards/", include("apps.cards.urls")),
    path("api/", include("apps.scheduling.urls")),
    path("api/", include((notif_urls, "notifications"), namespace="notifications")),
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
    path("metering/", include("apps.metering.urls")),
    path("stripe/", include("apps.billing.webhooks")),  # /stripe/webhook/
    path("", RedirectView.as_view(pattern_name="dashboard:index", permanent=False)),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/?$", card_public.card_public, name="card_public_main"),
]
