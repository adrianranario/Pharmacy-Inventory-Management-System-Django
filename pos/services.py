from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from customers.models import Customer
from inventory.models import Batch, Medicine
from inventory.services import deduct_fefo, record_movement
from core.sequences import next_invoice_no, next_or_number, next_return_no
from .models import Sale, SaleItem, SaleReturn, SaleReturnItem

CENT = Decimal('0.01')
DISCOUNT_RATE = Decimal(str(getattr(settings, 'SENIOR_DISCOUNT_RATE', '20')))


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _as_decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f'{field} must be a valid amount.')
    if result < 0:
        raise ValidationError(f'{field} cannot be negative.')
    return result


def _normalise_cart(cart):
    if not isinstance(cart, list) or not cart:
        raise ValidationError('Cart is empty.')
    merged = {}
    for row in cart:
        try:
            medicine_id = int(row.get('id'))
            quantity = int(row.get('quantity', 1))
        except (TypeError, ValueError, AttributeError):
            raise ValidationError('Cart contains an invalid item.')
        if quantity <= 0:
            raise ValidationError('Quantities must be greater than zero.')
        if quantity > 10000:
            raise ValidationError('Quantity is unreasonably large.')
        merged[medicine_id] = merged.get(medicine_id, 0) + quantity
    return merged


def resolve_customer(customer_id, customer_name, customer_type, id_no):
    customer = None
    if customer_id:
        customer = Customer.objects.filter(pk=customer_id, status=True).first()
    if customer is None and (customer_name or '').strip():
        customer = Customer.objects.filter(name__iexact=customer_name.strip()).first()
        if customer is None:
            customer = Customer.objects.create(
                name=customer_name.strip(),
                customer_type=customer_type if customer_type in {'regular', 'senior_citizen', 'pwd'} else 'regular',
                id_no=id_no or '',
            )
    if customer is not None:
        if customer_type in {'senior_citizen', 'pwd'} and not customer.id_no and id_no:
            customer.id_no = id_no
            customer.save(update_fields=['id_no'])
    return customer


@transaction.atomic
def checkout_cart(*, cart, user, customer_type='regular', customer_name='', id_no='', amount_paid='0',
                  payment_method='cash', payment_reference='', customer_id=None):
    """Create a sale, deduct stock FEFO and return the completed Sale."""
    if customer_type not in dict(Sale.CUSTOMER_CHOICES):
        raise ValidationError('Invalid customer type.')
    if customer_type in {'senior_citizen', 'pwd'} and not (id_no or '').strip():
        raise ValidationError('Enter the senior citizen/PWD ID number for this discounted sale.')
    if payment_method not in dict(Sale.PAYMENT_CHOICES):
        raise ValidationError('Invalid payment method.')

    quantities = _normalise_cart(cart)

    invoice_no = next_invoice_no()
    or_number = next_or_number()

    medicines = {
        medicine.pk: medicine
        for medicine in Medicine.objects.select_for_update().filter(pk__in=quantities.keys(), status=True).select_related('category')
    }
    missing = set(quantities) - set(medicines)
    if missing:
        raise ValidationError('One or more medicines are no longer available.')

    subtotal = Decimal('0')
    for medicine_id, quantity in quantities.items():
        medicine = medicines[medicine_id]
        subtotal += money(medicine.selling_price) * quantity

    vat_rate = Decimal(str(getattr(settings, 'VAT_RATE', 12)))
    vat_exempt = Decimal('0')
    discount_rate = Decimal('0')
    discount_amount = Decimal('0')
    if customer_type in {'senior_citizen', 'pwd'}:
        discount_rate = DISCOUNT_RATE
        vat_exempt = money(subtotal - (subtotal / (Decimal('1') + (vat_rate / Decimal('100')))))
        discount_amount = money((subtotal - vat_exempt) * (discount_rate / Decimal('100')))

    total_amount = money(subtotal - vat_exempt - discount_amount)
    paid = _as_decimal(amount_paid or '0', 'Amount paid')
    if paid < total_amount:
        raise ValidationError(f'Amount paid (₱{paid}) is less than the total (₱{total_amount}).')
    change_amount = money(paid - total_amount)

    customer = resolve_customer(customer_id, customer_name, customer_type, id_no)

    sale = Sale.objects.create(
        invoice_no=invoice_no,
        or_number=or_number,
        sold_by=user,
        customer=customer,
        customer_name=customer.name if customer else (customer_name or '')[:200],
        customer_type=customer_type,
        id_no=id_no[:50],
        subtotal=money(subtotal),
        discount_rate=discount_rate,
        discount_amount=discount_amount,
        vat_exempt=vat_exempt,
        total_amount=total_amount,
        amount_paid=paid,
        change_amount=change_amount,
        payment_method=payment_method,
        payment_reference=payment_reference[:80],
        status='completed',
    )

    for medicine_id, quantity in quantities.items():
        medicine = medicines[medicine_id]
        for batch, taken in deduct_fefo(
            medicine,
            quantity,
            user=user,
            reference=invoice_no,
            movement_type='sale',
            notes=f'Sold on {invoice_no}',
        ):
            SaleItem.objects.create(
                sale=sale,
                medicine=medicine,
                batch=batch,
                quantity=taken,
                price=money(medicine.selling_price),
            )

    if customer is not None:
        points = int(total_amount // Decimal('100'))
        if points:
            customer.loyalty_points += points
            customer.save(update_fields=['loyalty_points'])

    return sale


@transaction.atomic
def void_sale(sale, user, reason):
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status == 'voided':
        raise ValidationError('This sale is already voided.')
    if sale.returns.exists():
        raise ValidationError('Sales with returns cannot be voided. Process a return instead.')

    for item in sale.items.select_for_update().select_related('batch'):
        batch = Batch.objects.select_for_update().get(pk=item.batch_id)
        batch.remaining_quantity += item.quantity
        batch.save(update_fields=['remaining_quantity'])
        record_movement(
            item.medicine,
            batch,
            'void',
            item.quantity,
            user=user,
            reference=sale.invoice_no,
            notes=f'Sale voided: {reason}',
        )

    sale.status = 'voided'
    sale.voided_by = user
    sale.voided_at = timezone.now()
    sale.void_reason = reason
    sale.save(update_fields=['status', 'voided_by', 'voided_at', 'void_reason'])

    if sale.customer_id:
        points = int(sale.total_amount // Decimal('100'))
        if points:
            Customer.objects.filter(pk=sale.customer_id).update(
                loyalty_points=max(0, sale.customer.loyalty_points - points)
            )
    return sale


@transaction.atomic
def process_return(sale, item_quantities, reason, user, notes=''):
    """Return selected quantities. ``item_quantities`` maps SaleItem.pk -> qty."""
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if not sale.is_refundable:
        raise ValidationError('This sale can no longer be returned.')

    requested = {}
    for item_id, quantity in item_quantities.items():
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            continue
        if quantity > 0:
            requested[int(item_id)] = quantity
    if not requested:
        raise ValidationError('Select at least one item and quantity to return.')

    items = {item.pk: item for item in SaleItem.objects.select_for_update().filter(sale=sale, pk__in=requested)}
    if len(items) != len(requested):
        raise ValidationError('One or more returned items do not belong to this sale.')

    sale_return = SaleReturn.objects.create(
        return_no=next_return_no(),
        sale=sale,
        processed_by=user,
        reason=reason[:200],
        notes=notes,
    )

    total_refund = Decimal('0')
    ratio = (sale.total_amount / sale.subtotal) if sale.subtotal else Decimal('1')

    for item_id, quantity in requested.items():
        item = items[item_id]
        if quantity > item.refundable_quantity:
            raise ValidationError(
                f'Cannot return {quantity} of {item.medicine.generic_name}; only {item.refundable_quantity} remaining.'
            )
        amount = money(item.price * quantity * ratio)
        item.returned_quantity += quantity
        item.save(update_fields=['returned_quantity'])
        batch = Batch.objects.select_for_update().get(pk=item.batch_id)
        batch.remaining_quantity += quantity
        batch.save(update_fields=['remaining_quantity'])
        record_movement(
            item.medicine,
            batch,
            'return',
            quantity,
            user=user,
            reference=sale_return.return_no,
            notes=f'Return for {sale.invoice_no}: {reason}',
        )
        SaleReturnItem.objects.create(
            sale_return=sale_return,
            sale_item=item,
            quantity=quantity,
            amount=amount,
        )
        total_refund += amount

    sale_return.total_amount = money(total_refund)
    sale_return.save(update_fields=['total_amount'])
    sale.refunded_amount = money(sale.refunded_amount + total_refund)

    fully_returned = all(item.refundable_quantity == 0 for item in sale.items.all())
    sale.status = 'returned' if fully_returned else 'partially_returned'
    sale.save(update_fields=['refunded_amount', 'status'])

    if sale.customer_id and total_refund > 0:
        points = int(total_refund // Decimal('100'))
        if points:
            Customer.objects.filter(pk=sale.customer_id).update(
                loyalty_points=max(0, sale.customer.loyalty_points - points)
            )

    return sale_return
