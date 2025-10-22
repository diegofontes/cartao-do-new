import pytest
import re
from django.core.files.base import ContentFile
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.cards.models import Card, GalleryItem
from apps.scheduling.models import SchedulingService


@pytest.mark.django_db
def test_tabs_gallery_hides_non_visible(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.ROOT_URLCONF = "config.urls_viewer"
    owner = get_user_model().objects.create_user(username="owner", email="owner@example.com", password="pwd12345")
    card = Card.objects.create(
        owner=owner,
        title="Card Público",
        description="desc",
        slug="card-publico",
        nickname="cardpublico",
        status="published",
    )
    visible_thumb = ContentFile(b"thumb", name="thumb-visible.jpg")
    visible_large = ContentFile(b"thumb-large", name="thumb-visible-large.jpg")
    hidden_thumb = ContentFile(b"thumb", name="thumb-hidden.jpg")
    hidden_large = ContentFile(b"thumb-large", name="thumb-hidden-large.jpg")
    GalleryItem.objects.create(
        card=card,
        file=ContentFile(b"image-data", name="img-visible.jpg"),
        thumb_w256=visible_thumb,
        thumb_w768=visible_large,
        caption="Visível",
        visible_in_gallery=True,
        importance=1,
    )
    GalleryItem.objects.create(
        card=card,
        file=ContentFile(b"image-data", name="img-hidden.jpg"),
        thumb_w256=hidden_thumb,
        thumb_w768=hidden_large,
        caption="Oculta",
        visible_in_gallery=False,
        importance=1,
    )

    response = client.get(reverse("tabs_gallery", kwargs={"nickname": card.nickname}))

    body = response.content.decode()
    assert "Visível" in body
    assert "Oculta" not in body


@pytest.mark.django_db
def test_service_sidebar_orders_gallery_by_importance(client, settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    settings.ROOT_URLCONF = "config.urls_viewer"
    owner = get_user_model().objects.create_user(username="service-owner", email="svc@example.com", password="pwd12345")
    card = Card.objects.create(
        owner=owner,
        title="Agenda",
        description="desc",
        slug="agenda-card",
        nickname="agendacard",
        status="published",
    )
    service = SchedulingService.objects.create(
        card=card,
        name="Consulta",
        description="desc",
        timezone="UTC",
        duration_minutes=30,
        type="remote",
    )
    thumbs = [ContentFile(b"t1", name=f"thumb-{i}.jpg") for i in range(4)]
    thumbs_large = [ContentFile(b"tL", name=f"thumb-large-{i}.jpg") for i in range(4)]
    items = [
        GalleryItem.objects.create(
            card=card,
            file=ContentFile(b"img", name=f"img-{i}.jpg"),
            thumb_w256=thumbs[i],
            thumb_w768=thumbs_large[i],
            caption=f"Img {i}",
            importance=importance,
            service=service,
        )
        for i, importance in enumerate([1, 2, 2, 3])
    ]

    def reverse_shuffle(seq):
        seq.reverse()

    monkeypatch.setattr("apps.scheduling.views_public.random.shuffle", reverse_shuffle)

    response = client.get(reverse("public_service_sidebar", kwargs={"nickname": card.nickname, "id": str(service.id)}))

    body = response.content.decode()
    data_attrs = re.findall(r'data-gallery-item="([^"]+)"', body)
    expected_order = [str(items[0].id), str(items[2].id), str(items[1].id), str(items[3].id)]
    assert data_attrs == expected_order
