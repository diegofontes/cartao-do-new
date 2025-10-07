from django.urls import include, path

from django.contrib.auth import views as auth_views
from apps.media import urls as media_urls

urlpatterns = [
    path("img/", include((media_urls, "media"), namespace="media")),
    path("", include(("apps.search.urls", "search"), namespace="search")),
    path("auth/", include("apps.accounts.auth_urls")),
    path("accounts/", include("apps.accounts.urls")),
    # Global alias to satisfy `{% url 'logout' %}` if used without namespace
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]

# Custom error handlers
handler404 = "config.views_errors.handler404"