from __future__ import annotations

import pprint
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Final

import requests
from django.conf import settings
from django.core.cache import cache


GEOCODE_CACHE_TTL: Final[int] = 60 * 60 * 24


VIACEP_URL_TEMPLATE: Final[str] = "https://viacep.com.br/ws/{cep}/json/"
NOMINATIM_URL: Final[str] = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT: Final[str] = settings.NOMINATIM_USER_AGENT
DEFAULT_TIMEOUT: Final[int] = 10  # seconds
CEP_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{8}$")


@dataclass(slots=True)
class GeocodingError(Exception):
    message: str
    status_code: int

    def __str__(self) -> str:  # pragma: no cover - Exception.__str__ is trivial
        return self.message


def _normalize_cep(raw_cep: str) -> str:
    digits = re.sub(r"\D", "", raw_cep or "")
    if not CEP_PATTERN.match(digits):
        raise GeocodingError("CEP inválido.", 400)
    return digits


def _build_query(via_cep_payload: dict[str, str]) -> str:
    pieces = [
        via_cep_payload.get("logradouro"),
        # via_cep_payload.get("bairro"),
        via_cep_payload.get("localidade"),
        # via_cep_payload.get("uf"),
        "Brasil",
    ]
    filtered = [p.strip() for p in pieces if p]
    if len(filtered) < 2:
        raise GeocodingError("Endereço insuficiente para geocodificação.", 404)
    return ", ".join(filtered)


def _request_via_cep(cep: str) -> dict[str, str]:
    url = VIACEP_URL_TEMPLATE.format(cep=cep)
    try:
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        raise GeocodingError("Não foi possível consultar o ViaCEP.", 502) from exc
    if response.status_code == 404:
        raise GeocodingError("CEP não encontrado.", 404)
    if not response.ok:
        raise GeocodingError("Erro ao consultar o ViaCEP.", 502)
    payload = response.json()
    if payload.get("erro"):
        raise GeocodingError("CEP não encontrado.", 404)
    return payload


def _request_nominatim(query: str) -> dict[str, str]:
    headers = {
        "User-Agent": getattr(settings, "NOMINATIM_USER_AGENT", DEFAULT_USER_AGENT),
        "Accept-Language": "pt-BR,en",
    }
    pprint.pprint(query)
    params = {
        "format": "jsonv2",
        "q": query,
        "countrycodes": "br",
        "limit": 1,
    }
    try:
        response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        pprint.pprint(exc)
        raise GeocodingError("Não foi possível consultar o Nominatim.", 502) from exc
    if response.status_code == 429:
        raise GeocodingError("Limite de consultas ao Nominatim atingido.", 503)
    if not response.ok:
        raise GeocodingError("Erro ao consultar o Nominatim.", 502)
    payload: list[dict[str, str]] = response.json()
    if not payload:
        raise GeocodingError("Não encontramos coordenadas para o CEP informado.", 404)
    return payload[0]


def geocode_cep(raw_cep: str) -> dict[str, float]:
    cep = _normalize_cep(raw_cep)
    via_cep_payload = _request_via_cep(cep)
    query = _build_query(via_cep_payload)
    nominatim_payload = _request_nominatim(query)
    try:
        lat = float(nominatim_payload["lat"])
        lon = float(nominatim_payload["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GeocodingError("Resposta inválida do Nominatim.", 502) from exc
    return {"lat": lat, "lng": lon}


def _normalize_address(raw_address: str) -> str:
    normalized = re.sub(r"\s+", " ", (raw_address or "")).strip()
    if not normalized:
        raise GeocodingError("Informe um endereço válido.", 400)
    return normalized


def _cache_key_for_address(address: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", address.lower())
    slug = slug.strip("-") or "default"
    return f"geocode:br:sp:{slug}"


def _is_state_sp(state_name: str, state_code: str) -> bool:
    if state_code.upper() == "SP":
        return True
    if not state_name:
        return False
    normalized = unicodedata.normalize("NFKD", state_name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").strip().lower()
    return ascii_name == "sao paulo"


def geocode_address_sp(address: str) -> dict[str, float]:
    normalized = _normalize_address(address)
    cache_key = _cache_key_for_address(normalized)
    cached: dict[str, float] | None = cache.get(cache_key)
    if cached:
        return cached

    headers = {
        "User-Agent": getattr(settings, "NOMINATIM_USER_AGENT", DEFAULT_USER_AGENT),
        "Accept-Language": "pt-BR",
    }
    #pprint.pprint(normalized)
    params = {
        "format": "jsonv2",
        "q": f"{normalized} SP Brasil",
        "countrycodes": "br",
        "limit": 1,
    }
    try:
        response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        # pprint.pprint(exc)
        raise GeocodingError("Não foi possível consultar o Nominatim.", 502) from exc

    if response.status_code == 429:
        raise GeocodingError("Limite de consultas ao Nominatim atingido.", 503)
    if not response.ok:
        # pprint.pprint(response)
        raise GeocodingError("Erro ao consultar o Nominatim.", 502)

    payload: list[dict[str, Any]] = response.json()
    if not payload:
        raise GeocodingError("Não foi possível localizar este endereço em SP.", 404)

    # pprint.pprint(payload)
    result = payload[0]
    try:
        lat = float(result["lat"])
        lon = float(result["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        pprint.pprint(exc)
        raise GeocodingError("Resposta inválida do Nominatim.", 502) from exc

    # address_info: dict[str, Any] = result.get("address") or {}
    # state_name = (address_info.get("state") or "").strip()
    # state_code = (address_info.get("state_code") or "").strip().upper()
    # if not _is_state_sp(state_name, state_code):
    #     raise GeocodingError("O endereço localizado fica fora de São Paulo (SP).", 422)

    coordinates = {"lat": lat, "lng": lon}
    cache.set(cache_key, coordinates, GEOCODE_CACHE_TTL)
    return coordinates
