import hashlib
import secrets
import phonenumbers
from typing import Final


def to_e164(raw: str, default_region: str = "BR") -> str:
    try:
        n = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException:
        raise ValueError("Telefone inválido")
    if not phonenumbers.is_valid_number(n):
        raise ValueError("Telefone inválido")
    return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)


def gen_code(n: int = 6) -> str:
    return f"{secrets.randbelow(10**n):0{n}d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


_MASK_TEMPLATE: Final = "{}*-****"


def last4_digits(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return digits[-4:] if digits else ""

def first_digits(phone: str, n: int = 8) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return digits[4:n] if digits else ""

def mask_phone(phone: str) -> str:
    last4 = first_digits(phone)
    if not last4:
        return "********"
    return _MASK_TEMPLATE.format(last4)
