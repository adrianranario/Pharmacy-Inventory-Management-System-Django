from django import forms

from core.forms import StyledForm


class VoidSaleForm(StyledForm):
    reason = forms.CharField(max_length=300, widget=forms.Textarea(attrs={'rows': 2}), label='Reason for voiding')


class ReturnForm(StyledForm):
    reason = forms.CharField(max_length=200, label='Return reason')
    notes = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={'rows': 2}), label='Notes')
