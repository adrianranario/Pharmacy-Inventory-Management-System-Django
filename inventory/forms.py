from django import forms

from core.forms import StyledForm, StyledModelForm
from .models import Category, Medicine, Supplier


class MedicineForm(StyledModelForm):
    class Meta:
        model = Medicine
        fields = [
            'medicine_code', 'generic_name', 'brand_name', 'category', 'supplier',
            'dosage_form', 'strength', 'unit', 'purchase_price', 'selling_price',
            'reorder_level', 'shelf_location', 'barcode', 'description', 'status',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_barcode(self):
        return self.cleaned_data.get('barcode') or None


class CategoryForm(StyledModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']


class SupplierForm(StyledModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'contact_person', 'email', 'phone', 'address', 'lead_time_days', 'notes', 'status']


class StockAdjustmentForm(StyledForm):
    new_quantity = forms.IntegerField(min_value=0, label='New quantity')
    reason = forms.CharField(
        max_length=200,
        widget=forms.Textarea(attrs={'rows': 2}),
        help_text='Example: physical count, damaged units, supplier short delivery.',
    )


class WriteOffForm(StyledForm):
    quantity = forms.IntegerField(min_value=1, label='Quantity to write off')
    reason = forms.CharField(max_length=200, widget=forms.Textarea(attrs={'rows': 2}))
