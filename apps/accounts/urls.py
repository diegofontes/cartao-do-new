from django.urls import path
from django.views.generic import RedirectView
from django.contrib.auth import views as auth_views
from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    # Redirect legacy login to new auth flow
    path("login/", RedirectView.as_view(pattern_name="accounts:auth_login", permanent=False), name="login"),
    #path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
