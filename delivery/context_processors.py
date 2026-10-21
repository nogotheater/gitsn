from django.core.exceptions import PermissionDenied
from .services.access import audience_for_user, require_manager


def navigation(request):
    audience, manager = '', False
    try:
        audience = audience_for_user(request.user)
        require_manager(request.user)
        manager = True
    except PermissionDenied:
        pass
    return {'ui_audience': audience, 'ui_is_manager': manager}
