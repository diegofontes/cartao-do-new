from django.contrib.auth.decorators import login_required
import json
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_date
from .models import SchedulingService, Appointment, ServiceAvailability, ServiceOption
from django.utils import timezone
import datetime as dt
from zoneinfo import ZoneInfo
from .slots import generate_slots, prepare_booking
from .forms import SchedulingServiceForm, ServiceAvailabilityForm, ServiceOptionForm
from apps.cards.models import Card
from django.core.exceptions import ValidationError
from apps.notifications.api import enqueue
from django.conf import settings
from zoneinfo import ZoneInfo


@login_required
def list_slots(request, id):
    service = get_object_or_404(SchedulingService, id=id, card__owner=request.user)
    date_str = request.GET.get("date")
    if not date_str:
        return HttpResponseBadRequest("date is required")
    date = parse_date(date_str)
    if not date:
        return HttpResponseBadRequest("invalid date")
    slots = generate_slots(service, date)
    return JsonResponse({"service": str(service.id), "date": date_str, "slots": slots})


@login_required
def create_appointment(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    service = get_object_or_404(SchedulingService, id=id, card__owner=request.user)
    start = request.POST.get("start_at_utc")
    end = request.POST.get("end_at_utc")
    option_ids = request.POST.getlist("options")
    if not (start and end):
        return HttpResponseBadRequest("start_at_utc and end_at_utc required")
    try:
        s = dt.datetime.fromisoformat(start)
        e = dt.datetime.fromisoformat(end)
    except ValueError:
        return HttpResponseBadRequest("invalid datetime format")
    # Basic validation: must match a generated slot
    try:
        booking = prepare_booking(service, s, option_ids)
    except ValidationError as exc:
        return HttpResponseBadRequest(str(exc))
    # Ensure client-sent end matches expected window
    if e != booking["end_at"]:
        return HttpResponseBadRequest("slot duration mismatch")
    appt = Appointment.objects.create(
        service=service,
        user_name=request.POST.get("user_name", ""),
        user_email=request.POST.get("user_email", ""),
        user_phone=request.POST.get("user_phone", ""),
        start_at_utc=s,
        end_at_utc=booking["end_at"],
        timezone=request.POST.get("timezone", service.timezone),
        location_choice=request.POST.get("location_choice", service.type),
        form_answers_json={},
        options_snapshot_json=booking["options_snapshot"],
        base_price_cents=booking["base_price_cents"],
        price_cents=booking["price_cents"],
        status="pending",
    )
    # Notify card owner via SMS (best effort)
    try:
        card = service.card
        if getattr(card, 'notification_phone', None):
            try:
                tz = ZoneInfo(service.timezone or "UTC")
            except Exception:
                tz = ZoneInfo("UTC")
            s_local = s.astimezone(tz)
            date_label = s_local.strftime("%d/%m")
            time_label = s_local.strftime("%H:%M")
            base = (getattr(settings, 'DASHBOARD_BASE_URL', '') or '').rstrip('/')
            path = "/agenda/list?status=pending&contact=&start=&end="
            agenda_url = f"{base}{path}" if base else path
            enqueue(
                type='sms',
                to=card.notification_phone,
                template_code='owner_new_booking',
                payload={'service': service.name, 'date': date_label, 'time': time_label, 'agenda_url': agenda_url},
                idempotency_key=f'owner_new_booking:{appt.id}'
            )
    except Exception:
        pass
    return JsonResponse({"ok": True, "id": str(appt.id)})


# ---------- HTMX CRUD for SchedulingService ----------

@login_required
def services_partial(request, card_id):
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    services = SchedulingService.objects.filter(card=card).order_by("-created_at")
    return render(request, "scheduling/_services.html", {"card": card, "services": services})


@login_required
def service_form(request, card_id, id=None):
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    if id:
        svc = get_object_or_404(SchedulingService, id=id, card=card)
    else:
        svc = None
    form = SchedulingServiceForm(instance=svc)
    return render(request, "scheduling/_service_form.html", {"card": card, "form": form, "service": svc})


@login_required
def service_save(request, card_id, id=None):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    if id:
        svc = get_object_or_404(SchedulingService, id=id, card=card)
        form = SchedulingServiceForm(request.POST, instance=svc)
    else:
        form = SchedulingServiceForm(request.POST)
    if form.is_valid():
        # Enforce per-card service limit (10) with a lock
        from django.db import transaction
        with transaction.atomic():
            c = Card.objects.select_for_update().get(pk=card.pk)
            if SchedulingService.objects.filter(card=c).count() >= 10:
                res = render(request, "scheduling/_service_form.html", {"card": card, "form": form, "service": id and (svc if id else None), "error": "Limite atingido para serviços (10)."})
                res.status_code = 422
                res["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Limite atingido", "message": "Limite atingido para serviços (10)."}})
                return res
            svc = form.save(commit=False)
            svc.card = c
            svc.save()
        # after save, refresh the list
        services = SchedulingService.objects.filter(card=card).order_by("-created_at")
        resp = render(request, "scheduling/_services.html", {"card": card, "services": services})
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Feito!", "message": "Serviço salvo."}})
        return resp
    # invalid -> re-render form
    res = render(request, "scheduling/_service_form.html", {"card": card, "form": form, "service": id and (svc if id else None)})
    res.status_code = 422
    return res


@login_required
def service_delete(request, card_id, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    svc = get_object_or_404(SchedulingService, id=id, card=card)
    svc.delete()
    services = SchedulingService.objects.filter(card=card).order_by("-created_at")
    return render(request, "scheduling/_services.html", {"card": card, "services": services})


# ---------- Service Options HTMX CRUD ----------


@login_required
def options_partial(request, card_id, service_id):
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    svc = get_object_or_404(SchedulingService, id=service_id, card=card)
    items = ServiceOption.objects.filter(service=svc).order_by("order", "name")
    return render(request, "scheduling/_options.html", {"card": card, "service": svc, "items": items})


@login_required
def option_form(request, card_id, service_id, id=None):
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    svc = get_object_or_404(SchedulingService, id=service_id, card=card)
    if id:
        opt = get_object_or_404(ServiceOption, id=id, service=svc)
    else:
        opt = None
    form = ServiceOptionForm(instance=opt)
    return render(request, "scheduling/_option_form.html", {"card": card, "service": svc, "form": form, "item": opt})


@login_required
def option_save(request, card_id, service_id, id=None):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    svc = get_object_or_404(SchedulingService, id=service_id, card=card)
    if id:
        opt = get_object_or_404(ServiceOption, id=id, service=svc)
        form = ServiceOptionForm(request.POST, instance=opt)
    else:
        form = ServiceOptionForm(request.POST)
    if form.is_valid():
        opt = form.save(commit=False)
        opt.service = svc
        opt.save()
        items = ServiceOption.objects.filter(service=svc).order_by("order", "name")
        resp = render(request, "scheduling/_options.html", {"card": card, "service": svc, "items": items})
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Salvo", "message": "Opção atualizada."}})
        return resp
    res = render(request, "scheduling/_option_form.html", {"card": card, "service": svc, "form": form, "item": id and opt})
    res.status_code = 422
    return res


@login_required
def option_delete(request, card_id, service_id, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    svc = get_object_or_404(SchedulingService, id=service_id, card=card)
    opt = get_object_or_404(ServiceOption, id=id, service=svc)
    opt.delete()
    items = ServiceOption.objects.filter(service=svc).order_by("order", "name")
    return render(request, "scheduling/_options.html", {"card": card, "service": svc, "items": items})


# ---------- Availability HTMX CRUD ----------

@login_required
def availability_partial(request, card_id, service_id):
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    svc = get_object_or_404(SchedulingService, id=service_id, card=card)
    items = ServiceAvailability.objects.filter(service=svc).order_by("rule_type", "weekday", "date", "start_time")
    return render(request, "scheduling/_availability.html", {"card": card, "service": svc, "items": items})


@login_required
def availability_form(request, card_id, service_id, id=None):
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    svc = get_object_or_404(SchedulingService, id=service_id, card=card)
    if id:
        av = get_object_or_404(ServiceAvailability, id=id, service=svc)
    else:
        av = None
    form = ServiceAvailabilityForm(instance=av)
    return render(request, "scheduling/_availability_form.html", {"card": card, "service": svc, "form": form, "item": av})


@login_required
def availability_save(request, card_id, service_id, id=None):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    svc = get_object_or_404(SchedulingService, id=service_id, card=card)
    if id:
        av = get_object_or_404(ServiceAvailability, id=id, service=svc)
        form = ServiceAvailabilityForm(request.POST, instance=av)
    else:
        form = ServiceAvailabilityForm(request.POST)
    if form.is_valid():
        av = form.save(commit=False)
        av.service = svc
        av.save()
        items = ServiceAvailability.objects.filter(service=svc).order_by("rule_type", "weekday", "date", "start_time")
        return render(request, "scheduling/_availability.html", {"card": card, "service": svc, "items": items})
    return render(request, "scheduling/_availability_form.html", {"card": card, "service": svc, "form": form, "item": id and av})


@login_required
def availability_delete(request, card_id, service_id, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    svc = get_object_or_404(SchedulingService, id=service_id, card=card)
    av = get_object_or_404(ServiceAvailability, id=id, service=svc)
    av.delete()
    items = ServiceAvailability.objects.filter(service=svc).order_by("rule_type", "weekday", "date", "start_time")
    return render(request, "scheduling/_availability.html", {"card": card, "service": svc, "items": items})
