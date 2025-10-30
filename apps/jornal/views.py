from __future__ import annotations

from urllib.parse import urlparse

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from . import selectors
from .models import Helper


def _normalize_path(raw_path: str | None, *, fallback: str = "/") -> str:
    if raw_path:
        trimmed = raw_path.strip()
        if trimmed:
            return trimmed if trimmed.startswith("/") else f"/{trimmed}"
    return fallback


def _current_path(request: HttpRequest) -> str:
    supplied = request.GET.get("path")
    if supplied:
        return _normalize_path(supplied)
    current_url = request.headers.get("HX-Current-URL")
    if current_url:
        parsed = urlparse(current_url)
        return _normalize_path(parsed.path)
    return _normalize_path(request.path)


@require_GET
def news_card(request: HttpRequest) -> HttpResponse:
    posts = selectors.list_active_news()
    return render(request, "jornal/news_card.html", {"posts": posts})


@require_GET
def helper_list(request: HttpRequest) -> HttpResponse:
    path = _current_path(request)
    helpers = selectors.list_helpers_for_path(path)
    return render(request, "jornal/helper_list.html", {"helpers": helpers, "path": path})


@require_GET
def helper_detail(request: HttpRequest, slug: str) -> HttpResponse:
    path = _current_path(request)
    helper = get_object_or_404(Helper.objects.public(), slug=slug)
    allowed_helpers = selectors.list_helpers_for_path(path)
    if helper not in allowed_helpers:
        raise Http404("Helper não disponível para esta rota.")
    return render(
        request,
        "jornal/helper_detail.html",
        {
            "helper": helper,
            "path": path,
        },
    )
