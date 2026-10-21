"""Explicit local account administration; passwords are never returned or logged."""
import hashlib
import json
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from .access import require_manager
from delivery.models import UserAccessProfile


def account_role(user):
    try:
        audience = user.delivery_access.audience
    except UserAccessProfile.DoesNotExist:
        return 'unset'
    if audience == 'employee' and user.has_perm('delivery.manage_delivery'):
        return 'manager'
    return audience


def account_revision(user):
    profile = UserAccessProfile.objects.filter(user=user).values_list('audience', 'updated_at').first()
    state = [user.username, user.first_name, user.is_active, user.password,
             [str(value) for value in profile] if profile else None,
             sorted(user.user_permissions.values_list('pk', flat=True)), user.is_staff, user.is_superuser,
             sorted(user.groups.values_list('pk', flat=True))]
    return hashlib.sha256(json.dumps(state, ensure_ascii=True).encode()).hexdigest()


def _editable(user):
    if user.is_staff or user.is_superuser or user.groups.exists():
        raise ValidationError('별도로 운영하는 관리 계정은 이 화면에서 변경할 수 없습니다.')


def _lock_accounts(actor):
    # A common ordered lock serializes concurrent manager changes, including
    # revocations. Re-read the actor to avoid cached permissions after a wait.
    User = get_user_model()
    users = {user.pk: user for user in User.objects.select_for_update().order_by('pk')}
    fresh_actor = users.get(actor.pk)
    if fresh_actor is None:
        require_manager(actor)
        raise ValidationError('현재 계정을 다시 확인해 주세요.')
    require_manager(fresh_actor)
    return users


def _role(user, role):
    if role not in {'employee', 'partner', 'manager'}:
        raise ValidationError({'role': '이용 권한을 선택해 주세요.'})
    UserAccessProfile.objects.update_or_create(user=user, defaults={'audience': 'partner' if role == 'partner' else 'employee'})
    permission = Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery')
    if role == 'manager':
        user.user_permissions.add(permission)
    else:
        user.user_permissions.remove(permission)


@transaction.atomic
def create_account(actor, data):
    require_manager(actor)
    _lock_accounts(actor)
    User = get_user_model()
    username = data['username'].strip()
    if User.objects.filter(username__iexact=username).exists():
        raise ValidationError({'username': '이미 사용 중인 아이디입니다.'})
    user = User(username=username, first_name=data.get('first_name', ''), is_active=True)
    user.full_clean(exclude=['password'])
    validate_password(data['password1'], user)
    if data['password1'] != data['password2']:
        raise ValidationError({'password2': '비밀번호가 일치하지 않습니다.'})
    user.set_password(data['password1'])
    user.save()
    _role(user, data['role'])
    return user


@transaction.atomic
def update_account(actor, user_id, data):
    require_manager(actor)
    users = _lock_accounts(actor)
    user = users.get(user_id)
    if user is None:
        raise ValidationError('계정이 존재하지 않습니다.')
    _editable(user)
    if data.get('revision') != account_revision(user):
        raise ValidationError('다른 작업에서 계정이 수정됐습니다. 새로 열어 다시 확인해 주세요.')
    if actor.pk == user.pk and (data['role'] != 'manager' or not data['is_active']):
        raise ValidationError('현재 사용 중인 본인 계정의 관리 권한이나 접속 허용은 해제할 수 없습니다.')
    user.first_name = data.get('first_name', '')
    user.is_active = data['is_active']
    user.save(update_fields=['first_name', 'is_active'])
    _role(user, data['role'])
    return user


@transaction.atomic
def reset_account_password(actor, user_id, data):
    require_manager(actor)
    user = _lock_accounts(actor).get(user_id)
    if user is None:
        raise ValidationError('계정이 존재하지 않습니다.')
    _editable(user)
    if data.get('revision') != account_revision(user):
        raise ValidationError('다른 작업에서 계정이 수정됐습니다. 새로 열어 다시 확인해 주세요.')
    if data['new_password1'] != data['new_password2']:
        raise ValidationError({'new_password2': '비밀번호가 일치하지 않습니다.'})
    validate_password(data['new_password1'], user)
    user.set_password(data['new_password1'])
    user.save(update_fields=['password'])
    return user
