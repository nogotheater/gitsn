"""Access comes from the authenticated Django user, never request parameters."""
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from delivery.models import UserAccessProfile


def audience_for_user(user):
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False):
        raise PermissionDenied('Login required.')
    try:
        audience = user.delivery_access.audience
    except (ObjectDoesNotExist, AttributeError):
        raise PermissionDenied('Access profile required.') from None
    if audience not in UserAccessProfile.Audience.values:
        raise PermissionDenied('Invalid access profile.')
    return audience


def require_employee(user):
    if audience_for_user(user) != UserAccessProfile.Audience.EMPLOYEE:
        raise PermissionDenied('Employee access required.')


def require_manager(user):
    require_employee(user)
    if not user.has_perm('delivery.manage_delivery'):
        raise PermissionDenied('Planning-team access required.')
