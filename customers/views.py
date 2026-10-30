from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.audit import log
from core.permissions import capability_required, has_capability
from core.utils import paginate
from .forms import CustomerForm, PrescriptionForm
from .models import Customer, Prescription


@capability_required('view_customers')
def customer_list(request):
    customers = Customer.objects.all()
    query = request.GET.get('q', '').strip()
    if query:
        customers = customers.filter(
            Q(name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query) | Q(id_no__icontains=query)
        )
    page_obj = paginate(request, customers, 25)
    return render(request, 'customers/customer_list.html', {'page_obj': page_obj, 'customers': page_obj.object_list, 'query': query})


@capability_required('manage_customers')
def customer_add(request):
    form = CustomerForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        customer = form.save()
        log(request.user, 'create', customer, f'Created customer {customer.name}', request)
        messages.success(request, 'Customer added.')
        return redirect('customer_detail', pk=customer.pk)
    return render(request, 'customers/customer_form.html', {'form': form, 'title': 'Add customer'})


@capability_required('manage_customers')
def customer_edit(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    form = CustomerForm(request.POST or None, instance=customer)
    if request.method == 'POST' and form.is_valid():
        customer = form.save()
        log(request.user, 'update', customer, f'Updated customer {customer.name}', request)
        messages.success(request, 'Customer updated.')
        return redirect('customer_detail', pk=customer.pk)
    return render(request, 'customers/customer_form.html', {'form': form, 'customer': customer, 'title': 'Edit customer'})


@capability_required('view_customers')
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    sales = customer.sales.select_related('sold_by').order_by('-created_at')[:10]
    prescriptions = (
        customer.prescriptions.select_related('medicine').order_by('-created_at')
        if has_capability(request.user, 'manage_prescriptions')
        else Prescription.objects.none()
    )
    return render(request, 'customers/customer_detail.html', {
        'customer': customer,
        'sales': sales,
        'prescriptions': prescriptions,
    })


@capability_required('view_customers')
def customer_search(request):
    query = request.GET.get('q', '').strip()
    customers = Customer.objects.filter(status=True)
    if query:
        customers = customers.filter(Q(name__icontains=query) | Q(phone__icontains=query))
    data = [
        {
            'id': c.pk,
            'name': c.name,
            'phone': c.phone,
            'type': c.customer_type,
            'type_label': c.get_customer_type_display(),
            'id_no': c.id_no,
        }
        for c in customers[:10]
    ]
    return JsonResponse(data, safe=False)


@capability_required('manage_prescriptions')
def prescription_list(request):
    prescriptions = Prescription.objects.select_related('customer', 'medicine')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    if query:
        prescriptions = prescriptions.filter(
            Q(rx_no__icontains=query) | Q(customer__name__icontains=query) | Q(prescriber__icontains=query)
        )
    if status:
        prescriptions = prescriptions.filter(status=status)
    page_obj = paginate(request, prescriptions, 25)
    return render(request, 'customers/prescription_list.html', {
        'page_obj': page_obj,
        'prescriptions': page_obj.object_list,
        'query': query,
        'selected_status': status,
        'statuses': Prescription.STATUS_CHOICES,
    })


@capability_required('manage_prescriptions')
def prescription_add(request):
    initial = {}
    customer_id = request.GET.get('customer')
    if customer_id:
        initial['customer'] = customer_id
    form = PrescriptionForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        prescription = form.save(commit=False)
        prescription.created_by = request.user
        prescription.save()
        log(request.user, 'create', prescription, f'Created prescription {prescription.rx_no}', request)
        messages.success(request, 'Prescription recorded.')
        return redirect('customer_detail', pk=prescription.customer_id)
    return render(request, 'customers/prescription_form.html', {'form': form, 'title': 'Record prescription'})


@capability_required('manage_prescriptions')
def prescription_edit(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)
    form = PrescriptionForm(request.POST or None, instance=prescription)
    if request.method == 'POST' and form.is_valid():
        prescription = form.save()
        log(request.user, 'update', prescription, f'Updated prescription {prescription.rx_no}', request)
        messages.success(request, 'Prescription updated.')
        return redirect('customer_detail', pk=prescription.customer_id)
    return render(request, 'customers/prescription_form.html', {'form': form, 'prescription': prescription, 'title': 'Edit prescription'})
