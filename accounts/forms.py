from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

from core.forms import StyledForm, StyledModelForm
from .models import CustomUser


class UserCreateForm(StyledModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput, help_text='At least 8 characters.')
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'phone', 'license_no']

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Passwords do not match.')
        if password1:
            try:
                password_validation.validate_password(password1, self.instance)
            except ValidationError as exc:
                self.add_error('password1', exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.status = True
        if commit:
            user.save()
        return user


class UserUpdateForm(StyledModelForm):
    new_password = forms.CharField(
        label='New password',
        required=False,
        widget=forms.PasswordInput,
        help_text='Leave blank to keep the current password.',
    )

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'role', 'phone', 'license_no', 'status']

    def clean_new_password(self):
        password = self.cleaned_data.get('new_password')
        if password:
            try:
                password_validation.validate_password(password, self.instance)
            except ValidationError as exc:
                raise forms.ValidationError(exc.messages)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('new_password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class OTPVerifyForm(StyledForm):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        label='Authentication code',
        widget=forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'one-time-code', 'autofocus': True}),
    )


class OTPEnableForm(StyledForm):
    code = forms.CharField(max_length=6, min_length=6, label='Code from your authenticator app')


class OTPDisableForm(StyledForm):
    password = forms.CharField(widget=forms.PasswordInput, label='Current password')
    code = forms.CharField(max_length=6, min_length=6, label='Current authenticator code')
