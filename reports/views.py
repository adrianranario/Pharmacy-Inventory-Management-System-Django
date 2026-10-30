from datetime import timedelta

from django.conf import settings
from django.db.models import Q, Sum
from django.shortcuts import render
from django.utils import timezone

from core.audit import log
from core.permissions import capability_required
from core.utils import filter_date_range, parse_date_param, paginate
from inventory.models import Batch, Category, Medicine
from pos.models import Sale
from purchases.models import Purchase
from . import exports


def _inventory_queryset(request):
    medicines = (
        Medicine.objects.select_related('category', 'supplier')
        .prefetch_related('batches')
        .order_by('generic_name')
    )
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    if query:
        medicines = medicines.filter(
            Q(generic_name__icontains=query) | Q(brand_name__icontains=query) | Q(medicine_code__icontains=query)
        )
    if category:
        medicines = medicines.filter(category_id=category)
    return medicines, query, category


def _sales_queryset(request):
    sales = Sale.objects.select_related('sold_by', 'customer')
    date_from = parse_date_param(request.GET.get('from'))
    date_to = parse_date_param(request.GET.get('to'))
    status = request.GET.get('status', '')
    if status:
        sales = sales.filter(status=status)
    sales = filter_date_range(sales, 'created_at__date', date_from, date_to)
    return sales, date_from, date_to, status


def _purchases_queryset(request):
    purchases = Purchase.objects.select_related('supplier', 'purchased_by', 'received_by')
    date_from = parse_date_param(request.GET.get('from'))
    date_to = parse_date_param(request.GET.get('to'))
    status = request.GET.get('status', '')
    if status:
        purchases = purchases.filter(status=status)
    purchases = filter_date_range(purchases, 'purchase_date', date_from, date_to)
    return purchases, date_from, date_to, status


def _date_context(request):
    return {'date_from': request.GET.get('from', ''), 'date_to': request.GET.get('to', '')}


def _low_stock():
    return [m for m in Medicine.objects.filter(status=True).select_related('supplier').prefetch_related('batches').order_by('generic_name') if m.is_low_stock()]


def _near_expiry(days=None):
    today = timezone.localdate()
    days = days or getattr(settings, 'EXPIRY_WARNING_DAYS', 90)
    return Batch.objects.filter(
        remaining_quantity__gt=0,
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=days),
    ).select_related('medicine').order_by('expiry_date'), days


@capability_required('view_reports')
def reports_index(request):
    today = timezone.localdate()
    return render(request, 'reports/index.html', {
        'low_stock_count': len(_low_stock()),
        'near_expiry_count': _near_expiry()[0].count(),
        'month_sales': Sale.objects.filter(
            created_at__year=today.year, created_at__month=today.month, status__in=['completed', 'partially_returned']
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
    })


@capability_required('view_reports')
def report_inventory(request):
    medicines, query, category = _inventory_queryset(request)
    page_obj = paginate(request, medicines, 30)
    return render(request, 'reports/inventory.html', {
        'page_obj': page_obj,
        'medicines': page_obj.object_list,
        'query': query,
        'selected_category': category,
        'categories': Category.objects.all(),
    })


@capability_required('view_reports')
def report_low_stock(request):
    medicines = _low_stock()
    from django.core.paginator import Paginator

    page_obj = Paginator(medicines, 30).get_page(request.GET.get('page'))
    return render(request, 'reports/low_stock.html', {'page_obj': page_obj, 'low_stock': page_obj.object_list})


@capability_required('view_reports')
def report_near_expiry(request):
    try:
        days = int(request.GET.get('days', getattr(settings, 'EXPIRY_WARNING_DAYS', 90)))
    except (TypeError, ValueError):
        days = getattr(settings, 'EXPIRY_WARNING_DAYS', 90)
    batches, days = _near_expiry(days)
    page_obj = paginate(request, batches, 30)
    return render(request, 'reports/near_expiry.html', {'page_obj': page_obj, 'batches': page_obj.object_list, 'days': days})


@capability_required('view_reports')
def report_sales(request):
    sales, date_from, date_to, status = _sales_queryset(request)
    summary = sales.aggregate(
        gross=Sum('total_amount'),
        refunded=Sum('refunded_amount'),
        discount=Sum('discount_amount'),
    )
    page_obj = paginate(request, sales, 30)
    context = {
        'page_obj': page_obj,
        'sales': page_obj.object_list,
        'summary': summary,
        'selected_status': status,
        'statuses': Sale.STATUS_CHOICES,
    }
    context.update(_date_context(request))
    return render(request, 'reports/sales.html', context)


@capability_required('view_reports')
def report_purchases(request):
    purchases, date_from, date_to, status = _purchases_queryset(request)
    summary = purchases.aggregate(total=Sum('total_amount'))
    page_obj = paginate(request, purchases, 30)
    context = {
        'page_obj': page_obj,
        'purchases': page_obj.object_list,
        'summary': summary,
        'selected_status': status,
        'statuses': Purchase.STATUS_CHOICES,
    }
    context.update(_date_context(request))
    return render(request, 'reports/purchases.html', context)


# ---------------------------------------------------------------------------
# Excel exports (same filters as the on-screen report)
# ---------------------------------------------------------------------------
@capability_required('export_reports')
def export_inventory(request):
    medicines, _, _ = _inventory_queryset(request)
    log(request.user, 'export', description='Exported inventory report', request=request)
    return exports.inventory_export(medicines)


@capability_required('export_reports')
def export_low_stock(request):
    log(request.user, 'export', description='Exported low stock report', request=request)
    return exports.low_stock_export(_low_stock())


@capability_required('export_reports')
def export_near_expiry(request):
    try:
        days = int(request.GET.get('days', getattr(settings, 'EXPIRY_WARNING_DAYS', 90)))
    except (TypeError, ValueError):
        days = getattr(settings, 'EXPIRY_WARNING_DAYS', 90)
    batches, _ = _near_expiry(days)
    log(request.user, 'export', description='Exported near expiry report', request=request)
    return exports.near_expiry_export(batches)


@capability_required('export_reports')
def export_sales(request):
    sales, _, _, _ = _sales_queryset(request)
    log(request.user, 'export', description='Exported sales report', request=request)
    return exports.sales_export(sales)


@capability_required('export_reports')
def export_purchases(request):
    purchases, _, _, _ = _purchases_queryset(request)
    log(request.user, 'export', description='Exported purchases report', request=request)
    return exports.purchases_export(purchases)
