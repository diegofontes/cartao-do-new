from __future__ import annotations

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.db.models import F, QuerySet

from .forms import SearchQuery
from .models import SearchProfile


def build_point(lat: float, lng: float, srid: int = 4326) -> Point:
    """Return a GEOS point in lon/lat order."""
    return Point(float(lng), float(lat), srid=srid)


def search_profiles(query: SearchQuery, *, extra: int = 0) -> QuerySet[SearchProfile]:
    user_point = build_point(query.latitude, query.longitude)
    offset = max(0, int(getattr(query, "offset", 0) or 0))
    limit = max(1, int(getattr(query, "limit", 1) or 1))
    total = limit + max(0, int(extra))

    qs = (
        SearchProfile.objects
        .filter(active=True, origin__isnull=False)
        .filter(card__status="published", card__deactivation_marked=False)
        .annotate(distance=Distance("origin", user_point, spheroid=True))
        .filter(distance__lte=F("radius_km") * 1000)
    )

    if query.radius_km is not None:
        qs = qs.filter(distance__lte=query.radius_km * 1000)
    if query.category:
        qs = qs.filter(category=query.category)
    if query.mode:
        qs = qs.filter(card__mode=query.mode)

    return (
        qs
        .select_related("card")
        .order_by("distance", "created_at")[offset: offset + total]
    )


def profile_distance_km(profile: SearchProfile) -> float:
    distance = getattr(profile, "distance", None)
    if distance is None:
        return 0.0
    try:
        return float(distance.km)
    except AttributeError:
        # Distance may come back as meters (float)
        return float(distance) / 1000.0


def format_distance(distance_km: float) -> str:
    if distance_km < 1:
        return f"{distance_km * 1000:.0f} m"
    return f"{distance_km:.1f} km"
