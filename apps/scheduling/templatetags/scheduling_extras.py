from django import template

register = template.Library()

WEEKDAY_NAMES_PT = [
    "Seg",
    "Ter",
    "Qua",
    "Qui",
    "Sex",
    "Sáb",
    "Dom",
]


@register.filter
def weekday_name(value):
    try:
        i = int(value)
    except (TypeError, ValueError):
        return value
    if 0 <= i <= 6:
        return WEEKDAY_NAMES_PT[i]
    return value

