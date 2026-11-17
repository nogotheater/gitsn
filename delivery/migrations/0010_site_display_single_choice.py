from django.db import migrations
from django.db.models import Q


def unify(apps, schema_editor):
    """2026-11-17 형우: 설치 장소의 '실적 목록에 표시'·'총 고객사 수에 포함'을 선택 하나로 합쳤다.
    둘이 다르게 저장된 장소(카드 없이 숫자만 / 카드만)는 '별도 고객사로 표시'(둘 다 켬)로 맞춘다.
    2026-11-17 인터넷 서버에는 1곳(영천시 환경사업소: 숫자에만 포함)이었다 — 숫자에 넣으려던 뜻이라 카드도 보이게 한다."""
    SitePresentation = apps.get_model('delivery', 'SitePresentation')
    SitePresentation.objects.filter(Q(show_in_list=True, include_in_total=False) | Q(show_in_list=False, include_in_total=True)).update(
        show_in_list=True, include_in_total=True)


class Migration(migrations.Migration):
    dependencies = [('delivery', '0009_logo_fit')]
    operations = [migrations.RunPython(unify, migrations.RunPython.noop)]
