from django import template

register = template.Library()


@register.filter
def brl_cents(value):
    """Format integer cents as BRL currency (e.g., 1234 -> R$ 12,34)."""
    try:
        cents = int(value)
    except (TypeError, ValueError):
        return value
    reais = cents / 100.0
    # Format with thousands separator and 2 decimals, then swap dot/comma for pt-BR style
    s = f"{reais:,.2f}"  # e.g., 1,234.56
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"

