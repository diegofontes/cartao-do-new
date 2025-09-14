import datetime as dt
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from apps.billing.models import UsageEvent, Invoice, CustomerProfile
from apps.scheduling.models import Appointment, SchedulingService
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils.dateparse import parse_date
from zoneinfo import ZoneInfo
from math import ceil
from django.db.models import Q

def home(request):
    return redirect("dashboard:index")

@ensure_csrf_cookie
@login_required
def index(request):
    today = timezone.localdate()
    start = today.replace(day=1)
    month_events = UsageEvent.objects.filter(user=request.user, created_at__date__gte=start)
    month_units = sum(e.units for e in month_events)
    invoices = Invoice.objects.filter(user=request.user).order_by("-created_at")[:12]
    prof = CustomerProfile.objects.filter(user=request.user).first()
    return render(request, "dashboard/index.html", {
        "month_units": month_units,
        "invoices": invoices,
        "profile": prof,
    })


def _week_bounds(anchor: dt.date):
    # Monday as first day
    start = anchor - dt.timedelta(days=anchor.weekday())
    end = start + dt.timedelta(days=6)
    return start, end


@ensure_csrf_cookie
@login_required
def agenda(request):
    view = (request.GET.get("view") or "week").lower()
    anchor_str = request.GET.get("date") or ""
    # Robust parse: handle empty/invalid values gracefully
    anchor = timezone.localdate()
    if anchor_str:
        try:
            parsed = parse_date(anchor_str)
            if parsed:
                anchor = parsed
        except Exception:
            anchor = timezone.localdate()

    tz = timezone.get_current_timezone()

    if view == "day":
        start_date = anchor
        end_date = anchor
        header_range_label = anchor.strftime('%d/%m/%Y')
        prev = (anchor - dt.timedelta(days=1)).isoformat()
        next_ = (anchor + dt.timedelta(days=1)).isoformat()
        days = [{
            "iso": anchor.isoformat(),
            "label": anchor.strftime("%a %d/%m"),
        }]
    elif view == "month":
        # Range covering the whole calendar month grid (6 weeks view)
        first = anchor.replace(day=1)
        first_weekday = first.weekday()  # 0=Mon
        start_date = first - dt.timedelta(days=first_weekday)
        # 6 weeks grid
        end_date = start_date + dt.timedelta(days=41)
        header_range_label = anchor.strftime('%B %Y')
        # prev/next month
        prev_month = (first - dt.timedelta(days=1)).replace(day=1)
        next_month = (first + dt.timedelta(days=32)).replace(day=1)
        prev = prev_month.isoformat()
        next_ = next_month.isoformat()
        days = []  # not used by month grid
    else:  # week (default)
        week_start, week_end = _week_bounds(anchor)
        start_date, end_date = week_start, week_end
        header_range_label = f"{week_start.strftime('%d/%m')} – {week_end.strftime('%d/%m/%Y')}"
        prev = (anchor - dt.timedelta(days=7)).isoformat()
        next_ = (anchor + dt.timedelta(days=7)).isoformat()
        days = [{
            "iso": (week_start + dt.timedelta(days=i)).isoformat(),
            "label": (week_start + dt.timedelta(days=i)).strftime("%a %d/%m"),
        } for i in range(7)]

    context = {
        "view": view,
        "anchor": anchor,
        "today": timezone.localdate(),
        "prev": prev,
        "next": next_,
        "header_range_label": header_range_label,
        "tz_label": timezone.get_current_timezone_name(),
        "range_start_iso": dt.datetime.combine(start_date, dt.time(0, 0, tzinfo=tz)).isoformat(),
        "range_end_iso": dt.datetime.combine(end_date, dt.time(23, 59, tzinfo=tz)).isoformat(),
        "hours": list(range(24)),
        "days": days,
        # Month grid data
        "month_start": start_date,
        "month_end": end_date,
    }
    # Build month view helper weeks (list of weeks x 7 days) if needed
    if view == "month":
        # Fetch appointments for whole displayed month range
        start_dt = dt.datetime.combine(start_date, dt.time(0, 0, tzinfo=tz))
        end_dt = dt.datetime.combine(end_date, dt.time(23, 59, tzinfo=tz))
        aps = _user_appointments(request, start_dt, end_dt).select_related("service")
        status_filter = request.GET.get("status")
        if status_filter in {"pending", "confirmed", "denied", "cancelled"}:
            aps = aps.filter(status=status_filter)
        # Group events by local date (appointment timezone)
        from zoneinfo import ZoneInfo as _ZI
        events_by_date: dict[str, list[dict]] = {}
        for ap in aps:
            ap_tz = _ZI(ap.timezone or "UTC")
            s_local = ap.start_at_utc.astimezone(ap_tz)
            key = s_local.date().isoformat()
            events_by_date.setdefault(key, []).append({
                "id": ap.id,
                "time": s_local.strftime("%H:%M"),
                "service": ap.service.name,
                "status": ap.status,
            })
        # Build month grid with events embedded
        month_weeks = []
        cur = start_date
        for _ in range(6):
            week = []
            for _ in range(7):
                key = cur.isoformat()
                week.append({
                    "date": cur,
                    "label": cur.strftime('%d'),
                    "in_month": cur.month == anchor.month,
                    "events": events_by_date.get(key, []),
                })
                cur += dt.timedelta(days=1)
            month_weeks.append(week)
        context["month_weeks"] = month_weeks

    return render(request, "dashboard/agenda.html", context)


def _user_appointments(request, start: dt.datetime, end: dt.datetime):
    # Appointments whose service's card belongs to the logged user
    return (
        Appointment.objects
        .filter(service__card__owner=request.user)
        .filter(start_at_utc__lt=end, end_at_utc__gt=start)
    )


def _row_index(dtobj: dt.datetime):
    # minutes since midnight / 30 + 1 (1-based)
    minutes = dtobj.hour * 60 + dtobj.minute
    return minutes // 30 + 1


@login_required
def agenda_events(request):
    try:
        start = dt.datetime.fromisoformat(request.GET.get("start"))
        end = dt.datetime.fromisoformat(request.GET.get("end"))
    except Exception:
        return HttpResponseBadRequest("invalid range")
    view = (request.GET.get("view") or "week").lower()
    status_filter = request.GET.get("status")

    qs = _user_appointments(request, start, end)
    if status_filter in {"pending", "confirmed", "denied", "cancelled"}:
        qs = qs.filter(status=status_filter)

    events = []
    week_start_date = start.date()
    for ap in qs.select_related("service", "service__card"):
        # Use service timezone for display
        tz = ZoneInfo(ap.timezone or "UTC")
        s_local = ap.start_at_utc.astimezone(tz)
        e_local = ap.end_at_utc.astimezone(tz)
        day_col = (s_local.date() - week_start_date).days + 1
        rs = _row_index(s_local)
        re_ = max(rs + ceil((e_local - s_local).total_seconds() / 60 / 30), rs + 1)
        events.append({
            "id": ap.id,
            "customer_name": ap.user_name,
            "service_name": ap.service.name,
            "status": ap.status,
            "day_col": day_col,
            "row_start": rs,
            "row_end": re_,
            "start_label": s_local.strftime("%H:%M"),
            "end_label": e_local.strftime("%H:%M"),
        })
    return render(request, "dashboard/_events.html", {"events": events})


@login_required
def agenda_event_sidebar(request, id):
    ap = get_object_or_404(Appointment, id=id, service__card__owner=request.user)
    tz = ZoneInfo(ap.timezone or "UTC")
    s_local = ap.start_at_utc.astimezone(tz)
    e_local = ap.end_at_utc.astimezone(tz)
    return render(request, "dashboard/_event_sidebar.html", {
        "ap": ap,
        "start_local": s_local.strftime("%d/%m %H:%M"),
        "end_local": e_local.strftime("%H:%M"),
        "tz_label": ap.timezone,
    })


@login_required
def agenda_event_approve(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    ap = get_object_or_404(Appointment, id=id, service__card__owner=request.user)
    if ap.status != "pending":
        return HttpResponseBadRequest("invalid state")
    ap.status = "confirmed"
    ap.save(update_fields=["status"])
    resp = render(request, "dashboard/_event_sidebar.html", {"ap": ap})
    resp["HX-Trigger"] = "agenda:refresh"
    return resp


@login_required
def agenda_event_deny(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    ap = get_object_or_404(Appointment, id=id, service__card__owner=request.user)
    if ap.status != "pending":
        return HttpResponseBadRequest("invalid state")
    ap.status = "denied"
    ap.save(update_fields=["status"])
    resp = render(request, "dashboard/_event_sidebar.html", {"ap": ap})
    resp["HX-Trigger"] = "agenda:refresh"
    return resp
