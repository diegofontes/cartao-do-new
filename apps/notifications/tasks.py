import json
import os
import time as _time
import logging
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.template import Template as DjTemplate, Context
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import phonenumbers
import requests

from .models import Notification, NotificationAttempt, Template

log = logging.getLogger(__name__)


class TransientError(Exception):
    pass


def normalize_phone_e164(val: str) -> str:
    try:
        pn = phonenumbers.parse(val, None)
        if not phonenumbers.is_valid_number(pn):
            raise ValueError("invalid phone")
        return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
    except Exception as e:
        raise ValueError("invalid phone") from e


def render_template(code: str, channel: str, payload: dict) -> dict:
    t = Template.objects.filter(code=code, channel=channel).first()
    defaults = {
        ("sms", "login_2fa"): {"body_txt": "Seu código é {{ code }}. Validade: {{ ttl_min }} min."},
        ("sms", "booking_phone_verify"): {"body_txt": "Seu código para agendar é {{ code }} (válido por {{ ttl_min }} min). Não compartilhe."},
        ("sms", "booking_confirmed_sms"): {"body_txt": "Agendamento confirmado: {{ service }} em {{ date }} {{ time }}. Página: /@{{ nick }}"},
        ("sms", "delivery_order_status"): {"body_txt": "{% if message %}{{ message }}{% else %}Pedido {{ code }}: status {{ status }}.{% endif %}"},
        # Owner notifications (defaults)
        ("sms", "owner_new_booking"): {"body_txt": "Novo agendamento: {{ service }} em {{ date }} {{ time }}. Agenda: {{ agenda_url }}"},
        ("sms", "owner_new_order"): {"body_txt": "Novo pedido {{ code }}. Pedidos: {{ orders_url }}"},
        ("email", "login_2fa"): {
            "subject": "Seu código de acesso (expira em {{ ttl_min }} min)",
            "body_txt": "Olá{% if name %} {{ name }}{% endif %}, seu código é {{ code }}. Válido por {{ ttl_min }} minutos.",
            "body_html": "<p>Olá{% if name %} {{ name }}{% endif %}, seu código é <strong>{{ code }}</strong>. Válido por {{ ttl_min }} minutos.</p>",
        },
        ("email", "booking_confirmed_email"): {
            "subject": "Agendamento confirmado — {{ service }} ({{ date }} {{ time }})",
            "body_txt": "Olá{% if name %} {{ name }}{% endif %}, seu agendamento {{ service }} foi confirmado para {{ date }} {{ time }}. Página: /@{{ nick }}{% if ics_url %} — Adicione ao calendário: {{ ics_url }}{% endif %}.",
            "body_html": "<div style=\"font-family:system-ui,Arial;line-height:1.5;color:#111\"><p>Olá{% if name %} {{ name }}{% endif %},</p><p>Seu agendamento <strong>{{ service }}</strong> foi confirmado para <strong>{{ date }} {{ time }}</strong>.</p><p>Página: <a href=\"/@{{ nick }}\">/@{{ nick }}</a>{% if ics_url %} — <a href=\"{{ ics_url }}\">Adicionar ao calendário</a>{% endif %}.</p></div>",
        },
        ("email", "signup_verify"): {
            "subject": "Confirme seu e-mail — código de verificação",
            "body_txt": "Olá{% if name %} {{ name }}{% endif %}, seu código de verificação é {{ code }}. Válido por {{ ttl_min }} minutos.",
            "body_html": "<p>Olá{% if name %} {{ name }}{% endif %},</p><p>Seu código de verificação é <strong>{{ code }}</strong>.</p><p>Válido por {{ ttl_min }} minutos.</p>",
        },
        ("email", "reset_password"): {
            "subject": "Redefinir senha — código de verificação",
            "body_txt": "Olá{% if name %} {{ name }}{% endif %}, seu código para redefinir a senha é {{ code }}. Válido por {{ ttl_min }} minutos.",
            "body_html": "<p>Olá{% if name %} {{ name }}{% endif %},</p><p>Seu código para redefinir a senha é <strong>{{ code }}</strong>.</p><p>Válido por {{ ttl_min }} minutos.</p>",
        },
    }
    tpl = t or type("_obj", (), defaults.get((channel, code), {}))
    ctx = Context(payload or {})
    out = {}
    if channel == "sms":
        body = DjTemplate(getattr(tpl, "body_txt", "")).render(ctx)
        if not (body or "").strip():
            # Fallback to built-in default when DB template is empty
            _def = defaults.get((channel, code)) or {}
            body = DjTemplate(_def.get("body_txt", "")).render(ctx)
        out.update({"text": body})
    else:
        subj = DjTemplate(getattr(tpl, "subject", "")).render(ctx)
        txt = DjTemplate(getattr(tpl, "body_txt", "")).render(ctx)
        html = DjTemplate(getattr(tpl, "body_html", "")).render(ctx)
        out.update({"subject": subj, "text": txt, "html": html})
    return out


def _twilio_send_sms(to_e164: str, body: str) -> dict:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    tok = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_num = os.getenv("TWILIO_SMS_FROM", "")
    if not (sid and tok and from_num):
        raise TransientError("Twilio not configured")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = {"From": from_num, "To": to_e164, "Body": body[:1500]}
    resp = requests.post(url, data=data, auth=(sid, tok), timeout=20)
    if resp.status_code >= 500:
        raise TransientError(f"Twilio 5xx: {resp.status_code}")
    if resp.status_code in (429,):
        raise TransientError("Twilio rate limited")
    if resp.status_code >= 400:
        raise Exception(f"Twilio 4xx: {resp.text}")
    j = resp.json()
    return {"sid": j.get("sid"), "raw": j}


def _sendgrid_send_email(to_email: str, subject: str, text: str, html: str) -> dict:
    api_key = os.getenv("SENDGRID_API_KEY", "")
    from_email = os.getenv("SENDGRID_FROM_EMAIL", "")
    from_name = os.getenv("SENDGRID_FROM_NAME", "") or "Notifications"
    if not (api_key and from_email):
        raise TransientError("SendGrid not configured")
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": from_name},
        "subject": subject or "",
        "content": [
            {"type": "text/plain", "value": text or ""},
            {"type": "text/html", "value": html or ""},
        ],
    }
    resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=20)
    if resp.status_code >= 500:
        raise TransientError(f"SendGrid 5xx: {resp.status_code}")
    if resp.status_code in (429,):
        raise TransientError("SendGrid rate limited")
    if resp.status_code >= 400:
        raise Exception(f"SendGrid 4xx: {resp.text}")
    # SendGrid returns 202 and may include X-Message-Id header
    msg_id = resp.headers.get("X-Message-Id") or resp.headers.get("X-Message-Id".lower())
    return {"message_id": msg_id, "raw_headers": dict(resp.headers)}


@shared_task(bind=True, max_retries=5, autoretry_for=(TransientError,), retry_backoff=True, retry_backoff_max=3600)
def send_notification(self, notification_id: str):
    dev_mode = os.getenv("NOTIF_DEV_MODE", "true").lower() in ("1", "true", "yes")

    with transaction.atomic():
        try:
            n = Notification.objects.select_for_update().get(id=notification_id)
        except Notification.DoesNotExist:
            log.warning("Notification %s not found", notification_id)
            return
        if n.status not in ("queued", "processing"):
            return
        n.status = "processing"
        n.attempts = (n.attempts or 0) + 1
        n.save(update_fields=["status", "attempts", "updated_at"])

    attempt = NotificationAttempt(notification=n, started_at=timezone.now())
    try:
        if n.type == "sms":
            to_e164 = normalize_phone_e164(n.to)
            ren = render_template(n.template_code, "sms", n.payload_json)
            text = ren.get("text") or ""
            if dev_mode:
                log.info("DEV NOTIF [sms] to %s — template=%s — body=\"%s\"", to_e164, n.template_code, text)
                n.provider = "dev"
                n.provider_message_id = "DEV"
                n.status = "sent"
                n.sent_at = timezone.now()
                n.delivered_at = timezone.now()
                n.save()
                attempt.result = "ok"
                attempt.provider_response_json = {"dev": True}
                attempt.finished_at = timezone.now()
                attempt.save()
                return
            resp = _twilio_send_sms(to_e164, text)
            n.provider = "twilio"
            n.provider_message_id = resp.get("sid")
            n.status = "sent"
            n.sent_at = timezone.now()
            n.save()
            attempt.result = "ok"
            attempt.provider_response_json = resp
            attempt.finished_at = timezone.now()
            attempt.save()
            return
        elif n.type == "email":
            try:
                validate_email(n.to)
            except ValidationError:
                raise Exception("invalid email")
            ren = render_template(n.template_code, "email", n.payload_json)
            if dev_mode:
                log.info("DEV NOTIF [email] to %s — template=%s — body_txt=\"%s\"", n.to, n.template_code, ren.get("text"))
                n.provider = "dev"
                n.provider_message_id = "DEV"
                n.status = "sent"
                n.sent_at = timezone.now()
                n.delivered_at = timezone.now()
                n.save()
                attempt.result = "ok"
                attempt.provider_response_json = {"dev": True}
                attempt.finished_at = timezone.now()
                attempt.save()
                return
            resp = _sendgrid_send_email(n.to, ren.get("subject"), ren.get("text"), ren.get("html"))
            n.provider = "sendgrid"
            n.provider_message_id = resp.get("message_id") or ""
            n.status = "sent"
            n.sent_at = timezone.now()
            n.save()
            attempt.result = "ok"
            attempt.provider_response_json = resp
            attempt.finished_at = timezone.now()
            attempt.save()
            return
        else:
            raise Exception("invalid type")
    except TransientError as te:
        attempt.result = "error"
        attempt.error_message = str(te)
        attempt.finished_at = timezone.now()
        attempt.save()
        # escalate to Celery autoretry
        raise
    except Exception as e:
        # Permanent failure
        n.status = "failed"
        n.error_message = str(e)
        n.save(update_fields=["status", "error_message", "updated_at"])
        attempt.result = "error"
        attempt.error_message = str(e)
        attempt.finished_at = timezone.now()
        attempt.save()
