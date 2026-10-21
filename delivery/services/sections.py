"""납품현황 목록·인쇄의 섹션 구성.

C2(2026-10-21 형우 확정): 지방자치단체·지방자치단체 의회는 권역별 섹션으로 나눈다.
- 제목: '지방자치단체(수도권)' 형식. 권역은 고객사에 이미 입력된 '지역' 값(5권역)을 쓴다.
- 순서: 분류 순서 안에서 수도권 → 충청권 → 호남권 → 영남권 → 강원권(Region 선택지 순서와 같다).
- 제목 숫자: 고객사 수(분류 숫자와 같은 센 법). 권역 숫자를 더하면 분류 숫자가 된다.
- 지역이 비어 있으면 권역 없이 분류 이름 섹션으로 맨 뒤에 둔다.
분류 탭·요약 칸·필터는 분류 단위 그대로다.
"""
from delivery.models import Category, Region

SPLIT_CATEGORIES = frozenset({Category.LOCAL.value, Category.COUNCIL.value})
REGION_ORDER = tuple(Region.values)
_CATEGORY_RANK = {code: index for index, code in enumerate(Category.values)}
_REGION_RANK = {code: index for index, code in enumerate(REGION_ORDER)}


def section_of(category, region):
    """(분류, 권역) 쌍. 나누지 않는 분류이거나 모르는 권역이면 권역은 ''."""
    if category in SPLIT_CATEGORIES and region in _REGION_RANK:
        return (category, region)
    return (category, '')


def section_rank(category, region):
    category, region = section_of(category, region)
    return (_CATEGORY_RANK.get(category, len(_CATEGORY_RANK)), _REGION_RANK.get(region, len(_REGION_RANK)))


def section_label(category, region):
    label = Category(category).label
    return f'{label}({Region(region).label})' if region else label


def _region_counts(per_pair):
    out = {}
    for key, count in (per_pair or {}).items():
        category, _, region = key.partition(':')
        section = section_of(category, region)
        out[section] = out.get(section, 0) + count
    return out


def sections(counts):
    """화면 순서대로 모든 섹션. 숫자가 0인 권역 섹션도 넣는다(보여줄지는 화면이 정한다)."""
    by_pair = _region_counts(counts.get('by_category_region'))
    private_by_pair = _region_counts(counts.get('private_by_category_region'))
    out = []
    for code, _label in Category.choices:
        if code in SPLIT_CATEGORIES:
            pairs = [(code, region) for region in REGION_ORDER] + [(code, '')]
            numbers = [(by_pair.get(pair, 0), private_by_pair.get(pair, 0)) for pair in pairs]
        else:
            pairs = [(code, '')]
            numbers = [(counts.get('by_category', {}).get(code, 0), counts.get('private_by_category', {}).get(code, 0))]
        for (category, region), (count, private_count) in zip(pairs, numbers):
            out.append({'code': category, 'region': region, 'key': f'{category}-{region}' if region else category,
                        'label': section_label(category, region), 'count': count, 'private_count': private_count})
    return out
