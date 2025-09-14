from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Optional

from django.core.cache import caches


cache = caches["default"]


@dataclass
class LimitResult:
    allowed: bool
    remaining: int
    retry_after: int


def _key(namespace: str, ident: str) -> str:
    return f"rl:{namespace}:{ident}"


def rate_limit(namespace: str, ident: str, limit: int, window_seconds: int) -> LimitResult:
    key = _key(namespace, ident)
    now = int(time())
    bucket = now // window_seconds
    bucket_key = f"{key}:{bucket}"

    current = cache.get(bucket_key, 0)
    if current >= limit:
        # compute retry after until next bucket
        retry_after = (bucket + 1) * window_seconds - now
        return LimitResult(False, 0, retry_after)
    cache.add(bucket_key, 0, timeout=window_seconds)
    new_val = cache.incr(bucket_key)
    remaining = max(0, limit - new_val)
    return LimitResult(True, remaining, 0)

