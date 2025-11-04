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

RULE_LABELS_PT = {
    "weekly": "Semanal",
    "date_override": "Sobrepor data",
    "holiday": "Feriado",
}


@register.filter
def weekday_name(value):
    try:
        i = int(value)
    except (TypeError, ValueError):
        return value
    if 0 <= i <= 6:
        return WEEKDAY_NAMES_PT[i]
    return value


@register.filter
def availability_label(value):
    return RULE_LABELS_PT.get(value, value)
