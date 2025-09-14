from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Appointment
from apps.metering.utils import create_event


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

