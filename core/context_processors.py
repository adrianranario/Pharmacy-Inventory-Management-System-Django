from django.conf import settings

from inventory.models import Batch, Medicine
from .permissions import nav_capabilities


def pharmacy(request):
    today = None
    low_stock_count = near_expiry_count = expired_count = 0
    if getattr(request, 'user', None) is not None and request.user.is_authenticated:
        from django.utils import timezone
        from datetime import timedelta

        today = timezone.localdate()
        low_stock_count = sum(1 for m in Medicine.objects.filter(status=True).prefetch_related('batches') if m.is_low_stock())
        near_expiry_count = Batch.objects.filter(
            remaining_quantity__gt=0,
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=getattr(settings, 'EXPIRY_WARNING_DAYS', 90)),
        ).count()
        expired_count = Batch.objects.filter(remaining_quantity__gt=0, expiry_date__lt=today).count()

    return {
        'pharmacy': {
            'name': getattr(settings, 'PHARMACY_NAME', 'Pharmacy IMS'),
            'address': getattr(settings, 'PHARMACY_ADDRESS', ''),
            'tin': getattr(settings, 'PHARMACY_TIN', ''),
            'vat_rate': getattr(settings, 'VAT_RATE', 12),
        },
        'nav_perms': nav_capabilities(request.user) if getattr(request, 'user', None) and request.user.is_authenticated else {},
        'alert_counts': {
            'low_stock': low_stock_count,
            'near_expiry': near_expiry_count,
            'expired': expired_count,
            'total': low_stock_count + near_expiry_count + expired_count,
        },
    }
