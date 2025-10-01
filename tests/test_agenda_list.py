import datetime as dt
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
import pytest

from apps.cards.models import Card
from apps.scheduling.models import SchedulingService, Appointment


@pytest.mark.django_db
def test_agenda_list_shell_and_partial(client):
    User = get_user_model()
    user = User.objects.create_user(email="list@example.com", password="pwd123")
    client.force_login(user)

    card = Card.objects.create(owner=user, title="Card A", slug="card-a", nickname="carda", status="published")
    svc = SchedulingService.objects.create(card=card, name="Corte", description="desc", timezone="UTC", duration_minutes=30, type="remote")

    tz = timezone.get_current_timezone()
    base = dt.datetime.now(tz).replace(hour=9, minute=0, second=0, microsecond=0)
    ap1 = Appointment.objects.create(
        service=svc,
        user_name="Alice",
        user_email="a@example.com",
        user_phone="1111",
        start_at_utc=base.astimezone(dt.timezone.utc),
        end_at_utc=(base + dt.timedelta(minutes=30)).astimezone(dt.timezone.utc),
        timezone=str(tz),
        location_choice="remote",
        status="pending",
    )

    # Shell page
    r = client.get(reverse("dashboard:agenda") + "?view=list")
    assert r.status_code == 200
    assert b"Lista" in r.content

    # Partial list
    r2 = client.get(reverse("dashboard:agenda_list_partial"))
    assert r2.status_code == 200
    # Has at least one item rendered
    assert f"appt-{ap1.id}".encode() in r2.content


@pytest.mark.django_db
def test_agenda_list_actions_update_item(client):
    User = get_user_model()
    user = User.objects.create_user(email="list2@example.com", password="pwd123")
    client.force_login(user)

    card = Card.objects.create(owner=user, title="Card B", slug="card-b", nickname="cardb", status="published")
    svc = SchedulingService.objects.create(card=card, name="Consulta", description="desc", timezone="UTC", duration_minutes=30, type="remote")
    tz = timezone.get_current_timezone()
    base = dt.datetime.now(tz).replace(hour=10, minute=0, second=0, microsecond=0)
    ap = Appointment.objects.create(
        service=svc,
        user_name="Bob",
        user_email="b@example.com",
        user_phone="2222",
        start_at_utc=base.astimezone(dt.timezone.utc),
        end_at_utc=(base + dt.timedelta(minutes=30)).astimezone(dt.timezone.utc),
        timezone=str(tz),
        location_choice="remote",
        status="pending",
    )

    # Confirm
    r = client.post(reverse("dashboard:agenda_list_confirm", args=[ap.id]), HTTP_HX_REQUEST="true")
    assert r.status_code == 200
    ap.refresh_from_db()
    assert ap.status == "confirmed"

    # Cancel
    r2 = client.post(reverse("dashboard:agenda_list_cancel", args=[ap.id]), HTTP_HX_REQUEST="true")
    assert r2.status_code == 200
    ap.refresh_from_db()
    assert ap.status == "cancelled"


@pytest.mark.django_db
def test_filters_name_contact_period(client):
    User = get_user_model()
    user = User.objects.create_user(email="filt@example.com", password="pwd123")
    client.force_login(user)

    card = Card.objects.create(owner=user, title="Card F", slug="card-f", nickname="nickf", status="published")
    svc = SchedulingService.objects.create(card=card, name="Serv", description="d", timezone="UTC", duration_minutes=30, type="remote")
    tz = timezone.get_current_timezone()
    d0 = timezone.localdate()
    base = dt.datetime.combine(d0, dt.time(9, 0, tzinfo=tz))

    ap_pending = Appointment.objects.create(
        service=svc,
        user_name="Carlos",
        user_email="carlos@example.com",
        user_phone="555-0001",
        start_at_utc=base.astimezone(dt.timezone.utc),
        end_at_utc=(base + dt.timedelta(minutes=30)).astimezone(dt.timezone.utc),
        timezone=str(tz),
        location_choice="remote",
        status="pending",
    )
    ap_conf = Appointment.objects.create(
        service=svc,
        user_name="Carla",
        user_email="carla@example.com",
        user_phone="555-0002",
        start_at_utc=(base + dt.timedelta(hours=1)).astimezone(dt.timezone.utc),
        end_at_utc=(base + dt.timedelta(hours=1, minutes=30)).astimezone(dt.timezone.utc),
        timezone=str(tz),
        location_choice="remote",
        status="confirmed",
    )

    # Name filter matches both by name
    r_name = client.get(reverse("dashboard:agenda_list_partial"), {"name": "Car"})
    assert r_name.status_code == 200
    body = r_name.content.decode()
    assert f"appt-{ap_pending.id}" in body
    assert f"appt-{ap_conf.id}" in body

    # Contact filter must match only confirmed
    r_contact = client.get(reverse("dashboard:agenda_list_partial"), {"contact": "555-000"})
    assert r_contact.status_code == 200
    body2 = r_contact.content.decode()
    assert f"appt-{ap_conf.id}" in body2
    assert f"appt-{ap_pending.id}" not in body2

    # Period filter (date-only) limits to today
    today_iso = d0.isoformat()
    r_period = client.get(reverse("dashboard:agenda_list_partial"), {"start": today_iso, "end": today_iso})
    assert r_period.status_code == 200
