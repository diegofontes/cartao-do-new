import datetime as dt
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import CustomerProfile, Invoice
from .utils import current_period_end, local_date_for_process_utc
from .services import compute_metering_amount_cents, create_and_pay_invoice_for_period


User = get_user_model()


def _idem_key(user_id: int, start: dt.date, end: dt.date) -> str:
    return f"invoice:{user_id}:{start}:{end}"


def billing_run_daily(process_date_utc: dt.date | None = None) -> dict:
    """Idempotent daily billing runner.
    Iterates active profiles, checks if local today equals the anchor-adjusted day,
    aggregates metering, creates Stripe invoice and local record, and advances last_billed_period_end.
    """
    created = 0
    advanced_only = 0
    skipped = 0

    qs = CustomerProfile.objects.filter(is_active=True, payment_method_status="active")
    for prof in qs.select_related("user"):
        tz = prof.timezone or "America/Sao_Paulo"
        anchor = prof.billing_anchor_day
        if not anchor:
            skipped += 1
            continue

        today_local = local_date_for_process_utc(process_date_utc, tz)
        period_end = current_period_end(tz, anchor, today_local)
        if today_local != period_end:
            skipped += 1
            continue

        period_start = prof.last_billed_period_end or (prof.anchor_set_at.date() if prof.anchor_set_at else None)
        if not period_start:
            # If anchor exists but anchor_set_at missing for any reason, derive first period_start as the anchor day in current month
            period_start = period_end

        # Idempotency by period window
        if Invoice.objects.filter(user=prof.user, period_start=period_start, period_end=period_end).exists():
            skipped += 1
            continue

        total_cents, events = compute_metering_amount_cents(prof.user, period_start, period_end)
        idem = _idem_key(prof.user_id, period_start, period_end)

        inv = None
        if total_cents > 0:
            inv = create_and_pay_invoice_for_period(prof.user, period_start, period_end)
            if inv:
                inv.idempotency_key = idem
                inv.save(update_fields=["idempotency_key"])
                created += 1
        # Advance last_billed_period_end regardless of invoice existence to move the window forward
        prof.last_billed_period_end = period_end
        prof.save(update_fields=["last_billed_period_end"])
        if not inv:
            advanced_only += 1

    return {"invoices_created": created, "advanced_without_invoice": advanced_only, "skipped": skipped, "date": str(process_date_utc or timezone.localdate())}


def billing_run_for_user(user_id: int, process_date_utc: dt.date | None = None) -> dict:
    prof = CustomerProfile.objects.filter(user_id=user_id, is_active=True).first()
    if not prof:
        return {"ok": False, "reason": "no profile"}
    tz = prof.timezone or "America/Sao_Paulo"
    anchor = prof.billing_anchor_day
    if not anchor or prof.payment_method_status != "active":
        return {"ok": False, "reason": "not eligible"}
    today_local = local_date_for_process_utc(process_date_utc, tz)
    period_end = current_period_end(tz, anchor, today_local)
    period_start = prof.last_billed_period_end or (prof.anchor_set_at.date() if prof.anchor_set_at else period_end)
    if Invoice.objects.filter(user_id=user_id, period_start=period_start, period_end=period_end).exists():
        return {"ok": True, "skipped": True}
    total_cents, _ = compute_metering_amount_cents(prof.user, period_start, period_end)
    idem = _idem_key(user_id, period_start, period_end)
    inv = None
    if total_cents > 0:
        inv = create_and_pay_invoice_for_period(prof.user, period_start, period_end)
        if inv:
            inv.idempotency_key = idem
            inv.save(update_fields=["idempotency_key"])
    prof.last_billed_period_end = period_end
    prof.save(update_fields=["last_billed_period_end"])
    return {"ok": True, "invoice": bool(inv), "period": f"{period_start}..{period_end}"}

