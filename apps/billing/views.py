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
    base = MeteringEvent.objects.filter(user=request.user, occurred_at__gte=start, occurred_at__lt=end)
    counts = {
        "cards_published": base.filter(resource_type="card", event_type="publish").count(),
        "appointments_confirmed": base.filter(resource_type="appointment", event_type="appointment_confirmed").count(),
        "links_added": base.filter(resource_type="link", event_type="link_add").count(),
        "gallery_items": base.filter(resource_type="gallery", event_type="gallery_add").count(),
    }
    subtotal_expr = ExpressionWrapper(F("quantity") * F("unit_price_cents"), output_field=IntegerField())
    total_cents = base.aggregate(total=Sum(subtotal_expr)).get("total") or 0
    return render(request, "billing/_kpis.html", {
        **counts,
        "total_cents": total_cents,
        "total_brl": _fmt_brl(total_cents),
    })


@login_required
def preview_view(request):
    start, end = _parse_range(request)
    base = MeteringEvent.objects.filter(user=request.user, occurred_at__gte=start, occurred_at__lt=end)
    subtotal_expr = ExpressionWrapper(F("quantity") * F("unit_price_cents"), output_field=IntegerField())
    rows = (
        base.values("resource_type", "event_type")
        .annotate(events=Count("id"), subtotal_cents=Sum(subtotal_expr))
        .order_by("resource_type", "event_type")
    )
    total_cents = sum((r["subtotal_cents"] or 0) for r in rows)
    for r in rows:
        r["subtotal_brl"] = _fmt_brl(r.get("subtotal_cents") or 0)
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

    # Publicação de card
    from apps.cards.models import Card, LinkButton, GalleryItem
    from apps.scheduling.models import Appointment
    from django.db.models import Q

    window_q = Q(occurred_at__gte=start - timedelta(minutes=5), occurred_at__lt=end + timedelta(minutes=5))

    cards = Card.objects.filter(owner=user, status="published", published_at__gte=start, published_at__lt=end)
    missing_cards = []
    dup_cards = []
    for c in cards:
        evs = MeteringEvent.objects.filter(user=user, resource_type="card", event_type="publish", card=c).filter(window_q)
        if not evs.exists():
            missing_cards.append(str(c.id))
        elif evs.count() > 1:
            dup_cards.append(str(c.id))
    status = "OK" if not missing_cards and not dup_cards else "WARN"
    detail = "OK" if status == "OK" else f"Faltando: {', '.join(missing_cards)}; Duplicados: {', '.join(dup_cards)}"
    checks.append({"label": "Card publicado → evento publish", "status": status, "detail": detail})

    # Agendamento confirmado
    appts = Appointment.objects.filter(service__card__owner=user, status="confirmed", updated_at__gte=start, updated_at__lt=end)
    missing_ap = []
    for ap in appts:
        evs = MeteringEvent.objects.filter(user=user, resource_type="appointment", event_type="appointment_confirmed", appointment=ap).filter(window_q)
        if not evs.exists():
            missing_ap.append(str(ap.id))
    checks.append({"label": "Agendamento confirmado → appointment_confirmed", "status": "OK" if not missing_ap else "WARN", "detail": "OK" if not missing_ap else f"Faltando: {', '.join(missing_ap)}"})

    # Link criado
    links = LinkButton.objects.filter(card__owner=user, created_at__gte=start, created_at__lt=end)
    missing_links = []
    for lb in links:
        evs = MeteringEvent.objects.filter(user=user, resource_type="link", event_type="link_add", card=lb.card).filter(window_q)
        if not evs.exists():
            missing_links.append(str(lb.id))
    checks.append({"label": "Link criado → link_add", "status": "OK" if not missing_links else "WARN", "detail": "OK" if not missing_links else f"Faltando: {', '.join(missing_links)}"})

    # Item de galeria criado
    items = GalleryItem.objects.filter(card__owner=user, created_at__gte=start, created_at__lt=end)
    missing_g = []
    for gi in items:
        evs = MeteringEvent.objects.filter(user=user, resource_type="gallery", event_type="gallery_add", card=gi.card).filter(window_q)
        if not evs.exists():
            missing_g.append(str(gi.id))
    checks.append({"label": "Item de galeria criado → gallery_add", "status": "OK" if not missing_g else "WARN", "detail": "OK" if not missing_g else f"Faltando: {', '.join(missing_g)}"})

    # Integridade de preço histórico
    mismatched = []
    evs = MeteringEvent.objects.filter(user=user, occurred_at__gte=start, occurred_at__lt=end)
    for ev in evs.only("id", "resource_type", "event_type", "occurred_at", "unit_price_cents"):
        ref = resolve_unit_price(ev.resource_type, ev.event_type, when=ev.occurred_at)
        if (ev.unit_price_cents or 0) != (ref or 0):
            mismatched.append(str(ev.id))
    checks.append({"label": "Preço aplicado compatível com regra vigente", "status": "OK" if not mismatched else "WARN", "detail": "OK" if not mismatched else f"Eventos divergentes: {', '.join(mismatched)}"})

    return render(request, "billing/_self_checks.html", {"checks": checks})
