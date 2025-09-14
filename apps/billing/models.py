from django.conf import settings
from django.db import models
from apps.metering.models import MeteringEvent
from apps.common.models import BaseModel

class CustomerProfile(BaseModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    stripe_customer_id = models.CharField(max_length=80, blank=True, null=True)
    default_payment_method = models.CharField(max_length=80, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"CustomerProfile(user={self.user}, active={self.is_active})"


class UsageEvent(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    units = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [models.Index(fields=["user", "created_at"])]


class Invoice(BaseModel):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("open", "Open"),
        ("paid", "Paid"),
        ("uncollectible", "Uncollectible"),
        ("void", "Void"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    stripe_invoice_id = models.CharField(max_length=80, unique=True)
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=10, default="usd")
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    hosted_invoice_url = models.URLField(blank=True, null=True)
    # created_at and updated_at come from BaseModel

    class Meta:
        indexes = [models.Index(fields=["user", "period_start", "period_end"])]


class InvoiceLine(BaseModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    metering_event = models.OneToOneField(MeteringEvent, on_delete=models.PROTECT, related_name="invoice_line")
    amount_cents = models.PositiveIntegerField()

    class Meta:
        indexes = [
            models.Index(fields=["invoice"]),
        ]
