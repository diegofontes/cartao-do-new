import datetime as dt
from typing import Iterable
from zoneinfo import ZoneInfo
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import SchedulingService, ServiceAvailability, Appointment, ServiceOption


def _localize(service_tz: str, date: dt.date, t: dt.time) -> dt.datetime:
    tz = ZoneInfo(service_tz)
    return tz.localize(dt.datetime.combine(date, t)) if hasattr(tz, 'localize') else dt.datetime.combine(date, t).replace(tzinfo=tz)


def _to_utc(d: dt.datetime) -> dt.datetime:
    return d.astimezone(ZoneInfo("UTC"))


def _collect_windows(service: SchedulingService, date: dt.date):
    # Exclude holidays
    if ServiceAvailability.objects.filter(service=service, rule_type="holiday", date=date).exists():
        return []
    windows = []
    # Weekly rules
    for r in ServiceAvailability.objects.filter(service=service, rule_type="weekly", weekday=date.weekday()):
        if r.start_time and r.end_time:
            start_local = _localize(service.timezone, date, r.start_time)
            end_local = _localize(service.timezone, date, r.end_time)
            windows.append((_to_utc(start_local), _to_utc(end_local)))
    # Date overrides
    for r in ServiceAvailability.objects.filter(service=service, rule_type="date_override", date=date):
        if r.start_time and r.end_time:
            start_local = _localize(service.timezone, date, r.start_time)
            end_local = _localize(service.timezone, date, r.end_time)
            windows.append((_to_utc(start_local), _to_utc(end_local)))
    # Merge overlapping windows
    windows.sort()
    merged = []
    for s, e in windows:
        if not merged or s > merged[-1][1]:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)
    return [(s, e) for s, e in merged]


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    return not (a_end <= b_start or b_end <= a_start)


def _blocked_intervals(service: SchedulingService, date: dt.date, ignore_appointment_id: str | None = None):
    # Pending/confirmed appointments expanded by buffers
    start_day = dt.datetime.combine(date, dt.time.min, tzinfo=ZoneInfo("UTC"))
    end_day = dt.datetime.combine(date, dt.time.max, tzinfo=ZoneInfo("UTC"))
    qs = Appointment.objects.filter(
        service=service,
        status__in=["pending", "confirmed"],
        start_at_utc__lte=end_day,
        end_at_utc__gte=start_day,
    )
    if ignore_appointment_id:
        qs = qs.exclude(id=ignore_appointment_id)
    blocks = []
    for ap in qs:
        s = ap.start_at_utc - dt.timedelta(minutes=service.buffer_before)
        e = ap.end_at_utc + dt.timedelta(minutes=service.buffer_after)
        blocks.append((s, e))
    # merge
    blocks.sort()
    merged = []
    for s, e in blocks:
        if not merged or s > merged[-1][1]:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)
    return [(s, e) for s, e in merged]


def generate_slots(service: SchedulingService, date: dt.date, *, ignore_appointment_id: str | None = None):
    now_utc = timezone.now().astimezone(ZoneInfo("UTC"))
    lead_delta = dt.timedelta(minutes=service.lead_time_min)
    min_start = now_utc + lead_delta

    windows = _collect_windows(service, date)
    blocks = _blocked_intervals(service, date, ignore_appointment_id)
    dur = dt.timedelta(minutes=service.duration_minutes)

    slots = []
    for win_start, win_end in windows:
        # step by duration; ensure buffers around the proposed slot fit in the window and don't hit blocks
        cursor = win_start
        while cursor + dur <= win_end:
            s = cursor
            e = s + dur
            claim_start = s - dt.timedelta(minutes=service.buffer_before)
            claim_end = e + dt.timedelta(minutes=service.buffer_after)
            if s >= min_start:
                conflict = any(_overlaps(claim_start, claim_end, b0, b1) for b0, b1 in blocks)
                within_window = (claim_start >= win_start) and (claim_end <= win_end)
                if not conflict and within_window:
                    slots.append((s, e))
            cursor = cursor + dur
    # Return ISO8601 strings in UTC
    return [{
        "start_at_utc": s.isoformat(),
        "end_at_utc": e.isoformat(),
    } for s, e in slots]


def _active_options(service: SchedulingService, option_ids: Iterable[str]) -> list[ServiceOption]:
    if not option_ids:
        return []
    opts = ServiceOption.objects.filter(service=service, id__in=option_ids, is_active=True)
    opt_map = {str(opt.id): opt for opt in opts}
    ordered: list[ServiceOption] = []
    for oid in option_ids:
        opt = opt_map.get(str(oid))
        if opt and opt not in ordered:
            ordered.append(opt)
    return ordered


def prepare_booking(
    service: SchedulingService,
    start_at: dt.datetime,
    option_ids: Iterable[str] | None = None,
    *,
    ignore_appointment_id: str | None = None,
) -> dict:
    """Validates availability for a given start and selected options, returning booking metadata."""
    option_ids = list(option_ids or [])
    options = _active_options(service, option_ids)
    tz_service = ZoneInfo(service.timezone or "UTC")
    date_local = start_at.astimezone(tz_service).date()
    slots = generate_slots(service, date_local, ignore_appointment_id=ignore_appointment_id)
    if not any(dt.datetime.fromisoformat(slot["start_at_utc"]) == start_at for slot in slots):
        raise ValidationError("Horário indisponível.")
    extra_minutes = sum(opt.extra_duration_minutes for opt in options)
    total_minutes = service.duration_minutes + extra_minutes
    end_at = start_at + dt.timedelta(minutes=total_minutes)
    # Ensure appointment stays within service windows and doesn't overlap other appointments
    claim_start = start_at - dt.timedelta(minutes=service.buffer_before)
    claim_end = end_at + dt.timedelta(minutes=service.buffer_after)
    if claim_end.astimezone(tz_service).date() != date_local:
        raise ValidationError("Duração excede o limite diário disponível.")
    windows = _collect_windows(service, date_local)
    fits_window = any(
        claim_start >= win_start and claim_end <= win_end for win_start, win_end in windows
    )
    if not fits_window:
        raise ValidationError("Horário não comporta a duração selecionada.")
    blocks = []
    for chk_date in {date_local, claim_end.astimezone(tz_service).date()}:
        blocks.extend(_blocked_intervals(service, chk_date, ignore_appointment_id))
    has_conflict = any(_overlaps(claim_start, claim_end, b0, b1) for b0, b1 in blocks)
    if has_conflict:
        raise ValidationError("Horário indisponível devido a outro agendamento.")
    now_utc = timezone.now().astimezone(ZoneInfo("UTC"))
    if start_at < now_utc + dt.timedelta(minutes=service.lead_time_min):
        raise ValidationError("O horário selecionado não respeita o tempo mínimo de antecedência.")
    price_delta = sum(opt.price_delta_cents for opt in options)
    total_price = (service.price_cents or 0) + price_delta
    options_snapshot = [
        {
            "id": str(opt.id),
            "name": opt.name,
            "description": opt.description,
            "price_delta_cents": int(opt.price_delta_cents or 0),
            "extra_duration_minutes": int(opt.extra_duration_minutes or 0),
        }
        for opt in options
    ]
    return {
        "start_at": start_at,
        "end_at": end_at,
        "duration_minutes": total_minutes,
        "options": options,
        "options_snapshot": options_snapshot,
        "extra_minutes": extra_minutes,
        "price_cents": total_price,
        "base_price_cents": int(service.price_cents or 0),
        "price_delta_cents": price_delta,
    }
