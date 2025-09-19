from django.shortcuts import render, get_object_or_404
from django.conf import settings
from .models import Card, LinkButton, SocialLink, GalleryItem
from apps.scheduling.models import SchedulingService


def _get_card_by_nickname(nickname: str) -> Card:
    q = Card.objects.filter(nickname__iexact=nickname, status="published", deactivation_marked=False)
    return get_object_or_404(q)


def card_public(request, nickname: str):
    card = _get_card_by_nickname(nickname)
    links = LinkButton.objects.filter(card=card).order_by("order", "created_at")
    socials = SocialLink.objects.filter(card=card, is_active=True).order_by("order", "created_at")
    gallery = GalleryItem.objects.filter(card=card).order_by("order", "created_at")
    services = SchedulingService.objects.filter(card=card, is_active=True).order_by("-created_at")
    allowed = ("links", "gallery", "services")
    raw_order = (card.tabs_order or "links,gallery,services")
    tab_order = [k.strip() for k in raw_order.split(',') if k.strip() in allowed]
    if not tab_order:
        tab_order = ["links", "gallery", "services"]
    return render(request, "public/card_public.html", {
        "card": card,
        "links": links,
        "socials": socials,
        "gallery": gallery,
        "services": services,
        "tab_order": tab_order,
    })

def tabs_links(request, nickname: str):
    card = _get_card_by_nickname(nickname)
    links = LinkButton.objects.filter(card=card).order_by("order", "created_at")
    return render(request, "public/tabs_links.html", {"card": card, "links": links})

def tabs_gallery(request, nickname: str):
    card = _get_card_by_nickname(nickname)
    gallery = GalleryItem.objects.filter(card=card).order_by("order", "created_at")
    return render(request, "public/tabs_gallery.html", {"card": card, "gallery": gallery})

def tabs_services(request, nickname: str):
    card = _get_card_by_nickname(nickname)
    services = SchedulingService.objects.filter(card=card, is_active=True).order_by("-created_at")
    return render(request, "public/tabs_services.html", {"card": card, "services": services})
