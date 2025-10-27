from __future__ import annotations

import datetime as dt
import hmac
from dataclasses import dataclass
from typing import Any, Literal

from django.core.cache import cache
from django.db import transaction
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from zoneinfo import ZoneInfo

from apps.common.phone import last4_digits, mask_phone
from apps.delivery.models import Order
from apps.scheduling.models import Appointment, RescheduleRequest
from apps.notifications.api import enqueue
from apps.scheduling.slots import generate_slots


SESSION_PREFIX = "viewer:order:"
SESSION_TTL_HOURS = 24
RATE_LIMIT_WINDOW = dt.timedelta(minutes=15)
RATE_LIMIT_MAX_TRIES = 5

RESCHEDULE_LABELS: dict[str, str] = {
    "requested": "Pedido aguardando aprovação",
    "approved": "Pedido aprovado",
    "rejected": "Pedido recusado",
    "expired": "Pedido expirado",
}

DELIVERY_FLOW: list[tuple[str, str]] = [
    ("pending", "Pedido recebido"),
    ("accepted", "Pedido aceito"),
    ("preparing", "Em preparo"),
    ("ready", "Pedido pronto"),
    ("shipped", "Saiu para entrega"),
    ("completed", "Concluído"),
]
DELIVERY_EXTRA_LABELS: dict[str, str] = {
    "cancelled": "Pedido cancelado",
    "rejected": "Pedido rejeitado",
}
DELIVERY_INDEX = {status: idx for idx, (status, _label) in enumerate(DELIVERY_FLOW)}


def _delivery_status_label(status: str, order: Order, default: str) -> str:
    if status == "ready":
        return "Pronto para retirada" if order.fulfillment == "pickup" else "Pedido pronto"
    if status == "shipped":
        return "Saiu para entrega" if order.fulfillment == "delivery" else "Disponível para retirada"
    if status == "completed":
        return "Pedido concluído" if order.fulfillment == "delivery" else "Pedido finalizado"
    return default


@dataclass
class ViewerTarget:
    code: str
    kind: Literal["appointment", "delivery"]
    appointment: Appointment | None
    order: Order | None

    @property
    def card(self):
        if self.kind == "appointment" and self.appointment:
            return self.appointment.service.card  # type: ignore[return-value]
        if self.kind == "delivery" and self.order:
            return self.order.card  # type: ignore[return-value]
        raise AttributeError("target has no card")

    @property
    def phone(self) -> str:
        if self.kind == "appointment" and self.appointment:
            return self.appointment.user_phone
        if self.kind == "delivery" and self.order:
            return self.order.customer_phone
        return ""


def _resolve_target(code: str) -> ViewerTarget:
    normalized = (code or "").strip()
    if not normalized:
        raise Http404()
    normalized_upper = normalized.upper()
    appointment: Appointment | None = None
    order: Order | None = None
    if normalized_upper.startswith("A"):
        appointment = (
            Appointment.objects.select_related("service", "service__card")
            .filter(public_code=normalized_upper)
            .first()
        )
    elif normalized_upper.startswith("D"):
        order = Order.objects.select_related("card").prefetch_related(
            "items__menu_item",
            "items__options__modifier_option",
            "items__options__modifier_option__modifier_group",
            "items__texts__modifier_group",
            "status_changes",
        ).filter(public_code=normalized_upper).first()
    if not appointment and not order:
        appointment = (
            Appointment.objects.select_related("service", "service__card")
            .filter(public_code=normalized_upper)
            .first()
        )
        if not appointment:
            order = Order.objects.select_related("card").prefetch_related(
                "items__menu_item",
                "items__options__modifier_option",
                "items__options__modifier_option__modifier_group",
                "items__texts__modifier_group",
                "status_changes",
            ).filter(public_code=normalized_upper).first()
    if appointment:
        card = appointment.service.card
        if card.status != "published" or getattr(card, "deactivation_marked", False):
            raise Http404()
        if card.mode != "appointment":
            raise Http404()
        return ViewerTarget(code=normalized_upper, kind="appointment", appointment=appointment, order=None)
    if order:
        card = order.card
        if card.status != "published" or getattr(card, "deactivation_marked", False):
            raise Http404()
        if card.mode != "delivery":
            raise Http404()
        return ViewerTarget(code=normalized_upper, kind="delivery", appointment=None, order=order)
    raise Http404()


def _session_key(code: str) -> str:
    return f"{SESSION_PREFIX}{code}"


def _is_verified(request, code: str) -> bool:
    entry = request.session.get(_session_key(code))
    if not entry:
        return False
    exp = entry.get("exp")
    if not exp:
        return False
    try:
        expires_at = dt.datetime.fromisoformat(exp)
    except Exception:
        return False
    now = timezone.now()
    if now >= expires_at:
        request.session.pop(_session_key(code), None)
        return False
    return True


def _client_ip(request) -> str:
    xfwd = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    if xfwd:
        return xfwd
    return request.META.get("REMOTE_ADDR") or "0.0.0.0"


def _rate_limit_key(code: str, ip: str) -> str:
    return f"viewer:rate:{code}:{ip}"


def _rate_limited(code: str, ip: str) -> bool:
    key = _rate_limit_key(code, ip)
    data = cache.get(key)
    if not data:
        return False
    tries = int(data.get("tries", 0) if isinstance(data, dict) else data)
    return tries >= RATE_LIMIT_MAX_TRIES


def _increment_rate_limit(code: str, ip: str) -> int:
    key = _rate_limit_key(code, ip)
    data = cache.get(key)
    if not data:
        payload = {"tries": 1, "ts": timezone.now().isoformat()}
        cache.set(key, payload, int(RATE_LIMIT_WINDOW.total_seconds()))
        return 1
    tries = int(data.get("tries", 0) if isinstance(data, dict) else data)
    tries += 1
    payload = {"tries": tries, "ts": timezone.now().isoformat()}
    cache.set(key, payload, int(RATE_LIMIT_WINDOW.total_seconds()))
    return tries


def _reset_rate_limit(code: str, ip: str) -> None:
    cache.delete(_rate_limit_key(code, ip))


def _store_verified(request, code: str) -> None:
    expires_at = timezone.now() + dt.timedelta(hours=SESSION_TTL_HOURS)
    request.session[_session_key(code)] = {"exp": expires_at.isoformat()}
    request.session.modified = True


def _notify_owner_reschedule(req: RescheduleRequest) -> None:
    card = req.appointment.service.card
    phone = getattr(card, "notification_phone", None)
    if not phone:
        return
    try:
        enqueue(
            type="sms",
            to=phone,
            template_code="owner_reschedule_requested",
            payload={
                "service": req.appointment.service.name,
                "customer": req.appointment.user_name,
            },
            idempotency_key=f"resched:{req.id}:owner:notif",
        )
    except Exception:
        pass


def _base_context(target: ViewerTarget, request) -> dict[str, Any]:
    verified = _is_verified(request, target.code)
    ctx: dict[str, Any] = {
        "target": target,
        "card": target.card,
        "verified": verified,
        "masked_phone": mask_phone(target.phone),
    }
    if verified:
        if target.kind == "appointment" and target.appointment:
            ctx.update(_appointment_context(target.appointment))
        elif target.kind == "delivery" and target.order:
            ctx.update(_delivery_context(target.order))
    return ctx


def _appointment_context(ap: Appointment) -> dict[str, Any]:
    try:
        tz = ZoneInfo(ap.timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    start_local = ap.start_at_utc.astimezone(tz)
    end_local = ap.end_at_utc.astimezone(tz)
    today_local = timezone.now().astimezone(tz).date()
    pending_request = (
        ap.reschedule_requests.filter(status="requested").order_by("-created_at").first()
    )
    latest_request = ap.reschedule_requests.order_by("-created_at").first()
    timeline = []
    for req in ap.reschedule_requests.order_by("created_at"):
        label = RESCHEDULE_LABELS.get(req.status, req.status.capitalize())
        created_local = req.created_at.astimezone(tz)
        approved_window = None
        if req.new_start_at_utc:
            approved_window = {
                "start": req.new_start_at_utc.astimezone(tz),
                "end": req.new_end_at_utc.astimezone(tz) if req.new_end_at_utc else None,
            }
        requested_slot = req.requested_start_at_utc.astimezone(tz) if req.requested_start_at_utc else None
        timeline.append({
            "obj": req,
            "status": req.status,
            "label": label,
            "created": created_local,
            "requested": requested_slot,
            "approved_window": approved_window,
        })
    return {
        "appointment": ap,
        "start_local": start_local,
        "end_local": end_local,
        "pending_reschedule": pending_request,
        "latest_reschedule": latest_request,
        "reschedule_timeline": timeline,
        "can_cancel": ap.status in {"pending", "confirmed"},
        "can_reschedule": ap.status in {"pending", "confirmed"},
        "pending_requested_slot": pending_request.requested_start_at_utc.astimezone(tz) if pending_request and pending_request.requested_start_at_utc else None,
        "reschedule_min_date": today_local.isoformat(),
    }


def _delivery_context(order: Order) -> dict[str, Any]:
    items_data: list[dict[str, Any]] = []
    for item in order.items.all():
        options: list[dict[str, Any]] = []
        for opt in item.options.all():
            if not opt.modifier_option:
                continue
            mg = opt.modifier_option.modifier_group
            delta_val = int(opt.price_delta_cents_snapshot or 0)
            options.append({
                "group": mg.name if mg else "",
                "label": opt.modifier_option.label,
                "delta": delta_val,
                "delta_abs": abs(delta_val),
                "delta_sign": 1 if delta_val >= 0 else -1,
            })
        texts: list[dict[str, Any]] = []
        for txt in item.texts.all():
            mg = txt.modifier_group
            texts.append({
                "group": mg.name if mg else "",
                "value": txt.text_value,
            })
        items_data.append({
            "id": item.id,
            "qty": item.qty,
            "name": item.menu_item.name if item.menu_item else "Item",
            "subtotal": int(item.line_subtotal_cents or 0),
            "base": int(item.base_price_cents_snapshot or 0),
            "options": options,
            "texts": texts,
            "notes": item.notes or "",
        })

    logs = list(order.status_changes.all())
    log_map: dict[str, Any] = {}
    for log in logs:
        log_map.setdefault(log.status, log)
    reached_indices = [
        DELIVERY_INDEX[status] for status in log_map.keys() if status in DELIVERY_INDEX
    ]
    last_reached_idx = max(reached_indices) if reached_indices else -1
    current_idx = DELIVERY_INDEX.get(order.status, last_reached_idx)

    timeline = []
    for idx, (status, default_label) in enumerate(DELIVERY_FLOW):
        log_entry = log_map.get(status)
        label = _delivery_status_label(status, order, default_label)
        timeline.append({
            "status": status,
            "label": label,
            "timestamp": log_entry.created_at if log_entry else None,
            "note": getattr(log_entry, "note", "") if log_entry else "",
            "source": getattr(log_entry, "source", "") if log_entry else "",
            "done": log_entry is not None and idx <= current_idx,
            "current": order.status == status,
        })

    extras = []
    for log_entry in logs:
        if log_entry.status not in DELIVERY_INDEX:
            label = DELIVERY_EXTRA_LABELS.get(log_entry.status, log_entry.status.title())
            extras.append({
                "status": log_entry.status,
                "label": label,
                "timestamp": log_entry.created_at,
                "note": log_entry.note or "",
                "source": log_entry.source or "",
                "current": order.status == log_entry.status,
            })

    address_lines: list[str] = []
    cep = ""
    if order.fulfillment == "delivery":
        addr = order.address_json or {}
        if isinstance(addr, dict):
            logradouro = (addr.get("logradouro") or "").strip()
            numero = (addr.get("numero") or "").strip()
            complemento = (addr.get("complemento") or "").strip()
            bairro = (addr.get("bairro") or "").strip()
            cidade = (addr.get("cidade") or "").strip()
            uf = (addr.get("uf") or "").strip()
            if logradouro or numero:
                line1 = logradouro
                if numero:
                    line1 = f"{line1}, {numero}" if line1 else numero
                address_lines.append(line1)
            if complemento:
                address_lines.append(complemento)
            if bairro:
                address_lines.append(bairro)
            if cidade or uf:
                line_city = cidade
                if uf:
                    line_city = f"{line_city} - {uf}" if line_city else uf
                if line_city:
                    address_lines.append(line_city)
            cep = (addr.get("cep") or "").strip()

    created_local = timezone.localtime(order.created_at)
    updated_local = timezone.localtime(order.updated_at)

    return {
        "order": order,
        "order_items": items_data,
        "order_created_local": created_local,
        "order_updated_local": updated_local,
        "delivery_timeline": timeline,
        "delivery_timeline_extras": extras,
        "can_cancel": order.status in {"pending", "accepted"},
        "address_lines": address_lines,
        "address_cep": cep,
        "order_subtotal": int(order.subtotal_cents or 0),
        "order_delivery_fee": int(order.delivery_fee_cents or 0),
        "order_discount": int(order.discount_cents or 0),
        "order_discount_abs": abs(int(order.discount_cents or 0)),
        "order_total": int(order.total_cents or 0),
    }


@require_http_methods(["GET"])
def order_detail(request, code: str):
    target = _resolve_target(code)
    ctx = _base_context(target, request)
    return render(request, "viewer/order_detail.html", ctx)


@require_http_methods(["GET"])
def order_status_partial(request, code: str):
    target = _resolve_target(code)
    if not _is_verified(request, target.code):
        return HttpResponseForbidden("Sessão expirada ou não verificada.")
    ctx = _base_context(target, request)
    return render(request, "viewer/_order_status.html", ctx)


@require_http_methods(["POST"])
def verify_last4(request, code: str):
    target = _resolve_target(code)
    last4 = (request.POST.get("last4") or "").strip()
    if len(last4) != 4 or not last4.isdigit():
        return HttpResponseBadRequest("Código inválido.")
    expected = last4_digits(target.phone)
    ip = _client_ip(request)
    if _rate_limited(target.code, ip):
        resp = HttpResponseForbidden("Excesso de tentativas. Tente novamente mais tarde.")
        resp["HX-Trigger"] = '{"flash":{"type":"err","title":"Muitas tentativas","message":"Aguarde 15 minutos."}}'
        return resp
    if expected and hmac.compare_digest(expected, last4):
        _store_verified(request, target.code)
        _reset_rate_limit(target.code, ip)
        resp = HttpResponse(status=204)
        resp["HX-Trigger"] = '{"flash":{"type":"ok","title":"Verificado","message":"Sessão válida por 24h."}}'
        resp["HX-Redirect"] = reverse("viewer:order_detail", args=[target.code])
        return resp
    tries = _increment_rate_limit(target.code, ip)
    remaining = max(0, RATE_LIMIT_MAX_TRIES - tries)
    resp = HttpResponseForbidden("Últimos dígitos não conferem.")
    resp["HX-Trigger"] = (
        f'{{"flash":{{"type":"err","title":"Código incorreto","message":"Você ainda tem {remaining} tentativas."}}}}'
    )
    return resp


@require_http_methods(["POST"])
def order_cancel(request, code: str):
    target = _resolve_target(code)
    if not _is_verified(request, target.code):
        return HttpResponseForbidden("Sessão expirada ou não verificada.")
    if target.kind == "delivery" and target.order:
        order = target.order
        if order.status not in {"pending", "accepted"}:
            return HttpResponseBadRequest("Operação não permitida para o status atual.")
        order.set_status("cancelled", source="viewer")
        target = _resolve_target(code)
        ctx = _base_context(target, request)
        resp = render(request, "viewer/_order_status.html", ctx)
        resp["HX-Trigger"] = '{"flash":{"type":"ok","title":"Pedido cancelado","message":"Notificaremos o estabelecimento."}}'
        return resp
    if target.kind == "appointment" and target.appointment:
        ap = target.appointment
        if ap.status not in {"pending", "confirmed"}:
            return HttpResponseBadRequest("Operação não permitida para o status atual.")
        ap.status = "cancelled"
        ap.save(update_fields=["status"])
        target = _resolve_target(code)
        ctx = _base_context(target, request)
        resp = render(request, "viewer/_order_status.html", ctx)
        resp["HX-Trigger"] = '{"flash":{"type":"ok","title":"Agendamento cancelado","message":"O profissional foi avisado."}}'
        return resp
    raise Http404()


@require_http_methods(["POST"])
def order_reschedule_request(request, code: str):
    target = _resolve_target(code)
    if target.kind != "appointment" or not target.appointment:
        return HttpResponseBadRequest("Funcionalidade inválida para esse pedido.")
    if not _is_verified(request, target.code):
        return HttpResponseForbidden("Sessão expirada ou não verificada.")
    ap = target.appointment
    if ap.status not in {"pending", "confirmed"}:
        return HttpResponseBadRequest("Só é possível solicitar troca para agendamentos pendentes ou confirmados.")
    reason = (request.POST.get("reason") or "").strip()
    slot_raw = (request.POST.get("slot_start_at") or "").strip()
    if not slot_raw:
        return HttpResponseBadRequest("Escolha um horário disponível.")
    try:
        requested_start = dt.datetime.fromisoformat(slot_raw)
    except ValueError:
        return HttpResponseBadRequest("Horário inválido.")
    if requested_start.tzinfo is None:
        requested_start = requested_start.replace(tzinfo=ZoneInfo("UTC"))
    service = ap.service
    try:
        tz_service = ZoneInfo(service.timezone or "UTC")
    except Exception:
        tz_service = ZoneInfo("UTC")
    slot_date = requested_start.astimezone(tz_service).date()
    slots = generate_slots(service, slot_date, ignore_appointment_id=str(ap.id))
    match = next((sl for sl in slots if sl.get("start_at_utc") == requested_start.astimezone(ZoneInfo("UTC")).isoformat()), None)
    if not match:
        return HttpResponseBadRequest("Horário indisponível. Atualize a página e tente novamente.")
    requested_end = dt.datetime.fromisoformat(match["end_at_utc"])
    expires_at = timezone.now() + dt.timedelta(hours=48)
    with transaction.atomic():
        ap.reschedule_requests.filter(status="requested").update(status="expired")
        req = RescheduleRequest.objects.create(
            appointment=ap,
            status="requested",
            requested_by="customer",
            preferred_windows=[slot_raw],
            reason=reason,
            requested_start_at_utc=requested_start,
            requested_end_at_utc=requested_end,
            expires_at=expires_at,
            requested_ip=_client_ip(request),
        )
    _notify_owner_reschedule(req)
    ctx = _base_context(target, request)
    resp = render(request, "viewer/_order_status.html", ctx)
    resp["HX-Trigger"] = '{"flash":{"type":"ok","title":"Pedido enviado","message":"Aguardando aprovação do profissional."}}'
    return resp


@require_http_methods(["GET"])
def order_reschedule_slots(request, code: str):
    target = _resolve_target(code)
    if target.kind != "appointment" or not target.appointment:
        return HttpResponseBadRequest("Operação inválida para este pedido.")
    if not _is_verified(request, target.code):
        return HttpResponseForbidden("Sessão expirada ou não verificada.")
    ap = target.appointment
    date_str = (request.GET.get("date") or "").strip()
    if not date_str:
        return HttpResponseBadRequest("Informe uma data.")
    try:
        year, month, day = map(int, date_str.split("-"))
        target_date = dt.date(year, month, day)
    except Exception:
        return HttpResponseBadRequest("Data inválida.")
    if target_date < timezone.now().date():
        return HttpResponseBadRequest("Data inválida.")
    service = ap.service
    slots = generate_slots(service, target_date, ignore_appointment_id=str(ap.id))
    try:
        service_tz = ZoneInfo(service.timezone or "UTC")
    except Exception:
        service_tz = ZoneInfo("UTC")
    selected_value = (request.GET.get("selected") or request.GET.get("slot") or "").strip()
    labeled = []
    for sl in slots:
        try:
            start = dt.datetime.fromisoformat(sl["start_at_utc"]).astimezone(service_tz)
        except Exception:
            continue
        label = start.strftime("%H:%M")
        labeled.append({
            "value": sl["start_at_utc"],
            "label": label,
            "selected": selected_value == sl["start_at_utc"],
        })
    context = {
        "slots": labeled,
    }
    return render(request, "viewer/_reschedule_slots.html", context)
