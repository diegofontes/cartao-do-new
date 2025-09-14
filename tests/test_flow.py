import types
import datetime as dt
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.billing import services
from apps.billing.models import UsageEvent, Invoice, CustomerProfile

class DummyStripe:
    def __init__(self):
        self.customers = {}
        self.pms = set()
        self.invoice_items = []
        self.invoices = {}

    # mimic stripe.Customer.create
    def Customer_create(self, **kw):
        cid = f"cus_{len(self.customers)+1:06d}"
        self.customers[cid] = kw
        return {"id": cid}

    def PaymentMethod_attach(self, pm, customer):
        self.pms.add((pm, customer))
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
        inv["status"] = "paid"  # pretend payment succeeds
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

def test_end_to_end_billing(db, user, monkeypatch, settings):
    ds = patch_stripe(monkeypatch)

    # create stripe customer on signup
    prof = services.get_or_create_stripe_customer(user)
    assert prof.stripe_customer_id.startswith("cus_")

    # attach card
    services.attach_payment_method(user, "pm_12345")
    prof.refresh_from_db()
    assert prof.default_payment_method == "pm_12345"

    # simulate usage this month
    for _ in range(3):
        UsageEvent.objects.create(user=user, units=2)

    today = timezone.localdate()
    start = today.replace(day=1)
    end = today

    # force billing for custom short period (for the test)
    inv = services.create_and_pay_invoice_for_period(user, start, end)
    assert inv is not None
    inv.refresh_from_db()
    assert inv.status == "paid"
    assert Invoice.objects.count() == 1
    assert inv.hosted_invoice_url.startswith("https://stripe.test/")
