"""Stock mutation helpers.

All helpers assume they are called inside a transaction when they touch more
than one row. Every change writes a StockMovement so the ledger always explains
the current batch balance.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Batch, Medicine, StockMovement


def record_movement(medicine, batch, movement_type, quantity, user=None, reference='', notes=''):
    return StockMovement.objects.create(
        medicine=medicine,
        batch=batch,
        movement_type=movement_type,
        quantity=quantity,
        balance_after=batch.remaining_quantity if batch is not None else medicine.total_stock(),
        reference=reference[:80],
        notes=notes,
        user=user if getattr(user, 'is_authenticated', False) else None,
    )


def deduct_fefo(medicine, quantity, user=None, reference='', movement_type='sale', notes=''):
    """Remove ``quantity`` from the earliest-expiring batches (FEFO).

    Returns a list of ``(batch, taken)`` tuples. Raises ValidationError when
    there is not enough unexpired stock.
    """
    if quantity <= 0:
        raise ValidationError('Quantity must be greater than zero.')

    today = timezone.localdate()
    batches = list(
        Batch.objects.select_for_update()
        .filter(medicine=medicine, remaining_quantity__gt=0, expiry_date__gte=today)
        .order_by('expiry_date', 'created_at')
    )
    available = sum(batch.remaining_quantity for batch in batches)
    if available < quantity:
        raise ValidationError(
            f'Insufficient stock for {medicine.generic_name}. Available: {available} {medicine.unit}, requested: {quantity}.'
        )

    remaining = quantity
    consumed = []
    for batch in batches:
        take = min(batch.remaining_quantity, remaining)
        if take <= 0:
            continue
        batch.remaining_quantity -= take
        batch.save(update_fields=['remaining_quantity'])
        record_movement(medicine, batch, movement_type, -take, user=user, reference=reference, notes=notes)
        consumed.append((batch, take))
        remaining -= take
        if remaining == 0:
            break
    return consumed


def add_stock(medicine, quantity, unit_price, expiry_date, batch_no, user=None, reference='', received_date=None, movement_type='purchase'):
    if quantity <= 0:
        raise ValidationError('Quantity must be greater than zero.')
    if not expiry_date:
        raise ValidationError('Expiry date is required to receive stock.')

    batch = Batch.objects.create(
        medicine=medicine,
        batch_no=batch_no,
        quantity=quantity,
        remaining_quantity=quantity,
        purchase_price=unit_price,
        expiry_date=expiry_date,
        received_date=received_date or timezone.localdate(),
    )
    record_movement(medicine, batch, movement_type, quantity, user=user, reference=reference, notes='Stock received')
    return batch


def adjust_batch(batch, new_quantity, reason, user, reference=''):
    if new_quantity < 0:
        raise ValidationError('Stock cannot be negative.')
    delta = new_quantity - batch.remaining_quantity
    if delta == 0:
        return None
    batch.remaining_quantity = new_quantity
    batch.save(update_fields=['remaining_quantity'])
    return record_movement(
        batch.medicine,
        batch,
        'adjustment',
        delta,
        user=user,
        reference=reference or f'ADJ-{batch.pk}',
        notes=reason,
    )


def write_off_batch(batch, quantity, reason, user, movement_type='writeoff'):
    if quantity <= 0 or quantity > batch.remaining_quantity:
        raise ValidationError('Write-off quantity must be between 1 and the remaining quantity.')
    batch.remaining_quantity -= quantity
    batch.save(update_fields=['remaining_quantity'])
    return record_movement(
        batch.medicine,
        batch,
        movement_type,
        -quantity,
        user=user,
        reference=f'WO-{batch.pk}',
        notes=reason,
    )


@transaction.atomic
def receive_purchase(purchase, user):
    """Create batches for every line of a draft/ordered purchase exactly once."""
    purchase = type(purchase).objects.select_for_update().get(pk=purchase.pk)
    if purchase.status == 'received':
        raise ValidationError('This purchase has already been received.')
    if purchase.status == 'cancelled':
        raise ValidationError('Cancelled purchases cannot be received.')
    if not purchase.items.exists():
        raise ValidationError('Add at least one item before receiving this purchase.')

    for item in purchase.items.select_related('medicine'):
        add_stock(
            medicine=item.medicine,
            quantity=item.quantity,
            unit_price=item.unit_price,
            expiry_date=item.expiry_date,
            batch_no=item.batch_no,
            user=user,
            reference=purchase.purchase_no,
            received_date=purchase.purchase_date,
        )

    purchase.status = 'received'
    purchase.received_at = timezone.now()
    purchase.received_by = user
    purchase.total_amount = sum(item.subtotal for item in purchase.items.all())
    purchase.save(update_fields=['status', 'received_at', 'received_by', 'total_amount'])
    return purchase


@transaction.atomic
def expire_batches(today=None, user=None):
    """Zero out expired batches and record the loss. Returns affected batches."""
    today = today or timezone.localdate()
    expired = list(
        Batch.objects.select_for_update()
        .filter(remaining_quantity__gt=0, expiry_date__lt=today)
        .select_related('medicine')
    )
    for batch in expired:
        quantity = batch.remaining_quantity
        batch.remaining_quantity = 0
        batch.save(update_fields=['remaining_quantity'])
        record_movement(
            batch.medicine,
            batch,
            'expiry',
            -quantity,
            user=user,
            reference=f'EXP-{batch.pk}',
            notes=f'Expired on {batch.expiry_date}',
        )
    return expired
