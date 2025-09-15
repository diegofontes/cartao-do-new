from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional
from django.db import transaction

from .models import Notification
from .tasks import send_notification


def enqueue(*, type: str, to: str, template_code: str, payload: dict, idempotency_key: Optional[str] = None) -> Notification:
    n = Notification(
        type=type,
        to=to,
        template_code=template_code,
        payload_json=payload or {},
        status="queued",
    )
    if idempotency_key:
        n.idempotency_key = idempotency_key
    n.save()

    def _dispatch():
        send_notification.delay(str(n.id))

    try:
        transaction.on_commit(_dispatch)
    except Exception:
        _dispatch()
    return n


@dataclass
class Enqueue:
    type: str
    to: str
    template_code: str
    payload: dict
    idempotency_key: Optional[str] = None


def enqueue_many(items: Iterable[Optional[Enqueue]]):
    for it in items:
        if not it:
            continue
        enqueue(type=it.type, to=it.to, template_code=it.template_code, payload=it.payload, idempotency_key=it.idempotency_key)

