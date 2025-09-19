import datetime as dt
from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone
import logging
from .services import previous_month_bounds, create_and_pay_invoice_for_period, get_or_create_profile
from .daily import billing_run_daily
from .models import Invoice
from apps.cards.models import Card

User = get_user_model()

log = logging.getLogger(__name__)

@shared_task
def close_monthly_billing(run_for: str | None = None):
    
    """Fecha o ciclo do mês anterior (ou para AAAA-MM passado em run_for)."""
    log.info("Iniciando fechamento de faturamento mensal. run_for=%s", run_for)
    if run_for:
        year, month = map(int, run_for.split("-"))
        ref = dt.date(year, month, 15)
        start, end = previous_month_bounds(ref)
    else:
        start, end = previous_month_bounds()

    counter = 0
    for user in User.objects.all():
        prof = get_or_create_profile(user)
        if not prof.is_active:
            continue
        inv = create_and_pay_invoice_for_period(user, start, end)
        if inv:
            counter += 1
    return {"invoices_created": counter, "period": f"{start}..{end}"}


@shared_task
def run_daily_billing(process_date: str | None = None):
    """Task diária: usa data UTC (YYYY-MM-DD) opcional, idempotente por período/usuário."""
    d = None
    if process_date:
        try:
            year, month, day = map(int, process_date.split("-"))
            d = dt.date(year, month, day)
        except Exception:
            d = None
    return billing_run_daily(d)


def run_archive_marked_cards(period_end: dt.date, user_id: int | None = None):
    # Select users with paid invoice for the period
    inv_qs = Invoice.objects.filter(period_end=period_end, status="paid")
    if user_id:
        inv_qs = inv_qs.filter(user_id=user_id)
    user_ids = list(inv_qs.values_list("user_id", flat=True).distinct())
    archived = 0
    for uid in user_ids:
        cards = Card.objects.filter(owner_id=uid, status="published", deactivation_marked=True)
        for c in cards:
            c.status = "archived"
            c.archived_at = timezone.now()
            c.deactivation_marked = False
            c.deactivation_marked_at = None
            # Lock nickname for 30 days (if exists)
            try:
                c.nickname_locked_until = (period_end or timezone.localdate()) + dt.timedelta(days=30)
            except Exception:
                c.nickname_locked_until = None
            c.save(update_fields=[
                "status",
                "archived_at",
                "deactivation_marked",
                "deactivation_marked_at",
                "nickname_locked_until",
            ])
            archived += 1
    return {"ok": True, "archived": archived, "users": len(user_ids), "period_end": str(period_end)}


@shared_task
def billing_archive_marked_cards(period_end: str, user_id: int | None = None):
    try:
        y, m, d = map(int, period_end.split("-"))
        pe = dt.date(y, m, d)
    except Exception:
        pe = timezone.localdate()
    return run_archive_marked_cards(pe, user_id)
