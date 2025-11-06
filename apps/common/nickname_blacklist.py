from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Set

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parents[2]
_IBGE_NAME_CANDIDATES = [
    _BASE_DIR / "ibge-nomes.json",
    _BASE_DIR / "config" / "ibge-nomes.json",
]


def _normalize(values: Iterable[str]) -> Set[str]:
    normalized = set()
    for value in values:
        if not isinstance(value, str):
            continue
        stripped = value.strip().lower()
        if stripped:
            normalized.add(stripped)
    return normalized


@lru_cache(maxsize=1)
def load_ibge_blacklist() -> Set[str]:
    """Load the IBGE common names once and keep them cached in memory."""
    path = next((p for p in _IBGE_NAME_CANDIDATES if p.exists()), None)
    if path is None:
        logger.info("IBGE names file not found in any of %s; continuing without extra blacklist", _IBGE_NAME_CANDIDATES)
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Failed to decode IBGE names file %s; ignoring contents", path)
        return set()
    if isinstance(raw, list):
        return _normalize(raw)
    logger.warning("Unexpected IBGE names payload type %s; ignoring contents", type(raw).__name__)
    return set()


def build_reserved_nicknames(base_values: Iterable[str]) -> Set[str]:
    """Combine system-defined reserved nicknames with the IBGE blacklist."""
    return _normalize(base_values) | load_ibge_blacklist()
