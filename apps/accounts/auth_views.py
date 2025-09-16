from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import logging
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, get_user_model
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.common.mail import MailMessage, default_mail_provider
from apps.notifications.api import enqueue
from apps.common.rate_limit import rate_limit
from .models import EmailChallenge, TrustedDevice

User = get_user_model()
logger = logging.getLogger(__name__)


TD_COOKIE = "tdid"


def is_hx(request: HttpRequest) -> bool:
    return (
        request.headers.get("HX-Request") == "true"
        or request.META.get("HTTP_HX_REQUEST") == "true"
    )


def render_card(request: HttpRequest, shell_template: str, card_template: str, ctx: dict, status: int | None = None) -> HttpResponse:
    if is_hx(request):
        return render(request, card_template, ctx, status=status)
    data = dict(ctx)
    data["card_template"] = card_template
    return render(request, shell_template, data, status=status)


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _hx_redirect(url: str) -> HttpResponse:
    resp = HttpResponse(status=204)
    resp["HX-Redirect"] = url
    return resp


def login_page(request: HttpRequest) -> HttpResponse:
    return render(request, "auth/login.html")


def _check_trusted_device(request: HttpRequest, user: User) -> bool:
    cookie = request.COOKIES.get(TD_COOKIE)
    if not cookie:
        return False
    parsed = TrustedDevice.parse_cookie(cookie)
    if not parsed:
        return False
    user_id, device_id = parsed
    if str(user.id) != user_id:
        return False
    td = TrustedDevice.objects.filter(user=user, device_id=device_id, expires_at__gt=datetime.now(timezone.utc)).first()
    return bool(td)


def login_start(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    rl = rate_limit("login", f"{request.META.get('REMOTE_ADDR')}", limit=20, window_seconds=60)
    if not rl.allowed:
        return HttpResponse("Muitas tentativas. Tente novamente em alguns segundos.", status=429)

    email = _normalize_email(request.POST.get("email", ""))
    password = request.POST.get("password", "")
    remember_device = bool(request.POST.get("remember_device"))

    user = User.objects.filter(email__iexact=email).first()
    if not user or not user.check_password(password):
        logger.warning("Login failed for email=%s from ip=%s", email, request.META.get('REMOTE_ADDR'))
        messages.error(request, "Credenciais inválidas")
        return render_card(request, "auth/login.html", "auth/_card_login.html", {"email": email}, status=400)

    # Check trusted device
    if _check_trusted_device(request, user):
        logger.info("Login success via trusted device: user_id=%s", user.id)
        auth_login(request, user)
        user.last_login = datetime.now(timezone.utc)
        user.save(update_fields=["last_login"])
        return _hx_redirect(reverse("dashboard:index"))

    # Create 2FA challenge
    challenge, code = EmailChallenge.create_for(user, EmailChallenge.PURPOSE_LOGIN)

    # Enfileira notificação de 2FA por e-mail
    logger.info("2FA code generated for user_id=%s purpose=login", user.id)
    try:
        ip = request.META.get('REMOTE_ADDR')
    except Exception:
        ip = None
    enqueue(
        type='email',
        to=user.email,
        template_code='login_2fa',
        payload={'code': code, 'name': user.first_name, 'ip': ip, 'ttl_min': 10},
        idempotency_key=f'login2fa:{challenge.id}'
    )

    request.session["pending_2fa_user_id"] = str(user.id)
    request.session["pending_2fa_challenge_id"] = str(challenge.id)
    request.session["pending_2fa_remember"] = remember_device

    return render_card(request, "auth/login.html", "auth/_card_2fa.html", {"email": user.email})


def login_2fa(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    rl = rate_limit("login_2fa", f"{request.META.get('REMOTE_ADDR')}", limit=30, window_seconds=60)
    if not rl.allowed:
        return HttpResponse("Muitas tentativas. Tente novamente em alguns segundos.", status=429)

    code = (request.POST.get("code", "") or "").strip()
    user_id = request.session.get("pending_2fa_user_id")
    challenge_id = request.session.get("pending_2fa_challenge_id")
    remember_device = bool(request.session.get("pending_2fa_remember"))

    if not (user_id and challenge_id):
        messages.error(request, "Sessão 2FA expirada. Faça login novamente.")
        return render_card(request, "auth/login.html", "auth/_card_login.html", {}, status=400)

    user = User.objects.filter(id=user_id).first()
    ch = EmailChallenge.objects.filter(id=challenge_id).first()
    if not user or not ch or ch.user_id != user.id:
        logger.warning("2FA session invalid user_id=%s ch_id=%s", user_id, challenge_id)
        messages.error(request, "Sessão 2FA inválida.")
        return render_card(request, "auth/login.html", "auth/_card_login.html", {}, status=400)

    if not ch.consume_with_code(code):
        # failed attempt
        if ch.attempts_left == 0 or ch.is_expired():
            logger.warning("2FA exhausted/expired for user_id=%s ch_id=%s", user.id, ch.id)
            messages.error(request, "Código inválido ou expirado. Novo código necessário.")
            return render_card(request, "auth/login.html", "auth/_card_login.html", {}, status=400)
        messages.error(request, "Código inválido. Tente novamente.")
        return render_card(request, "auth/login.html", "auth/_card_2fa.html", {"email": user.email}, status=400)

    logger.info("2FA success for user_id=%s", user.id)
    auth_login(request, user)
    user.last_login = datetime.now(timezone.utc)
    user.save(update_fields=["last_login"])

    if is_hx(request):
        resp = _hx_redirect(reverse("dashboard:index"))
    else:
        resp = redirect("dashboard:index")

    if remember_device:
        td = TrustedDevice.create_for(user, days=30)
        cookie_val = TrustedDevice.make_cookie(str(user.id), td.device_id)
        resp.set_cookie(TD_COOKIE, cookie_val, max_age=30 * 24 * 3600, httponly=True, samesite="Lax")

    # cleanup
    for k in ("pending_2fa_user_id", "pending_2fa_challenge_id", "pending_2fa_remember"):
        request.session.pop(k, None)

    return resp


def signup_page(request: HttpRequest) -> HttpResponse:
    return render(request, "auth/signup.html")


@transaction.atomic
def signup_start(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    rl = rate_limit("signup", f"{request.META.get('REMOTE_ADDR')}", limit=20, window_seconds=60)
    if not rl.allowed:
        return HttpResponse("Muitas tentativas. Tente novamente em alguns segundos.", status=429)

    email = _normalize_email(request.POST.get("email", ""))
    password = (request.POST.get("password", "") or "").strip()
    agree = request.POST.get("agree_terms") in ("on", "true", "1", "yes")
    if not email or not password:
        messages.error(request, "Informe e-mail e senha válidos.")
        return render_card(request, "auth/signup.html", "auth/_card_signup.html", {}, status=400)
    if not agree:
        messages.error(request, "Você precisa aceitar a Política de Privacidade e os Termos de Uso.")
        return render_card(request, "auth/signup.html", "auth/_card_signup.html", {}, status=400)

    if User.objects.filter(email__iexact=email).exists():
        messages.error(request, "E-mail já cadastrado.")
        return render_card(request, "auth/signup.html", "auth/_card_signup.html", {}, status=400)

    # Generate unique internal username (hidden from UI)
    username = f"u_{uuid.uuid4().hex[:12]}"
    user = User.objects.create(username=username, email=email)
    user.password = make_password(password)
    user.save(update_fields=["password"])

    ch, code = EmailChallenge.create_for(user, EmailChallenge.PURPOSE_SIGNUP)
    default_mail_provider.send(
        MailMessage(to=email, subject="Verify your email", body=f"Code: {code}")
    )
    request.session["pending_signup_user_id"] = str(user.id)
    request.session["pending_signup_challenge_id"] = str(ch.id)
    return render_card(request, "auth/signup.html", "auth/_card_signup_verify.html", {"email": email})


def signup_verify(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    rl = rate_limit("signup_verify", f"{request.META.get('REMOTE_ADDR')}", limit=30, window_seconds=60)
    if not rl.allowed:
        return HttpResponse("Muitas tentativas. Tente novamente em alguns segundos.", status=429)

    code = (request.POST.get("code", "") or "").strip()
    user_id = request.session.get("pending_signup_user_id")
    ch_id = request.session.get("pending_signup_challenge_id")
    user = User.objects.filter(id=user_id).first()
    ch = EmailChallenge.objects.filter(id=ch_id).first()
    if not user or not ch or ch.user_id != user.id:
        logger.warning("Signup verify session invalid user_id=%s ch_id=%s", user_id, ch_id)
        messages.error(request, "Sessão expirada. Refaça o cadastro.")
        return render_card(request, "auth/signup.html", "auth/_card_signup.html", {}, status=400)

    if not ch.consume_with_code(code):
        if ch.attempts_left == 0 or ch.is_expired():
            messages.error(request, "Código inválido/expirado. Refaça o cadastro.")
            return render_card(request, "auth/signup.html", "auth/_card_signup.html", {}, status=400)
        messages.error(request, "Código inválido. Tente novamente.")
        return render_card(request, "auth/signup.html", "auth/_card_signup_verify.html", {"email": user.email}, status=400)

    user.email_verified_at = datetime.now(timezone.utc)
    user.save(update_fields=["email_verified_at"])
    # Auto login after verify
    logger.info("Signup verified and logged in user_id=%s", user.id)
    auth_login(request, user)
    if is_hx(request):
        return _hx_redirect(reverse("dashboard:index"))
    return redirect("dashboard:index")


def forgot_page(request: HttpRequest) -> HttpResponse:
    return render(request, "auth/forgot.html")


def forgot_start(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    rl = rate_limit("forgot", f"{request.META.get('REMOTE_ADDR')}", limit=10, window_seconds=60)
    if not rl.allowed:
        return HttpResponse("Muitas tentativas. Tente novamente em alguns segundos.", status=429)

    email = _normalize_email(request.POST.get("email", ""))
    user = User.objects.filter(email__iexact=email).first()
    # Don't reveal if user exists
    if user:
        ch, code = EmailChallenge.create_for(user, EmailChallenge.PURPOSE_RESET)
        default_mail_provider.send(
            MailMessage(to=email, subject="Reset password", body=f"Code: {code}")
        )
        request.session["pending_reset_user_id"] = str(user.id)
        request.session["pending_reset_challenge_id"] = str(ch.id)
        return render_card(request, "auth/forgot.html", "auth/_card_reset_stage.html", {"email": email})
    # Always render the next stage for UX consistency
    return render_card(request, "auth/forgot.html", "auth/_card_reset_stage.html", {"email": email})


def reset_apply(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    rl = rate_limit("reset", f"{request.META.get('REMOTE_ADDR')}", limit=15, window_seconds=60)
    if not rl.allowed:
        return HttpResponse("Muitas tentativas. Tente novamente em alguns segundos.", status=429)

    code = (request.POST.get("code", "") or "").strip()
    new_password = (request.POST.get("new_password", "") or "").strip()
    user_id = request.session.get("pending_reset_user_id")
    ch_id = request.session.get("pending_reset_challenge_id")
    user = User.objects.filter(id=user_id).first()
    ch = EmailChallenge.objects.filter(id=ch_id).first()
    if not user or not ch or ch.user_id != user.id:
        logger.warning("Reset session invalid user_id=%s ch_id=%s", user_id, ch_id)
        messages.error(request, "Sessão expirada. Solicite novamente.")
        return render_card(request, "auth/forgot.html", "auth/_card_forgot.html", {}, status=400)

    if not ch.consume_with_code(code):
        if ch.attempts_left == 0 or ch.is_expired():
            messages.error(request, "Código inválido/expirado. Solicite novamente.")
            return render_card(request, "auth/forgot.html", "auth/_card_forgot.html", {}, status=400)
        messages.error(request, "Código inválido. Tente novamente.")
        return render_card(request, "auth/forgot.html", "auth/_card_reset_stage.html", {"email": user.email}, status=400)

    user.set_password(new_password)
    user.save(update_fields=["password"])
    # Invalidate any other active reset challenges for this user
    EmailChallenge.objects.filter(user=user, purpose=EmailChallenge.PURPOSE_RESET, consumed_at__isnull=True).update(
        consumed_at=datetime.now(timezone.utc)
    )

    if is_hx(request):
        return _hx_redirect(f"{reverse('accounts:auth_login')}?reset=ok")
    return redirect(f"{reverse('accounts:auth_login')}?reset=ok")


def code_resend(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    rl = rate_limit("resend", f"{request.META.get('REMOTE_ADDR')}", limit=10, window_seconds=60)
    if not rl.allowed:
        return HttpResponse("Aguarde antes de reenviar.", status=429)

    # Determine context by session preference order
    ctx = None
    if request.session.get("pending_2fa_user_id"):
        ctx = (EmailChallenge.PURPOSE_LOGIN, request.session.get("pending_2fa_user_id"))
    elif request.session.get("pending_signup_user_id"):
        ctx = (EmailChallenge.PURPOSE_SIGNUP, request.session.get("pending_signup_user_id"))
    elif request.session.get("pending_reset_user_id"):
        ctx = (EmailChallenge.PURPOSE_RESET, request.session.get("pending_reset_user_id"))

    if not ctx:
        return HttpResponseBadRequest("Nada para reenviar")

    purpose, user_id = ctx
    user = User.objects.filter(id=user_id).first()
    if not user:
        return HttpResponseBadRequest("Sessão inválida")

    # Cooldown: 60s between sends
    last = EmailChallenge.objects.filter(user=user, purpose=purpose).order_by("-created_at").first()
    if last and (datetime.now(timezone.utc) - last.created_at) < timedelta(seconds=60):
        return HttpResponse("Aguarde antes de reenviar.", status=429)

    ch, code = EmailChallenge.create_for(user, purpose)
    if purpose == EmailChallenge.PURPOSE_LOGIN:
        enqueue(
            type='email',
            to=user.email,
            template_code='login_2fa',
            payload={'code': code, 'name': user.first_name, 'ttl_min': 10},
            idempotency_key=f'login2fa:{ch.id}'
        )
    else:
        # mantém fluxo atual para signup/reset por enquanto
        default_mail_provider.send(MailMessage(to=user.email, subject=f"{purpose} code", body=f"Code: {code}"))

    # Return the current form unchanged (HTMX will just keep it)
    # Optionally we could re-render the form with a timer indicator
    if purpose == EmailChallenge.PURPOSE_LOGIN:
        return render_card(request, "auth/login.html", "auth/_card_2fa.html", {"email": user.email})
    if purpose == EmailChallenge.PURPOSE_SIGNUP:
        return render_card(request, "auth/signup.html", "auth/_card_signup_verify.html", {"email": user.email})
    return render_card(request, "auth/forgot.html", "auth/_card_reset_stage.html", {"email": user.email})
