"""Tiny factories shared by the test suite."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from accounts.models import CustomUser
from inventory.models import Batch, Category, Medicine, Supplier


def make_user(username='staff', role='admin', password='Test-pass-123', **extra):
    user = CustomUser(username=username, role=role, status=True, **extra)
    user.set_password(password)
    user.save()
    return user


def make_medicine(code='MED-001', name='Paracetamol', price='100.00', cost='60.00', reorder_level=5, supplier=None):
    category, _ = Category.objects.get_or_create(name='General')
    supplier = supplier or Supplier.objects.create(name=f'Supplier {code}', lead_time_days=7)
    return Medicine.objects.create(
        medicine_code=code,
        generic_name=name,
        category=category,
        supplier=supplier,
        unit='tablet',
        purchase_price=Decimal(cost),
        selling_price=Decimal(price),
        reorder_level=reorder_level,
    )


def make_batch(medicine, quantity=10, days=365, price='60.00', batch_no=None):
    today = timezone.localdate()
    return Batch.objects.create(
        medicine=medicine,
        batch_no=batch_no or f'B-{medicine.pk}-{quantity}',
        quantity=quantity,
        remaining_quantity=quantity,
        purchase_price=Decimal(price),
        expiry_date=today + timedelta(days=days),
        received_date=today,
    )
