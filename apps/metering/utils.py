from django.utils import timezone
from .models import MeteringEvent, PricingRule


def resolve_unit_price(resource_type: str, event_type: str, when=None) -> int:
    when = when or timezone.now()
    qs = PricingRule.objects.filter(
        resource_type=resource_type,
        event_type=event_type,
        is_active=True,
    )
    qs = qs.filter(starts_at__lte=when) | qs.filter(starts_at__isnull=True)
    qs = qs.filter(ends_at__gte=when) | qs.filter(ends_at__isnull=True)
    rule = qs.order_by("-starts_at").first()
    return rule.unit_price_cents if rule else 0


def create_event(*, user, resource_type: str, event_type: str, card=None, service=None, appointment=None, quantity: int = 1, when=None):
    unit_price = resolve_unit_price(resource_type, event_type, when)
    return MeteringEvent.objects.create(
        user=user,
        card=card,
        service=service,
        appointment=appointment,
        resource_type=resource_type,
        event_type=event_type,
        quantity=quantity,
        unit_price_cents=unit_price,
        occurred_at=when or timezone.now(),
    )

