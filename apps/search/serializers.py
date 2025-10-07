from __future__ import annotations

from typing import Any

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from .models import SearchProfile
from .services import format_distance, profile_distance_km

MODE_LABELS = {
    "appointment": "Agendamentos",
    "delivery": "Delivery",
}


def serialize_profile(profile: SearchProfile) -> dict[str, Any]:
    card = profile.card
    distance_km = profile_distance_km(profile)
    viewer_base = getattr(settings, "VIEWER_BASE_URL", "")
    avatar_path = None
    image_fields = ["avatar_w128", "avatar_w64", "avatar"]
    for field in image_fields:
        image = getattr(card, field, None)
        name = getattr(image, "name", "") if image else ""
        if name:
            avatar_path = name
            break

    avatar_url = None
    if avatar_path:
        try:
            avatar_url = reverse("media:image_public", kwargs={"path": avatar_path})
        except NoReverseMatch:
            avatar_url = None
    return {
        "card_id": str(card.id),
        "title": card.title,
        "nickname": card.nickname,
        "mode": card.mode,
        "mode_label": MODE_LABELS.get(card.mode, card.mode),
        "category": profile.category,
        "category_label": profile.get_category_display(),
        "radius_km": float(profile.radius_km),
        "distance_km": distance_km,
        "distance_label": format_distance(distance_km),
        "avatar_thumb_path": avatar_path,
        "avatar_thumb_url": avatar_url,
        "viewer_url": f"{viewer_base}/@{card.nickname}" if card.nickname else None,
    }
