import datetime as dt

import pytest
from django.urls import reverse
from django.test import override_settings
from django.utils import timezone

from apps.cards.models import Card
from zoneinfo import ZoneInfo

from apps.scheduling.models import SchedulingService, ServiceAvailability
from apps.notifications.models import Notification


@pytest.mark.django_db
def test_public_create_appointment_sends_viewer_link(client, user, caplog):
    card = Card.objects.create(
        owner=user,
        title="Studio",
        description="",
        nickname="studio",
        status="published",
        mode="appointment",
        notification_phone="+551199887766",
    )
    service = SchedulingService.objects.create(
        card=card,
        name="Sessão Foto",
        description="",
        timezone="UTC",
        duration_minutes=45,
        type="remote",
        is_active=True,
        price_cents=15000,
    )
    target_date = (timezone.now() + dt.timedelta(days=1)).astimezone(ZoneInfo("UTC")).date()
    ServiceAvailability.objects.create(
        service=service,
        rule_type="weekly",
        weekday=target_date.weekday(),
        start_time=dt.time(9, 0),
        end_time=dt.time(18, 0),
    )
    start = dt.datetime.combine(target_date, dt.time(9, 0), tzinfo=ZoneInfo("UTC"))
    start_iso = start.replace(microsecond=0).isoformat()

    session = client.session
    session["phone_verified"] = True
    session.save()

    with override_settings(ROOT_URLCONF="config.urls_viewer"):
        with caplog.at_level("INFO"):
            resp = client.post(
                reverse("public_create_appointment", args=[card.nickname]),
                {
                    "service": service.id,
                    "start_at_utc": start_iso,
                    "name": "Cliente",
                    "email": "cli@example.com",
                    "phone": "+55 11 91234-5678",
                },
            )
    assert resp.status_code == 200
    notif = Notification.objects.filter(template_code="viewer_order_link", to="+5511912345678").first()
    assert notif is not None
    assert notif.payload_json.get("url")
