from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Appointment
from apps.metering.utils import create_event
from django.db import transaction
from apps.notifications.api import enqueue, Enqueue, enqueue_many
from django.utils import timezone
from zoneinfo import ZoneInfo


@receiver(pre_save, sender=Appointment)
def appointment_confirmed_event(sender, instance: Appointment, **kwargs):
    if not instance.pk:
        return
    try:
        old = Appointment.objects.get(pk=instance.pk)
    except Appointment.DoesNotExist:
        return
    if old.status != "confirmed" and instance.status == "confirmed":
        create_event(
            user=instance.service.card.owner,
            resource_type="appointment",
            event_type="appointment_confirmed",
            service=instance.service,
            appointment=instance,
        )
        # Envia confirmações (SMS/email) após commit
        svc = instance.service
        card = svc.card
        tz = ZoneInfo(instance.timezone or "UTC")
        date_local = instance.start_at_utc.astimezone(tz).strftime("%d/%m/%Y")
        time_local = instance.start_at_utc.astimezone(tz).strftime("%H:%M")
        ics_url = None  # opcional, pode ser preenchido no futuro
        def _dispatch():
            enqueue_many([
                Enqueue(
                    type='sms',
                    to=instance.user_phone,
                    template_code='booking_confirmed_sms',
                    payload={'name': instance.user_name, 'service': svc.name, 'date': date_local, 'time': time_local, 'nick': card.nickname},
                    idempotency_key=f'appt_confirm:{instance.id}:sms'
                ) if instance.user_phone else None,
                Enqueue(
                    type='email',
                    to=instance.user_email,
                    template_code='booking_confirmed_email',
                    payload={'name': instance.user_name, 'service': svc.name, 'date': date_local, 'time': time_local, 'nick': card.nickname, 'ics_url': ics_url},
                    idempotency_key=f'appt_confirm:{instance.id}:email'
                ) if instance.user_email else None,
            ])
        try:
            transaction.on_commit(_dispatch)
        except Exception:
            _dispatch()
