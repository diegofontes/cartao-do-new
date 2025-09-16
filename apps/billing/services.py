import datetime as dt
from calendar import monthrange
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
import stripe
import logging
from zoneinfo import ZoneInfo

from .models import CustomerProfile, UsageEvent, Invoice, InvoiceLine
from apps.metering.models import MeteringEvent

User = get_user_model()
log = logging.getLogger(__name__)

def month_bounds(date: dt.date):
    first = date.replace(day=1)
    last_day = monthrange(date.year, date.month)[1]
    last = date.replace(day=last_day)
    return first, last

def previous_month_bounds(ref: dt.date | None = None):
    ref = ref or timezone.localdate()
    first_of_current = ref.replace(day=1)
    prev_last = first_of_current - dt.timedelta(days=1)
    return month_bounds(prev_last)

def get_or_create_profile(user: User) -> CustomerProfile:
    prof, _ = CustomerProfile.objects.get_or_create(user=user)
    return prof

def get_or_create_stripe_customer(user: User) -> CustomerProfile:
    prof = get_or_create_profile(user)
    if not prof.stripe_customer_id:
        log.info("[billing] Creating Stripe customer for user_id=%s", user.id)
        customer = stripe.Customer.create(
            email=user.email or None,
            name=str(user),
        )
        prof.stripe_customer_id = customer["id"]
        prof.save(update_fields=["stripe_customer_id"])
        log.info("[billing] Created Stripe customer id=%s for user_id=%s", prof.stripe_customer_id, user.id)
    return prof

def create_setup_intent(user: User):
    prof = get_or_create_stripe_customer(user)
    si = stripe.SetupIntent.create(
        customer=prof.stripe_customer_id,
        payment_method_types=["card"],
        usage="off_session",
    )
    log.info("[billing] Created SetupIntent id=%s for customer=%s", si.get("id"), prof.stripe_customer_id)
    return si

def attach_payment_method(user: User, payment_method_id: str):
    prof = get_or_create_stripe_customer(user)
    # attach and set as default
    log.info("[billing] Attaching payment_method id=%s to customer=%s (user_id=%s)", payment_method_id, prof.stripe_customer_id, user.id)
    stripe.PaymentMethod.attach(payment_method_id, customer=prof.stripe_customer_id)
    stripe.Customer.modify(
        prof.stripe_customer_id,
        invoice_settings={"default_payment_method": payment_method_id},
    )
    # Read back from Stripe to ensure it was set and persist locally
    try:
        cust = stripe.Customer.retrieve(prof.stripe_customer_id)
        default_pm = (
            (cust.get("invoice_settings") or {}).get("default_payment_method")
            or payment_method_id
        )
        log.info("[billing] Customer %s default_payment_method now=%s", prof.stripe_customer_id, default_pm)
    except Exception:
        log.exception("[billing] Failed to retrieve Stripe customer after setting default payment method")
        default_pm = payment_method_id
    prof.default_payment_method = default_pm
    # Set anchor on first successful PM attachment
    updates = ["default_payment_method"]
    if not prof.billing_anchor_day:
        tz = prof.timezone or "America/Sao_Paulo"
        local_today = timezone.now().astimezone(ZoneInfo(tz)).date()
        prof.billing_anchor_day = local_today.day
        prof.anchor_set_at = timezone.now()
        updates += ["billing_anchor_day", "anchor_set_at"]
    # Update payment method status
    if getattr(prof, "payment_method_status", None) is not None:
        prof.payment_method_status = "active"
        updates.append("payment_method_status")
    prof.save(update_fields=updates)
    log.info("[billing] Persisted default_payment_method for user_id=%s value=%s", user.id, prof.default_payment_method)
    return prof

def compute_usage_units(user: User, start: dt.date, end: dt.date) -> int:
    qs = UsageEvent.objects.filter(user=user, created_at__date__gte=start, created_at__date__lte=end)
    return sum(e.units for e in qs)

def compute_amount_cents(units: int) -> int:
    return units * int(getattr(settings, "UNIT_PRICE_CENTS", 25))


def get_unbilled_metering_events(user: User, start: dt.date, end: dt.date):
    return (
        MeteringEvent.objects
        .filter(user=user, occurred_at__date__gte=start, occurred_at__date__lte=end)
        .filter(invoice_line__isnull=True)
        .order_by("occurred_at")
    )


def compute_metering_amount_cents(user: User, start: dt.date, end: dt.date) -> tuple[int, list[MeteringEvent]]:
    events = list(get_unbilled_metering_events(user, start, end))
    total = sum(e.quantity * e.unit_price_cents for e in events)
    return total, events

@transaction.atomic
def create_and_pay_invoice_for_period(user: User, start: dt.date, end: dt.date) -> Invoice | None:
    prof = get_or_create_stripe_customer(user)
    if not prof.default_payment_method:
        return None  # não há cartão cadastrado, não fatura

    # Prefer metering aggregation; fallback to legacy usage units
    amount_cents, events = compute_metering_amount_cents(user, start, end)
    created_items = []
    if amount_cents > 0:
        # Group events by (resource_type, event_type) for transparency
        from collections import defaultdict
        groups = defaultdict(list)
        for e in events:
            groups[(e.resource_type, e.event_type)].append(e)
        for (rtype, etype), evs in groups.items():
            group_amount = sum(e.quantity * e.unit_price_cents for e in evs)
            if group_amount <= 0:
                continue
            desc = f"{rtype}:{etype} x{sum(e.quantity for e in evs)} — {start.strftime('%Y-%m-%d')} a {end.strftime('%Y-%m-%d')}"
            created_items.append(
                stripe.InvoiceItem.create(
                    customer=prof.stripe_customer_id,
                    amount=group_amount,
                    currency=getattr(settings, "DEFAULT_CURRENCY", "usd"),
                    description=desc,
                )
            )
    else:
        # Legacy usage fallback
        units = compute_usage_units(user, start, end)
        amount_cents = compute_amount_cents(units)
        if amount_cents <= 0:
            return None
        desc = f"Consumo {start.strftime('%Y-%m-%d')} a {end.strftime('%Y-%m-%d')} ({units} unidades)"
        created_items.append(
            stripe.InvoiceItem.create(
                customer=prof.stripe_customer_id,
                amount=amount_cents,
                currency=getattr(settings, "DEFAULT_CURRENCY", "usd"),
                description=desc,
            )
        )
    inv = stripe.Invoice.create(
        customer=prof.stripe_customer_id,
        collection_method="charge_automatically",
        auto_advance=True,
        # Inclui itens de fatura pendentes criados anteriormente
        pending_invoice_items_behavior="include",
        # Garante moeda consistente com a configuração
        currency=getattr(settings, "DEFAULT_CURRENCY", "usd"),
        # Usa o método padrão salvo no perfil para esta fatura
        default_payment_method=prof.default_payment_method,
        description=desc,
    )
    # Finalize to attempt payment immediately
    inv = stripe.Invoice.finalize_invoice(inv["id"])
    # Se não estiver paga após a finalização, força pagamento usando o método padrão do perfil
    if not inv.get("paid") and prof.default_payment_method:
        try:
            inv = stripe.Invoice.pay(
                inv["id"],
                payment_method=prof.default_payment_method,
            )
        except Exception:
            # Mantém a fatura registrada mesmo se o pay falhar; status refletirá no Stripe
            pass

    invoice = Invoice.objects.create(
        user=user,
        stripe_invoice_id=inv["id"],
        amount_cents=amount_cents,
        currency=inv.get("currency") or getattr(settings, "DEFAULT_CURRENCY", "usd"),
        period_start=start,
        period_end=end,
        status=inv.get("status", "open"),
        hosted_invoice_url=inv.get("hosted_invoice_url"),
    )
    # Create invoice lines for each metering event included
    for e in events:
        InvoiceLine.objects.create(
            invoice=invoice,
            metering_event=e,
            amount_cents=e.quantity * e.unit_price_cents,
        )
    return invoice

def cancel_account(user: User):
    prof = get_or_create_profile(user)
    prof.is_active = False
    prof.save(update_fields=["is_active"])
    return prof


def has_active_payment_method(user: User) -> bool:
    """Simplified check: considers a default_payment_method in CustomerProfile as active."""
    prof = get_or_create_profile(user)
    return bool(prof.default_payment_method)
