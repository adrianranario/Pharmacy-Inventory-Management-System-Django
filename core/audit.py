from .models import AuditLog


def log(user, action, obj=None, description='', request=None):
    """Record an auditable action without ever breaking the request."""
    try:
        ip = None
        if request is not None:
            ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
        AuditLog.objects.create(
            user=user if getattr(user, 'is_authenticated', False) else None,
            action=action,
            model_name=obj.__class__.__name__ if obj is not None else '',
            object_id=str(getattr(obj, 'pk', '') or ''),
            description=description[:2000],
            ip_address=ip,
        )
    except Exception:
        # Auditing must never take down a business flow.
        pass
