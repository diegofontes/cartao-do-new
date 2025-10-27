import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.cards.models import Card
from apps.scheduling.models import SchedulingService, Appointment, ServiceAvailability, RescheduleRequest
from apps.scheduling.slots import generate_slots
from apps.notifications.models import Notification


@pytest.mark.django_db
def test_viewer_verify_and_request_reschedule(client, user):
    card = Card.objects.create(
        owner=user,
        title="Clínica",
        description="",
        nickname="clinic",
        status="published",
        mode="appointment",
        notification_phone="+551199998888",
    )
    service = SchedulingService.objects.create(
        card=card,
        name="Consulta",
        description="",
        timezone="UTC",
        duration_minutes=30,
        type="remote",
        is_active=True,
    )
    start = timezone.now() + dt.timedelta(days=2)
    start = start.replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=dt.timezone.utc)
    ServiceAvailability.objects.create(
        service=service,
        rule_type="weekly",
        weekday=start.date().weekday(),
        start_time=dt.time(9, 0),
        end_time=dt.time(18, 0),
        timezone="UTC",
    )
    ap = Appointment.objects.create(
        service=service,
        user_name="Cliente",
        user_email="cliente@example.com",
        user_phone="+5511991112222",
        start_at_utc=start,
        end_at_utc=start + dt.timedelta(minutes=30),
        timezone="UTC",
        status="pending",
    )
    code = ap.public_code

    resp = client.get(f"/order/{code}")
    assert resp.status_code == 200

    # Wrong last4
    resp = client.post(f"/order/{code}/verify-last4", {"last4": "0000"})
    assert resp.status_code == 403

    # Correct last4 triggers redirect and stores session
    resp = client.post(f"/order/{code}/verify-last4", {"last4": "2222"})
    assert resp.status_code == 204
    assert resp.headers["HX-Redirect"] == f"/order/{code}"

    # Emulate redirect by marking session as verified
    session = client.session
    session[f"viewer:order:{code}"] = {"exp": (timezone.now() + dt.timedelta(hours=12)).isoformat()}
    session.save()

    slots_response = client.get(f"/order/{code}/slots", {"date": start.date().isoformat()})
    assert slots_response.status_code == 200
    assert "input type=\"radio\"" in slots_response.content.decode()

    slots = generate_slots(service, start.date(), ignore_appointment_id=str(ap.id))
    assert slots
    desired_slot = next((s for s in slots if s["start_at_utc"] != ap.start_at_utc.isoformat()), slots[0])

    resp = client.post(
        f"/order/{code}/reschedule-request",
        {
            "reason": "Preciso alterar",
            "date": start.date().isoformat(),
            "slot_start_at": desired_slot["start_at_utc"],
        },
    )
    assert resp.status_code == 200
    req = RescheduleRequest.objects.get(appointment=ap)
    assert req.status == "requested"
    assert req.requested_start_at_utc.isoformat() == desired_slot["start_at_utc"]
    # Owner notified via SMS notification record
    notif = Notification.objects.filter(template_code="owner_reschedule_requested", to=card.notification_phone).first()
    assert notif is not None


@pytest.mark.django_db
def test_dashboard_can_approve_reschedule(client, user):
    card = Card.objects.create(
        owner=user,
        title="Estúdio",
        description="",
        nickname="studio",
        status="published",
        mode="appointment",
    )
    service = SchedulingService.objects.create(
        card=card,
        name="Sessão",
        description="",
        timezone="UTC",
        duration_minutes=60,
        type="remote",
        is_active=True,
    )
    target_date = (timezone.now() + dt.timedelta(days=2)).date()
    ServiceAvailability.objects.create(
        service=service,
        rule_type="weekly",
        weekday=target_date.weekday(),
        start_time=dt.time(9, 0),
        end_time=dt.time(18, 0),
        timezone="UTC",
    )
    start = timezone.make_aware(dt.datetime.combine(target_date, dt.time(10, 0)), dt.timezone.utc)
    ap = Appointment.objects.create(
        service=service,
        user_name="Maria",
        user_email="maria@example.com",
        user_phone="+5511987654321",
        start_at_utc=start,
        end_at_utc=start + dt.timedelta(hours=1),
        timezone="UTC",
        status="pending",
    )
    slots = generate_slots(service, target_date, ignore_appointment_id=str(ap.id))
    assert slots
    requested_slot = slots[0]
    primary_req = RescheduleRequest.objects.create(
        appointment=ap,
        status="requested",
        reason="Compromisso urgente",
        requested_start_at_utc=dt.datetime.fromisoformat(requested_slot["start_at_utc"]),
        requested_end_at_utc=dt.datetime.fromisoformat(requested_slot["end_at_utc"]),
    )
    RescheduleRequest.objects.create(
        appointment=ap,
        status="requested",
        reason="Entrada duplicada",
        created_at=timezone.now() - dt.timedelta(hours=1),
        requested_start_at_utc=dt.datetime.fromisoformat(slots[-1]["start_at_utc"]),
        requested_end_at_utc=dt.datetime.fromisoformat(slots[-1]["end_at_utc"]),
    )

    client.force_login(user)

    new_slot = next((s for s in slots if s["start_at_utc"] != ap.start_at_utc.isoformat()), slots[0])

    resp = client.post(
        reverse("dashboard:reschedule_approve", args=[primary_req.id]),
        {"slot": new_slot["start_at_utc"], "message": "Te aguardo!"},
        HTTP_HX_REQUEST='true'
    )
    assert resp.status_code == 200
    primary_req.refresh_from_db()
    ap.refresh_from_db()
    assert primary_req.status == "approved"
    assert primary_req.owner_message == "Te aguardo!"
    assert ap.start_at_utc.isoformat() == new_slot["start_at_utc"]
    # Other pending requests marked expired
    assert RescheduleRequest.objects.exclude(id=primary_req.id).filter(appointment=ap, status="expired").exists()
    # Customer notification queued
    assert Notification.objects.filter(template_code="customer_reschedule_approved", to=ap.user_phone).exists()
