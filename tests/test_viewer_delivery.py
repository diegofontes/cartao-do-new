import json

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.cards.models import Card
from apps.delivery.models import Order, OrderItem


@pytest.fixture
def delivery_card(user):
    return Card.objects.create(
        owner=user,
        title="Padaria Lua",
        slug="padaria-lua",
        nickname="padarialua",
        status="published",
        mode="delivery",
    )


@pytest.fixture
def make_order(delivery_card):
    def _make_order(*, status: str = "pending", phone: str = "+5511987651234") -> Order:
        order = Order.objects.create(
            card=delivery_card,
            code="#AA11",
            status=status,
            customer_name="João Cliente",
            customer_phone=phone,
            customer_email="cliente@example.com",
            fulfillment="delivery",
            address_json={
                "logradouro": "Rua das Flores",
                "numero": "100",
                "bairro": "Centro",
                "cidade": "São Paulo",
                "uf": "SP",
                "cep": "01000-000",
            },
            subtotal_cents=3200,
            delivery_fee_cents=800,
            discount_cents=200,
            total_cents=3800,
            notes="Retirar salsa",
        )
        OrderItem.objects.create(
            order=order,
            menu_item=None,
            qty=2,
            base_price_cents_snapshot=1600,
            line_subtotal_cents=3200,
            notes="Sem pimenta",
        )
        return order

    return _make_order


@pytest.mark.django_db
def test_order_status_changes_logged(make_order):
    order = make_order()
    statuses = list(order.status_changes.values_list("status", flat=True))
    assert statuses == ["pending"]

    order.set_status("accepted", source="test")
    order.set_status("preparing", source="test")
    order.refresh_from_db()

    history = list(order.status_changes.order_by("created_at").values_list("status", flat=True))
    assert history == ["pending", "accepted", "preparing"]


@pytest.mark.django_db
def test_viewer_requires_verification_and_sets_session(client, make_order):
    order = make_order()
    detail_url = reverse("viewer:order_detail", args=[order.public_code])
    verify_url = reverse("viewer:order_verify", args=[order.public_code])

    resp = client.get(detail_url)
    html = resp.content.decode()
    assert "Últimos 4 dígitos" in html

    resp_fail = client.post(verify_url, {"last4": "0000"})
    assert resp_fail.status_code == 403
    assert "HX-Trigger" in resp_fail.headers

    resp_ok = client.post(verify_url, {"last4": order.customer_phone[-4:]})
    assert resp_ok.status_code == 204
    assert resp_ok.headers.get("HX-Redirect") == detail_url

    resp_after = client.get(detail_url)
    body_after = resp_after.content.decode()
    assert "Detalhes do pedido" in body_after
    assert "Itens" in body_after


@pytest.mark.django_db
def test_timeline_shows_status_history(client, make_order):
    order = make_order()
    order.set_status("accepted", source="test")
    order.set_status("preparing", source="test")

    verify_url = reverse("viewer:order_verify", args=[order.public_code])
    status_url = reverse("viewer:order_status_partial", args=[order.public_code])

    client.post(verify_url, {"last4": order.customer_phone[-4:]})
    resp = client.get(status_url)
    assert resp.status_code == 200

    html = resp.content.decode()
    assert "Pedido aceito" in html
    assert "Em preparo" in html

    accepted_change = order.status_changes.filter(status="accepted").first()
    assert accepted_change is not None
    stamp = timezone.localtime(accepted_change.created_at).strftime("%d/%m/%Y")
    assert stamp in html


@pytest.mark.django_db
def test_cancel_blocked_after_preparing(client, make_order):
    order = make_order(status="preparing")
    verify_url = reverse("viewer:order_verify", args=[order.public_code])
    cancel_url = reverse("viewer:order_cancel", args=[order.public_code])

    client.post(verify_url, {"last4": order.customer_phone[-4:]})
    resp = client.post(cancel_url)
    assert resp.status_code == 400


@pytest.mark.django_db
def test_cancel_allowed_until_accepted(client, make_order):
    order = make_order(status="accepted")
    verify_url = reverse("viewer:order_verify", args=[order.public_code])
    cancel_url = reverse("viewer:order_cancel", args=[order.public_code])

    client.post(verify_url, {"last4": order.customer_phone[-4:]})
    resp = client.post(cancel_url)
    assert resp.status_code == 200
    hx_header = resp.headers.get("HX-Trigger")
    assert hx_header is not None
    data = json.loads(hx_header)
    assert data["flash"]["type"] == "ok"
