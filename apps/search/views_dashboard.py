from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.cards.models import Card
from .forms import SearchPreviewForm, SearchProfileForm
from .services import search_profiles
from .serializers import serialize_profile
from .forms import SearchQuery
from .geocoding import GeocodingError, geocode_cep


def _get_card_or_403(request, card_id: str) -> Card:
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        raise PermissionError("Card marcado para desativação")
    return card


def _render_panel(request, card: Card, status: int = 200) -> HttpResponse:
    profile = getattr(card, "search_profile", None)
    form = SearchProfileForm(instance=profile)
    preview_initial = {}
    if profile and profile.origin:
        preview_initial = {
            "latitude": profile.origin.y,
            "longitude": profile.origin.x,
            "radius_km": min(profile.radius_km, 10.0),
        }
    preview_form = SearchPreviewForm(initial=preview_initial)
    response = render(
        request,
        "search/_dashboard_panel.html",
        {
            "card": card,
            "profile": profile,
            "form": form,
            "preview_form": preview_form,
            "preview_results": [],
        },
    )
    response.status_code = status
    return response


@login_required
@require_http_methods(["GET"])
def profile_panel(request, card_id: str) -> HttpResponse:
    try:
        card = _get_card_or_403(request, card_id)
    except PermissionError:
        return HttpResponseForbidden("Card marcado para desativação")
    return _render_panel(request, card)


@login_required
@require_POST
def profile_save(request, card_id: str) -> HttpResponse:
    try:
        card = _get_card_or_403(request, card_id)
    except PermissionError:
        return HttpResponseForbidden("Card marcado para desativação")
    profile = getattr(card, "search_profile", None)
    form = SearchProfileForm(request.POST, instance=profile)
    if not form.is_valid():
        return render(
            request,
            "search/_dashboard_panel.html",
            {
                "card": card,
                "profile": profile,
                "form": form,
                "preview_form": SearchPreviewForm(),
                "preview_results": [],
            },
            status=422,
        )
    form.save(card=card)
    resp = _render_panel(request, card)
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Perfil salvo", "message": "Atualizamos o perfil de busca."}})
    return resp


@login_required
@require_POST
def profile_deactivate(request, card_id: str) -> HttpResponse:
    try:
        card = _get_card_or_403(request, card_id)
    except PermissionError:
        return HttpResponseForbidden("Card marcado para desativação")
    profile = getattr(card, "search_profile", None)
    if profile is None:
        return _render_panel(request, card)
    profile.active = False
    profile.save(update_fields=["active"])
    resp = _render_panel(request, card)
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Perfil desativado", "message": "O perfil não aparecerá nas buscas."}})
    return resp


@login_required
@require_POST
def profile_preview(request, card_id: str) -> HttpResponse:
    try:
        card = _get_card_or_403(request, card_id)
    except PermissionError:
        return HttpResponseForbidden("Card marcado para desativação")
    form = SearchPreviewForm(request.POST)
    if not form.is_valid():
        return render(request, "search/_preview_results.html", {"form": form, "results": []}, status=422)
    cleaned = form.cleaned_data
    query = SearchQuery(
        latitude=cleaned["latitude"],
        longitude=cleaned["longitude"],
        radius_km=cleaned.get("radius_km"),
        category=cleaned.get("category") or None,
        mode=cleaned.get("mode") or None,
        limit=20,
    )
    profiles = search_profiles(query)
    data = [serialize_profile(p) for p in profiles]
    return render(
        request,
        "search/_preview_results.html",
        {
            "results": data,
            "form": SearchPreviewForm(initial=cleaned),
            "query": query,
        },
    )


@login_required
@require_POST
def geocode_stub(request) -> HttpResponse:
    cep = (request.POST.get("cep") or "").strip()
    if not cep:
        return JsonResponse({"error": "Informe um CEP."}, status=400)
    try:
        payload = geocode_cep(cep)
    except GeocodingError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status_code)
    return JsonResponse(payload)
