from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

from .models import TeamAdminAccount


class TeamAdminPasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.path.startswith('/admin/'):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), login_url=reverse('staff_login'))
            if not request.user.is_staff:
                raise PermissionDenied

        if not request.user.is_authenticated or request.path.startswith('/static/'):
            return None

        account = TeamAdminAccount.objects.filter(
            user=request.user,
            user__is_superuser=False,
            must_change_password=True,
        ).only('pk').first()
        if account is None:
            return None

        if request.resolver_match and request.resolver_match.url_name in {
            'team_admin_password_change',
            'logout',
        }:
            return None

        return redirect('team_admin_password_change')
