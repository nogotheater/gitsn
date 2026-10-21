"""Interactive local manager setup. Never stores or prints a plain password."""
from pathlib import Path
import getpass
import os
import sys
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from delivery.models import Product, UserAccessProfile


def main():
    if not settings.DEBUG:
        raise SystemExit('이 도구는 로컬 개발 환경에서만 사용합니다.')
    probe = settings.MEDIA_ROOT / ('.planning-check-' + uuid4().hex)
    try:
        settings.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b'local-write-check')
        if probe.read_bytes() != b'local-write-check':
            raise OSError('Media readback failed.')
    except OSError:
        raise SystemExit('심볼 저장 폴더를 사용할 수 없습니다. 폴더 권한을 확인한 뒤 다시 실행해 주세요.') from None
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
    User = get_user_model()
    username = input('기획팀 로그인 아이디: ').strip()
    user = User(username=username)
    if not username or User.objects.filter(username=username).exists():
        raise SystemExit('아이디가 비어 있거나 이미 등록되어 있습니다. 기존 계정은 변경하지 않았습니다.')
    try:
        user.full_clean(exclude=['password'])
    except ValidationError as error:
        raise SystemExit(' '.join(error.messages)) from None
    while True:
        password = getpass.getpass('비밀번호 입력(화면에 표시되지 않음): ')
        confirm = getpass.getpass('비밀번호 다시 입력: ')
        if password != confirm:
            print('비밀번호가 일치하지 않습니다. 다시 입력해 주세요.')
            continue
        try:
            validate_password(password, user=user)
        except ValidationError as error:
            print(' '.join(error.messages))
            continue
        break
    with transaction.atomic():
        user.set_password(password)
        user.save()
        UserAccessProfile.objects.create(user=user, audience='employee')
        user.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))
        for code, marker in [('Alpha-C', 'C'), ('Alpha-I', 'I')]:
            Product.objects.get_or_create(code=code, defaults={'name': code, 'marker': marker})
    print('기획팀 계정을 만들었습니다. 입력한 아이디와 비밀번호로 로그인해 주세요.')
    print('확정된 Alpha-C/C, Alpha-I/I 제품을 준비했습니다. 고객사·계약 자료는 만들지 않았습니다.')


if __name__ == '__main__':
    main()
