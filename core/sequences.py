"""Human readable, gap-free-enough document numbers.

Numbers are derived inside the same transaction as the document insert, so the
only realistic collision is two simultaneous requests in the same second. On
SQLite (single writer) this is safe; on Postgres the unique constraint plus a
short retry in the caller protects against it.
"""
from django.db import transaction
from django.utils import timezone


def _next_sequence(prefix, field):
    last = (
        field.model.objects.filter(**{f'{field.name}__startswith': prefix})
        .order_by(f'-{field.name}')
        .values_list(field.name, flat=True)
        .first()
    )
    number = 1
    if last:
        try:
            number = int(last.rsplit('-', 1)[-1]) + 1
        except (ValueError, IndexError):
            number = 1
    return f'{prefix}{number:04d}'


def next_invoice_no():
    prefix = f'INV-{timezone.localtime().strftime("%Y%m%d")}-'
    from pos.models import Sale

    return _next_sequence(prefix, Sale._meta.get_field('invoice_no'))


def next_or_number():
    prefix = f'OR-{timezone.localtime().strftime("%Y")}-'
    from pos.models import Sale

    return _next_sequence(prefix, Sale._meta.get_field('or_number'))


def next_purchase_no():
    prefix = f'PO-{timezone.localtime().strftime("%Y%m%d")}-'
    from purchases.models import Purchase

    return _next_sequence(prefix, Purchase._meta.get_field('purchase_no'))


def next_return_no():
    prefix = f'RET-{timezone.localtime().strftime("%Y%m%d")}-'
    from pos.models import SaleReturn

    return _next_sequence(prefix, SaleReturn._meta.get_field('return_no'))
