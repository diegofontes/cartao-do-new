import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.accounts.models import EmailChallenge


User = get_user_model()


@pytest.mark.django_db
def test_login_happy_path(client, settings, monkeypatch):
    u = User.objects.create_user(username="u_x", email="user@example.com", password="pwd123")

    # Control 2FA code
    monkeypatch.setattr(EmailChallenge, "generate_code", staticmethod(lambda: "123456"))

    # Step 1: submit credentials, expect 2FA card returned
    r = client.post(reverse("accounts:auth_login_post"), {"email": "user@example.com", "password": "pwd123"})
    assert r.status_code == 200
    assert b"Verifica\xc3\xa7\xc3\xa3o 2FA" in r.content

    # Step 2: consume code
    r2 = client.post(reverse("accounts:auth_login_2fa"), {"code": "123456"}, HTTP_HX_REQUEST="true")
    assert r2.status_code == 204
    assert r2.headers.get("HX-Redirect") == reverse("dashboard:index")


@pytest.mark.django_db
def test_signup_verify_flow(client, monkeypatch):
    monkeypatch.setattr(EmailChallenge, "generate_code", staticmethod(lambda: "654321"))

    r = client.post(reverse("accounts:auth_signup_post"), {"email": "new@example.com", "password": "pwd123"})
    assert r.status_code == 200
    assert b"Verifique seu e-mail" in r.content

    r2 = client.post(reverse("accounts:auth_signup_verify"), {"code": "654321"}, HTTP_HX_REQUEST="true")
    assert r2.status_code == 204
    assert r2.headers.get("HX-Redirect") == reverse("dashboard:index")


@pytest.mark.django_db
def test_forgot_and_reset(client, monkeypatch):
    User.objects.create_user(username="u_x", email="lost@example.com", password="oldpwd")
    monkeypatch.setattr(EmailChallenge, "generate_code", staticmethod(lambda: "111222"))

    r = client.post(reverse("accounts:auth_forgot_post"), {"email": "lost@example.com"})
    assert r.status_code == 200
    assert b"Redefinir senha" in r.content

    r2 = client.post(reverse("accounts:auth_reset"), {"code": "111222", "new_password": "newpwd"}, HTTP_HX_REQUEST="true")
    assert r2.status_code == 204
    assert reverse("accounts:auth_login") in r2.headers.get("HX-Redirect", "")

