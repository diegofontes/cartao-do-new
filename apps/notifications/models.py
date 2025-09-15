from django.db import models
from django.utils import timezone
from apps.common.models import BaseModel


class Notification(BaseModel):
    TYPE_CHOICES = [("sms", "SMS"), ("email", "Email")]
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("processing", "Processing"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
        ("bounced", "Bounced"),
        ("cancelled", "Cancelled"),
    ]
    PROVIDER_CHOICES = [("twilio", "Twilio"), ("sendgrid", "SendGrid"), ("dev", "Dev Mode")]

    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    to = models.CharField(max_length=200)
    template_code = models.CharField(max_length=80)
    payload_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued", db_index=True)
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, blank=True, null=True)
    provider_message_id = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    error_code = models.CharField(max_length=50, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    attempts = models.PositiveIntegerField(default=0)
    idempotency_key = models.CharField(max_length=120, blank=True, null=True, unique=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    is_dlq = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]

    def mark(self, *, status: str, **extra):
        for k, v in extra.items():
            setattr(self, k, v)
        self.status = status
        self.save()


class NotificationAttempt(BaseModel):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="attempts_log")
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(blank=True, null=True)
    result = models.CharField(max_length=20)  # ok | error
    provider_response_json = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, null=True)


class Template(BaseModel):
    CHANNEL_CHOICES = [("sms", "SMS"), ("email", "Email")]
    code = models.CharField(max_length=80)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    subject = models.CharField(max_length=200, blank=True)
    body_txt = models.TextField(blank=True)
    body_html = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["code", "channel"], name="uniq_template_code_channel")]

