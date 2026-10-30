from django.contrib.auth.signals import user_logged_out, user_login_failed
from django.dispatch import receiver

from core.audit import log


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user is not None:
        log(user, 'logout', description='Signed out', request=request)


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request, **kwargs):
    username = (credentials or {}).get('username', 'unknown')
    log(None, 'login_failed', description=f'Failed sign-in for {username}', request=request)
