import hmac
import hashlib
import base64
import json
import logging
import os
from urllib.parse import urlparse

from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.cache import cache
from django.db import IntegrityError

from .models import Notification
from .tasks import send_notification, normalize_phone_e164

log = logging.getLogger(__name__)


def _rate_limit_key(prefix: str, key: str, window: str) -> str:
    return f"notif:{prefix}:{key}:{window}"


def _now_windows():
    now = timezone.now()
    return now.strftime("%Y%m%d%H%M"), now.strftime("%Y%m%d%H")


@csrf_exempt
@require_POST
def api_create_notification(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("invalid json")

    typ = (data.get("type") or "").lower()
    to = (data.get("to") or "").strip()
    template_code = (data.get("template_code") or "").strip()
    payload = data.get("payload") or {}
    idem = data.get("idempotency_key") or None

    if typ not in ("sms", "email"):
        return HttpResponseBadRequest("invalid type")
    if not to or not template_code:
        return HttpResponseBadRequest("missing fields")

    # Normalize and validate destination
    try:
        if typ == "sms":
            to = normalize_phone_e164(to)
        else:
            # lazy email validation; full validation occurs in task
            if "@" not in to:
                return HttpResponseBadRequest("invalid email")
    except Exception:
        return HttpResponseBadRequest("invalid destination")

    # Rate limit: 5 SMS/min, 50/h per destination
    mm, hh = _now_windows()
    k_min = _rate_limit_key("min", f"{typ}:{to}", mm)
    k_hour = _rate_limit_key("hour", f"{typ}:{to}", hh)
    min_count = cache.get_or_set(k_min, 0, timeout=70)
    hour_count = cache.get_or_set(k_hour, 0, timeout=3600)
    if typ == "sms":
        min_cap, hour_cap = 5, 50
    else:
        min_cap, hour_cap = 10, 200
    if min_count >= min_cap or hour_count >= hour_cap:
        return HttpResponse(status=429)
    cache.incr(k_min)
    cache.incr(k_hour)

    # Idempotency: if provided and exists, return existing
    if idem:
        existing = Notification.objects.filter(idempotency_key=idem).first()
        if existing:
            return JsonResponse({"id": str(existing.id), "status": existing.status}, status=202)

    n = Notification(
        type=typ,
        to=to,
        template_code=template_code,
        payload_json=payload,
        status="queued",
    )
    if idem:
        n.idempotency_key = idem
    try:
        n.save()
    except IntegrityError:
        # race on idempotency_key unique
        existing = Notification.objects.filter(idempotency_key=idem).first()
        if existing:
            return JsonResponse({"id": str(existing.id), "status": existing.status}, status=202)
        raise
    # Enqueue celery task
    send_notification.delay(str(n.id))
    return JsonResponse({"id": str(n.id), "status": n.status}, status=202)


def _twilio_validate_signature(request) -> bool:
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not token:
        return False
    signature = request.headers.get("X-Twilio-Signature", "")
    url = request.build_absolute_uri()
    # Twilio sends form-encoded params; signature is computed by concatenating url + sorted params
    items = sorted((k, v) for k, v in request.POST.items())
    s = url + "".join(k + v for k, v in items)
    digest = hmac.new(token.encode(), s.encode(), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(signature, expected)


@csrf_exempt
@require_POST
def twilio_sms_status(request):
    # Validate signature; if missing and DEBUG true, allow
    if not _twilio_validate_signature(request) and os.getenv("DEBUG", "1") != "1":
        return HttpResponseForbidden("invalid signature")
    sid = request.POST.get("MessageSid") or request.POST.get("SmsSid")
    status = (request.POST.get("MessageStatus") or "").lower()
    error_code = request.POST.get("ErrorCode")
    n = Notification.objects.filter(provider="twilio", provider_message_id=sid).first()
    if not n:
        return HttpResponse("ok")
    if status == "delivered":
        n.status = "delivered"
        n.delivered_at = timezone.now()
        n.save(update_fields=["status", "delivered_at", "updated_at"])
    elif status in ("failed", "undelivered"):
        n.status = "failed"
        n.error_code = error_code
        n.error_message = request.POST.get("ErrorMessage") or ""
        n.save(update_fields=["status", "error_code", "error_message", "updated_at"])
    return HttpResponse("ok")


def _sendgrid_verify(request) -> bool:
    # Twilio SendGrid Event Webhook uses Ed25519 signature with public key
    pubkey = os.getenv("SENDGRID_WEBHOOK_PUBLIC_KEY", "")
    if not pubkey:
        return os.getenv("DEBUG", "1") == "1"
    try:
        import nacl.signing
        import nacl.exceptions
        sig = request.headers.get("X-Twilio-Email-Event-Webhook-Signature", "")
        ts = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp", "")
        payload = request.body
        verify_key = nacl.signing.VerifyKey(base64.b64decode(pubkey))
        message = (ts.encode() + payload)
        verify_key.verify(message, base64.b64decode(sig))
        return True
    except Exception:
        return False


@csrf_exempt
@require_POST
def sendgrid_email_events(request):
    if not _sendgrid_verify(request) and os.getenv("DEBUG", "1") != "1":
        return HttpResponseForbidden("invalid signature")
    try:
        events = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("invalid json")
    for ev in events:
        msg_id = ev.get("sg_message_id") or ev.get("smtp-id") or ev.get("message_id")
        event = (ev.get("event") or ev.get("event_type") or "").lower()
        n = Notification.objects.filter(provider="sendgrid", provider_message_id=msg_id).first()
        if not n:
            continue
        if event == "delivered":
            n.status = "delivered"
            n.delivered_at = timezone.now()
            n.save(update_fields=["status", "delivered_at", "updated_at"])
        elif event in ("bounce", "dropped"):
            n.status = "bounced"
            n.error_message = ev.get("reason") or ev.get("response") or ""
            n.save(update_fields=["status", "error_message", "updated_at"])
    return HttpResponse("ok")

