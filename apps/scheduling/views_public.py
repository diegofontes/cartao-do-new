import datetime as dt
from zoneinfo import ZoneInfo
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from apps.cards.models import Card
from .models import SchedulingService, Appointment
from .slots import generate_slots
from django.core.cache import cache
from django.utils import timezone
from apps.common.phone import to_e164, gen_code, hash_code
from apps.notifications.api import enqueue
import logging
import datetime as dt

log = logging.getLogger(__name__)


def _card(nickname: str) -> Card:
    return get_object_or_404(Card, nickname__iexact=nickname, status="published")


def public_slots(request, nickname: str):
    card = _card(nickname)
    svc_id = request.GET.get("service")
    date = request.GET.get("date")
    if not (svc_id and date):
        return HttpResponseBadRequest("service and date required")
    service = get_object_or_404(SchedulingService, id=svc_id, card=card, is_active=True)
    try:
        y, m, d = map(int, date.split("-"))
        the_date = dt.date(y, m, d)
    except Exception:
        return HttpResponseBadRequest("invalid date")
    slots = generate_slots(service, the_date)
    # If HTMX request, return an HTML partial for the slots picker; else JSON
    if request.headers.get("HX-Request"):
        # Render labels in the service timezone for display
        try:
            tz = ZoneInfo(service.timezone or "UTC")
        except Exception:
            tz = ZoneInfo("UTC")
        labeled = []
        for sl in slots:
            try:
                sdt = dt.datetime.fromisoformat(sl["start_at_utc"])  # aware
                label = sdt.astimezone(tz).strftime("%H:%M")
            except Exception:
                label = (sl.get("start_at_utc") or "")[11:16]
            labeled.append({**sl, "label": label})
        return render(request, "public/_slots.html", {"slots": labeled, "tz": service.timezone})
    return JsonResponse({"service": str(service.id), "date": date, "slots": slots})


@require_http_methods(["POST"]) 
def public_create_appointment(request, nickname: str):
    card = _card(nickname)
    svc_id = request.POST.get("service")
    start = (request.POST.get("start_at_utc") or "").strip()
    name = (request.POST.get("name") or "").strip()
    email = (request.POST.get("email") or "").strip()
    phone_raw = (request.POST.get("phone") or "").strip()
    if not (svc_id and start and name and phone_raw and request.session.get("phone_verified")):
        return HttpResponseBadRequest("missing fields")
    service = get_object_or_404(SchedulingService, id=svc_id, card=card, is_active=True)
    # Idempotência básica: evita dupes com mesmo service+email+start
    dupe = Appointment.objects.filter(service=service, user_email=email or None, start_at_utc=start).exists()
    if dupe:
        return render(request, "public/_appointment_result.html", {"ok": True, "duplicate": True})
    # compute end
    try:
        sdt = dt.datetime.fromisoformat(start)
    except ValueError:
        return HttpResponseBadRequest("invalid start")
    edt = sdt + dt.timedelta(minutes=service.duration_minutes)
    # normalize phone
    try:
        phone = to_e164(phone_raw)
    except Exception:
        return HttpResponseBadRequest("invalid phone")
    appt = Appointment.objects.create(
        service=service,
        user_name=name,
        user_email=email or None,
        user_phone=phone,
        start_at_utc=sdt,
        end_at_utc=edt,
        timezone=service.timezone,
        location_choice=service.type,
        form_answers_json={},
        status="pending",
    )
    # clear verification flag
    request.session["phone_verified"] = False
    return render(request, "public/_appointment_result.html", {"ok": True, "appointment": appt})


def public_book_modal(request, nickname: str):
    card = _card(nickname)
    svc_id = request.GET.get("service")
    service = get_object_or_404(SchedulingService, id=svc_id, card=card, is_active=True)
    return render(request, "public/_appointment_modal.html", {"card": card, "service": service})

def public_service_sidebar(request, nickname: str, id: str):
    card = _card(nickname)
    service = get_object_or_404(SchedulingService, id=id, card=card, is_active=True)
    return render(request, "public/_service_sidebar.html", {"card": card, "service": service})


def _session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


@require_http_methods(["POST"])
def public_send_code(request, nickname: str, id: str):
    card = _card(nickname)
    service = get_object_or_404(SchedulingService, id=id, card=card, is_active=True)
    phone_raw = (request.POST.get("phone") or "").strip()
    try:
        phone = to_e164(phone_raw)
    except Exception as e:
        return render(request, "public/_verify_block.html", {"error": str(e), "card": card, "service": service})
    sk = _session_key(request)
    cooldown_key = f"pv:cool:{sk}:{phone}"
    if cache.get(cooldown_key):
        return render(request, "public/_verify_block.html", {"error": "Aguarde antes de reenviar.", "card": card, "service": service})
    code = gen_code(6)
    # Enfileira SMS de verificação (dev mode imprime no console)
    try:
        enqueue(
            type='sms',
            to=phone,
            template_code='booking_phone_verify',
            payload={'code': code, 'ttl_min': 5},
            idempotency_key=f'phoneverify:{sk}:{hash_code(code)}'
        )
    except Exception as e:
        log.warning("failed to enqueue SMS verify: %s", e)
    pv_key = f"pv:data:{sk}:{phone}"
    cache.set(pv_key, {"code": hash_code(code), "attempts": 5, "exp": timezone.now() + dt.timedelta(minutes=5)}, 300)
    cache.set(cooldown_key, 1, 60)
    request.session["phone_verified"] = False
    return render(request, "public/_verify_block.html", {"phone": phone, "card": card, "service": service})


@require_http_methods(["POST"])
def public_verify_code(request, nickname: str, id: str):
    card = _card(nickname)
    service = get_object_or_404(SchedulingService, id=id, card=card, is_active=True)
    phone_raw = (request.POST.get("phone") or "").strip()
    code = (request.POST.get("code") or "").strip()
    try:
        phone = to_e164(phone_raw)
    except Exception as e:
        return render(request, "public/_verify_block.html", {"error": str(e), "card": card, "service": service})
    sk = _session_key(request)
    pv_key = f"pv:data:{sk}:{phone}"
    data = cache.get(pv_key)
    if not data:
        return render(request, "public/_verify_block.html", {"error": "Código expirado. Reenvie.", "card": card, "service": service})
    if data["attempts"] <= 0:
        return render(request, "public/_verify_block.html", {"error": "Muitas tentativas. Reenvie.", "card": card, "service": service})
    if data["code"] != hash_code(code):
        data["attempts"] -= 1
        cache.set(pv_key, data, 300)
        return render(request, "public/_verify_block.html", {"phone": phone, "error": "Código incorreto.", "card": card, "service": service})
    request.session["phone_verified"] = True
    return render(request, "public/_verify_block.html", {"phone": phone, "verified": True, "card": card, "service": service})


@require_http_methods(["POST"])
def public_validate_booking(request, nickname: str, id: str):
    name = (request.POST.get("name") or "").strip()
    start = (request.POST.get("start_at_utc") or "").strip()
    valid = bool(name) and bool(start) and request.session.get("phone_verified")
    return render(request, "public/_footer.html", {"form_valid": valid, "nickname": nickname, "service_id": id})
