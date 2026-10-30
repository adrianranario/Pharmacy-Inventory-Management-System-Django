from datetime import datetime

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.audit import log
from core.permissions import capability_required
from core.sequences import next_purchase_no
from core.utils import filter_date_range, parse_date_param, paginate
from inventory.models import Medicine, Supplier
from inventory.services import receive_purchase
from .models import Purchase, PurchaseItem


@capability_required('manage_purchases')
def purchase_list(request):
    purchases = Purchase.objects.select_related('supplier', 'purchased_by', 'received_by')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    date_from = parse_date_param(request.GET.get('from'))
    date_to = parse_date_param(request.GET.get('to'))
    if query:
        purchases = purchases.filter(
            Q(purchase_no__icontains=query) | Q(supplier__name__icontains=query) | Q(invoice_no__icontains=query)
        )
    if status:
        purchases = purchases.filter(status=status)
    purchases = filter_date_range(purchases, 'purchase_date', date_from, date_to)
    page_obj = paginate(request, purchases, 25)
    return render(request, 'purchases/purchase_list.html', {
        'page_obj': page_obj,
        'purchases': page_obj.object_list,
        'query': query,
        'selected_status': status,
        'statuses': Purchase.STATUS_CHOICES,
        'date_from': request.GET.get('from', ''),
        'date_to': request.GET.get('to', ''),
    })


@capability_required('manage_purchases')
def purchase_add(request):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                supplier = Supplier.objects.get(pk=request.POST['supplier'])
                purchase_date = datetime.strptime(request.POST['purchase_date'], '%Y-%m-%d').date()
                purchase = Purchase.objects.create(
                    purchase_no=next_purchase_no(),
                    supplier=supplier,
                    purchased_by=request.user,
                    purchase_date=purchase_date,
                    invoice_no=request.POST.get('invoice_no', '')[:80],
                    notes=request.POST.get('notes', ''),
                    status='draft',
                )

                medicines = request.POST.getlist('medicine_id[]')
                quantities = request.POST.getlist('quantity[]')
                unit_prices = request.POST.getlist('unit_price[]')
                batch_nos = request.POST.getlist('batch_no[]')
                expiry_dates = request.POST.getlist('expiry_date[]')

                added = 0
                for index, medicine_id in enumerate(medicines):
                    if not medicine_id:
                        continue
                    medicine = Medicine.objects.get(pk=medicine_id)
                    quantity = int(quantities[index] or 0)
                    unit_price = unit_prices[index] or '0'
                    expiry = datetime.strptime(expiry_dates[index], '%Y-%m-%d').date()
                    if quantity <= 0:
                        raise ValidationError('Every purchase line needs a quantity greater than zero.')
                    if expiry < timezone.localdate():
                        raise ValidationError(f'Expiry for {medicine.generic_name} cannot be in the past.')
                    PurchaseItem.objects.create(
                        purchase=purchase,
                        medicine=medicine,
                        batch_no=batch_nos[index] or f'B-{purchase.pk}-{index + 1}',
                        quantity=quantity,
                        unit_price=unit_price,
                        expiry_date=expiry,
                    )
                    added += 1

                if not added:
                    raise ValidationError('Add at least one purchase line.')

                purchase.total_amount = sum(item.subtotal for item in purchase.items.all())
                purchase.save(update_fields=['total_amount'])

                if request.POST.get('action') == 'receive':
                    receive_purchase(purchase, request.user)
                    purchase.refresh_from_db()
                    message = f'Purchase {purchase.purchase_no} received and stock updated.'
                else:
                    message = f'Purchase order {purchase.purchase_no} saved as draft.'
        except (KeyError, ValueError, ValidationError, Medicine.DoesNotExist, Supplier.DoesNotExist) as exc:
            message = exc.messages[0] if isinstance(exc, ValidationError) else 'Please check the purchase details and try again.'
            messages.error(request, message)
        else:
            log(request.user, 'create', purchase, f'Created purchase {purchase.purchase_no} ({purchase.status})', request)
            messages.success(request, message)
            return redirect('purchase_view', pk=purchase.pk)

    suppliers = Supplier.objects.filter(status=True)
    medicines = Medicine.objects.filter(status=True).select_related('category')
    return render(request, 'purchases/purchase_add.html', {
        'suppliers': suppliers,
        'medicines': medicines,
        'today': timezone.localdate(),
    })


@capability_required('manage_purchases')
def purchase_view(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier', 'purchased_by', 'received_by').prefetch_related('items__medicine'),
        pk=pk,
    )
    return render(request, 'purchases/purchase_view.html', {'purchase': purchase})


@capability_required('manage_purchases')
@require_POST
def purchase_mark_ordered(request, pk):
    purchase = get_object_or_404(Purchase, pk=pk)
    if purchase.status != 'draft':
        messages.error(request, 'Only draft purchases can be marked as ordered.')
    else:
        purchase.status = 'ordered'
        purchase.save(update_fields=['status'])
        log(request.user, 'update', purchase, f'Marked purchase {purchase.purchase_no} as ordered', request)
        messages.success(request, f'Purchase {purchase.purchase_no} marked as ordered.')
    return redirect('purchase_view', pk=purchase.pk)


@capability_required('manage_purchases')
@require_POST
def purchase_receive(request, pk):
    purchase = get_object_or_404(Purchase, pk=pk)
    try:
        receive_purchase(purchase, request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        log(request.user, 'update', purchase, f'Received purchase {purchase.purchase_no}', request)
        messages.success(request, f'Purchase {purchase.purchase_no} received. Stock and batches updated.')
    return redirect('purchase_view', pk=purchase.pk)


@capability_required('manage_purchases')
@require_POST
def purchase_cancel(request, pk):
    purchase = get_object_or_404(Purchase, pk=pk)
    if not purchase.is_receivable:
        messages.error(request, 'Only draft or ordered purchases can be cancelled.')
    else:
        purchase.status = 'cancelled'
        purchase.save(update_fields=['status'])
        log(request.user, 'update', purchase, f'Cancelled purchase {purchase.purchase_no}', request)
        messages.success(request, f'Purchase {purchase.purchase_no} cancelled.')
    return redirect('purchase_view', pk=purchase.pk)
