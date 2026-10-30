from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


class ActiveUserMiddleware:
    """End sessions for accounts that an administrator has deactivated."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and (not user.status or not user.is_active):
            logout(request)
            messages.error(request, 'This account has been disabled. Contact an administrator.')
            return redirect('login')
        return self.get_response(request)
