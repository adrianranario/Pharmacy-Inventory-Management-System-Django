from datetime import datetime

from django.core.paginator import Paginator
from django.utils.dateparse import parse_date


def paginate(request, queryset, per_page=25):
    """Return a Page for the current request, tolerating bad page values."""
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get('page'))


def parse_date_param(value):
    if not value:
        return None
    try:
        return parse_date(value)
    except (ValueError, TypeError):
        return None


def filter_date_range(queryset, field, date_from=None, date_to=None):
    if date_from:
        queryset = queryset.filter(**{f'{field}__gte': date_from})
    if date_to:
        queryset = queryset.filter(**{f'{field}__lte': date_to})
    return queryset


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_decimal(value, default='0'):
    from decimal import Decimal, InvalidOperation

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def humanize_dt(value):
    if not value:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M')
    return value.strftime('%Y-%m-%d')
