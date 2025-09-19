from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Card, LinkButton, CardAddress, GalleryItem


LIMITS = {"link": 15, "address": 5, "gallery": 20}


@transaction.atomic
def add_link(card: Card, **attrs) -> LinkButton:
    card = Card.objects.select_for_update().get(pk=card.pk)
    if card.linkbutton_set.count() >= LIMITS["link"]:
        raise ValidationError("Limite atingido para links (15).")
    return LinkButton.objects.create(card=card, **attrs)


@transaction.atomic
def add_address(card: Card, **attrs) -> CardAddress:
    card = Card.objects.select_for_update().get(pk=card.pk)
    if card.addresses.count() >= LIMITS["address"]:
        raise ValidationError("Limite atingido para endereços (5).")
    return CardAddress.objects.create(card=card, **attrs)


@transaction.atomic
def add_gallery_item(card: Card, **attrs) -> GalleryItem:
    card = Card.objects.select_for_update().get(pk=card.pk)
    if GalleryItem.objects.filter(card=card).count() >= LIMITS["gallery"]:
        raise ValidationError("Limite atingido para itens de galeria (20).")
    return GalleryItem.objects.create(card=card, **attrs)

