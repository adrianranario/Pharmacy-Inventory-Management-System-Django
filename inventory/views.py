from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.audit import log
from core.permissions import capability_required
from core.utils import filter_date_range, parse_date_param, paginate
from .forms import CategoryForm, MedicineForm, StockAdjustmentForm, SupplierForm, WriteOffForm
from .models import Batch, Category, Medicine, StockMovement, Supplier
from .services import adjust_batch, expire_batches, write_off_batch


@capability_required('manage_inventory')
def medicine_list(request):
    medicines = Medicine.objects.select_related('category', 'supplier').prefetch_related('batches').order_by('generic_name')
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    state = request.GET.get('state', '')

    if query:
        medicines = medicines.filter(
            Q(generic_name__icontains=query)
            | Q(brand_name__icontains=query)
            | Q(medicine_code__icontains=query)
            | Q(barcode__icontains=query)
        )
    if category:
        medicines = medicines.filter(category_id=category)
    if state == 'low':
        medicines = [m for m in medicines if m.is_low_stock()]
    elif state == 'inactive':
        medicines = medicines.filter(status=False)
    elif state == 'active':
        medicines = medicines.filter(status=True)

    page_obj = paginate(request, medicines, 25) if not isinstance(medicines, list) else None
    if page_obj is None:
        from django.core.paginator import Paginator

        page_obj = Paginator(medicines, 25).get_page(request.GET.get('page'))
    return render(request, 'inventory/medicine_list.html', {
        'page_obj': page_obj,
        'medicines': page_obj.object_list,
        'categories': Category.objects.all(),
        'query': query,
        'selected_category': category,
        'selected_state': state,
    })


@capability_required('manage_inventory')
def medicine_add(request):
    form = MedicineForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        medicine = form.save()
        log(request.user, 'create', medicine, f'Created medicine {medicine.medicine_code}', request)
        messages.success(request, 'Medicine added successfully.')
        return redirect('medicine_list')
    return render(request, 'inventory/medicine_add.html', {'form': form})


@capability_required('manage_inventory')
def medicine_edit(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)
    form = MedicineForm(request.POST or None, instance=medicine)
    if request.method == 'POST' and form.is_valid():
        medicine = form.save()
        log(request.user, 'update', medicine, f'Updated medicine {medicine.medicine_code}', request)
        messages.success(request, 'Medicine updated successfully.')
        return redirect('medicine_list')
    return render(request, 'inventory/medicine_edit.html', {'form': form, 'medicine': medicine})


@capability_required('manage_inventory')
def category_list(request):
    categories = Category.objects.all().order_by('name')
    return render(request, 'inventory/category_list.html', {'categories': categories})


@capability_required('manage_inventory')
def category_add(request):
    form = CategoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        category = form.save()
        log(request.user, 'create', category, f'Created category {category.name}', request)
        messages.success(request, 'Category added successfully.')
        return redirect('category_list')
    return render(request, 'inventory/category_add.html', {'form': form})


@capability_required('manage_inventory')
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == 'POST' and form.is_valid():
        category = form.save()
        log(request.user, 'update', category, f'Updated category {category.name}', request)
        messages.success(request, 'Category updated successfully.')
        return redirect('category_list')
    return render(request, 'inventory/category_add.html', {'form': form, 'category': category})


@capability_required('manage_inventory')
def supplier_list(request):
    suppliers = Supplier.objects.all()
    query = request.GET.get('q', '').strip()
    if query:
        suppliers = suppliers.filter(
            Q(name__icontains=query) | Q(contact_person__icontains=query) | Q(email__icontains=query)
        )
    page_obj = paginate(request, suppliers, 25)
    return render(request, 'inventory/supplier_list.html', {'page_obj': page_obj, 'suppliers': page_obj.object_list, 'query': query})


@capability_required('manage_inventory')
def supplier_add(request):
    form = SupplierForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        supplier = form.save()
        log(request.user, 'create', supplier, f'Created supplier {supplier.name}', request)
        messages.success(request, 'Supplier added successfully.')
        return redirect('supplier_list')
    return render(request, 'inventory/supplier_add.html', {'form': form})


@capability_required('manage_inventory')
def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    form = SupplierForm(request.POST or None, instance=supplier)
    if request.method == 'POST' and form.is_valid():
        supplier = form.save()
        log(request.user, 'update', supplier, f'Updated supplier {supplier.name}', request)
        messages.success(request, 'Supplier updated successfully.')
        return redirect('supplier_list')
    return render(request, 'inventory/supplier_add.html', {'form': form, 'supplier': supplier})


@capability_required('manage_inventory')
def inventory_list(request):
    batches = (
        Batch.objects.select_related('medicine', 'medicine__category')
        .filter(remaining_quantity__gt=0)
        .order_by('expiry_date')
    )
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    state = request.GET.get('state', '')
    today = timezone.localdate()

    if query:
        batches = batches.filter(
            Q(medicine__generic_name__icontains=query)
            | Q(medicine__brand_name__icontains=query)
            | Q(medicine__medicine_code__icontains=query)
            | Q(batch_no__icontains=query)
        )
    if category:
        batches = batches.filter(medicine__category_id=category)
    if state == 'expired':
        batches = batches.filter(expiry_date__lt=today)
    elif state == 'near':
        batches = batches.filter(
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=getattr(settings, 'EXPIRY_WARNING_DAYS', 90)),
        )
    elif state == 'good':
        batches = batches.filter(expiry_date__gt=today + timedelta(days=getattr(settings, 'EXPIRY_WARNING_DAYS', 90)))

    page_obj = paginate(request, batches, 30)
    return render(request, 'inventory/stock_list.html', {
        'page_obj': page_obj,
        'batches': page_obj.object_list,
        'categories': Category.objects.all(),
        'query': query,
        'selected_category': category,
        'selected_state': state,
    })


@capability_required('manage_inventory')
def alerts(request):
    today = timezone.localdate()
    warning_days = getattr(settings, 'EXPIRY_WARNING_DAYS', 90)
    low_stock = [m for m in Medicine.objects.filter(status=True).prefetch_related('batches') if m.is_low_stock()]
    near_expiry = (
        Batch.objects.filter(
            remaining_quantity__gt=0,
            expiry_date__lte=today + timedelta(days=warning_days),
            expiry_date__gte=today,
        )
        .select_related('medicine')
        .order_by('expiry_date')
    )
    expired = Batch.objects.filter(remaining_quantity__gt=0, expiry_date__lt=today).select_related('medicine').order_by('expiry_date')
    tiers = {
        'd30': near_expiry.filter(expiry_date__lte=today + timedelta(days=30)).count(),
        'd60': near_expiry.filter(expiry_date__lte=today + timedelta(days=60)).count(),
        'd90': near_expiry.count(),
    }
    return render(request, 'inventory/alerts.html', {
        'low_stock': low_stock,
        'near_expiry': near_expiry,
        'expired': expired,
        'tiers': tiers,
        'warning_days': warning_days,
    })


@capability_required('manage_inventory')
def write_off_expired(request):
    if request.method != 'POST':
        return redirect('alerts')
    expired = expire_batches(user=request.user)
    log(request.user, 'stock', description=f'Wrote off {len(expired)} expired batch(es)', request=request)
    messages.success(request, f'Wrote off {len(expired)} expired batch(es).')
    return redirect('alerts')


@capability_required('manage_inventory')
def adjust_stock(request, pk):
    batch = get_object_or_404(Batch.objects.select_related('medicine'), pk=pk)
    form = StockAdjustmentForm(request.POST or None, initial={'new_quantity': batch.remaining_quantity})
    if request.method == 'POST' and form.is_valid():
        try:
            adjust_batch(
                batch,
                form.cleaned_data['new_quantity'],
                form.cleaned_data['reason'],
                request.user,
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            log(request.user, 'stock', batch, f'Adjusted batch {batch.batch_no} to {batch.remaining_quantity}', request)
            messages.success(request, 'Stock adjusted and recorded in the ledger.')
            return redirect('inventory_list')
    return render(request, 'inventory/adjust_stock.html', {'batch': batch, 'form': form})


@capability_required('manage_inventory')
def write_off_batch_view(request, pk):
    batch = get_object_or_404(Batch.objects.select_related('medicine'), pk=pk)
    form = WriteOffForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            write_off_batch(
                batch,
                form.cleaned_data['quantity'],
                form.cleaned_data['reason'],
                request.user,
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            log(request.user, 'stock', batch, f'Wrote off {form.cleaned_data["quantity"]} from {batch.batch_no}', request)
            messages.success(request, 'Write-off recorded.')
            return redirect('inventory_list')
    return render(request, 'inventory/write_off.html', {'batch': batch, 'form': form})


@capability_required('manage_inventory')
def stock_movements(request):
    movements = StockMovement.objects.select_related('medicine', 'batch', 'user')
    query = request.GET.get('q', '').strip()
    movement_type = request.GET.get('type', '')
    date_from = parse_date_param(request.GET.get('from'))
    date_to = parse_date_param(request.GET.get('to'))
    if query:
        movements = movements.filter(
            Q(medicine__generic_name__icontains=query)
            | Q(reference__icontains=query)
            | Q(batch__batch_no__icontains=query)
        )
    if movement_type:
        movements = movements.filter(movement_type=movement_type)
    movements = filter_date_range(movements, 'created_at__date', date_from, date_to)
    page_obj = paginate(request, movements, 40)
    return render(request, 'inventory/movements.html', {
        'page_obj': page_obj,
        'movements': page_obj.object_list,
        'types': StockMovement.TYPE_CHOICES,
        'query': query,
        'selected_type': movement_type,
        'date_from': request.GET.get('from', ''),
        'date_to': request.GET.get('to', ''),
    })
