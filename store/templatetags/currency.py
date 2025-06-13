from django import template

register = template.Library()


@register.filter
def to_eur(value):
    try:
        return "{:.2f} €".format(float(value) / 1.95583)
    except (ValueError, TypeError):
        return ""
