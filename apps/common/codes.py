import secrets
import string
from typing import Callable, Protocol


class _ExistsFunc(Protocol):
    def __call__(self, code: str) -> bool:
        ...


_ALPHABET = string.ascii_uppercase + string.digits


def _random_code(length: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def generate_unique_code(
    *,
    length: int = 8,
    exists: _ExistsFunc,
    max_attempts: int = 12,
) -> str:
    """Return a random uppercase+digits code that is unique under the provided exists() check."""
    for _ in range(max_attempts):
        code = _random_code(length)
        if not exists(code):
            return code
    raise RuntimeError("unable to generate unique code")
