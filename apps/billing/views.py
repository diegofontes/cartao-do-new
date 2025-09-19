import json
import random
from django.contrib.auth.decorators import login_required
import logging
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

from django.conf import settings
from .services import create_setup_intent, attach_payment_method, get_or_create_stripe_customer
from .models import UsageEvent, CustomerProfile
from apps.metering.models import MeteringEvent
from apps.metering.utils import resolve_unit_price
from apps.cards.models import Card
from django.utils import timezone
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta, time
from django.db.models import Sum, F, ExpressionWrapper, IntegerField, Count

log = logging.getLogger(__name__)

@ensure_csrf_cookie
@login_required
def payment_method(request):
    prof = CustomerProfile.objects.filter(user=request.user).first()
    publishable = settings.STRIPE_PUBLISHABLE_KEY
    return render(request, "billing/payment_method.html", {"profile": prof, "pk": publishable})

@login_required
def create_setup_intent_view(request):
    si = create_setup_intent(request.user)
    log.info("[billing] API create_setup_intent user_id=%s si_id=%s", request.user.id, si.get("id"))
    return JsonResponse({"clientSecret": si["client_secret"]})

@login_required
def attach_payment_method_view(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    pm = request.POST.get("payment_method_id")
    log.info("[billing] API attach_payment_method user_id=%s pm_id=%s", request.user.id, pm)
    if not pm:
        return HttpResponseBadRequest("missing payment_method_id")
    prof = attach_payment_method(request.user, pm)
    return render(request, "billing/_card_info.html", {"profile": prof})

@login_required
def cancel_view(request):
    prof = CustomerProfile.objects.get(user=request.user)
    prof.is_active = False
    prof.save(update_fields=["is_active"])
    return redirect("dashboard:index")

@login_required
def simulate_usage(request):
    units = int(request.POST.get("units") or random.randint(1, 5))
    UsageEvent.objects.create(user=request.user, units=units)
    # retorna parcial para HTMX atualizar contador
    month_units = UsageEvent.objects.filter(user=request.user).count()
    return render(request, "dashboard/_usage_stats.html", {"month_units": month_units})


# ------------------- Billing KPIs / Preview / Self-checks -------------------

def _current_billing_window(user):
    today = timezone.localdate()
    start = datetime.combine(today.replace(day=1), time.min, tzinfo=timezone.get_current_timezone())
    end = timezone.now()
    return start, end


def _parse_range(request):
    s = request.GET.get("start")
    e = request.GET.get("end")
    period = request.GET.get("period")  # YYYY-MM
    tz = timezone.get_current_timezone()
    if period and len(period) == 7 and period[4] == '-':
        try:
            year = int(period[:4]); month = int(period[5:7])
            ds = timezone.datetime(year, month, 1, tzinfo=tz)
            start = ds
            # compute end = start of next month - tiny
            if month == 12:
                de = timezone.datetime(year+1, 1, 1, tzinfo=tz)
            else:
                de = timezone.datetime(year, month+1, 1, tzinfo=tz)
            end = de
            return start, end
        except Exception:
            pass
    if s:
        try:
            ds = parse_date(s)
            start = datetime.combine(ds, time.min, tzinfo=tz)
        except Exception:
            start, _ = _current_billing_window(request.user)
    else:
        start, _ = _current_billing_window(request.user)
    if e:
        try:
            de = parse_date(e)
            end = datetime.combine(de, time.max, tzinfo=tz)
        except Exception:
            _, end = _current_billing_window(request.user)
    else:
        _, end = _current_billing_window(request.user)
    return start, end


def _fmt_brl(cents: int) -> str:
    try:
        v = (cents or 0) / 100.0
        txt = f"{v:,.2f}"
        return "R$ " + txt.replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"R$ {cents/100:.2f}"


@login_required
def kpis_view(request):
    start, end = _parse_range(request)
    # Cards faturáveis no fechamento: published (inclui marcados)
    cards_published = Card.objects.filter(owner=request.user, status="published").count()
    # Agendamentos aprovados no período (per-event)
    base = MeteringEvent.objects.filter(user=request.user, occurred_at__gte=start, occurred_at__lt=end, resource_type="appointment", event_type="appointment_confirmed")
    appointments_confirmed = base.count()
    # Valores (prévia): cards monthly + appointments
    card_unit = resolve_unit_price("card", "publish", when=end)
    appt_unit = resolve_unit_price("appointment", "appointment_confirmed", when=end)
    total_cents = cards_published * (card_unit or 0) + appointments_confirmed * (appt_unit or 0)
    return render(request, "billing/_kpis.html", {
        "cards_published": cards_published,
        "appointments_confirmed": appointments_confirmed,
        "total_cents": total_cents,
        "total_brl": _fmt_brl(total_cents),
    })


@login_required
def preview_view(request):
    start, end = _parse_range(request)
    # Build two-row preview: cards monthly and appointments per-event
    rows = []
    cards_published = Card.objects.filter(owner=request.user, status="published").count()
    card_unit = resolve_unit_price("card", "publish", when=end)
    cards_subtotal = cards_published * (card_unit or 0)
    rows.append({"resource_type": "card", "event_type": "monthly_count", "events": cards_published, "subtotal_cents": cards_subtotal, "subtotal_brl": _fmt_brl(cards_subtotal)})
    appts = MeteringEvent.objects.filter(user=request.user, occurred_at__gte=start, occurred_at__lt=end, resource_type="appointment", event_type="appointment_confirmed")
    appt_count = appts.count()
    appt_unit = resolve_unit_price("appointment", "appointment_confirmed", when=end)
    appt_subtotal = appt_count * (appt_unit or 0)
    rows.append({"resource_type": "appointment", "event_type": "appointment_confirmed", "events": appt_count, "subtotal_cents": appt_subtotal, "subtotal_brl": _fmt_brl(appt_subtotal)})
    total_cents = cards_subtotal + appt_subtotal
    return render(request, "billing/_preview.html", {
        "rows": rows,
        "total_cents": total_cents,
        "total_brl": _fmt_brl(total_cents),
        "start": start,
        "end": end,
    })


@login_required
def self_checks_view(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    start, end = _parse_range(request)
    user = request.user

    checks = []
    problems = []

    # Último evento recebido
    last_ev = MeteringEvent.objects.filter(user=user).order_by("-occurred_at").first()
    last_ts = last_ev.occurred_at if last_ev else None
    checks.append({"label": "Último evento recebido", "status": "OK" if last_ts else "WARN", "detail": last_ts or "Nenhum evento"})

    # Publicação de card — billing não usa mais evento publish; removido
    from apps.cards.models import Card, LinkButton, GalleryItem
    from apps.scheduling.models import Appointment
    from django.db.models import Q

    window_q = Q(occurred_at__gte=start - timedelta(minutes=5), occurred_at__lt=end + timedelta(minutes=5))

    # Removido: publish events não são mais faturados

    # Agendamento confirmado
    appts = Appointment.objects.filter(service__card__owner=user, status="confirmed", updated_at__gte=start, updated_at__lt=end)
    missing_ap = []
    for ap in appts:
        evs = MeteringEvent.objects.filter(user=user, resource_type="appointment", event_type="appointment_confirmed", appointment=ap).filter(window_q)
        if not evs.exists():
            missing_ap.append(str(ap.id))
    checks.append({"label": "Agendamento confirmado → appointment_confirmed", "status": "OK" if not missing_ap else "WARN", "detail": "OK" if not missing_ap else f"Faltando: {', '.join(missing_ap)}"})

    # Removidos: link/gallery não são faturados

    # Integridade de preço histórico
    mismatched = []
    evs = MeteringEvent.objects.filter(user=user, occurred_at__gte=start, occurred_at__lt=end, resource_type="appointment", event_type="appointment_confirmed")
    for ev in evs.only("id", "resource_type", "event_type", "occurred_at", "unit_price_cents"):
        ref = resolve_unit_price(ev.resource_type, ev.event_type, when=ev.occurred_at)
        if (ev.unit_price_cents or 0) != (ref or 0):
            mismatched.append(str(ev.id))
    checks.append({"label": "Preço aplicado compatível com regra vigente", "status": "OK" if not mismatched else "WARN", "detail": "OK" if not mismatched else f"Eventos divergentes: {', '.join(mismatched)}"})


@login_required
def archive_marked_cards_view(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    period_end_raw = request.GET.get("period_end") or request.POST.get("period_end")
    if not period_end_raw:
        return HttpResponseBadRequest("period_end required (YYYY-MM-DD)")
    try:
        pe = timezone.datetime.fromisoformat(period_end_raw).date()
    except Exception:
        return HttpResponseBadRequest("invalid period_end")
    user_id = request.GET.get("user_id") or request.POST.get("user_id")
    try:
        uid = int(user_id) if user_id else None
    except Exception:
        uid = None
    # Run synchronously (internal use)
    from .tasks import run_archive_marked_cards
    res = run_archive_marked_cards(pe, uid)
    return JsonResponse(res)

    return render(request, "billing/_self_checks.html", {"checks": checks})
