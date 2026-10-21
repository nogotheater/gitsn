"""지역 현황 지도(8단계): DB에서 지자체·의회 기록을 읽어 네 조합(제품군 × 대상)의 지도 데이터를 만든다."""
from django.db.models import Max
from django.utils import timezone
from django.urls import reverse

from delivery.domain import admin_areas as aa
from delivery.domain.locations import guess_location
from delivery.domain.region_map import FAMILIES, compute_map
from delivery.models import Category, Contract, ContractProduct, Customer

TARGETS = (('local', Category.LOCAL, '지자체'), ('council', Category.COUNCIL, '지자체 의회'))


def _records(category):
    customers = list(Customer.objects.filter(category=category, merged_into__isnull=True)
                     .select_related('organization'))
    ids = [c.pk for c in customers]
    lines = (ContractProduct.objects.filter(contract__customer_id__in=ids)
             .values_list('contract__customer_id', 'contract__is_active', 'contract__contract_date',
                          'product__marker', 'product__name'))
    contracts = {}
    for cid, active, cdate, marker, pname in lines:
        contracts.setdefault(cid, []).append({'active': active, 'date': cdate, 'marker': marker or '', 'product': pname})
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


def region_map_payload(show_unassigned=True):
    """화면에 넘길 데이터. 네 조합을 한 번에 만들어 전환할 때 서버를 다시 부르지 않게 한다."""
    combos = {}
    for tkey, category, _label in TARGETS:
        records = _records(category)
        for fkey, _flabel, _m in FAMILIES:
            m = compute_map(records, fkey)
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
        'sido': [{'code': c, 'name': n, 'short': s} for c, n, s in aa.SIDO],
        'units': {c: {'name': n, 'sido': s, 'whole': w} for c, n, s, w in aa.UNITS},
        'combos': combos,
    }
