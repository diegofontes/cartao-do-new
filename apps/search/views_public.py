from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse, QueryDict
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from django.urls import reverse

from .forms import SearchQuery, SearchQueryForm
from .models import SearchCategory
from .serializers import serialize_profile
from .services import search_profiles
from .geocoding import GeocodingError, geocode_cep, geocode_address_sp

DEFAULT_RATE_LIMIT = int(getattr(settings, "SEARCH_RATE_LIMIT", 60))
DEFAULT_RATE_WINDOW = int(getattr(settings, "SEARCH_RATE_WINDOW", 60))
GEOCODE_RATE_LIMIT = 5
GEOCODE_RATE_WINDOW = 60
DEFAULT_RADIUS = float(getattr(settings, "SEARCH_DEFAULT_RADIUS", 10))
MAX_RADIUS = float(getattr(settings, "SEARCH_MAX_RADIUS", 50))
SP_LAT_MIN = -25.5
SP_LAT_MAX = -19.0
SP_LNG_MIN = -53.5
SP_LNG_MAX = -44.0
RESULTS_PAGE_SIZE = max(1, int(getattr(settings, "SEARCH_RESULTS_PAGE_SIZE", 15)))


def _client_key(request: HttpRequest) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "anon")


def _check_rate_limit(
    request: HttpRequest,
    *,
    prefix: str = "search:rate",
    limit: int | None = None,
    window: int | None = None,
) -> tuple[bool, int]:
    window = int(window or DEFAULT_RATE_WINDOW)
    limit = int(limit or DEFAULT_RATE_LIMIT)
    key = f"{prefix}:{_client_key(request)}"
    now = int(time.time())
    entry = cache.get(key)
    if entry is None:
        cache.set(key, json.dumps({"count": 1, "reset": now + window}), timeout=window)
        return True, window
    try:
        payload: dict[str, Any] = json.loads(entry)
    except Exception:
        payload = {"count": 0, "reset": now + window}
    count = int(payload.get("count", 0)) + 1
    reset = int(payload.get("reset", now + window))
    if count > limit:
        ttl = max(0, reset - now)
        return False, ttl
    cache.set(key, json.dumps({"count": count, "reset": reset}), timeout=max(1, reset - now))
    return True, max(0, reset - now)


def _clamp_radius(value: float | None) -> float:
    if value is None or value <= 0:
        return DEFAULT_RADIUS
    return max(1.0, min(float(value), MAX_RADIUS))


def _is_inside_sp(lat: float, lng: float) -> bool:
    return (SP_LAT_MIN <= lat <= SP_LAT_MAX) and (SP_LNG_MIN <= lng <= SP_LNG_MAX)


def _encode_querystring(query: SearchQuery, *, offset: int | None = None) -> str:
    actual_offset = query.offset if offset is None else max(0, offset)
    params: dict[str, Any] = {
        "lat": f"{float(query.latitude):.6f}",
        "lng": f"{float(query.longitude):.6f}",
        "limit": str(int(query.limit)),
        "offset": str(int(actual_offset)),
    }
    radius = getattr(query, "radius_km", None)
    if radius is not None:
        params["radius_km"] = str(radius)
    category = getattr(query, "category", None)
    if category:
        params["category"] = category
    mode = getattr(query, "mode", None)
    if mode:
        params["mode"] = mode
    return urlencode(params)


def _serialize_results(
    query_data: QueryDict,
    *,
    initial: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    form = SearchQueryForm(query_data)
    if not form.is_valid():
        context = {
            "form": form,
            "results": [],
            "error": "Parâmetros inválidos para a busca.",
            "viewer_base": getattr(settings, "VIEWER_BASE_URL", ""),
        }
        if extra:
            context.update(extra)
        return context

    query = form.to_query()
    query.limit = max(1, min(query.limit, RESULTS_PAGE_SIZE))
    query.offset = max(0, query.offset)
    query.radius_km = _clamp_radius(query.radius_km)
    raw_profiles = list(search_profiles(query, extra=1))
    has_more = len(raw_profiles) > query.limit
    if has_more:
        profiles = raw_profiles[: query.limit]
    else:
        profiles = raw_profiles
    next_offset = query.offset + len(profiles)
    context = {
        "form": SearchQueryForm(initial=initial or query_data),
        "results": [serialize_profile(profile) for profile in profiles],
        "viewer_base": getattr(settings, "VIEWER_BASE_URL", ""),
        "radius": query.radius_km,
        "query": query,
        "center": {"lat": query.latitude, "lng": query.longitude},
        "has_more": has_more,
        "next_offset": next_offset,
        "limit": query.limit,
        "offset": query.offset,
        "load_more_url": (
            f"{reverse('search:results')}?{_encode_querystring(query, offset=next_offset)}" if has_more else ""
        ),
    }
    if not _is_inside_sp(query.latitude, query.longitude):
        context.setdefault(
            "warning",
            "A busca está disponível somente no Estado de São Paulo no momento.",
        )
    if extra:
        context.update(extra)
    return context


@require_GET
def search_page(request: HttpRequest) -> HttpResponse:
    categories = [{"value": "", "label": "Todas"}] + [
        {"value": choice.value, "label": choice.label} for choice in SearchCategory
    ]
    radius_options = [1, 3, 5, 10, 15, 20, 30, 40, 50]
    return render(
        request,
        "public/search.html",
        {
            "categories": categories,
            "default_radius": DEFAULT_RADIUS,
            "max_radius": MAX_RADIUS,
            "radius_options": radius_options,
            "page_size": RESULTS_PAGE_SIZE,
        },
    )


@require_GET
def search_results(request: HttpRequest) -> HttpResponse:
    query_data = request.GET.copy()
    try:
        limit_val = int(query_data.get("limit", RESULTS_PAGE_SIZE))
    except (TypeError, ValueError):
        limit_val = RESULTS_PAGE_SIZE
    limit_val = max(1, min(limit_val, RESULTS_PAGE_SIZE))
    query_data["limit"] = str(limit_val)
    try:
        offset_val = int(query_data.get("offset", 0))
    except (TypeError, ValueError):
        offset_val = 0
    offset_val = max(0, offset_val)
    query_data["offset"] = str(offset_val)
    if not query_data.get("radius_km"):
        query_data["radius_km"] = str(DEFAULT_RADIUS)
    context = _serialize_results(query_data, initial=query_data, extra={"source": "results"})
    status = 200 if context.get("results") or not context.get("error") else 422
    template_name = (
        "search/_search_results_append.html"
        if request.headers.get("HX-Target") == "results-list"
        else "search/_search_results.html"
    )
    return render(request, template_name, context, status=status)


@require_POST
def search_geocode(request: HttpRequest) -> HttpResponse:
    allowed, ttl = _check_rate_limit(
        request,
        prefix="search:geo",
        limit=GEOCODE_RATE_LIMIT,
        window=GEOCODE_RATE_WINDOW,
    )
    if not allowed:
        response = render(
            request,
            "search/_search_results.html",
            {
                "results": [],
                "error": "Muitas consultas em sequência. Tente novamente em instantes.",
            },
            status=429,
        )
        if ttl:
            response["Retry-After"] = str(ttl)
        return response

    address = (request.POST.get("address") or "").strip()
    state = (request.POST.get("state") or "").strip().upper()
    category = (request.POST.get("category") or "").strip()
    radius_km = (request.POST.get("radius_km") or "").strip()
    lat = request.POST.get("lat")
    lng = request.POST.get("lng")
    limit_raw = request.POST.get("limit")
    try:
        limit_val = int(limit_raw) if limit_raw else RESULTS_PAGE_SIZE
    except (TypeError, ValueError):
        limit_val = RESULTS_PAGE_SIZE
    limit_val = max(1, min(limit_val, RESULTS_PAGE_SIZE))

    if lat and lng and not address:
        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except (TypeError, ValueError):
            return render(
                request,
                "search/_search_results.html",
                {
                    "results": [],
                    "error": "Coordenadas inválidas informadas.",
                },
                status=400,
            )

        query_params = QueryDict(mutable=True)
        query_params.setlist("lat", [str(lat_f)])
        query_params.setlist("lng", [str(lng_f)])
        if radius_km:
            query_params.setlist("radius_km", [radius_km])
        if category:
            query_params.setlist("category", [category])
        query_params.setlist("limit", [str(limit_val)])
        query_params.setlist("offset", ["0"])

        context = _serialize_results(
            query_params,
            initial={
                "lat": lat_f,
                "lng": lng_f,
                "radius_km": radius_km or DEFAULT_RADIUS,
                "category": category,
                "limit": str(limit_val),
                "offset": "0",
            },
            extra={"source": "geolocation"},
        )
        status = 200 if context.get("results") or not context.get("error") else 422
        return render(request, "search/_search_results.html", context, status=status)

    if not address:
        return render(
            request,
            "search/_search_results.html",
            {"results": [], "error": "Informe um endereço para buscar."},
            status=400,
        )
    if state and state != "SP":
        return render(
            request,
            "search/_search_results.html",
            {
                "results": [],
                "error": "No momento a busca está liberada apenas para o Estado de São Paulo.",
            },
            status=422,
        )

    try:
        coords = geocode_address_sp(address)
    except GeocodingError as exc:
        return render(
            request,
            "search/_search_results.html",
            {"results": [], "error": str(exc)},
            status=exc.status_code,
        )

    query_params = QueryDict(mutable=True)
    query_params.setlist("lat", [str(coords["lat"])])
    query_params.setlist("lng", [str(coords["lng"])])
    if radius_km:
        query_params.setlist("radius_km", [radius_km])
    if category:
        query_params.setlist("category", [category])
    query_params.setlist("limit", [str(limit_val)])
    query_params.setlist("offset", ["0"])

    context = _serialize_results(
        query_params,
        initial={
            "lat": coords["lat"],
            "lng": coords["lng"],
            "radius_km": radius_km or DEFAULT_RADIUS,
            "category": category,
            "limit": str(limit_val),
            "offset": "0",
        },
        extra={"resolved_address": address, "source": "geocode"},
    )
    status = 200 if context.get("results") or not context.get("error") else 422
    return render(request, "search/_search_results.html", context, status=status)


@require_GET
def ping(_: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


@require_GET
def cards_api(request: HttpRequest) -> JsonResponse:
    allowed, ttl = _check_rate_limit(request)
    if not allowed:
        response = JsonResponse({"detail": "Rate limit excedido. Tente novamente mais tarde."}, status=429)
        if ttl:
            response["Retry-After"] = str(ttl)
        return response
    form = SearchQueryForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=422)
    query = form.to_query()
    profiles = search_profiles(query)
    data = [serialize_profile(p) for p in profiles]
    return JsonResponse({"results": data, "count": len(data)}, status=200)


@require_GET
def cards_nearby_partial(request: HttpRequest) -> HttpResponse:
    form = SearchQueryForm(request.GET)
    if not form.is_valid():
        return render(request, "search/_public_results.html", {"form": form, "results": []}, status=422)
    query = form.to_query()
    profiles = search_profiles(query)
    return render(
        request,
        "search/_public_results.html",
        {
            "form": SearchQueryForm(initial=request.GET),
            "results": [serialize_profile(p) for p in profiles],
            "viewer_base": getattr(settings, "VIEWER_BASE_URL", ""),
        },
    )


@require_GET
def nearby_page(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "public/search_nearby.html",
        {
            "viewer_base": getattr(settings, "VIEWER_BASE_URL", ""),
            "default_radius": getattr(settings, "SEARCH_DEFAULT_RADIUS", 10),
        },
    )


@require_GET
def healthcheck(_: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


@require_POST
def geocode_stub(request: HttpRequest) -> JsonResponse:
    cep = (request.POST.get("cep") or "").strip()
    if not cep:
        return JsonResponse({"error": "Informe um CEP."}, status=400)
    try:
        payload = geocode_cep(cep)
    except GeocodingError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status_code)
    return JsonResponse(payload)
