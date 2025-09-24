from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.common.models import BaseModel


class PricingRule(BaseModel):
    CADENCE_CHOICES = [("once", "Once"), ("monthly", "Monthly"), ("per_event", "Per Event")]
    RESOURCE_CHOICES = [
        ("card", "Card"),
        ("link", "Link"),
        ("gallery", "Gallery"),
        ("appointment", "Appointment"),
        ("delivery", "Delivery"),
    ]
    EVENT_CHOICES = [
        ("publish", "Publish"),
        ("link_add", "Link Added"),
        ("gallery_add", "Gallery Added"),
        ("appointment_confirmed", "Appointment Confirmed"),
        ("order_accepted", "Order Accepted"),
    ]

    code = models.CharField(max_length=50, unique=True)
    resource_type = models.CharField(max_length=20, choices=RESOURCE_CHOICES)
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    unit_price_cents = models.PositiveIntegerField()
    cadence = models.CharField(max_length=20, choices=CADENCE_CHOICES, default="per_event")
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(blank=True, null=True)
    ends_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["resource_type", "event_type", "is_active"]),
        ]


class MeteringEvent(BaseModel):
    RESOURCE_CHOICES = PricingRule.RESOURCE_CHOICES
    EVENT_CHOICES = PricingRule.EVENT_CHOICES

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # Optional FKs for traceability
    card = models.ForeignKey("cards.Card", on_delete=models.SET_NULL, null=True, blank=True)
    service = models.ForeignKey("scheduling.SchedulingService", on_delete=models.SET_NULL, null=True, blank=True)
    appointment = models.ForeignKey("scheduling.Appointment", on_delete=models.SET_NULL, null=True, blank=True)

    resource_type = models.CharField(max_length=20, choices=RESOURCE_CHOICES)
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    quantity = models.PositiveIntegerField(default=1)
    unit_price_cents = models.PositiveIntegerField(default=0)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["user", "occurred_at"]),
            models.Index(fields=["resource_type", "event_type"]),
        ]
