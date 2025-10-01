import datetime as dt
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from apps.billing.models import UsageEvent, Invoice, CustomerProfile
from apps.scheduling.models import Appointment, SchedulingService
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils.dateparse import parse_date
from zoneinfo import ZoneInfo
from math import ceil
from django.db.models import Q
from django.utils.formats import date_format

def home(request):
    return redirect("dashboard:index")

@ensure_csrf_cookie
@login_required
def index(request):
    today = timezone.localdate()
    start = today.replace(day=1)
    period_start = start.isoformat()
    period_end = today.isoformat()
    current_month = today.strftime("%Y-%m")
    prof = CustomerProfile.objects.filter(user=request.user).first()
    paid_invoices = Invoice.objects.filter(user=request.user, status="paid").order_by("-created_at")[:12]
    return render(request, "dashboard/index.html", {
        "profile": prof,
        "period_start": period_start,
        "period_end": period_end,
        "current_month": current_month,
        "paid_invoices": paid_invoices,
    })


def _week_bounds(anchor: dt.date):
    # Monday as first day
    start = anchor - dt.timedelta(days=anchor.weekday())
    end = start + dt.timedelta(days=6)
    return start, end


@ensure_csrf_cookie
@login_required
def agenda(request):
    view = (request.GET.get("view") or "list").lower()
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

    # Shortcut: render list (timeline) shell and exit. The list body loads via HTMX.
    if view == "list":
        return render(request, "dashboard/agenda.html", {
            "view": view,
            "today": timezone.localdate(),
            "anchor": timezone.localdate(),
            "tz_label": timezone.get_current_timezone_name(),
        })

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
    # Normalize ISO datetimes from query (handle '+' being turned into space and optional 'Z')
    def _norm_iso(s: str | None) -> str:
        if not s:
            return ""
        s = s.strip().replace(" ", "+")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return s
    try:
        start = dt.datetime.fromisoformat(_norm_iso(request.GET.get("start")))
        end = dt.datetime.fromisoformat(_norm_iso(request.GET.get("end")))
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


# ---------- Timeline (List) endpoints ----------

def _norm_iso(s: str | None) -> str:
    if not s:
        return ""
    s = s.strip().replace(" ", "+")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return s


@login_required
def agenda_list_partial(request):
    """HTMX-friendly timeline list partial.
    Supports filters and pagination by day-window with a datetime cursor.
    """
    # If not an HTMX request, render the full shell (list view) instead of the partial
    if not getattr(request, "htmx", False):
        return render(request, "dashboard/agenda.html", {
            "view": "list",
            "today": timezone.localdate(),
            "anchor": timezone.localdate(),
            "tz_label": timezone.get_current_timezone_name(),
        })
    DAYS_WINDOW = 5

    # Filters
    status_ = (request.GET.get("status") or "").strip().lower()
    service_id = request.GET.get("service_id")
    card_id = request.GET.get("card_id")
    channel = (request.GET.get("channel") or "").strip().lower()  # local/remote/onsite
    # Separate filters: name and contact (phone/email). Keep q for backward compat.
    name_q = (request.GET.get("name") or "").strip()
    contact_q = (request.GET.get("contact") or "").strip()
    q = (request.GET.get("q") or "").strip()

    # Range and cursor
    tz_user = timezone.get_current_timezone()
    today_local = timezone.localdate()
    start_qs = request.GET.get("start")
    end_qs = request.GET.get("end")
    cursor_qs = request.GET.get("cursor")

    # Start baseline: from cursor+1s, else from start date, else today at 00:00 local
    start_dt_local: dt.datetime
    if cursor_qs:
        try:
            cursor = dt.datetime.fromisoformat(_norm_iso(cursor_qs))
        except Exception:
            return HttpResponseBadRequest("invalid cursor")
        start_dt_local = cursor.astimezone(tz_user) + dt.timedelta(seconds=1)
    elif start_qs:
        # Accept ISO datetime or YYYY-MM-DD
        try:
            s_norm = _norm_iso(start_qs)
            if "T" in s_norm or s_norm.endswith("+00:00"):
                d = dt.datetime.fromisoformat(s_norm)
                start_dt_local = d.astimezone(tz_user)
            else:
                d_date = parse_date(start_qs)
                if not d_date:
                    return HttpResponseBadRequest("invalid start")
                start_dt_local = dt.datetime.combine(d_date, dt.time(0, 0, tzinfo=tz_user))
        except Exception:
            return HttpResponseBadRequest("invalid start")
    else:
        start_dt_local = dt.datetime.combine(today_local, dt.time(0, 0, tzinfo=tz_user))

    if end_qs:
        try:
            e_norm = _norm_iso(end_qs)
            if "T" in e_norm or e_norm.endswith("+00:00"):
                end_dt_local = dt.datetime.fromisoformat(e_norm).astimezone(tz_user)
            else:
                e_date = parse_date(end_qs)
                if not e_date:
                    return HttpResponseBadRequest("invalid end")
                end_dt_local = dt.datetime.combine(e_date, dt.time(23, 59, 59, tzinfo=tz_user))
        except Exception:
            return HttpResponseBadRequest("invalid end")
    else:
        # Provisional end: +60 days; we will trim to DAYS_WINDOW groups
        end_dt_local = start_dt_local + dt.timedelta(days=60)

    start_utc = start_dt_local.astimezone(ZoneInfo("UTC"))
    end_utc = end_dt_local.astimezone(ZoneInfo("UTC"))

    qs = (
        Appointment.objects
        .filter(service__card__owner=request.user)
        .filter(start_at_utc__gte=start_utc, start_at_utc__lte=end_utc)
        .select_related("service", "service__card")
        .order_by("start_at_utc")
    )
    if status_ in {"pending", "confirmed", "denied", "cancelled", "no_show"}:
        qs = qs.filter(status=status_)
    if service_id:
        qs = qs.filter(service_id=service_id)
    if card_id:
        qs = qs.filter(service__card_id=card_id)
    if channel in {"local", "remote", "onsite"}:
        qs = qs.filter(location_choice=channel)
    # Name filter
    if name_q:
        qs = qs.filter(
            Q(user_name__icontains=name_q) | Q(service__card__nickname__icontains=name_q)
        )
    # Contact filter: only on confirmed
    if contact_q:
        qs = qs.filter(
            Q(status="confirmed") & (Q(user_email__icontains=contact_q) | Q(user_phone__icontains=contact_q))
        )
    # Backward compatibility single box
    if q and not (name_q or contact_q):
        qs = qs.filter(
            Q(user_name__icontains=q)
            | (Q(status="confirmed") & (Q(user_email__icontains=q) | Q(user_phone__icontains=q)))
            | Q(service__card__nickname__icontains=q)
        )

    # Build day groups (in user's timezone)
    groups: list[dict] = []
    current_day: dt.date | None = None
    items_this_day: list[dict] = []
    days_count = 0
    last_day_end_local: dt.datetime | None = None

    def flush_day(day: dt.date, items: list[dict]):
        nonlocal groups
        if day is None:
            return
        # Localized label per Django's current LANGUAGE_CODE (e.g., pt-BR)
        try:
            label = date_format(day, "D, d M").title()
        except Exception:
            label = day.strftime("%a, %d %b").title()
        groups.append({
            "date_iso": day.isoformat(),
            "label": label,
            "count": len(items),
            "items": items[:],
        })

    for ap in qs.iterator():
        s_local = ap.start_at_utc.astimezone(tz_user)
        e_local = ap.end_at_utc.astimezone(tz_user)
        d = s_local.date()
        if current_day is None:
            current_day = d
            items_this_day = []
        if d != current_day:
            flush_day(current_day, items_this_day)
            days_count += 1
            if days_count >= DAYS_WINDOW:
                # Stop, set cursor to the end of the last flushed day
                last_day_end_local = dt.datetime.combine(current_day, dt.time(23, 59, 59, tzinfo=tz_user))
                current_day = None
                items_this_day = []
                break
            current_day = d
            items_this_day = []

        duration_min = int((e_local - s_local).total_seconds() // 60)
        show_contact = (ap.status == "confirmed")
        items_this_day.append({
            "id": ap.id,
            "start_label": s_local.strftime("%H:%M"),
            "end_label": e_local.strftime("%H:%M"),
            "duration_min": duration_min,
            "status": ap.status,
            "status_label": ap.status.capitalize(),
            "customer_name": ap.user_name,
            "phone": ap.user_phone if show_contact else "",
            "email": ap.user_email if show_contact else "",
            "service_name": ap.service.name,
            "card_nick": getattr(ap.service.card, "nickname", "") or "",
            "channel": ap.location_choice,
            "channel_label": {
                "local": "Local",
                "remote": "Remoto",
                "onsite": "Visita",
            }.get(ap.location_choice, ap.location_choice),
            "address_or_link": _fmt_address_or_link(ap),
        })

    # If we broke early due to DAYS_WINDOW, compute next_cursor
    if last_day_end_local is None:
        # We either exhausted all items or still in the last day
        if current_day is not None:
            flush_day(current_day, items_this_day)
            if groups:
                last_day = dt.date.fromisoformat(groups[-1]["date_iso"])  # type: ignore[arg-type]
                last_day_end_local = dt.datetime.combine(last_day, dt.time(23, 59, 59, tzinfo=tz_user))

    next_cursor = None
    if groups and last_day_end_local is not None:
        next_cursor = last_day_end_local.astimezone(ZoneInfo("UTC")).isoformat()

    context = {
        "groups": groups,
        "next_cursor": next_cursor,
    }
    return render(request, "dashboard/_agenda_list.html", context)


def _fmt_address_or_link(ap: Appointment) -> str:
    try:
        if ap.location_choice == "remote" and ap.service.video_link_template:
            return ap.service.video_link_template
        if ap.location_choice in {"local", "onsite"}:
            addr = ap.address_json or {}
            parts = [addr.get(k, "") for k in ("street", "number", "city")]
            s = ", ".join([p for p in parts if p])
            return s
    except Exception:
        return ""
    return ""


@login_required
def agenda_list_confirm(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    ap = get_object_or_404(Appointment, id=id, service__card__owner=request.user)
    if ap.status != "pending":
        return HttpResponseBadRequest("invalid state")
    ap.status = "confirmed"
    ap.save(update_fields=["status"])
    item_html = render_to_string("dashboard/_agenda_list_item.html", {"it": _item_dto(ap)}, request=request)
    sidebar_html = render_to_string("dashboard/_event_sidebar.html", {
        "ap": ap,
        "start_local": ap.start_at_utc.astimezone(ZoneInfo(ap.timezone or "UTC")).strftime("%d/%m %H:%M"),
        "end_local": ap.end_at_utc.astimezone(ZoneInfo(ap.timezone or "UTC")).strftime("%H:%M"),
        "tz_label": ap.timezone,
        "oob": True,
    }, request=request)
    html = item_html + sidebar_html
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Agendamento atualizado"}})
    return resp


@login_required
def agenda_list_reject(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    ap = get_object_or_404(Appointment, id=id, service__card__owner=request.user)
    # Using "denied" to mirror current calendar endpoints behavior
    if ap.status != "pending":
        return HttpResponseBadRequest("invalid state")
    ap.status = "denied"
    ap.save(update_fields=["status"])
    item_html = render_to_string("dashboard/_agenda_list_item.html", {"it": _item_dto(ap)}, request=request)
    sidebar_html = render_to_string("dashboard/_event_sidebar.html", {
        "ap": ap,
        "start_local": ap.start_at_utc.astimezone(ZoneInfo(ap.timezone or "UTC")).strftime("%d/%m %H:%M"),
        "end_local": ap.end_at_utc.astimezone(ZoneInfo(ap.timezone or "UTC")).strftime("%H:%M"),
        "tz_label": ap.timezone,
        "oob": True,
    }, request=request)
    html = item_html + sidebar_html
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Agendamento atualizado"}})
    return resp


@login_required
def agenda_list_cancel(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    ap = get_object_or_404(Appointment, id=id, service__card__owner=request.user)
    if ap.status not in {"pending", "confirmed"}:
        return HttpResponseBadRequest("invalid state")
    ap.status = "cancelled"
    ap.save(update_fields=["status"])
    item_html = render_to_string("dashboard/_agenda_list_item.html", {"it": _item_dto(ap)}, request=request)
    sidebar_html = render_to_string("dashboard/_event_sidebar.html", {
        "ap": ap,
        "start_local": ap.start_at_utc.astimezone(ZoneInfo(ap.timezone or "UTC")).strftime("%d/%m %H:%M"),
        "end_local": ap.end_at_utc.astimezone(ZoneInfo(ap.timezone or "UTC")).strftime("%H:%M"),
        "tz_label": ap.timezone,
        "oob": True,
    }, request=request)
    html = item_html + sidebar_html
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Agendamento atualizado"}})
    return resp


def _item_dto(ap: Appointment) -> dict:
    tz_user = timezone.get_current_timezone()
    s_local = ap.start_at_utc.astimezone(tz_user)
    e_local = ap.end_at_utc.astimezone(tz_user)
    duration_min = int((e_local - s_local).total_seconds() // 60)
    show_contact = (ap.status == "confirmed")
    return {
        "id": ap.id,
        "start_label": s_local.strftime("%H:%M"),
        "end_label": e_local.strftime("%H:%M"),
        "duration_min": duration_min,
        "status": ap.status,
        "status_label": ap.status.capitalize(),
        "customer_name": ap.user_name,
        "phone": ap.user_phone if show_contact else "",
        "email": ap.user_email if show_contact else "",
        "service_name": ap.service.name,
        "card_nick": getattr(ap.service.card, "nickname", "") or "",
        "channel": ap.location_choice,
        "channel_label": {
            "local": "Local",
            "remote": "Remoto",
            "onsite": "Visita",
        }.get(ap.location_choice, ap.location_choice),
        "address_or_link": _fmt_address_or_link(ap),
    }


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
    tz = ZoneInfo(ap.timezone or "UTC")
    s_local = ap.start_at_utc.astimezone(tz)
    e_local = ap.end_at_utc.astimezone(tz)
    resp = render(request, "dashboard/_event_sidebar.html", {
        "ap": ap,
        "start_local": s_local.strftime("%d/%m %H:%M"),
        "end_local": e_local.strftime("%H:%M"),
        "tz_label": ap.timezone,
    })
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
    tz = ZoneInfo(ap.timezone or "UTC")
    s_local = ap.start_at_utc.astimezone(tz)
    e_local = ap.end_at_utc.astimezone(tz)
    resp = render(request, "dashboard/_event_sidebar.html", {
        "ap": ap,
        "start_local": s_local.strftime("%d/%m %H:%M"),
        "end_local": e_local.strftime("%H:%M"),
        "tz_label": ap.timezone,
    })
    resp["HX-Trigger"] = "agenda:refresh"
    return resp
