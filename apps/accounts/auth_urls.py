from django.urls import path
from . import auth_views as views


app_name = "accounts"

urlpatterns = [
    path("login", views.login_page, name="auth_login"),
    path("login.post", views.login_start, name="auth_login_post"),
    path("login/2fa", views.login_2fa, name="auth_login_2fa"),
    path("signup", views.signup_page, name="auth_signup"),
    path("signup.post", views.signup_start, name="auth_signup_post"),
    path("signup/verify", views.signup_verify, name="auth_signup_verify"),
    path("forgot", views.forgot_page, name="auth_forgot"),
    path("forgot.post", views.forgot_start, name="auth_forgot_post"),
    path("reset", views.reset_apply, name="auth_reset"),
    path("code/resend", views.code_resend, name="auth_code_resend"),
]

