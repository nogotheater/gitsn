"""섹션 안 나열 순서(화면·인쇄 공통). 2026-10-22 형우:
- 중앙정부: 정부조직법 기준(domain.central_order)
- 민간: 재계순위(domain.private_order)
- 지자체·의회: 광역 → 광역 소속 시설·공기업 → 기초 가나다, 시·도 차례(domain.local_order)
- 나머지: 가나다
"""
from delivery.domain.central_order import name_order_key
from delivery.domain.local_order import local_sort_key
from delivery.domain.locations import guess_location
from delivery.models import Customer

LOCAL = frozenset({'local', 'council'})


def item_order_key(items):
    """items(현재 목록 행)에 맞는 정렬 키 함수를 돌려준다. 지자체·의회는 저장된 소재지(없으면 명칭 추정)를 쓴다."""
    ids = [item['id'] for item in items if item['kind'] == 'customer' and item['category'] in LOCAL]
    saved = {str(pk): (code, kind) for pk, code, kind in
             Customer.objects.filter(pk__in=ids).values_list('id', 'location_code', 'institution_type')} if ids else {}

    def key(item):
        if item['category'] not in LOCAL:
            return name_order_key(item['category'], item['name'])
        code, kind = saved.get(item['id'], ('', ''))
        if not code:
            guess = guess_location(item['name'], item['category'], item['region'])
            code, kind = guess.location_code, kind or guess.institution_type
        return local_sort_key(item['name'], code, kind)
    return key
