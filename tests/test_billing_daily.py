import types
import datetime as dt
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.billing.utils import anchor_day_in_month
from apps.billing import services
from apps.billing.daily import billing_run_daily
from apps.billing.models import Invoice
from apps.metering.models import MeteringEvent, PricingRule


class DummyStripe:
    def __init__(self):
        self.customers = {}
        self.invoice_items = []
        self.invoices = {}

    def Customer_create(self, **kw):
        cid = f"cus_{len(self.customers)+1:06d}"
        self.customers[cid] = kw
        return {"id": cid}

    def PaymentMethod_attach(self, pm, customer):
        return {"id": pm}

    def Customer_modify(self, cid, invoice_settings):
        return {"id": cid, **invoice_settings}

    def InvoiceItem_create(self, **kw):
        self.invoice_items.append(kw)
        return {"id": f"ii_{len(self.invoice_items):06d}"}

    def Invoice_create(self, **kw):
        inv_id = f"in_{len(self.invoices)+1:06d}"
        inv = {"id": inv_id, "status": "open", "currency": kw.get("currency", "usd")}
        self.invoices[inv_id] = inv
        return inv

    def Invoice_finalize(self, inv_id):
        inv = self.invoices[inv_id]
        inv["status"] = "paid"
        inv["hosted_invoice_url"] = f"https://stripe.test/{inv_id}"
        return inv


def patch_stripe(monkeypatch):
    ds = DummyStripe()
    import apps.billing.services as s
    monkeypatch.setattr(s.stripe, "Customer", types.SimpleNamespace(create=ds.Customer_create, modify=ds.Customer_modify))
    monkeypatch.setattr(s.stripe, "PaymentMethod", types.SimpleNamespace(attach=ds.PaymentMethod_attach))
    monkeypatch.setattr(s.stripe, "InvoiceItem", types.SimpleNamespace(create=ds.InvoiceItem_create))
    monkeypatch.setattr(s.stripe, "Invoice", types.SimpleNamespace(create=ds.Invoice_create, finalize_invoice=ds.Invoice_finalize))
    return ds


def test_anchor_rules():
    assert anchor_day_in_month(2025, 4, 31) == 30  # April has 30
    assert anchor_day_in_month(2025, 2, 29) == 28  # 2025 is not leap year


def test_daily_billing_idempotent(db, user, monkeypatch):
    patch_stripe(monkeypatch)
    # Attach first payment method (sets anchor)
    prof = services.attach_payment_method(user, "pm_test")
    prof.refresh_from_db()
    assert prof.billing_anchor_day is not None

    # Create pricing + one metering event within the current period
    PricingRule.objects.create(
        code="card_publish",
        resource_type="card",
        event_type="publish",
        unit_price_cents=100,
        cadence="per_event",
        is_active=True,
    )
    MeteringEvent.objects.create(
        user=user,
        resource_type="card",
        event_type="publish",
        quantity=1,
        unit_price_cents=100,
        occurred_at=timezone.now(),
    )

    # Force today local to be period_end by setting anchor to today
    today_local = timezone.localdate()
    prof.billing_anchor_day = today_local.day
    prof.payment_method_status = "active"
    prof.anchor_set_at = timezone.now() - dt.timedelta(days=31)
    prof.last_billed_period_end = None
    prof.save()

    # Run twice with same process date (UTC). Expect only one invoice.
    res1 = billing_run_daily(today_local)
    res2 = billing_run_daily(today_local)
    assert Invoice.objects.count() == 1
    assert res1["invoices_created"] >= 1
    assert res2["invoices_created"] in (0, 1)

