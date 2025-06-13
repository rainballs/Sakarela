# store/templatetags/currency.py
from django import template

register = template.Library()


@register.filter
def to_eur(value):
    """
    Делим стойност (лв.) на фиксиран курс 1.95583,
    връщаме formatted string с две цифри и €
    """
    try:
        return "{:.2f} €".format(float(value) / 1.95583)
    except (ValueError, TypeError):
        return ""
