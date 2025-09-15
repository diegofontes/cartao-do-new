from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    # API
    path("notifications", views.api_create_notification, name="create"),
    # Webhooks
    path("webhooks/twilio/sms-status", views.twilio_sms_status, name="twilio_sms_status"),
    path("webhooks/sendgrid/email-events", views.sendgrid_email_events, name="sendgrid_email_events"),
]

