from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from django import forms
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError

from .models import SearchCategory, SearchProfile


LAT_MIN, LAT_MAX = -90.0, 90.0
LNG_MIN, LNG_MAX = -180.0, 180.0
PROFILE_RADIUS_MIN = 0.5
PROFILE_RADIUS_MAX = 200.0
DEFAULT_PREVIEW_RADIUS = 10.0
MAX_API_RADIUS = 200.0


def _validate_lat_lng(lat: float | None, lng: float | None) -> None:
    if lat is None or lng is None:
        raise ValidationError("Latitude e longitude são obrigatórias.")
    if not (LAT_MIN <= lat <= LAT_MAX):
        raise ValidationError("Latitude fora do intervalo -90 a 90.")
    if not (LNG_MIN <= lng <= LNG_MAX):
        raise ValidationError("Longitude fora do intervalo -180 a 180.")


class SearchProfileForm(forms.Form):
    category = forms.ChoiceField(choices=SearchCategory.choices, label="Categoria", widget=forms.Select(attrs={"class": "input"}))
    radius_km = forms.FloatField(
        label="Raio de atuação (km)",
        min_value=PROFILE_RADIUS_MIN,
        max_value=PROFILE_RADIUS_MAX,
        widget=forms.NumberInput(attrs={"step": "0.1", "min": PROFILE_RADIUS_MIN, "max": PROFILE_RADIUS_MAX, "class": "input"}),
    )
    latitude = forms.FloatField(
        label="Latitude",
        required=False,
        widget=forms.NumberInput(attrs={"step": "0.0000001", "class": "input"}),
    )
    longitude = forms.FloatField(
        label="Longitude",
        required=False,
        widget=forms.NumberInput(attrs={"step": "0.0000001", "class": "input"}),
    )
    active = forms.BooleanField(label="Perfil ativo", required=False, initial=True)

    def __init__(self, *args: Any, instance: Optional[SearchProfile] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.instance = instance
        if instance is not None and not self.is_bound:
            self.initial.update(
                {
                    "category": instance.category,
                    "radius_km": instance.radius_km,
                    "active": instance.active,
                }
            )
            if instance.origin:
                self.initial.update(
                    {
                        "latitude": instance.origin.y,
                        "longitude": instance.origin.x,
                    }
                )

    def clean(self) -> dict[str, Any]:
        data = super().clean()
        active = data.get("active")
        lat = data.get("latitude")
        lng = data.get("longitude")
        if active:
            _validate_lat_lng(lat, lng)
        elif lat is None and lng is None:
            return data
        elif lat is None or lng is None:
            raise ValidationError("Informe latitude e longitude ou deixe ambos vazios.")
        else:
            _validate_lat_lng(lat, lng)
        if lat is not None and lng is not None:
            data["origin"] = Point(float(lng), float(lat), srid=4326)
        return data

    def save(self, *, card) -> SearchProfile:
        if not self.is_valid():
            raise ValueError("Form must be valid before calling save().")
        cleaned = self.cleaned_data
        instance = self.instance or SearchProfile(card=card)
        instance.category = cleaned["category"]
        instance.radius_km = cleaned["radius_km"]
        instance.active = bool(cleaned.get("active"))
        origin = cleaned.get("origin")
        if origin is None and instance.active:
            raise ValidationError("Perfil ativo precisa de coordenadas válidas.")
        instance.origin = origin
        instance.save()
        self.instance = instance
        return instance


class SearchPreviewForm(forms.Form):
    latitude = forms.FloatField(label="Latitude", required=True, widget=forms.NumberInput(attrs={"step": "0.0000001"}))
    longitude = forms.FloatField(label="Longitude", required=True, widget=forms.NumberInput(attrs={"step": "0.0000001"}))
    radius_km = forms.FloatField(
        label="Raio (km)",
        required=False,
        min_value=PROFILE_RADIUS_MIN,
        max_value=PROFILE_RADIUS_MAX,
        widget=forms.NumberInput(attrs={"step": "0.5", "min": PROFILE_RADIUS_MIN, "max": PROFILE_RADIUS_MAX}),
    )
    category = forms.ChoiceField(choices=[("", "Todas")] + list(SearchCategory.choices), required=False)
    mode = forms.ChoiceField(choices=[("", "Todos"), ("appointment", "Agendamentos"), ("delivery", "Delivery")], required=False)

    def clean(self) -> dict[str, Any]:
        data = super().clean()
        _validate_lat_lng(data.get("latitude"), data.get("longitude"))
        if not data.get("radius_km"):
            data["radius_km"] = DEFAULT_PREVIEW_RADIUS
        return data


@dataclass(slots=True)
class SearchQuery:
    latitude: float
    longitude: float
    radius_km: float | None
    category: str | None
    mode: str | None
    limit: int
    offset: int = 0

    @property
    def user_point(self) -> Point:
        point = Point(self.longitude, self.latitude, srid=4326)
        return point


class SearchQueryForm(forms.Form):
    lat = forms.FloatField()
    lng = forms.FloatField()
    radius_km = forms.FloatField(required=False)
    category = forms.ChoiceField(choices=[("", "Todas")] + list(SearchCategory.choices), required=False)
    mode = forms.ChoiceField(choices=[("", "Todos"), ("appointment", "Agendamentos"), ("delivery", "Delivery")], required=False)
    limit = forms.IntegerField(required=False, min_value=1, max_value=200)
    offset = forms.IntegerField(required=False, min_value=0)

    def clean(self) -> dict[str, Any]:
        data = super().clean()
        _validate_lat_lng(data.get("lat"), data.get("lng"))
        radius = data.get("radius_km")
        if radius is not None:
            if radius <= 0:
                raise ValidationError("Raio precisa ser positivo.")
            radius = min(float(radius), MAX_API_RADIUS)
        data["radius_km"] = radius
        mode = data.get("mode") or ""
        if mode and mode not in {"appointment", "delivery"}:
            raise ValidationError("Modo inválido.")
        cat = data.get("category") or ""
        if cat and cat not in dict(SearchCategory.choices):
            raise ValidationError("Categoria inválida.")
        limit = data.get("limit") or 50
        data["limit"] = max(1, min(int(limit), 200))
        offset = data.get("offset") or 0
        data["offset"] = max(0, int(offset))
        return data

    def to_query(self) -> SearchQuery:
        if not self.is_valid():
            raise ValueError("Form must be valid before to_query().")
        cleaned = self.cleaned_data
        return SearchQuery(
            latitude=float(cleaned["lat"]),
            longitude=float(cleaned["lng"]),
            radius_km=cleaned.get("radius_km"),
            category=(cleaned.get("category") or None),
            mode=(cleaned.get("mode") or None),
            limit=int(cleaned.get("limit")),
            offset=int(cleaned.get("offset", 0)),
        )
