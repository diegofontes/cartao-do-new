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
    public_code = models.CharField(max_length=12, unique=True)
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

    def save(self, *args, **kwargs):
        from apps.common.codes import generate_unique_code

        if not self.public_code:
            def _exists(code: str) -> bool:
                qs = type(self).objects.filter(public_code=f"A{code}")
                if self.pk:
                    qs = qs.exclude(pk=self.pk)
                return qs.exists()

            base_code = generate_unique_code(length=7, exists=_exists)
            self.public_code = f"A{base_code}"
        super().save(*args, **kwargs)


class RescheduleRequest(BaseModel):
    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
    ]

    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="reschedule_requests")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="requested")
    requested_by = models.CharField(max_length=20, default="customer")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    preferred_windows = models.JSONField(default=list, blank=True)
    reason = models.TextField(blank=True)
    owner_message = models.TextField(blank=True)
    new_start_at_utc = models.DateTimeField(blank=True, null=True)
    new_end_at_utc = models.DateTimeField(blank=True, null=True)
    requested_start_at_utc = models.DateTimeField(blank=True, null=True)
    requested_end_at_utc = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    requested_ip = models.GenericIPAddressField(blank=True, null=True)
    action_ip = models.GenericIPAddressField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["appointment", "status", "created_at"]),
        ]
