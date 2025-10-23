from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings
from .models import Card, LinkButton, SocialLink, GalleryItem
from .markdown import has_about_content, sanitize_about_markdown
from apps.scheduling.models import SchedulingService

#from apps.delivery.views_public import menu_home as delivery_menu_home

try:
    # Optional import to delegate to delivery menu renderer
    from apps.delivery.views_public import menu_home as delivery_menu_home
except Exception:  # pragma: no cover - delivery app may not be loaded in some contexts
    delivery_menu_home = None


def _get_card_by_nickname(nickname: str) -> Card:
    q = Card.objects.filter(nickname__iexact=nickname, status="published", deactivation_marked=False)
    return get_object_or_404(q)


@ensure_csrf_cookie
def card_public(request, nickname: str):
    card = _get_card_by_nickname(nickname)
    print(card.mode, delivery_menu_home)
    if getattr(card, "mode", "appointment") == "delivery" and delivery_menu_home:
        return delivery_menu_home(request, nickname)
    links = LinkButton.objects.filter(card=card).order_by("order", "created_at")
    socials = SocialLink.objects.filter(card=card, is_active=True).order_by("order", "created_at")
    gallery = GalleryItem.objects.filter(card=card, visible_in_gallery=True).order_by("importance", "order", "created_at")
    services = SchedulingService.objects.filter(card=card, is_active=True).order_by("-created_at") if card.mode != "delivery" else []
    about_html = ""
    about_enabled = False
    if has_about_content(card.about_markdown):
        try:
            about_html = sanitize_about_markdown(card.about_markdown or "")
            about_enabled = bool(about_html.strip())
        except ValueError:
            about_html = ""
            about_enabled = False
    allowed_base = ["links", "gallery"]
    if card.mode != "delivery":
        allowed_base.append("services")
    if about_enabled:
        allowed_base.append("about")
    allowed = tuple(allowed_base)
    raw_order = (card.tabs_order or "links,gallery,services")
    tab_order = [k.strip() for k in raw_order.split(',') if k.strip() in allowed]
    if about_enabled and "about" not in tab_order:
        tab_order.append("about")
    if not tab_order:
        tab_order = ["links", "gallery"] + (["services"] if card.mode != "delivery" else [])
        if about_enabled:
            tab_order.append("about")
    return render(request, "public/card_public.html", {
        "card": card,
        "links": links,
        "socials": socials,
        "gallery": gallery,
        "services": services,
        "tab_order": tab_order,
        "about_html": about_html,
        "about_enabled": about_enabled,
    })

def tabs_links(request, nickname: str):
    card = _get_card_by_nickname(nickname)
    links = LinkButton.objects.filter(card=card).order_by("order", "created_at")
    return render(request, "public/tabs_links.html", {"card": card, "links": links})

def tabs_gallery(request, nickname: str):
    card = _get_card_by_nickname(nickname)
    gallery = GalleryItem.objects.filter(card=card, visible_in_gallery=True).order_by("importance", "order", "created_at")
    return render(request, "public/tabs_gallery.html", {"card": card, "gallery": gallery})

def tabs_services(request, nickname: str):
    card = _get_card_by_nickname(nickname)
    if card.mode == "delivery":
        # Services tab not available for delivery-mode cards
        from django.http import Http404
        raise Http404()
    services = SchedulingService.objects.filter(card=card, is_active=True).order_by("-created_at")
    return render(request, "public/tabs_services.html", {"card": card, "services": services})
