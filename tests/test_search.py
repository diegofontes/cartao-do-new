import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse

from apps.cards.models import Card
from apps.search.forms import SearchQuery
from apps.search.geocoding import GeocodingError, geocode_cep
from apps.search.models import SearchProfile, SearchCategory
from apps.search.services import search_profiles


@pytest.mark.django_db
def test_search_profiles_filters_by_distance(user):
    card_near = Card.objects.create(
        owner=user,
        title="Studio",
        slug="studio",
        nickname="studio",
        status="published",
        mode="appointment",
    )
    card_far = Card.objects.create(
        owner=user,
        title="Consultoria",
        slug="consult",
        nickname="consult",
        status="published",
        mode="delivery",
    )
    SearchProfile.objects.create(
        card=card_near,
        category=SearchCategory.CONSULTORIA,
        origin=Point(-46.633309, -23.55052, srid=4326),
        radius_km=10,
        active=True,
    )
    SearchProfile.objects.create(
        card=card_far,
        category=SearchCategory.CONSULTORIA,
        origin=Point(-43.197169, -22.908333, srid=4326),
        radius_km=10,
        active=True,
    )

    query = SearchQuery(latitude=-23.55052, longitude=-46.633309, radius_km=15, category=None, mode=None, limit=10)
    results = list(search_profiles(query))
    assert len(results) == 1
    assert results[0].card == card_near


@pytest.mark.django_db
def test_search_api_returns_only_published_cards(user, client):
    card_public = Card.objects.create(
        owner=user,
        title="Loja",
        slug="loja",
        nickname="loja",
        status="published",
        mode="delivery",
    )
    card_hidden = Card.objects.create(
        owner=user,
        title="Draft",
        slug="draft",
        nickname="draft",
        status="draft",
        mode="appointment",
    )
    SearchProfile.objects.create(
        card=card_public,
        category=SearchCategory.DELIVERY,
        origin=Point(-46.633309, -23.55052, srid=4326),
        radius_km=25,
        active=True,
    )
    SearchProfile.objects.create(
        card=card_hidden,
        category=SearchCategory.MANUTENCAO,
        origin=Point(-46.633309, -23.55052, srid=4326),
        radius_km=25,
        active=True,
    )

    resp = client.get(
        reverse("search:cards_api"),
        {"lat": -23.55052, "lng": -46.633309, "radius_km": 30},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["nickname"] == "loja"


@pytest.mark.django_db
def test_search_api_mode_filter(user, client):
    delivery_card = Card.objects.create(
        owner=user,
        title="Delivery",
        slug="delivery",
        nickname="delivery",
        status="published",
        mode="delivery",
    )
    SearchProfile.objects.create(
        card=delivery_card,
        category=SearchCategory.DELIVERY,
        origin=Point(-46.633, -23.55, srid=4326),
        radius_km=20,
        active=True,
    )
    resp = client.get(
        reverse("search:cards_api"),
        {"lat": -23.55, "lng": -46.633, "radius_km": 30, "mode": "appointment"},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.django_db
def test_geocode_stub_known_cep(client, monkeypatch):
    monkeypatch.setattr("apps.search.views_public.geocode_cep", lambda _: {"lat": -23.55, "lng": -46.63})
    resp = client.post(reverse("search:geocode_stub"), {"cep": "01000-000"})
    assert resp.status_code == 200
    assert resp.json() == {"lat": -23.55, "lng": -46.63}


@pytest.mark.django_db
def test_geocode_stub_unknown_cep(client, monkeypatch):
    def fake_geocode(_: str) -> dict[str, float]:
        raise GeocodingError("CEP não encontrado.", 404)

    monkeypatch.setattr("apps.search.views_public.geocode_cep", fake_geocode)
    resp = client.post(reverse("search:geocode_stub"), {"cep": "99999-999"})
    assert resp.status_code == 404
    assert resp.json()["error"] == "CEP não encontrado."


class DummyResponse:
    def __init__(self, status_code: int, payload: object):
        self.status_code = status_code
        self._payload = payload

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def test_geocode_cep_success(monkeypatch, settings):
    def fake_get(url, *_, **kwargs):
        if "viacep" in url:
            return DummyResponse(
                200,
                {
                    "logradouro": "Praça da Sé",
                    "bairro": "Sé",
                    "localidade": "São Paulo",
                    "uf": "SP",
                },
            )
        params = kwargs.get("params")
        headers = kwargs.get("headers")
        assert params["q"] == "Praça da Sé, Sé, São Paulo, SP, Brasil"
        assert params["limit"] == 1
        assert params["countrycodes"] == "br"
        assert headers["User-Agent"] == settings.NOMINATIM_USER_AGENT
        return DummyResponse(200, [{"lat": "-23.55052", "lon": "-46.633309"}])

    settings.NOMINATIM_USER_AGENT = "stripe-paygo-tests/1.0 (dev@example.com)"
    monkeypatch.setattr("apps.search.geocoding.requests.get", fake_get)
    result = geocode_cep("01000-000")
    assert result == {"lat": -23.55052, "lng": -46.633309}


def test_geocode_cep_invalid_cep():
    with pytest.raises(GeocodingError) as excinfo:
        geocode_cep("abc")
    assert excinfo.value.status_code == 400


def test_geocode_cep_via_cep_not_found(monkeypatch):
    def fake_get(url, *_, **__):
        if "viacep" in url:
            return DummyResponse(404, {"erro": True})
        pytest.fail("Nominatim should not be called when ViaCEP fails")

    monkeypatch.setattr("apps.search.geocoding.requests.get", fake_get)
    with pytest.raises(GeocodingError) as excinfo:
        geocode_cep("01000-000")
    assert excinfo.value.status_code == 404


@pytest.mark.django_db
def test_search_geocode_success(client, user, monkeypatch):
    card = Card.objects.create(
        owner=user,
        title="Barbearia",
        slug="barbearia",
        nickname="barber",
        status="published",
        mode="appointment",
    )
    SearchProfile.objects.create(
        card=card,
        category=SearchCategory.ESTETICA,
        origin=Point(-46.633309, -23.55052, srid=4326),
        radius_km=15,
        active=True,
    )

    monkeypatch.setattr(
        "apps.search.views_public.geocode_address_sp",
        lambda _addr: {"lat": -23.55052, "lng": -46.633309},
    )

    resp = client.post(
        reverse("search:geocode"),
        {
            "address": "Av. Paulista, 1000",
            "state": "SP",
            "category": SearchCategory.ESTETICA,
            "radius_km": 10,
        },
        HTTP_HX_REQUEST="true",
    )

    assert resp.status_code == 200
    content = resp.content.decode()
    assert "barbearia" in content.lower()
    assert "@barber" in content


@pytest.mark.django_db
def test_search_geocode_rejects_other_states(client):
    resp = client.post(
        reverse("search:geocode"),
        {
            "address": "Rua qualquer",
            "state": "RJ",
            "category": "",
            "radius_km": 10,
        },
    )
    assert resp.status_code == 422
    assert "Estado de São Paulo" in resp.content.decode()


@pytest.mark.django_db
def test_search_results_orders_by_distance(client, user):
    near = Card.objects.create(
        owner=user,
        title="Studio",
        slug="studio2",
        nickname="studio2",
        status="published",
        mode="appointment",
    )
    far = Card.objects.create(
        owner=user,
        title="Viagens",
        slug="viagens",
        nickname="viagens",
        status="published",
        mode="delivery",
    )
    SearchProfile.objects.create(
        card=near,
        category=SearchCategory.CONSULTORIA,
        origin=Point(-46.63, -23.55, srid=4326),
        radius_km=60,
        active=True,
    )
    SearchProfile.objects.create(
        card=far,
        category=SearchCategory.CONSULTORIA,
        origin=Point(-46.4, -23.45, srid=4326),
        radius_km=60,
        active=True,
    )

    resp = client.get(
        reverse("search:results"),
        {"lat": -23.55, "lng": -46.63, "radius_km": 40},
        HTTP_HX_REQUEST="true",
    )

    assert resp.status_code == 200
    html = resp.content.decode()
    assert html.index("@studio2") < html.index("@viagens")


@pytest.mark.django_db
def test_search_results_warns_outside_sp(client):
    resp = client.get(
        reverse("search:results"),
        {"lat": -3.12, "lng": -60.02, "radius_km": 10},
        HTTP_HX_REQUEST="true",
    )
    assert resp.status_code in {200, 422}
    assert "São Paulo" in resp.content.decode()
