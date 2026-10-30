from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from inventory.models import Batch, Category, Medicine
from pos.models import Sale, SaleItem
from purchases.models import Purchase


@login_required
def dashboard(request):
    today = timezone.localdate()
    start = today - timedelta(days=29)

    active_sales = Sale.objects.exclude(status='voided')
    today_sales_qs = active_sales.filter(created_at__date=today)
    month_sales_qs = active_sales.filter(created_at__year=today.year, created_at__month=today.month)

    total_medicines = Medicine.objects.filter(status=True).count()
    today_sales = today_sales_qs.aggregate(total=Sum('total_amount'))['total'] or 0
    month_sales = month_sales_qs.aggregate(total=Sum('total_amount'))['total'] or 0
    today_transactions = today_sales_qs.count()
    avg_basket = (month_sales / month_sales_qs.count()) if month_sales_qs.count() else 0

    medicines = Medicine.objects.filter(status=True).prefetch_related('batches')
    low_stock = [m for m in medicines if m.is_low_stock()]
    near_expiry = (
        Batch.objects.filter(
            remaining_quantity__gt=0,
            expiry_date__lte=today + timedelta(days=getattr(settings, 'EXPIRY_WARNING_DAYS', 90)),
            expiry_date__gte=today,
        )
        .select_related('medicine')
        .order_by('expiry_date')[:10]
    )
    expired_count = Batch.objects.filter(remaining_quantity__gt=0, expiry_date__lt=today).count()
    pending_purchases = Purchase.objects.filter(status__in=['draft', 'ordered']).count()
    inventory_value = sum(
        batch.remaining_quantity * batch.purchase_price
        for batch in Batch.objects.filter(remaining_quantity__gt=0).select_related('medicine')
    )

    recent_sales = active_sales.select_related('sold_by', 'customer').order_by('-created_at')[:10]

    # 30 day sales trend (fill missing days with zero)
    rows = (
        active_sales.filter(created_at__date__gte=start)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(total=Sum('total_amount'))
        .order_by('day')
    )
    by_day = {row['day']: float(row['total'] or 0) for row in rows}
    labels, values = [], []
    for offset in range(30):
        day = start + timedelta(days=offset)
        labels.append(day.strftime('%b %d'))
        values.append(round(by_day.get(day, 0), 2))

    top_medicines = (
        SaleItem.objects.filter(sale__created_at__date__gte=start)
        .exclude(sale__status='voided')
        .values('medicine__generic_name')
        .annotate(qty=Sum('quantity'), revenue=Sum('subtotal'))
        .order_by('-qty')[:5]
    )

    category_rows = (
        Batch.objects.filter(remaining_quantity__gt=0)
        .values('medicine__category__name')
        .annotate(qty=Sum('remaining_quantity'))
        .order_by('-qty')[:6]
    )

    context = {
        'total_medicines': total_medicines,
        'today_sales': today_sales,
        'month_sales': month_sales,
        'today_transactions': today_transactions,
        'avg_basket': avg_basket,
        'inventory_value': inventory_value,
        'low_stock': low_stock,
        'low_stock_count': len(low_stock),
        'near_expiry': near_expiry,
        'expired_count': expired_count,
        'pending_purchases': pending_purchases,
        'recent_sales': recent_sales,
        'chart_labels': labels,
        'chart_values': values,
        'top_medicines': list(top_medicines),
        'category_rows': list(category_rows),
    }
    return render(request, 'dashboard/index.html', context)
