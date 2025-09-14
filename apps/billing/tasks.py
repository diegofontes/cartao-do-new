import datetime as dt
from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone
import logging
from .services import previous_month_bounds, create_and_pay_invoice_for_period, get_or_create_profile

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
