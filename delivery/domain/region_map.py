"""지역 현황 지도(8단계)의 판정 규칙. DB를 쓰지 않는다.

제품군 묶음은 spec v3 확정 규칙을 따른다.
- 도청 보안: Alpha-I(I) · Alpha-S(S) · Alpha-B(B) · Smart-D(D) · Alpha-P(P)
- 불법촬영 보안: Alpha-C(C)
- 묶음 밖 제품(Alpha-H 등)만 있는 기관은 두 제품군 모두 미도입이다.
"""
from . import admin_areas as aa

EAVESDROP = 'eavesdrop'
CAMERA = 'camera'
FAMILIES = (
    (EAVESDROP, '도청 보안', ('I', 'S', 'B', 'D', 'P')),
    (CAMERA, '불법촬영 보안', ('C',)),
)
FAMILY_LABEL = {key: label for key, label, _m in FAMILIES}
MARKER_ORDER = ('I', 'S', 'B', 'D', 'P', 'C')


def family_of_marker(marker):
    """제품 표시 기호 → 제품군 키. 묶음 밖이면 None."""
    for key, _label, markers in FAMILIES:
        if marker in markers:
            return key
    return None


# ---------------------------------------------------------------------------
# 지도 계산(5단계). 입력은 DB와 무관한 기록 목록이다.
# record = {
#   'id', 'name', 'location' (면 5자리 / 시·도 2자리 / ''), 'type' ('admin'/'facility'/''),
#   'public' (파트너 공개), 'listed' (목록 표시), 'logo' (URL 또는 ''),
#   'contracts': [{'active': bool, 'date': date|None, 'marker': 'S', 'product': 'Alpha-S'}, ...],
# }
# ---------------------------------------------------------------------------
ADMIN = 'admin'
FACILITY = 'facility'


def _family_summary(record, family):
    """기관 하나의 한 제품군 요약. 유효 계약이 없으면 None."""
    lines = [c for c in record['contracts'] if c['active'] and family_of_marker(c['marker']) == family]
    if not lines:
        return None
    dates = [c['date'] for c in lines]
    # 날짜 없는 유효 계약이 하나라도 있으면 그 계약이 더 오래됐을 수 있으므로 연도를 확정하지 않는다
    year = '—' if any(d is None for d in dates) else str(min(dates).year)
    order = {m: i for i, m in enumerate(MARKER_ORDER)}
    products = sorted({(order.get(c['marker'], 99), c['product']) for c in lines})
    name = record['name']
    return {'id': record['id'], 'name': name, 'initial': name[:1], 'logo': record.get('logo') or '',
            'products': ', '.join(p for _o, p in products), 'year': year}


def compute_map(records, family):
    """한 조합(제품군 × 대상)의 지도 데이터. records는 이미 대상(지자체/의회)으로 거른 목록이다."""
    units = {code: {'state': 'out', 'orgs': [], 'facilities': []} for code, *_ in aa.UNITS}
    wide = {code: {'orgs': [], 'facilities': []} for code, *_ in aa.SIDO}
    unassigned = []
    for r in records:
        if not r['public'] or not r['listed']:
            continue  # 결정 A: 비공개 기관은 지도 계산에서 뺀다. 목록에 표시하지 않는 기관도 뺀다
        summary = _family_summary(r, family)
        if summary is None:
            continue
        loc, kind = r['location'], r['type'] or ADMIN
        if loc in aa.UNIT_BY_CODE:
            slot = units[loc]
            if kind == ADMIN:
                slot['state'] = 'in'
                slot['orgs'].append(summary)
            else:
                slot['facilities'].append(summary)
        elif loc in aa.SIDO_BY_CODE:
            wide[loc]['orgs' if kind == ADMIN else 'facilities'].append(summary)
        else:
            unassigned.append(summary)
    sido_rows = []
    for code, name, short in aa.SIDO:
        codes = aa.units_in(code)
        whole = aa.UNIT_BY_CODE[codes[0]][2] if len(codes) == 1 else False
        adopted = [c for c in codes if units[c]['state'] == 'in']
        # 세종·제주: 광역 기관이 곧 그 한 면이다. 도입한 곳 목록에만 두고 광역 줄에는 다시 넣지 않는다(리뷰 24)
        wide_orgs = list(wide[code]['orgs'])
        sido_rows.append({
            'code': code, 'name': name, 'short': short, 'whole': whole,
            'adopted': len(adopted), 'total': len(codes),
            'wide_orgs': sorted(wide_orgs, key=lambda o: o['name']),
            'wide_facilities': sorted(wide[code]['facilities'], key=lambda o: o['name']),
            'missing': [c for c in codes if units[c]['state'] == 'out'],
            'adopted_units': adopted,
        })
    for slot in units.values():
        slot['orgs'].sort(key=lambda o: o['name'])
        slot['facilities'].sort(key=lambda o: o['name'])
    total_in = sum(s['adopted'] for s in sido_rows)
    return {
        'family': family, 'units': units, 'sido': sido_rows,
        'national': {'adopted': total_in, 'total': len(aa.UNITS)},
        'unassigned': sorted(unassigned, key=lambda o: o['name']),
    }
