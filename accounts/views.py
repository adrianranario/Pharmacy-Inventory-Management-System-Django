import pyotp
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.audit import log
from core.permissions import capability_required
from core.utils import paginate
from .forms import OTPDisableForm, OTPEnableForm, OTPVerifyForm, UserCreateForm, UserUpdateForm
from .models import CustomUser


class OTPLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        user = form.get_user()
        if not user.status:
            form.add_error(None, 'This account has been disabled. Contact an administrator.')
            return self.form_invalid(form)
        if user.otp_enabled:
            self.request.session['pre_otp_user_id'] = user.pk
            self.request.session['pre_otp_next'] = self.get_redirect_url() or settings.LOGIN_REDIRECT_URL
            messages.info(self.request, 'Enter the 6-digit code from your authenticator app.')
            return redirect('otp_verify')
        auth_login(self.request, user)
        log(user, 'login', description='Signed in', request=self.request)
        return redirect(self.get_success_url())


def otp_verify(request):
    user_id = request.session.get('pre_otp_user_id')
    if not user_id:
        messages.info(request, 'Sign in with your username and password first.')
        return redirect('login')

    user = get_object_or_404(CustomUser, pk=user_id)
    form = OTPVerifyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        totp = pyotp.TOTP(user.otp_secret)
        if totp.verify(form.cleaned_data['code'], valid_window=getattr(settings, 'OTP_VALID_WINDOW', 1)):
            backend = 'django.contrib.auth.backends.ModelBackend'
            auth_login(request, user, backend=backend)
            next_url = request.session.pop('pre_otp_next', None) or settings.LOGIN_REDIRECT_URL
            request.session.pop('pre_otp_user_id', None)
            log(user, 'login', description='Signed in with 2FA', request=request)
            messages.success(request, f'Welcome back, {user.get_full_name() or user.username}.')
            return redirect(next_url)
        form.add_error('code', 'That code is invalid or has expired. Try the next one.')

    return render(request, 'registration/otp_verify.html', {'form': form, 'username': user.username})


@login_required
def security_settings(request):
    user = request.user
    if not user.otp_secret:
        user.otp_secret = pyotp.random_base32()
        user.save(update_fields=['otp_secret'])

    provisioning_uri = pyotp.TOTP(user.otp_secret).provisioning_uri(
        name=user.email or user.username,
        issuer_name=getattr(settings, 'OTP_ISSUER', 'Pharmacy IMS'),
    )
    enable_form = OTPEnableForm()
    disable_form = OTPDisableForm()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'enable':
            enable_form = OTPEnableForm(request.POST)
            if enable_form.is_valid():
                totp = pyotp.TOTP(user.otp_secret)
                if totp.verify(enable_form.cleaned_data['code'], valid_window=1):
                    user.otp_enabled = True
                    user.save(update_fields=['otp_enabled'])
                    log(user, 'security', user, 'Enabled two-factor authentication', request)
                    messages.success(request, 'Two-factor authentication is now enabled.')
                    return redirect('security_settings')
                enable_form.add_error('code', 'Invalid code. Make sure your device time is correct.')
        elif action == 'disable':
            disable_form = OTPDisableForm(request.POST)
            if disable_form.is_valid():
                if not user.check_password(disable_form.cleaned_data['password']):
                    disable_form.add_error('password', 'Incorrect password.')
                else:
                    totp = pyotp.TOTP(user.otp_secret)
                    if not totp.verify(disable_form.cleaned_data['code'], valid_window=1):
                        disable_form.add_error('code', 'Invalid authentication code.')
                    else:
                        user.otp_enabled = False
                        user.save(update_fields=['otp_enabled'])
                        log(user, 'security', user, 'Disabled two-factor authentication', request)
                        messages.success(request, 'Two-factor authentication disabled.')
                        return redirect('security_settings')

    return render(request, 'registration/security.html', {
        'enable_form': enable_form,
        'disable_form': disable_form,
        'provisioning_uri': provisioning_uri,
        'secret': user.otp_secret,
    })


@login_required
def password_change(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        log(user, 'security', user, 'Changed password', request)
        messages.success(request, 'Password updated.')
        return redirect('security_settings')
    return render(request, 'registration/password_change_form.html', {'form': form})


@capability_required('manage_users')
def user_list(request):
    users = CustomUser.objects.all().order_by('username')
    query = request.GET.get('q', '').strip()
    role = request.GET.get('role', '')
    if query:
        users = users.filter(
            Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
        )
    if role:
        users = users.filter(role=role)
    page_obj = paginate(request, users, 25)
    return render(request, 'accounts/user_list.html', {
        'page_obj': page_obj,
        'users': page_obj.object_list,
        'roles': CustomUser.ROLE_CHOICES,
        'query': query,
        'selected_role': role,
    })


@capability_required('manage_users')
def user_add(request):
    form = UserCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        log(request.user, 'create', user, f'Created user {user.username} ({user.role})', request)
        messages.success(request, 'User added successfully.')
        return redirect('user_list')
    return render(request, 'accounts/user_add.html', {'form': form})


@capability_required('manage_users')
def user_edit(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    form = UserUpdateForm(request.POST or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        updated = form.save()
        log(request.user, 'update', updated, f'Updated user {updated.username} ({updated.role})', request)
        messages.success(request, 'User updated successfully.')
        return redirect('user_list')
    return render(request, 'accounts/user_edit.html', {'form': form, 'edit_user': user})


@capability_required('manage_users')
def user_delete(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if user == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('user_list')
    if request.method == 'POST':
        if user.is_superuser and CustomUser.objects.filter(is_superuser=True).count() <= 1:
            messages.error(request, 'The last administrator cannot be deleted.')
            return redirect('user_list')
        username = user.username
        try:
            user.delete()
        except ProtectedError:
            messages.error(
                request,
                f'{username} has sales, purchases, or other records and cannot be deleted. '
                'Deactivate the account instead.',
            )
            return redirect('user_list')
        log(request.user, 'delete', description=f'Deleted user {username}', request=request)
        messages.success(request, 'User deleted successfully.')
        return redirect('user_list')
    return render(request, 'accounts/user_delete.html', {'object': user})


@capability_required('view_audit')
def audit_log(request):
    from core.models import AuditLog

    logs = AuditLog.objects.select_related('user')
    query = request.GET.get('q', '').strip()
    action = request.GET.get('action', '')
    if query:
        logs = logs.filter(Q(description__icontains=query) | Q(model_name__icontains=query) | Q(user__username__icontains=query))
    if action:
        logs = logs.filter(action=action)
    page_obj = paginate(request, logs, 50)
    return render(request, 'accounts/audit_log.html', {
        'page_obj': page_obj,
        'logs': page_obj.object_list,
        'actions': AuditLog.ACTION_CHOICES,
        'query': query,
        'selected_action': action,
    })
