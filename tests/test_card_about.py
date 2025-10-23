import pytest
from django.test import Client, override_settings
from django.urls import reverse

from apps.cards.markdown import sanitize_about_markdown
from apps.cards.models import Card


def test_sanitize_about_markdown_filters_and_sets_links():
    html = sanitize_about_markdown("# Título\n\n<script>alert('x')</script>\n\nVeja [link](https://exemplo.com)")
    assert "<script" not in html
    assert "<h1>" in html and "Título" in html
    assert 'href="https://exemplo.com"' in html
    assert 'target="_blank"' in html
    assert 'rel="nofollow noopener noreferrer"' in html


@pytest.mark.django_db
def test_save_about_rejects_large_payload(client, user):
    card = Card.objects.create(owner=user, title="Teste", slug="teste", mode="appointment")
    client.force_login(user)
    url = reverse("cards:save_about", args=[card.id])
    payload = {"about_markdown": "x" * 20001}
    resp = client.post(url, payload, HTTP_HX_REQUEST="true")
    assert resp.status_code == 422
    card.refresh_from_db()
    assert not card.about_markdown


@pytest.mark.django_db
def test_save_about_persists_content(client, user):
    card = Card.objects.create(owner=user, title="Outro", slug="outro", mode="appointment")
    client.force_login(user)
    url = reverse("cards:save_about", args=[card.id])
    resp = client.post(url, {"about_markdown": "## Sobre\n\nConteúdo **rico**."}, HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    card.refresh_from_db()
    assert card.about_markdown == "## Sobre\n\nConteúdo **rico**."


@pytest.mark.django_db
def test_public_view_hides_about_without_content(client, user):
    card = Card.objects.create(
        owner=user,
        title="Sem Sobre",
        slug="sem-sobre",
        mode="appointment",
        status="published",
        nickname="semsobre",
    )
    resp = client.get(f"/@{card.nickname}")
    assert resp.status_code == 200
    assert "panel-about" not in resp.content.decode()


@pytest.mark.django_db
def test_public_view_shows_about_tab_for_delivery_and_appointment(client, user):
    card1 = Card.objects.create(
        owner=user,
        title="Com Sobre",
        slug="com-sobre",
        mode="appointment",
        status="published",
        nickname="comsobre",
        about_markdown="Detalhes *importantes*.",
    )
    resp1 = client.get(f"/@{card1.nickname}")
    assert resp1.status_code == 200
    body1 = resp1.content.decode()
    assert "panel-about" in body1
    assert "Detalhes" in body1

    card2 = Card.objects.create(
        owner=user,
        title="Delivery Sobre",
        slug="delivery-sobre",
        mode="delivery",
        status="published",
        nickname="deliverysobre",
        about_markdown="Cardápio com **história**.",
        tabs_order="menu,links,gallery",
    )
    with override_settings(ROOT_URLCONF="config.urls_viewer"):
        resp2 = Client().get(f"/@{card2.nickname}")
    assert resp2.status_code == 200
    body2 = resp2.content.decode()
    assert "panel-about" in body2
    assert "Cardápio com" in body2


@pytest.mark.django_db
def test_tabs_partial_includes_about_option_when_content(client, user):
    card = Card.objects.create(
        owner=user,
        title="Tabs Sobre",
        slug="tabs-sobre",
        mode="appointment",
        about_markdown="### Bio",
    )
    client.force_login(user)
    resp = client.get(reverse("cards:tabs_partial", args=[card.id]), HTTP_HX_REQUEST="true")
    body = resp.content.decode()
    assert 'value="links,gallery,services,about"' in body
    assert ">Links, Galeria, Serviços, Sobre<" in body


@pytest.mark.django_db
def test_tabs_partial_excludes_about_option_when_empty(client, user):
    card = Card.objects.create(
        owner=user,
        title="Tabs Sem Sobre",
        slug="tabs-sem-sobre",
        mode="appointment",
        about_markdown="",
    )
    client.force_login(user)
    resp = client.get(reverse("cards:tabs_partial", args=[card.id]), HTTP_HX_REQUEST="true")
    body = resp.content.decode()
    assert 'value="links,gallery,services,about"' not in body
