"""지역 현황 지도(8단계): DB에서 지자체·의회 기록을 읽어 네 조합(제품군 × 대상)의 지도 데이터를 만든다."""
from django.db.models import Max
from django.utils import timezone
from django.urls import reverse

from delivery.domain import admin_areas as aa
from delivery.domain.locations import guess_location
from delivery.domain.unit_labels import UNIT_LABEL
from delivery.domain.region_map import FAMILIES, compute_map
from delivery.models import Category, Contract, ContractProduct, Customer

TARGETS = (('local', Category.LOCAL, '지자체'), ('council', Category.COUNCIL, '지자체 의회'))
# 광역을 여러 칸으로 세는 시·도(형우 2026-10-21 16:10·16:13): 전남광주는 지자체·의회 모두 2칸(광주·무안 청사).
WIDE_SLOTS = {'local': {'12': 2}, 'council': {'12': 2}}
# 지도 위 광역 배지 자리(spec v4 1-A): korea-lite.json 시·도 외곽선의 가장 큰 덩어리에서 구한 '가장 안쪽 점'(polylabel, 지도 좌표).
# 경기는 서울·인천 구멍을 피해 잡힌다. 배지(기관 이름, 의회는 더 김)끼리 겹치지 않게 옮긴 곳(원래 → 지금):
# 서울 419,237.1 → 425,228 / 인천 363.8,259.5 → 318,272(서쪽 바다) / 세종 468,466.9 → 470,435 / 충남 387.6,468.2 → 365,478 / 대전 489.1,502.3 → 500,515
SIDO_LABEL = {
    '11': (425.0, 228.0), '26': (804.8, 749.7), '27': (707.4, 612.1), '28': (318.0, 272.0), '12': (393.9, 804.8),
    '30': (500.0, 515.0), '31': (820.4, 679.1), '36': (470.0, 435.0), '41': (496.2, 279.6), '51': (661.9, 213.6),
    '43': (560.2, 378.1), '44': (365.0, 478.0), '47': (757.5, 439.7), '48': (603.0, 719.1), '50': (328.0, 1161.8),
    '52': (449.4, 635.7),
}


def _records(category):
    customers = list(Customer.objects.filter(category=category, merged_into__isnull=True)
                     .select_related('organization'))
    ids = [c.pk for c in customers]
    lines = (ContractProduct.objects.filter(contract__customer_id__in=ids)
             .values_list('contract__customer_id', 'contract__is_active', 'contract__contract_date',
                          'product__marker', 'product__name', 'product__color'))
    contracts = {}
    for cid, active, cdate, marker, pname, color in lines:
        contracts.setdefault(cid, []).append({'active': active, 'date': cdate, 'marker': marker or '', 'product': pname,
                                              'color': color or ''})
    out = []
    for c in customers:
        kind = c.institution_type or (guess_location(str(c), c.category, c.region).institution_type if c.location_code else '')
        out.append({
            'id': str(c.pk), 'name': str(c), 'location': c.location_code, 'type': kind,
            'public': c.partner_public, 'listed': c.show_in_list,
            'logo': reverse('performance-logo', args=['customer', c.pk]) if c.logo else '',
            'contracts': contracts.get(c.pk, []),
        })
    return out


def basis_date():
    """실적 기준일: 지자체·의회 고객사 계약의 가장 최근 수정일(한국 시간 날짜).
    소재지·심볼처럼 지도 표시만 바꾸는 수정은 기준일을 움직이지 않는다(리뷰 7, 2026-10-21 형우 확정)."""
    cats = [Category.LOCAL, Category.COUNCIL]
    latest = Contract.objects.filter(customer__category__in=cats).aggregate(m=Max('updated_at'))['m']
    return timezone.localdate(latest) if latest else None


def _region_map_payload(show_unassigned=True):
    """화면에 넘길 데이터. 네 조합을 한 번에 만들어 전환할 때 서버를 다시 부르지 않게 한다."""
    combos = {}
    for tkey, category, _label in TARGETS:
        records = _records(category)
        for fkey, _flabel, _m in FAMILIES:
            m = compute_map(records, fkey, WIDE_SLOTS[tkey])
            combos[f'{fkey}:{tkey}'] = {
                'national': m['national'],
                'units': {code: slot for code, slot in m['units'].items() if slot['state'] == 'in' or slot['facilities']},
                'sido': m['sido'],
                # 미지정 기관 목록은 기획팀(관리자)에게만 보낸다(리뷰 9). 다른 직원에게는 페이지 소스에도 넣지 않는다
                'unassigned': m['unassigned'] if show_unassigned else [],
            }
    return {
        'version': aa.BOUNDARY_VERSION,
        'families': [{'key': k, 'label': l} for k, l, _m in FAMILIES],
        'targets': [{'key': k, 'label': l} for k, _c, l in TARGETS],
        'sido': [{'code': c, 'name': n, 'short': s, 'label': SIDO_LABEL.get(c)} for c, n, s in aa.SIDO],
        # lp: 시군구 이름 자리(확대했을 때 지도 위 이름, 11d)
        'units': {c: {'name': n, 'sido': s, 'whole': w, 'lp': UNIT_LABEL.get(c)} for c, n, s, w in aa.UNITS},
        'combos': combos,
    }


_PAYLOAD_CACHE = {}


def _data_signature():
    """고객사·계약·제품 줄이 바뀌면 달라지는 값(가벼운 질의 3개)."""
    from django.db.models import Count, Max
    from delivery.models import Organization
    return (tuple(Customer.objects.aggregate(Max('updated_at'), Count('id')).values()),
            tuple(Organization.objects.aggregate(Max('updated_at'), Count('id')).values()),
            tuple(Contract.objects.aggregate(Max('updated_at'), Count('id')).values()),
            tuple(ContractProduct.objects.aggregate(Max('updated_at'), Count('id')).values()))


def region_map_payload(show_unassigned=True):
    """지역 현황 데이터. 인터넷 서버에서는 자료가 그대로면 계산해 둔 것을 다시 쓴다(2026-10-22, 속도). PC·검사는 매번 계산."""
    import os
    if not os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
        return _region_map_payload(show_unassigned)
    key = (show_unassigned, _data_signature(), aa.BOUNDARY_VERSION)
    if key not in _PAYLOAD_CACHE:
        if len(_PAYLOAD_CACHE) > 8:
            _PAYLOAD_CACHE.clear()
        _PAYLOAD_CACHE[key] = _region_map_payload(show_unassigned)
    return _PAYLOAD_CACHE[key]
