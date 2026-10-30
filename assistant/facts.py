import re
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from core.permissions import has_capability
from inventory.models import Batch, Medicine
from pos.models import Sale


def _count_label(count, singular, plural=None):
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def _batch_label(count):
    return _count_label(count, 'batch', 'batches')


def _expired_batch_label(count):
    return f"{count} expired {'batch' if count == 1 else 'batches'}"


def _medicine_label(count):
    return _count_label(count, 'medicine')


def _money(value):
    return f"₱{Decimal(value or 0):,.2f}"


def _expiry_text(batch):
    days = batch.days_to_expire()
    if days < 0:
        return f"expired {batch.expiry_date}"
    if days == 0:
        return f"expires today ({batch.expiry_date})"
    if days == 1:
        return f"expires tomorrow ({batch.expiry_date})"
    return f"expires {batch.expiry_date} ({days} days)"


def _batch_line(batch):
    brand = f" ({batch.medicine.brand_name})" if batch.medicine.brand_name else ""
    return (
        f"{batch.medicine.generic_name}{brand} / batch {batch.batch_no}: "
        f"{batch.remaining_quantity} units, {_expiry_text(batch)}"
    )


def _batch_detail(batch):
    return f"batch {batch.batch_no}: {batch.remaining_quantity} units, {_expiry_text(batch)}"


def _parse_days(question):
    match = re.search(r'(\d+)\s*day', question)
    if match:
        return max(0, int(match.group(1)))
    match = re.search(r'(\d+)\s*week', question)
    if match:
        return max(0, int(match.group(1)) * 7)
    match = re.search(r'(\d+)\s*month', question)
    if match:
        return max(0, int(match.group(1)) * 30)
    if 'tomorrow' in question:
        return 1
    if 'today' in question:
        return 0
    if 'this week' in question or 'next week' in question:
        return 7
    if 'this month' in question or 'next month' in question:
        return 30
    return getattr(settings, 'EXPIRY_WARNING_DAYS', 90)


def _answer_expiry(question):
    today = timezone.localdate()
    days = _parse_days(question)
    show_30_day_note = days > 30 and not any(
        term in question
        for term in ['today', 'tomorrow', 'this week', 'next week', 'this month', 'next month']
    )

    if 'tomorrow' in question:
        start = today + timedelta(days=1)
        end = start
        header = 'Expiry check for tomorrow'
        when = 'tomorrow'
    elif 'today' in question or days == 0:
        start = today
        end = today
        header = 'Expiry check for today'
        when = 'today'
    elif 'this week' in question:
        start = today
        end = today + timedelta(days=6 - today.weekday())
        header = 'Expiry check for this week'
        when = 'this week'
    elif 'next week' in question:
        start = today + timedelta(days=7 - today.weekday())
        end = start + timedelta(days=6)
        header = 'Expiry check for next week'
        when = 'next week'
    elif 'this month' in question:
        start = today
        end = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        header = 'Expiry check for this month'
        when = 'this month'
    elif 'next month' in question:
        start = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        header = 'Expiry check for next month'
        when = 'next month'
    else:
        start = today
        end = today + timedelta(days=days)
        header = f"Expiry check for the next {_count_label(days, 'day')}"
        when = f"within {days} days"

    batches = list(
        Batch.objects.filter(
            remaining_quantity__gt=0,
            expiry_date__gte=start,
            expiry_date__lte=end,
        )
        .select_related('medicine')
        .order_by('expiry_date')
    )

    lines = [header, '']
    if batches:
        medicine_count = len({batch.medicine_id for batch in batches})
        if medicine_count == 1:
            summary = (
                f"1 medicine has {_batch_label(len(batches))} due to expire {when}."
            )
        else:
            summary = (
                f"{_medicine_label(medicine_count)} have "
                f"{_batch_label(len(batches))} due to expire {when}."
            )
        lines.append(summary)
        lines.append('')
        for index, batch in enumerate(batches[:20], 1):
            lines.append(f"{index}. {_batch_line(batch)}")
        if len(batches) > 20:
            lines.append(f"...and {len(batches) - 20} more batches.")
    else:
        lines.append(f"No batches with remaining stock are due to expire {when}.")

    if show_30_day_note:
        count_30 = Batch.objects.filter(
            remaining_quantity__gt=0,
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=30),
        ).count()
        lines.extend(['', f"Within 30 days: {_batch_label(count_30)}."])

    return '\n'.join(lines)


def _answer_expired(user=None):
    today = timezone.localdate()
    batches = list(
        Batch.objects.filter(remaining_quantity__gt=0, expiry_date__lt=today)
        .select_related('medicine')
        .order_by('expiry_date')
    )

    lines = ['Expired stock', '']
    if not batches:
        lines.append('There are no expired batches with remaining stock.')
        return '\n'.join(lines)

    medicine_count = len({batch.medicine_id for batch in batches})
    if medicine_count == 1:
        summary = (
            f"1 medicine has {_expired_batch_label(len(batches))} "
            "with remaining stock:"
        )
    else:
        summary = (
            f"{_medicine_label(medicine_count)} have "
            f"{_expired_batch_label(len(batches))} with remaining stock:"
        )
    lines.append(summary)
    lines.append('')
    for index, batch in enumerate(batches[:20], 1):
        lines.append(f"{index}. {_batch_line(batch)}")
    if len(batches) > 20:
        lines.append(f"...and {len(batches) - 20} more batches.")
    if user is not None and not has_capability(user, 'manage_inventory'):
        lines.extend(
            ['', 'Ask a pharmacist or inventory clerk to review and write off expired stock.']
        )
    else:
        lines.extend(['', 'Use the Alerts page to review and write off expired stock.'])
    return '\n'.join(lines)


def _answer_low_stock():
    medicines = list(Medicine.objects.filter(status=True).prefetch_related('batches'))
    low_stock = sorted(
        (medicine for medicine in medicines if medicine.is_low_stock()),
        key=lambda medicine: (medicine.sellable_stock(), medicine.generic_name.lower()),
    )

    lines = ['Low-stock medicines', '']
    if not low_stock:
        lines.append('No medicines are at or below their reorder level.')
        return '\n'.join(lines)

    lines.append(f"{_medicine_label(len(low_stock))} at or below the reorder level:")
    lines.append('')
    for index, medicine in enumerate(low_stock[:20], 1):
        brand = f" ({medicine.brand_name})" if medicine.brand_name else ''
        lines.append(f"{index}. {medicine.generic_name}{brand} [{medicine.medicine_code}]")
        lines.append(f"   On hand: {medicine.sellable_stock()} {medicine.unit}")
        lines.append(f"   Reorder level: {medicine.reorder_level} {medicine.unit}")
        lines.append(f"   Suggested order: {medicine.suggested_order_quantity()} {medicine.unit}")
    if len(low_stock) > 20:
        lines.append(f"...and {len(low_stock) - 20} more medicines.")
    return '\n'.join(lines)


def _answer_sales(question, user=None):
    if user is not None and not has_capability(user, 'view_sales'):
        return 'Sales summaries are available to cashiers, pharmacists, and administrators.'

    today = timezone.localdate()
    start = today
    end = today
    label = "Today's sales"

    if 'last week' in question:
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
        label = "Last week's sales"
    elif 'week' in question:
        start = today - timedelta(days=today.weekday())
        label = "This week's sales"
    elif 'last month' in question:
        first_this_month = today.replace(day=1)
        end = first_this_month - timedelta(days=1)
        start = end.replace(day=1)
        label = "Last month's sales"
    elif 'month' in question:
        start = today.replace(day=1)
        label = "This month's sales"
    elif 'yesterday' in question:
        start = today - timedelta(days=1)
        end = start
        label = "Yesterday's sales"

    sales = Sale.objects.exclude(status='voided').filter(
        created_at__date__gte=start,
        created_at__date__lte=end,
    )
    scope = 'Store'
    if (
        user is not None
        and not getattr(user, 'is_superuser', False)
        and getattr(user, 'role', None) not in {'admin', 'pharmacist'}
    ):
        sales = sales.filter(sold_by=user)
        scope = 'Your'

    totals = sales.aggregate(gross=Sum('total_amount'), refunds=Sum('refunded_amount'))
    total = (totals['gross'] or 0) - (totals['refunds'] or 0)
    return (
        f"{label}\n\n"
        f"{scope} sales: {_count_label(sales.count(), 'transaction')}, {_money(total)}."
    )


def _find_medicines(question):
    query = question.lower()
    matches = []
    for medicine in Medicine.objects.filter(status=True).prefetch_related('batches'):
        terms = [
            medicine.generic_name,
            medicine.medicine_code,
            medicine.brand_name or '',
            medicine.barcode or '',
        ]
        if any(term and term.lower() in query for term in terms):
            matches.append(medicine)
    return matches


def _answer_medicine_stock(medicines):
    lines = ['Medicine stock', '']
    if len(medicines) == 1:
        lines.append(f"Stock details for {medicines[0].generic_name}:")
    else:
        lines.append(f"Stock details for {len(medicines)} matching medicines:")
    lines.append('')

    for index, medicine in enumerate(medicines[:5], 1):
        brand = f" ({medicine.brand_name})" if medicine.brand_name else ''
        lines.append(f"{index}. {medicine.generic_name}{brand} [{medicine.medicine_code}]")
        lines.append(f"   Sellable stock: {medicine.sellable_stock()} {medicine.unit}")
        lines.append(f"   Reorder level: {medicine.reorder_level} {medicine.unit}")
        batches = [batch for batch in medicine.batches.all() if batch.remaining_quantity > 0]
        if not batches:
            lines.append('   No active batches.')
            continue
        lines.append('   Batches:')
        for batch in batches[:10]:
            lines.append(f"   • {_batch_detail(batch)}")
        if len(batches) > 10:
            lines.append(f"   ...and {len(batches) - 10} more batches.")

    if len(medicines) > 5:
        lines.append(f"...and {len(medicines) - 5} more matching medicines.")
    return '\n'.join(lines)


def _answer_total_medicines():
    count = Medicine.objects.filter(status=True).count()
    return f"Medicine catalog\n\nThere are {_medicine_label(count)} in the active catalog."


def answer_inventory_question(question, user=None):
    """Return an exact answer for common inventory questions, or None for the LLM."""
    query = (question or '').lower().strip()
    if not query:
        return None

    if (
        any(
            term in query
            for term in [
                'low stock',
                'low-stock',
                'low on stock',
                'low in stock',
                'running low',
                'out of stock',
                'restock',
                'reorder',
            ]
        )
        and 'reorder level' not in query
        and 'reorder point' not in query
    ):
        return _answer_low_stock()

    expiry_question = bool(re.search(r'\bexpir\w*\b', query))
    stock_question = any(
        term in query
        for term in ['stock', 'on hand', 'quantity', 'how much', 'reorder level', 'reorder point']
    )
    medicine_matches = None
    if expiry_question or stock_question:
        medicine_matches = _find_medicines(query)

    if medicine_matches and expiry_question:
        return _answer_medicine_stock(medicine_matches)

    if re.search(r'\bexpired\b', query) and not re.search(r'\b(?:expiring|expires|expire|expiry)\b', query):
        return _answer_expired(user)

    if expiry_question:
        return _answer_expiry(query)

    if any(term in query for term in ['sales', 'revenue', 'sold']):
        return _answer_sales(query, user)

    if medicine_matches and stock_question:
        return _answer_medicine_stock(medicine_matches)

    if any(
        term in query
        for term in [
            'how many medicines',
            'total medicines',
            'number of medicines',
            'medicines in inventory',
            'medicines in the catalog',
        ]
    ):
        return _answer_total_medicines()

    return None
