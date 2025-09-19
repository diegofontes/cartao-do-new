from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Card, LinkButton, GalleryItem
from apps.metering.utils import create_event


@receiver(pre_save, sender=Card)
def card_publish_metering(sender, instance: Card, **kwargs):
    if not instance.pk:
        return
    try:
        old = Card.objects.get(pk=instance.pk)
    except Card.DoesNotExist:
        return
    if old.status != "published" and instance.status == "published":
        # publish event
        create_event(user=instance.owner, resource_type="card", event_type="publish", card=instance)


@receiver(post_save, sender=LinkButton)
def link_button_created(sender, instance: LinkButton, created, **kwargs):
    # Billing for links disabled: do not create metering events
    return


@receiver(post_save, sender=GalleryItem)
def gallery_item_created(sender, instance: GalleryItem, created, **kwargs):
    # Billing for gallery disabled: do not create metering events
    return
