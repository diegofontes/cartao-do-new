import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.cards.models import Card
from apps.scheduling.models import SchedulingService
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
    )
    start = timezone.now() + dt.timedelta(days=1)
    start_iso = start.replace(microsecond=0).isoformat()

    session = client.session
    session["phone_verified"] = True
    session.save()

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
    assert any("viewer order link enqueued" in rec.message for rec in caplog.records)
