import json

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.audit import log
from core.permissions import capability_required
from inventory.models import Batch, Medicine
from .models import Sale
from .services import checkout_cart


@capability_required('sell')
def pos_index(request):
    medicines = Medicine.objects.filter(status=True).select_related('category')
    return render(request, 'pos/index.html', {
        'medicines': medicines,
        'vat_rate': float(getattr(settings, 'VAT_RATE', 12)) / 100,
        'discount_rate': float(getattr(settings, 'SENIOR_DISCOUNT_RATE', 20)) / 100,
    })


@capability_required('sell')
def search_medicine(request):
    query = request.GET.get('q', '').strip()
    medicines = Medicine.objects.filter(status=True)
    if query:
        medicines = medicines.filter(
            Q(generic_name__icontains=query)
            | Q(brand_name__icontains=query)
            | Q(barcode__iexact=query)
            | Q(medicine_code__iexact=query)
            | Q(barcode__icontains=query)
            | Q(medicine_code__icontains=query)
        )
    medicines = medicines.select_related('category').prefetch_related('batches')[:50]
    data = []
    for med in medicines:
        stock = med.sellable_stock()
        if stock <= 0:
            continue
        data.append({
            'id': med.id,
            'name': f'{med.generic_name} {med.brand_name or ""}'.strip(),
            'price': float(med.selling_price),
            'stock': stock,
            'barcode': med.barcode or '',
            'code': med.medicine_code,
        })
    return JsonResponse(data[:20], safe=False)


@require_POST
@capability_required('sell')
def checkout(request):
    try:
        cart = json.loads(request.POST.get('cart', '[]'))
    except json.JSONDecodeError:
        cart = []

    try:
        sale = checkout_cart(
            cart=cart,
            user=request.user,
            customer_type=request.POST.get('customer_type', 'regular'),
            customer_name=request.POST.get('customer_name', ''),
            customer_id=request.POST.get('customer_id') or None,
            id_no=request.POST.get('id_no', ''),
            amount_paid=request.POST.get('amount_paid', '0'),
            payment_method=request.POST.get('payment_method', 'cash'),
            payment_reference=request.POST.get('payment_reference', ''),
        )
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if exc.messages else 'Unable to complete the sale.')
        return redirect('pos_index')

    log(request.user, 'sale', sale, f'Completed sale {sale.invoice_no} for ₱{sale.total_amount}', request)
    messages.success(request, f'Sale {sale.invoice_no} completed. Change: ₱{sale.change_amount}.')
    return redirect('pos_receipt', pk=sale.pk)


@capability_required('view_sales')
def receipt(request, pk):
    sale = get_object_or_404(
        Sale.objects.select_related('sold_by', 'customer').prefetch_related('items__medicine', 'items__batch'),
        pk=pk,
    )
    from decimal import Decimal, ROUND_HALF_UP
    from django.conf import settings as django_settings

    vat_rate = Decimal(str(getattr(django_settings, 'VAT_RATE', 12)))
    net = sale.total_amount or Decimal('0')
    if sale.vat_exempt:
        vat = Decimal('0.00')
        vatable = Decimal('0.00')
        exempt_sale = (sale.subtotal or Decimal('0')) - sale.vat_exempt
    else:
        vat = (net - (net / (Decimal('1') + vat_rate / Decimal('100')))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        vatable = net - vat
        exempt_sale = Decimal('0.00')
    return render(request, 'pos/receipt.html', {
        'sale': sale,
        'vat_amount': vat,
        'vatable_sales': vatable,
        'exempt_sale': exempt_sale,
    })
