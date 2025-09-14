import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from apps.common.models import BaseModel


class SchedulingService(BaseModel):
    TYPE_CHOICES = [("local", "Local"), ("remote", "Remote"), ("onsite", "Onsite")]

    card = models.ForeignKey("cards.Card", on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    timezone = models.CharField(max_length=64)
    duration_minutes = models.PositiveIntegerField(default=30)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="remote")
    video_link_template = models.CharField(max_length=200, blank=True)
    buffer_before = models.PositiveIntegerField(default=0)
    buffer_after = models.PositiveIntegerField(default=0)
    lead_time_min = models.PositiveIntegerField(default=0)
    cancel_min = models.PositiveIntegerField(default=0)
    resched_min = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["card", "is_active"])]


class ServiceGalleryItem(BaseModel):
    service = models.ForeignKey(SchedulingService, on_delete=models.CASCADE)
    file = models.FileField(upload_to="services/gallery/")
    caption = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        indexes = [models.Index(fields=["service", "order"])]


class ServiceAvailability(BaseModel):
    RULE_CHOICES = [("weekly", "Weekly"), ("date_override", "Date Override"), ("holiday", "Holiday")]
    service = models.ForeignKey(SchedulingService, on_delete=models.CASCADE, related_name="availability")
    rule_type = models.CharField(max_length=20, choices=RULE_CHOICES)
    weekday = models.PositiveSmallIntegerField(blank=True, null=True)  # 0=Mon .. 6=Sun
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    timezone = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [models.Index(fields=["service", "rule_type"]) ]


class CustomForm(BaseModel):
    service = models.ForeignKey(SchedulingService, on_delete=models.CASCADE)
    schema_json = models.JSONField(default=dict)


class Appointment(BaseModel):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("cancelled", "Cancelled"),
        ("no_show", "No Show"),
    ]
    LOC_CHOICES = [("local", "Local"), ("remote", "Remote"), ("onsite", "Onsite")]

    service = models.ForeignKey(SchedulingService, on_delete=models.CASCADE)
    user_name = models.CharField(max_length=120)
    user_email = models.EmailField()
    user_phone = models.CharField(max_length=40, blank=True)
    start_at_utc = models.DateTimeField()
    end_at_utc = models.DateTimeField()
    timezone = models.CharField(max_length=64)
    location_choice = models.CharField(max_length=10, choices=LOC_CHOICES, default="remote")
    address_json = models.JSONField(default=dict, blank=True)
    form_answers_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        indexes = [
            models.Index(fields=["service", "start_at_utc"]),
            models.Index(fields=["status"]),
        ]

