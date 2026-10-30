from django import forms
from django.utils import timezone

from core.forms import StyledModelForm
from .models import Customer, Prescription


class CustomerForm(StyledModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email', 'address', 'customer_type', 'id_no', 'notes', 'status']
        widgets = {'address': forms.Textarea(attrs={'rows': 2}), 'notes': forms.Textarea(attrs={'rows': 2})}


class PrescriptionForm(StyledModelForm):
    class Meta:
        model = Prescription
        fields = ['customer', 'medicine', 'rx_no', 'prescriber', 'issued_date', 'expiry_date', 'refills_remaining', 'directions', 'notes', 'status']
        widgets = {
            'issued_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def clean_issued_date(self):
        issued = self.cleaned_data.get('issued_date')
        if issued and issued > timezone.localdate():
            raise forms.ValidationError('The issue date cannot be in the future.')
        return issued
