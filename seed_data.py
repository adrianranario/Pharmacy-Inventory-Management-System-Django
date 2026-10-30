import os
import django
import random
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmacy_project.settings')
django.setup()

from accounts.models import CustomUser
from inventory.models import Category, Supplier, Medicine, Batch
from purchases.models import Purchase, PurchaseItem
from pos.models import Sale, SaleItem
from django.contrib.auth.hashers import make_password
from django.utils import timezone

# Clear existing
Batch.objects.all().delete()
PurchaseItem.objects.all().delete()
Purchase.objects.all().delete()
SaleItem.objects.all().delete()
Sale.objects.all().delete()
Medicine.objects.all().delete()
Supplier.objects.all().delete()
Category.objects.all().delete()

# Categories
cats = ['Analgesics', 'Antibiotics', 'Antihistamines', 'Vitamins & Supplements', 'Cough & Cold', 'Gastrointestinal', 'Antipyretics', 'Antiseptics']
for c in cats:
    Category.objects.create(name=c)

# Suppliers
suppliers = [
    Supplier.objects.create(name='MediSource Pharma', contact_person='Juan Cruz', phone='09171234567', email='medisource@gmail.com', address='Manila'),
    Supplier.objects.create(name='HealthPlus Distributors', contact_person='Maria Santos', phone='09182345678', email='healthplus@gmail.com', address='Cebu City'),
    Supplier.objects.create(name='PharmaDirect Inc.', contact_person='Pedro Reyes', phone='09193456789', email='pharmadirect@gmail.com', address='Davao City'),
]
cat_map = {c.name: c for c in Category.objects.all()}

medicines_data = [
    ('MED-001', 'Paracetamol', 'Biogesic', 'Analgesics', 'Tablet', '500mg', 25.00, 35.00),
    ('MED-002', 'Ibuprofen', 'Advil', 'Analgesics', 'Tablet', '400mg', 28.00, 45.00),
    ('MED-003', 'Amoxicillin', 'Amoxil', 'Antibiotics', 'Capsule', '500mg', 15.00, 28.00),
    ('MED-004', 'Cetirizine', 'Zyrtec', 'Antihistamines', 'Tablet', '10mg', 12.00, 22.00),
    ('MED-005', 'Ascorbic Acid', 'Ceelin', 'Vitamins & Supplements', 'Tablet', '500mg', 8.00, 15.00),
    ('MED-006', 'Ambroxol', 'Mucosolvan', 'Cough & Cold', 'Tablet', '30mg', 16.00, 28.00),
    ('MED-007', 'Omeprazole', 'Losec', 'Gastrointestinal', 'Capsule', '20mg', 35.00, 55.00),
    ('MED-008', 'Metformin', 'Glucophage', 'Vitamins & Supplements', 'Tablet', '500mg', 10.00, 18.00),
    ('MED-009', 'Cefalexin', 'Keflex', 'Antibiotics', 'Capsule', '500mg', 20.00, 35.00),
    ('MED-010', 'Loratadine', 'Claritin', 'Antihistamines', 'Tablet', '10mg', 14.00, 25.00),
    ('MED-011', 'Dextromethorphan', 'Robitussin', 'Cough & Cold', 'Syrup', '60ml', 55.00, 85.00),
    ('MED-012', 'Mefenamic Acid', 'Dolfenal', 'Analgesics', 'Capsule', '500mg', 18.00, 32.00),
]

meds = []
for code, gen, brand, cat, form, strength, buy, sell in medicines_data:
    m = Medicine.objects.create(
        medicine_code=code, generic_name=gen, brand_name=brand,
        category=cat_map[cat], dosage_form=form, strength=strength,
        unit='pcs' if form in ['Tablet', 'Capsule'] else 'bottle',
        purchase_price=buy, selling_price=sell, reorder_level=20,
        shelf_location=f'Aisle {random.randint(1,5)}', barcode=f'BAR{code}'
    )
    meds.append(m)

# Add batches
admin = CustomUser.objects.filter(role='admin').first()
for m in meds:
    for i in range(2):
        qty = random.randint(30, 100)
        Batch.objects.create(
            medicine=m, batch_no=f'B{m.medicine_code}-{i+1}2025',
            quantity=qty, remaining_quantity=qty,
            purchase_price=m.purchase_price,
            expiry_date=date.today() + timedelta(days=random.randint(60, 365)),
            received_date=date.today() - timedelta(days=random.randint(10, 60))
        )

print('Seeded categories, suppliers, medicines, batches')
