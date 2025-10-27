import datetime as dt
import json
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from apps.billing.models import UsageEvent, Invoice, CustomerProfile
from apps.scheduling.models import Appointment, SchedulingService, RescheduleRequest
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils.dateparse import parse_date
from zoneinfo import ZoneInfo
from math import ceil
from django.db.models import Q, Prefetch
from django.utils.formats import date_format
from django.db import transaction

from apps.scheduling.slots import generate_slots
from apps.notifications.api import enqueue
from apps.common.phone import mask_phone

RESCHEDULE_LABELS = {
    "requested": "Pedido aguardando ação",
    "approved": "Pedido aprovado",
    "rejected": "Pedido recusado",
    "expired": "Pedido expirado",
}


def _client_ip(request) -> str:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.META.get("REMOTE_ADDR") or "0.0.0.0"


def _appointment_tz(ap: Appointment) -> ZoneInfo:
    tz_name = ap.timezone or getattr(ap.service, "timezone", None)
    if not tz_name:
        owner = getattr(getattr(ap.service, "card", None), "owner", None)
        if owner is not None:
            profile = getattr(owner, "customerprofile", None)
            if profile is None:
                profile = CustomerProfile.objects.filter(user=owner).only("timezone").first()
            tz_name = getattr(profile, "timezone", None)
    if not tz_name:
        tz_name = settings.TIME_ZONE
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def _tz_label(tz: ZoneInfo, reference: dt.datetime | None = None) -> str:
    label = getattr(tz, "key", None)
    if label:
        return label
    try:
        ref = reference or dt.datetime.now(tz)
        label = tz.tzname(ref)
    except Exception:
        label = None
    return label or settings.TIME_ZONE


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

    profile = CustomerProfile.objects.filter(user=request.user).only("timezone").first()
    tz_name = profile.timezone if profile and profile.timezone else timezone.get_current_timezone_name()
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.get_current_timezone()
        tz_name = getattr(tz, "key", None) or tz.tzname(None) or "UTC"
    today_local = timezone.now().astimezone(tz).date()
    pending_reschedules = _pending_reschedules_count(request.user)

    # Shortcut: render list (timeline) shell and exit. The list body loads via HTMX.
    if view == "list":
        return render(request, "dashboard/agenda.html", {
            "view": view,
            "today": today_local,
            "anchor": today_local,
            "tz_label": tz_name,
            "reschedule_pending_count": pending_reschedules,
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
        "today": today_local,
        "prev": prev,
        "next": next_,
        "header_range_label": header_range_label,
        "tz_label": tz_name,
        "range_start_iso": dt.datetime.combine(start_date, dt.time(0, 0, tzinfo=tz)).isoformat(),
        "range_end_iso": dt.datetime.combine(end_date, dt.time(23, 59, tzinfo=tz)).isoformat(),
        "hours": list(range(24)),
        "days": days,
        # Month grid data
        "month_start": start_date,
        "month_end": end_date,
        "reschedule_pending_count": pending_reschedules,
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
            ap_tz = _ZI(ap.timezone or getattr(ap.service, "timezone", None) or "UTC")
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
        .select_related("service", "service__card", "service__card__owner", "service__card__owner__customerprofile")
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
        # Use appointment/service timezone for display
        tz = _appointment_tz(ap)
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
    profile = CustomerProfile.objects.filter(user=request.user).only("timezone").first()
    tz_name = profile.timezone if profile and profile.timezone else timezone.get_current_timezone_name()
    try:
        tz_user = ZoneInfo(tz_name)
    except Exception:
        tz_user = timezone.get_current_timezone()
        tz_name = getattr(tz_user, "key", None) or tz_user.tzname(None) or "UTC"
    today_local = timezone.now().astimezone(tz_user).date()

    # If not an HTMX request, render the full shell (list view) instead of the partial
    if not getattr(request, "htmx", False):
        return render(request, "dashboard/agenda.html", {
            "view": "list",
            "today": today_local,
            "anchor": today_local,
            "tz_label": tz_name,
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
    needs_action = (request.GET.get("needs_action") or "").strip().lower()

    # Range and cursor
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

    reschedule_prefetch = Prefetch(
        "reschedule_requests",
        queryset=RescheduleRequest.objects.order_by("-created_at"),
    )
    qs = (
        Appointment.objects
        .filter(service__card__owner=request.user)
        .filter(start_at_utc__gte=start_utc, start_at_utc__lte=end_utc)
        .select_related("service", "service__card", "service__card__owner", "service__card__owner__customerprofile")
        .prefetch_related(reschedule_prefetch)
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
    if needs_action in {"1", "true", "yes"}:
        qs = qs.filter(reschedule_requests__status="requested").distinct()
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
    current_day_max_end_local_user: dt.datetime | None = None

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

    for ap in qs.iterator(chunk_size=200):
        tz_name_ap = ap.timezone or getattr(ap.service, "timezone", None) or tz_name
        try:
            ap_tz = ZoneInfo(tz_name_ap)
        except Exception:
            ap_tz = tz_user
        s_local = ap.start_at_utc.astimezone(ap_tz)
        e_local = ap.end_at_utc.astimezone(ap_tz)
        end_local_user = e_local.astimezone(tz_user)
        reschedule_requests = list(ap.reschedule_requests.all())
        res_meta = _reschedule_meta(ap, reschedule_requests)
        pending_request = res_meta["pending_request"]
        d = s_local.date()
        if current_day is None:
            current_day = d
            items_this_day = []
            current_day_max_end_local_user = end_local_user
        if d != current_day:
            flush_day(current_day, items_this_day)
            days_count += 1
            if current_day_max_end_local_user is not None:
                last_day_end_local = current_day_max_end_local_user
            if days_count >= DAYS_WINDOW:
                current_day = None
                items_this_day = []
                current_day_max_end_local_user = None
                break
            current_day = d
            items_this_day = []
            current_day_max_end_local_user = end_local_user
        else:
            if current_day_max_end_local_user is None or end_local_user > current_day_max_end_local_user:
                current_day_max_end_local_user = end_local_user

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
            "reschedule_action_needed": res_meta["has_pending"],
        "reschedule_pending_id": res_meta["pending_request_id"],
        "reschedule_pending_requested": res_meta["pending_requested_local"],
        "reschedule_pending_requested_label": res_meta["pending_requested_label"],
        "reschedule_pending_reason": pending_request.reason if pending_request else "",
            "reschedule_latest_status": res_meta["latest_status"],
            "reschedule_latest_label": res_meta["latest_label"],
            "day_iso": d.isoformat(),
            "start_iso": ap.start_at_utc.isoformat(),
        })

    # If we broke early due to DAYS_WINDOW, compute next_cursor
    if last_day_end_local is None:
        # We either exhausted all items or still in the last day
        if current_day is not None:
            flush_day(current_day, items_this_day)
            if current_day_max_end_local_user is not None:
                last_day_end_local = current_day_max_end_local_user
            if last_day_end_local is None and groups:
                last_day = dt.date.fromisoformat(groups[-1]["date_iso"])  # type: ignore[arg-type]
                last_day_end_local = dt.datetime.combine(last_day, dt.time(23, 59, 59, tzinfo=tz_user))

    next_cursor = None
    if groups and last_day_end_local is not None:
        next_cursor = last_day_end_local.astimezone(ZoneInfo("UTC")).isoformat()

    context = {
        "groups": groups,
        "next_cursor": next_cursor,
    }
    resp = render(request, "dashboard/_agenda_list.html", context)
    pending_count = _pending_reschedules_count(request.user)
    resp["HX-Trigger"] = json.dumps({"agenda:pending-count": pending_count})
    return resp


def _reschedule_meta(ap: Appointment, reqs: list[RescheduleRequest] | None = None) -> dict:
    if reqs is None:
        reqs = list(ap.reschedule_requests.order_by("-created_at"))
    pending = next((req for req in reqs if req.status == "requested"), None)
    latest = reqs[0] if reqs else None
    tz = _appointment_tz(ap)
    pending_requested_local = None
    pending_requested_label = ""
    if pending and pending.requested_start_at_utc:
        pending_requested_local = pending.requested_start_at_utc.astimezone(tz)
        pending_requested_label = pending_requested_local.strftime("%d/%m %H:%M")
    if latest:
        latest_label = {
            "approved": "Reagendamento aprovado",
            "rejected": "Reagendamento negado",
            "expired": "Reagendamento expirado",
            "requested": "Ação necessária",
        }.get(latest.status, RESCHEDULE_LABELS.get(latest.status, latest.get_status_display()))
    else:
        latest_label = ""
    return {
        "requests": reqs,
        "pending_request": pending,
        "latest_request": latest,
        "has_pending": pending is not None,
        "pending_request_id": str(pending.id) if pending else "",
        "pending_requested_local": pending_requested_local,
        "pending_requested_label": pending_requested_label,
        "latest_status": latest.status if latest else "",
        "latest_label": latest_label,
    }


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
    ap.save(update_fields=["status", "updated_at"])
    ap_refreshed = _load_appointment_with_reschedules(ap.id, request.user)
    dto = _item_dto(ap_refreshed)
    item_html = render_to_string("dashboard/_agenda_list_item.html", {"it": dto}, request=request)
    sidebar_ctx = _agenda_sidebar_context(ap_refreshed, request=request)
    sidebar_ctx["oob"] = True
    sidebar_html = render_to_string("dashboard/_agenda_sidebar.html", sidebar_ctx, request=request)
    html = item_html + sidebar_html
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps({
        "flash": {"type": "success", "title": "Agendamento atualizado"},
        "agenda:item-updated": {
            "id": str(ap_refreshed.id),
            "html": item_html,
            "old_day": dto["day_iso"],
            "new_day": dto["day_iso"],
        },
        "agenda:pending-count": _pending_reschedules_count(request.user),
        "agenda:refresh": True,
    })
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
    ap.save(update_fields=["status", "updated_at"])
    ap_refreshed = _load_appointment_with_reschedules(ap.id, request.user)
    dto = _item_dto(ap_refreshed)
    item_html = render_to_string("dashboard/_agenda_list_item.html", {"it": dto}, request=request)
    sidebar_ctx = _agenda_sidebar_context(ap_refreshed, request=request)
    sidebar_ctx["oob"] = True
    sidebar_html = render_to_string("dashboard/_agenda_sidebar.html", sidebar_ctx, request=request)
    html = item_html + sidebar_html
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps({
        "flash": {"type": "success", "title": "Agendamento atualizado"},
        "agenda:item-updated": {
            "id": str(ap_refreshed.id),
            "html": item_html,
            "old_day": dto["day_iso"],
            "new_day": dto["day_iso"],
        },
        "agenda:pending-count": _pending_reschedules_count(request.user),
        "agenda:refresh": True,
    })
    return resp


@login_required
def agenda_list_cancel(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    ap = get_object_or_404(Appointment, id=id, service__card__owner=request.user)
    if ap.status not in {"pending", "confirmed"}:
        return HttpResponseBadRequest("invalid state")
    ap.status = "cancelled"
    ap.save(update_fields=["status", "updated_at"])
    ap_refreshed = _load_appointment_with_reschedules(ap.id, request.user)
    dto = _item_dto(ap_refreshed)
    item_html = render_to_string("dashboard/_agenda_list_item.html", {"it": dto}, request=request)
    sidebar_ctx = _agenda_sidebar_context(ap_refreshed, request=request)
    sidebar_ctx["oob"] = True
    sidebar_html = render_to_string("dashboard/_agenda_sidebar.html", sidebar_ctx, request=request)
    html = item_html + sidebar_html
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps({
        "flash": {"type": "success", "title": "Agendamento atualizado"},
        "agenda:item-updated": {
            "id": str(ap_refreshed.id),
            "html": item_html,
            "old_day": dto["day_iso"],
            "new_day": dto["day_iso"],
        },
        "agenda:pending-count": _pending_reschedules_count(request.user),
        "agenda:refresh": True,
    })
    return resp


def _item_dto(ap: Appointment) -> dict:
    ap_tz = _appointment_tz(ap)
    s_local = ap.start_at_utc.astimezone(ap_tz)
    e_local = ap.end_at_utc.astimezone(ap_tz)
    duration_min = int((e_local - s_local).total_seconds() // 60)
    show_contact = (ap.status == "confirmed")
    res_meta = _reschedule_meta(ap)
    pending_request = res_meta["pending_request"]
    day_iso = s_local.date().isoformat()
    start_iso = ap.start_at_utc.isoformat()
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
        "reschedule_action_needed": res_meta["has_pending"],
        "reschedule_pending_id": res_meta["pending_request_id"],
        "reschedule_pending_requested": res_meta["pending_requested_local"],
        "reschedule_pending_requested_label": res_meta["pending_requested_label"],
        "reschedule_pending_reason": pending_request.reason if pending_request else "",
        "reschedule_latest_status": res_meta["latest_status"],
        "reschedule_latest_label": res_meta["latest_label"],
        "day_iso": day_iso,
        "start_iso": start_iso,
    }


def _agenda_sidebar_context(ap: Appointment, *, request=None, res_meta: dict | None = None) -> dict:
    tz = _appointment_tz(ap)
    start_local = ap.start_at_utc.astimezone(tz)
    end_local = ap.end_at_utc.astimezone(tz)
    if res_meta is None:
        reqs = list(ap.reschedule_requests.order_by("-created_at"))
        res_meta = _reschedule_meta(ap, reqs)
    else:
        reqs = res_meta["requests"]
    timeline = _reschedule_timeline(ap, reqs)
    target_request = res_meta["pending_request"] or res_meta["latest_request"]
    reschedule_detail = _reschedule_detail_context(target_request) if target_request else None
    hx_target = "#agenda-sidebar"
    hx_swap = "innerHTML"
    context_value = "agenda"
    reschedule_detail_html = ""
    if reschedule_detail and request is not None:
        detail_ctx = {
            "appointment": reschedule_detail["appointment"],
            "request_obj": reschedule_detail["request_obj"],
            "timeline": reschedule_detail["timeline"],
            "slot_calendar": reschedule_detail["slot_calendar"],
            "can_act": reschedule_detail["can_act"],
            "start_local": reschedule_detail["start_local"],
            "end_local": reschedule_detail["end_local"],
            "start_label": reschedule_detail["start_label"],
            "end_label": reschedule_detail["end_label"],
            "timezone": reschedule_detail["timezone"],
            "customer_phone_mask": reschedule_detail["customer_phone_mask"],
            "customer_email": reschedule_detail["customer_email"],
            "status_label": reschedule_detail["status_label"],
            "requested_slot_local": reschedule_detail["requested_slot_local"],
            "requested_slot_label": reschedule_detail["requested_slot_label"],
            "requested_slot_value": reschedule_detail["requested_slot_value"],
            "hide_header": True,
            "hx_target": hx_target,
            "hx_swap": hx_swap,
            "reschedule_context": context_value,
        }
        reschedule_detail_html = render_to_string("dashboard/_reschedule_detail.html", detail_ctx, request=request)
    return {
        "ap": ap,
        "start_local": start_local,
        "end_local": end_local,
        "tz_label": _tz_label(tz, start_local),
        "reschedule_detail": reschedule_detail,
        "reschedule_detail_html": reschedule_detail_html,
        "reschedule_meta": res_meta,
        "timeline": timeline,
        "reschedule_context_value": context_value,
        "reschedule_hx_target": hx_target,
        "reschedule_hx_swap": hx_swap,
    }


def _load_appointment_with_reschedules(ap_id, user):
    return (
        Appointment.objects
        .select_related("service", "service__card", "service__card__owner", "service__card__owner__customerprofile")
        .prefetch_related(
            Prefetch("reschedule_requests", queryset=RescheduleRequest.objects.order_by("-created_at"))
        )
        .get(id=ap_id, service__card__owner=user)
    )


def _pending_reschedules_count(user) -> int:
    return (
        RescheduleRequest.objects
        .filter(appointment__service__card__owner=user, status="requested")
        .count()
    )


@login_required
def agenda_event_sidebar(request, id):
    ap = get_object_or_404(
        Appointment.objects
        .select_related("service", "service__card", "service__card__owner", "service__card__owner__customerprofile")
        .prefetch_related(
            Prefetch("reschedule_requests", queryset=RescheduleRequest.objects.order_by("-created_at"))
        ),
        id=id,
        service__card__owner=request.user,
    )
    res_meta = _reschedule_meta(ap, list(ap.reschedule_requests.all()))
    ctx = _agenda_sidebar_context(ap, request=request, res_meta=res_meta)
    return render(request, "dashboard/_agenda_sidebar.html", ctx)


@login_required
def agenda_event_approve(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    ap = get_object_or_404(Appointment, id=id, service__card__owner=request.user)
    if ap.status != "pending":
        return HttpResponseBadRequest("invalid state")
    ap.status = "confirmed"
    ap.save(update_fields=["status", "updated_at"])
    ap_refreshed = _load_appointment_with_reschedules(ap.id, request.user)
    ctx = _agenda_sidebar_context(ap_refreshed, request=request)
    resp = render(request, "dashboard/_agenda_sidebar.html", ctx)
    dto = _item_dto(ap_refreshed)
    trigger_payload = {
        "agenda:refresh": True,
        "agenda:item-updated": {
            "id": str(ap_refreshed.id),
            "html": render_to_string("dashboard/_agenda_list_item.html", {"it": dto}, request=request),
            "old_day": dto["day_iso"],
            "new_day": dto["day_iso"],
        },
        "agenda:pending-count": _pending_reschedules_count(request.user),
    }
    resp["HX-Trigger"] = json.dumps(trigger_payload)
    return resp


@login_required
def agenda_event_deny(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    ap = get_object_or_404(Appointment, id=id, service__card__owner=request.user)
    if ap.status != "pending":
        return HttpResponseBadRequest("invalid state")
    ap.status = "denied"
    ap.save(update_fields=["status", "updated_at"])
    ap_refreshed = _load_appointment_with_reschedules(ap.id, request.user)
    ctx = _agenda_sidebar_context(ap_refreshed, request=request)
    resp = render(request, "dashboard/_agenda_sidebar.html", ctx)
    dto = _item_dto(ap_refreshed)
    trigger_payload = {
        "agenda:refresh": True,
        "agenda:item-updated": {
            "id": str(ap_refreshed.id),
            "html": render_to_string("dashboard/_agenda_list_item.html", {"it": dto}, request=request),
            "old_day": dto["day_iso"],
            "new_day": dto["day_iso"],
        },
        "agenda:pending-count": _pending_reschedules_count(request.user),
    }
    resp["HX-Trigger"] = json.dumps(trigger_payload)
    return resp


def _reschedule_queryset(request):
    return (
        RescheduleRequest.objects
        .select_related(
            "appointment",
            "appointment__service",
            "appointment__service__card",
            "appointment__service__card__owner",
            "appointment__service__card__owner__customerprofile",
            "approved_by",
        )
        .filter(appointment__service__card__owner=request.user)
    )


def _reschedule_timeline(ap: Appointment, reqs: list[RescheduleRequest] | None = None):
    tz = _appointment_tz(ap)
    timeline = []
    if reqs is None:
        req_iter = ap.reschedule_requests.order_by("created_at")
    else:
        req_iter = sorted(reqs, key=lambda r: r.created_at)
    for req in req_iter:
        label = RESCHEDULE_LABELS.get(req.status, req.status.capitalize())
        entry = {
            "obj": req,
            "status": req.status,
            "label": label,
            "created": req.created_at.astimezone(tz),
            "created_label": req.created_at.astimezone(tz).strftime("%d/%m/%Y %H:%M"),
            "owner_message": req.owner_message,
            "reason": req.reason,
        }
        if req.requested_start_at_utc:
            requested_local = req.requested_start_at_utc.astimezone(tz)
            entry["requested"] = requested_local
            entry["requested_label"] = requested_local.strftime("%d/%m/%Y %H:%M")
        if req.new_start_at_utc:
            entry["approved_window"] = {
                "start": req.new_start_at_utc.astimezone(tz),
                "end": req.new_end_at_utc.astimezone(tz) if req.new_end_at_utc else None,
            }
            entry["approved_window_label"] = {
                "start": entry["approved_window"]["start"].strftime("%d/%m/%Y %H:%M"),
                "end": entry["approved_window"]["end"].strftime("%H:%M") if entry["approved_window"]["end"] else "",
            }
        timeline.append(entry)
    return timeline


def _slot_options_for_date(
    ap: Appointment,
    day: dt.date,
    *,
    preferred: dt.datetime | None = None,
) -> list[dict[str, object]]:
    tz = _appointment_tz(ap)
    now_ref = timezone.now()
    preferred_utc = None
    if preferred is not None:
        try:
            preferred_utc = preferred.astimezone(ZoneInfo("UTC")).replace(microsecond=0)
        except Exception:
            preferred_utc = None

    options: list[dict[str, object]] = []
    for raw in generate_slots(ap.service, day, ignore_appointment_id=ap.id):
        try:
            start = dt.datetime.fromisoformat(raw["start_at_utc"])
            end = dt.datetime.fromisoformat(raw["end_at_utc"])
        except (KeyError, ValueError, TypeError):
            continue
        if start <= now_ref:
            continue
        start_local = start.astimezone(tz)
        end_local = end.astimezone(tz)
        start_label = start_local.strftime("%H:%M")
        end_label = end_local.strftime("%H:%M")
        selected = False
        if preferred_utc is not None:
            selected = start.astimezone(ZoneInfo("UTC")).replace(microsecond=0) == preferred_utc
        options.append({
            "value": raw["start_at_utc"],
            "start_label": start_label,
            "end_label": end_label,
            "range_label": f"{start_label} – {end_label}",
            "selected": selected,
        })
    return options


def _slot_calendar(
    ap: Appointment,
    *,
    preferred: dt.datetime | None = None,
    days: int = 10,
) -> dict[str, object]:
    tz = _appointment_tz(ap)
    today_local = timezone.now().astimezone(tz).date()
    preferred_date: dt.date | None = None
    if preferred:
        try:
            preferred_local = preferred.astimezone(tz)
            preferred_date = preferred_local.date()
        except Exception:
            preferred_date = None
        if preferred_date and preferred_date < today_local:
            preferred_date = None

    candidate_dates = [today_local + dt.timedelta(days=offset) for offset in range(days)]
    if preferred_date and preferred_date not in candidate_dates:
        candidate_dates.append(preferred_date)
    candidate_dates = sorted(set(candidate_dates))

    available_dates: list[dt.date] = []
    initial_date: dt.date | None = None
    initial_slots: list[dict[str, object]] = []
    selected_value = ""

    for day in candidate_dates:
        slots = _slot_options_for_date(ap, day, preferred=preferred)
        if not slots:
            continue
        available_dates.append(day)
        if not selected_value:
            selected = next((slot["value"] for slot in slots if slot["selected"]), "")
            selected_value = selected
        if preferred_date and day == preferred_date:
            initial_date = day
            initial_slots = slots
            break
        if initial_date is None:
            initial_date = day
            initial_slots = slots

    if initial_date is None:
        baseline_date = preferred_date or (candidate_dates[0] if candidate_dates else today_local)
        initial_date = baseline_date
        initial_slots = _slot_options_for_date(ap, baseline_date, preferred=preferred)
        if not selected_value:
            selected_value = next((slot["value"] for slot in initial_slots if slot["selected"]), "")

    max_candidate = candidate_dates[-1] if candidate_dates else today_local
    return {
        "min_date": today_local.isoformat(),
        "max_date": max_candidate.isoformat(),
        "initial_date": initial_date.isoformat(),
        "initial_date_label": initial_date.strftime("%d/%m/%Y"),
        "available_dates": [d.isoformat() for d in available_dates],
        "slots": initial_slots,
        "selected": selected_value,
    }


def _validate_slot_choice(req: RescheduleRequest, start: dt.datetime) -> dt.datetime | None:
    if start.tzinfo is None:
        return None
    service = req.appointment.service
    try:
        tz = ZoneInfo(service.timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    date_local = start.astimezone(tz).date()
    slots = generate_slots(service, date_local, ignore_appointment_id=req.appointment_id)
    target = start.astimezone(ZoneInfo("UTC")).replace(microsecond=0)
    for sl in slots:
        try:
            slot_start = dt.datetime.fromisoformat(sl["start_at_utc"]).astimezone(ZoneInfo("UTC")).replace(microsecond=0)
        except Exception:
            continue
        if slot_start == target:
            try:
                return dt.datetime.fromisoformat(sl["end_at_utc"]).astimezone(ZoneInfo("UTC")).replace(microsecond=0)
            except Exception:
                return None
    return None


def _reschedule_detail_context(req: RescheduleRequest) -> dict:
    ap = req.appointment
    tz = _appointment_tz(ap)
    timezone_label = _tz_label(tz)
    slot_calendar = _slot_calendar(ap, preferred=req.requested_start_at_utc) if req.status == "requested" else None
    ctx = {
        "request_obj": req,
        "appointment": ap,
        "timeline": _reschedule_timeline(ap),
        "slot_calendar": slot_calendar,
        "can_act": req.status == "requested",
        "start_local": ap.start_at_utc.astimezone(tz),
        "end_local": ap.end_at_utc.astimezone(tz),
        "start_label": ap.start_at_utc.astimezone(tz).strftime("%d/%m/%Y %H:%M"),
        "end_label": ap.end_at_utc.astimezone(tz).strftime("%H:%M"),
        "timezone": timezone_label,
        "customer_phone_mask": mask_phone(ap.user_phone),
        "customer_email": ap.user_email,
        "status_label": RESCHEDULE_LABELS.get(req.status, req.get_status_display()),
        "requested_slot_local": req.requested_start_at_utc.astimezone(tz) if req.requested_start_at_utc else None,
        "requested_slot_label": req.requested_start_at_utc.astimezone(tz).strftime("%d/%m/%Y %H:%M") if req.requested_start_at_utc else "",
        "requested_slot_value": req.requested_start_at_utc.isoformat() if req.requested_start_at_utc else "",
    }
    return ctx


@login_required
def reschedule_slots(request, id):
    if request.method != "GET":
        return HttpResponseBadRequest("GET required")
    req = get_object_or_404(_reschedule_queryset(request), id=id)
    if req.status != "requested":
        return HttpResponseBadRequest("Solicitação já tratada")
    date_param = (request.GET.get("date") or "").strip()
    if not date_param:
        return HttpResponseBadRequest("Data obrigatória")
    target_date = parse_date(date_param)
    if not target_date:
        return HttpResponseBadRequest("Data inválida")
    tz = _appointment_tz(req.appointment)
    today_local = timezone.now().astimezone(tz).date()
    if target_date < today_local:
        return HttpResponseBadRequest("Data no passado")
    preferred_raw = (request.GET.get("slot") or request.GET.get("selected") or "").strip()
    preferred_choice: dt.datetime | None = None
    if preferred_raw:
        try:
            preferred_choice = dt.datetime.fromisoformat(preferred_raw)
        except ValueError:
            preferred_choice = None
    slots = _slot_options_for_date(
        req.appointment,
        target_date,
        preferred=preferred_choice or req.requested_start_at_utc,
    )
    context = {
        "slots": slots,
        "slot_date": target_date,
        "slot_date_label": target_date.strftime("%d/%m/%Y"),
    }
    return render(request, "dashboard/_reschedule_slot_options.html", context)


@ensure_csrf_cookie
@login_required
def reschedule_index(request):
    current_status = (request.GET.get("status") or "requested").strip()
    if current_status not in RESCHEDULE_LABELS:
        current_status = "requested"
    cards = request.user.cards.order_by("title")
    services = SchedulingService.objects.filter(card__owner=request.user).order_by("name")
    pending_count = _reschedule_queryset(request).filter(status="requested").count()
    initial_filters = request.GET.dict()
    initial_query = request.GET.urlencode()
    selected_status = initial_filters.get("status") or current_status
    return render(request, "dashboard/reschedule.html", {
        "cards": cards,
        "services": services,
        "current_status": current_status,
        "pending_count": pending_count,
        "initial_filters": initial_filters,
        "initial_query": initial_query,
        "selected_status": selected_status,
        "RESCHEDULE_LABELS": RESCHEDULE_LABELS,
    })


@login_required
def reschedule_list(request):
    qs = _reschedule_queryset(request).order_by("-created_at")
    status = (request.GET.get("status") or "").strip()
    if status and status in RESCHEDULE_LABELS:
        qs = qs.filter(status=status)
    card_id = request.GET.get("card") or ""
    if card_id:
        qs = qs.filter(appointment__service__card_id=card_id)
    service_id = request.GET.get("service") or ""
    if service_id:
        qs = qs.filter(appointment__service_id=service_id)
    start_q = request.GET.get("start") or ""
    if start_q:
        start_date = parse_date(start_q)
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
    end_q = request.GET.get("end") or ""
    if end_q:
        end_date = parse_date(end_q)
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)
    requests_list = list(qs[:200])
    for item in requests_list:
        setattr(item, "status_label", RESCHEDULE_LABELS.get(item.status, item.get_status_display()))
    return render(request, "dashboard/_reschedule_list.html", {
        "requests": requests_list,
        "filters": {
            "status": status,
            "card": card_id,
            "service": service_id,
            "start": start_q,
            "end": end_q,
        },
        "labels": RESCHEDULE_LABELS,
    })


@login_required
def reschedule_detail(request, id):
    req = get_object_or_404(_reschedule_queryset(request), id=id)
    ctx = _reschedule_detail_context(req)
    return render(request, "dashboard/_reschedule_detail.html", ctx)


def _notify_customer_reschedule(req: RescheduleRequest, outcome: str) -> None:
    ap = req.appointment
    tz = _appointment_tz(ap)
    start_local = (req.new_start_at_utc or ap.start_at_utc).astimezone(tz)
    payload = {
        "service": ap.service.name,
        "date": start_local.strftime("%d/%m"),
        "time": start_local.strftime("%H:%M"),
        "card": ap.service.card.title,
    }
    if outcome == "rejected" and req.owner_message:
        payload["message"] = req.owner_message
    tmpl_sms = {
        "approved": "customer_reschedule_approved",
        "rejected": "customer_reschedule_rejected",
    }.get(outcome)
    if tmpl_sms and ap.user_phone:
        try:
            enqueue(
                type="sms",
                to=ap.user_phone,
                template_code=tmpl_sms,
                payload=payload,
                idempotency_key=f"resched:{req.id}:{outcome}:sms",
            )
        except Exception:
            pass


def _notify_owner_reschedule(req: RescheduleRequest) -> None:
    card = req.appointment.service.card
    if not getattr(card, "notification_phone", None):
        return
    try:
        enqueue(
            type="sms",
            to=card.notification_phone,
            template_code="owner_reschedule_requested",
            payload={
                "service": req.appointment.service.name,
                "customer": req.appointment.user_name,
            },
            idempotency_key=f"resched:{req.id}:owner",
        )
    except Exception:
        pass


@login_required
def reschedule_approve(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    req = get_object_or_404(_reschedule_queryset(request), id=id)
    if req.status != "requested":
        return HttpResponseBadRequest("Solicitação já tratada")
    context_mode = (request.POST.get("context") or "").strip().lower()
    slot_raw = (request.POST.get("slot") or "").strip()
    if not slot_raw:
        return HttpResponseBadRequest("Informe um horário válido")
    try:
        new_start = dt.datetime.fromisoformat(slot_raw)
    except ValueError:
        return HttpResponseBadRequest("Formato de data inválido")
    new_end = _validate_slot_choice(req, new_start)
    if not new_end:
        return HttpResponseBadRequest("Horário indisponível")
    owner_message = (request.POST.get("message") or "").strip()
    old_day_iso = None
    with transaction.atomic():
        req = RescheduleRequest.objects.select_for_update().get(id=req.id)
        if req.status != "requested":
            return HttpResponseBadRequest("Solicitação já tratada")
        end_check = _validate_slot_choice(req, new_start)
        if not end_check:
            return HttpResponseBadRequest("Horário indisponível")
        ap = req.appointment
        ap_tz = _appointment_tz(ap)
        old_start_local = ap.start_at_utc.astimezone(ap_tz)
        old_day_iso = old_start_local.date().isoformat()
        req.status = "approved"
        req.owner_message = owner_message
        req.approved_by = request.user
        req.new_start_at_utc = new_start
        req.new_end_at_utc = end_check
        req.action_ip = _client_ip(request)
        req.save()
        ap.start_at_utc = new_start
        ap.end_at_utc = end_check
        ap.status = "confirmed"
        ap.save(update_fields=["start_at_utc", "end_at_utc", "status", "updated_at"])
        RescheduleRequest.objects.filter(appointment=ap, status="requested").exclude(id=req.id).update(status="expired")
    _notify_customer_reschedule(req, "approved")
    trigger_payload: dict[str, object] = {
        "reschedule:reload": True,
        "flash": {"type": "ok", "title": "Pedido aprovado", "message": "O cliente será notificado."},
    }
    trigger_payload["agenda:pending-count"] = _pending_reschedules_count(request.user)
    trigger_payload["agenda:refresh"] = True
    if context_mode == "agenda":
        ap_fresh = _load_appointment_with_reschedules(req.appointment_id, request.user)
        ctx = _agenda_sidebar_context(ap_fresh, request=request)
        resp = render(request, "dashboard/_agenda_sidebar.html", ctx)
        ap_tz = _appointment_tz(ap_fresh)
        new_start_local = ap_fresh.start_at_utc.astimezone(ap_tz)
        new_day_iso = new_start_local.date().isoformat()
        trigger_payload["agenda:item-updated"] = {
            "id": str(ap_fresh.id),
            "html": render_to_string("dashboard/_agenda_list_item.html", {"it": _item_dto(ap_fresh)}, request=request),
            "old_day": old_day_iso,
            "new_day": new_day_iso,
        }
    else:
        ctx = _reschedule_detail_context(req)
        resp = render(request, "dashboard/_reschedule_detail.html", ctx)
    resp["HX-Trigger"] = json.dumps(trigger_payload)
    return resp


@login_required
def reschedule_reject(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    req = get_object_or_404(_reschedule_queryset(request), id=id)
    if req.status != "requested":
        return HttpResponseBadRequest("Solicitação já tratada")
    context_mode = (request.POST.get("context") or "").strip().lower()
    owner_message = (request.POST.get("message") or "").strip()
    old_day_iso = None
    with transaction.atomic():
        req = RescheduleRequest.objects.select_for_update().get(id=req.id)
        if req.status != "requested":
            return HttpResponseBadRequest("Solicitação já tratada")
        ap = req.appointment
        ap_tz = _appointment_tz(ap)
        old_start_local = ap.start_at_utc.astimezone(ap_tz)
        old_day_iso = old_start_local.date().isoformat()
        req.status = "rejected"
        req.owner_message = owner_message
        req.approved_by = request.user
        req.action_ip = _client_ip(request)
        req.save(update_fields=["status", "owner_message", "approved_by", "action_ip", "updated_at"])
    _notify_customer_reschedule(req, "rejected")
    trigger_payload: dict[str, object] = {
        "reschedule:reload": True,
        "flash": {"type": "ok", "title": "Pedido atualizado", "message": "O cliente foi avisado."},
    }
    trigger_payload["agenda:pending-count"] = _pending_reschedules_count(request.user)
    trigger_payload["agenda:refresh"] = True
    if context_mode == "agenda":
        ap_fresh = _load_appointment_with_reschedules(req.appointment_id, request.user)
        ctx = _agenda_sidebar_context(ap_fresh, request=request)
        resp = render(request, "dashboard/_agenda_sidebar.html", ctx)
        ap_tz = _appointment_tz(ap_fresh)
        new_start_local = ap_fresh.start_at_utc.astimezone(ap_tz)
        new_day_iso = new_start_local.date().isoformat()
        trigger_payload["agenda:item-updated"] = {
            "id": str(ap_fresh.id),
            "html": render_to_string("dashboard/_agenda_list_item.html", {"it": _item_dto(ap_fresh)}, request=request),
            "old_day": old_day_iso,
            "new_day": new_day_iso,
        }
    else:
        ctx = _reschedule_detail_context(req)
        resp = render(request, "dashboard/_reschedule_detail.html", ctx)
    resp["HX-Trigger"] = json.dumps(trigger_payload)
    return resp
