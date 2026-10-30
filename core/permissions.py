"""Role based access control helpers.

Roles mirror ``accounts.CustomUser.ROLE_CHOICES``. Superusers are always
allowed. ``role_required`` redirects with a message instead of raising a 403
so the UI stays friendly, while still denying the action server-side.
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

ADMIN = ('admin',)
CLINICAL = ('admin', 'pharmacist')
STOCK = ('admin', 'pharmacist', 'inventory_clerk')
SALES = ('admin', 'pharmacist', 'cashier')
REPORTS = ('admin', 'pharmacist')
ALL_STAFF = ('admin', 'pharmacist', 'cashier', 'inventory_clerk')

CAPABILITIES = {
    'manage_users': ADMIN,
    'view_audit': ADMIN,
    'manage_inventory': STOCK,
    'manage_purchases': STOCK,
    'manage_prescriptions': CLINICAL,
    'view_customers': ALL_STAFF,
    'manage_customers': SALES,
    'sell': SALES,
    'view_sales': SALES,
    'refund': CLINICAL,
    'void_sale': ADMIN,
    'view_reports': REPORTS,
    'export_reports': REPORTS,
    'use_assistant': ALL_STAFF,
}

CAPABILITY_LABELS = {
    'manage_users': 'manage users',
    'view_audit': 'view the audit log',
    'manage_inventory': 'manage inventory',
    'manage_purchases': 'manage purchases',
    'manage_prescriptions': 'manage prescriptions',
    'view_customers': 'view customers',
    'manage_customers': 'manage customers',
    'sell': 'use the point of sale',
    'view_sales': 'view sales',
    'refund': 'process returns',
    'void_sale': 'void sales',
    'view_reports': 'view reports',
    'export_reports': 'export reports',
    'use_assistant': 'use the assistant',
}


def has_capability(user, capability):
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'role', None) in CAPABILITIES.get(capability, ())


def capability_required(capability, redirect_to='dashboard'):
    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if not has_capability(request.user, capability):
                messages.error(request, f'You do not have permission to {CAPABILITY_LABELS.get(capability, "do that")}.')
                return redirect(redirect_to)
            return view(request, *args, **kwargs)

        return _wrapped

    return decorator


def role_required(*roles, redirect_to='dashboard'):
    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'role', None) in roles:
                return view(request, *args, **kwargs)
            messages.error(request, 'You do not have permission to access that page.')
            return redirect(redirect_to)

        return _wrapped

    return decorator


def nav_capabilities(user):
    return {name: has_capability(user, name) for name in CAPABILITIES}
