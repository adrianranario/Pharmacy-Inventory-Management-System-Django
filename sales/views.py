from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.audit import log
from core.permissions import capability_required
from core.utils import filter_date_range, parse_date_param, paginate
from pos.forms import ReturnForm, VoidSaleForm
from pos.models import Sale
from pos.services import process_return, void_sale
from .models import Sale as _Sale  # noqa: F401  (sales app re-exports pos models)


@capability_required('view_sales')
def sales_list(request):
    sales = Sale.objects.select_related('sold_by', 'customer').prefetch_related('items')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    payment = request.GET.get('payment', '')
    date_from = parse_date_param(request.GET.get('from'))
    date_to = parse_date_param(request.GET.get('to'))

    if query:
        sales = sales.filter(
            Q(invoice_no__icontains=query)
            | Q(or_number__icontains=query)
            | Q(customer_name__icontains=query)
            | Q(customer__name__icontains=query)
        )
    if status:
        sales = sales.filter(status=status)
    if payment:
        sales = sales.filter(payment_method=payment)
    sales = filter_date_range(sales, 'created_at__date', date_from, date_to)

    page_obj = paginate(request, sales, 25)
    return render(request, 'sales/sales_list.html', {
        'page_obj': page_obj,
        'sales': page_obj.object_list,
        'query': query,
        'selected_status': status,
        'selected_payment': payment,
        'date_from': request.GET.get('from', ''),
        'date_to': request.GET.get('to', ''),
        'statuses': Sale.STATUS_CHOICES,
        'payments': Sale.PAYMENT_CHOICES,
    })


@capability_required('view_sales')
def sale_view(request, pk):
    sale = get_object_or_404(
        Sale.objects.select_related('sold_by', 'customer', 'voided_by').prefetch_related(
            'items__medicine', 'items__batch', 'returns__items__sale_item__medicine', 'returns__processed_by'
        ),
        pk=pk,
    )
    return render(request, 'sales/sale_view.html', {
        'sale': sale,
        'return_form': ReturnForm(),
        'void_form': VoidSaleForm(),
    })


@capability_required('refund')
def return_sale(request, pk):
    sale = get_object_or_404(Sale.objects.prefetch_related('items__medicine'), pk=pk)
    form = ReturnForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        item_quantities = {}
        for item in sale.items.all():
            value = request.POST.get(f'qty_{item.pk}', '').strip()
            if value:
                item_quantities[item.pk] = value
        try:
            sale_return = process_return(
                sale,
                item_quantities,
                form.cleaned_data['reason'],
                request.user,
                form.cleaned_data.get('notes', ''),
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            log(request.user, 'return', sale, f'Processed return {sale_return.return_no} for {sale.invoice_no}', request)
            messages.success(request, f'Return processed. Refund: ₱{sale_return.total_amount}.')
            return redirect('sale_view', pk=sale.pk)
    return render(request, 'sales/return_sale.html', {'sale': sale, 'form': form})


@capability_required('void_sale')
@require_POST
def void_sale_view(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    form = VoidSaleForm(request.POST)
    if form.is_valid():
        try:
            void_sale(sale, request.user, form.cleaned_data['reason'])
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            log(request.user, 'void', sale, f'Voided sale {sale.invoice_no}: {form.cleaned_data["reason"]}', request)
            messages.success(request, f'Sale {sale.invoice_no} voided and stock restored.')
    else:
        messages.error(request, 'A reason is required to void a sale.')
    return redirect('sale_view', pk=sale.pk)
