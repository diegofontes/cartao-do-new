from __future__ import annotations

import re
from typing import Iterable

from django.core.cache import cache

from .models import Helper, HelperRule, NewsPost

NEWS_CACHE_KEY = "jornal:news:active"
NEWS_CACHE_TIMEOUT = 60  # seconds
HELPER_CACHE_KEY_TEMPLATE = "jornal:helpers:{path}"
HELPER_CACHE_TIMEOUT = 60  # seconds
HELPER_CACHE_INDEX_KEY = "jornal:helpers:index"


def _compile(pattern: str) -> re.Pattern[str] | None:
    try:
        return re.compile(pattern)
    except re.error:
        return None


def list_active_news() -> list[NewsPost]:
    cached: list[int] | None = cache.get(NEWS_CACHE_KEY)
    if cached is None:
        posts = list(NewsPost.objects.public())
        cache.set(NEWS_CACHE_KEY, [post.pk for post in posts], timeout=NEWS_CACHE_TIMEOUT)
        return posts
    if not cached:
        return []
    preserved = {pk: idx for idx, pk in enumerate(cached)}
    posts = list(NewsPost.objects.filter(pk__in=cached))
    posts.sort(key=lambda post: preserved.get(post.pk, 0))
    return posts


def _helpers_queryset() -> Iterable[HelperRule]:
    return (
        HelperRule.objects.filter(is_active=True, helper__is_public=True)
        .select_related("helper")
        .order_by("helper__order", "helper__title", "pk")
    )


def list_helpers_for_path(path: str) -> list[Helper]:
    normalized = "/" + path.lstrip("/") if path else "/"
    cache_key = HELPER_CACHE_KEY_TEMPLATE.format(path=normalized)
    cached: list[int] | None = cache.get(cache_key)
    if cached is None:
        helpers = _match_helpers(normalized)
        helper_ids = [helper.pk for helper in helpers]
        cache.set(cache_key, helper_ids, timeout=HELPER_CACHE_TIMEOUT)
        _remember_helper_key(cache_key)
        return helpers
    if not cached:
        return []
    helpers = list(Helper.objects.filter(pk__in=cached).order_by())
    preserved = {pk: idx for idx, pk in enumerate(cached)}
    helpers.sort(key=lambda helper: preserved.get(helper.pk, 0))
    return helpers


def _match_helpers(path: str) -> list[Helper]:
    matched: list[Helper] = []
    seen: set[int] = set()
    for rule in _helpers_queryset():
        regex = _compile(rule.route_pattern)
        if regex is None:
            continue
        if regex.match(path):
            helper = rule.helper
            if helper.pk not in seen:
                matched.append(helper)
                seen.add(helper.pk)
    return matched


def _remember_helper_key(cache_key: str) -> None:
    keys = cache.get(HELPER_CACHE_INDEX_KEY)
    if not keys:
        cache.set(HELPER_CACHE_INDEX_KEY, [cache_key], timeout=None)
        return
    if cache_key in keys:
        return
    cache.set(HELPER_CACHE_INDEX_KEY, [*keys, cache_key], timeout=None)


def invalidate_news_cache() -> None:
    cache.delete(NEWS_CACHE_KEY)


def invalidate_helper_cache() -> None:
    keys = cache.get(HELPER_CACHE_INDEX_KEY) or []
    if keys:
        cache.delete_many(keys)
    cache.delete(HELPER_CACHE_INDEX_KEY)
