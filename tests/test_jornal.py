from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.jornal.markdown import render_markdown
from apps.jornal.models import Helper, HelperRule, NewsPost


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_render_markdown_sanitizes_links_and_scripts():
    html = render_markdown(
        "Veja [site seguro](https://example.com)\n<script>alert(1)</script>\nClique [aqui](javascript:alert('x'))"
    )
    assert "<script" not in html
    assert 'href="javascript' not in html
    assert 'href="https://example.com"' in html
    assert 'target="_blank"' in html


def test_news_post_queryset_respects_public_window(db):
    now = timezone.now()
    active = NewsPost.objects.create(
        title="Ativo",
        slug="ativo",
        body_markdown="**Olá**",
        starts_at=now - timedelta(days=1),
        ends_at=now + timedelta(days=1),
    )
    NewsPost.objects.create(
        title="Futuro",
        slug="futuro",
        body_markdown="Futuro",
        starts_at=now + timedelta(days=1),
    )
    NewsPost.objects.create(
        title="Expirado",
        slug="expirado",
        body_markdown="Expirado",
        ends_at=now - timedelta(days=1),
    )

    public_slugs = set(NewsPost.objects.public().values_list("slug", flat=True))
    assert public_slugs == {"ativo"}
    assert active.is_active is True


def test_news_card_view_renders_active_items(db, client):
    NewsPost.objects.create(title="Atualização", slug="atualizacao", body_markdown="Detalhes")
    response = client.get(reverse("jornal:news"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Quadro de Notícias" in content
    assert "Atualização" in content


def test_helper_list_matches_regex_and_orders(db, client):
    helper_cards = Helper.objects.create(title="Cartões", slug="cards", body_markdown="Ajuda cards", order=1)
    helper_agenda = Helper.objects.create(title="Agenda", slug="agenda", body_markdown="Ajuda agenda", order=0)
    HelperRule.objects.create(helper=helper_cards, route_pattern=r"^/d/cards/?$")
    HelperRule.objects.create(helper=helper_agenda, route_pattern=r"^/d/agenda/?$")

    response = client.get(reverse("jornal:helper_list"), {"path": "/d/cards/"})

    assert response.status_code == 200
    html = response.content.decode()
    assert "Cartões" in html
    assert "Agenda" not in html


def test_helper_detail_requires_matching_path(db, client):
    helper = Helper.objects.create(title="Cartões", slug="cards", body_markdown="Ajuda cards")
    HelperRule.objects.create(helper=helper, route_pattern=r"^/d/cards/?$")

    ok_response = client.get(
        reverse("jornal:helper_detail", args=[helper.slug]),
        {"path": "/d/cards/"},
    )
    assert ok_response.status_code == 200

    not_found = client.get(
        reverse("jornal:helper_detail", args=[helper.slug]),
        {"path": "/d/agenda/"},
    )
    assert not_found.status_code == 404


def test_helper_list_uses_hx_current_url_header(db, client):
    helper = Helper.objects.create(title="Agenda", slug="agenda", body_markdown="Agenda help")
    HelperRule.objects.create(helper=helper, route_pattern=r"^/d/agenda/?$")

    response = client.get(
        reverse("jornal:helper_list"),
        HTTP_HX_CURRENT_URL="https://example.com/d/agenda/",
    )
    assert response.status_code == 200
    assert "Agenda" in response.content.decode()


def test_helper_cache_invalidation_on_new_item(db, client):
    path = "/d/cards/"
    empty_response = client.get(reverse("jornal:helper_list"), {"path": path})
    assert "Ainda não há conteúdos" in empty_response.content.decode()

    helper = Helper.objects.create(title="Cartões", slug="cards", body_markdown="Conteúdo")
    HelperRule.objects.create(helper=helper, route_pattern=r"^/d/cards/?$")

    filled_response = client.get(reverse("jornal:helper_list"), {"path": path})
    assert "Cartões" in filled_response.content.decode()
