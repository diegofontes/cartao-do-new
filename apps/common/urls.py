from django.conf import settings
from django.urls import reverse


def viewer_order_url(code: str) -> str:
    """Return an absolute URL for the public order detail page."""
    base = (getattr(settings, "VIEWER_BASE_URL", "") or "").rstrip("/")
    path = reverse("viewer:order_detail", args=[code])
    return f"{base}{path}" if base else path
