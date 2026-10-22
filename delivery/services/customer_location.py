"""고객사 소재지·기관 유형 입력(4단계, 2026-10-22 형우 확정).

- 지방자치단체·의회에서만 입력칸을 보여준다. 다른 분류로 저장해도 기존 값은 그대로 둔다.
- 화면은 명칭·분류·지역으로 바로 제안받는다(추정은 domain.locations.guess_location 한 곳에서만).
- 소재지를 고르면 지역(권역)을 자동으로 맞춘다. 제주는 권역이 없어 지역을 직접 고른다.
- 소재지는 '시·도 + 시군구'로 고른다. 시군구를 비우면 '(시·도 전체)' — 도청·광역 의회용.
"""
from delivery.domain import admin_areas as aa
from delivery.domain.locations import REGION_SIDO, format_location, guess_location
from delivery.models import Category

LOCATION_CATEGORIES = frozenset({Category.LOCAL.value, Category.COUNCIL.value})
REGION_OF_SIDO = {sido: region for region, sidos in REGION_SIDO.items() for sido in sidos}


def _whole_unit(sido):
    """세종·제주처럼 시·도 전체가 한 면이면 그 면 코드."""
    for code in aa.units_in(sido):
        if aa.UNIT_BY_CODE[code][2]:
            return code
    return ''


def split_location(code):
    """저장된 코드 → (시·도, 시군구). 시·도 전체이거나 한 면짜리 시·도면 시군구는 ''."""
    if not code:
        return '', ''
    if code in aa.SIDO_BY_CODE:
        return code, ''
    _name, sido, whole = aa.UNIT_BY_CODE[code]
    return sido, '' if whole else code


def join_location(sido, unit):
    """(시·도, 시군구) → 저장할 코드. 시군구가 비면 시·도 전체(한 면짜리 시·도는 그 면)."""
    if not sido:
        return ''
    return unit or _whole_unit(sido) or sido


def unit_in_sido(unit, sido):
    return unit in aa.UNIT_BY_CODE and aa.UNIT_BY_CODE[unit][1] == sido


def sido_choices():
    return [('', '시·도 선택')] + [(code, short) for code, _name, short in aa.SIDO]


def unit_choices():
    groups = []
    for code, _name, short in aa.SIDO:
        units = [(unit, aa.UNIT_BY_CODE[unit][0]) for unit in aa.units_in(code) if not aa.UNIT_BY_CODE[unit][2]]
        if units:
            groups.append((short, units))
    return [('', '(시·도 전체)')] + groups


def location_data():
    """화면 스크립트용: 시·도별 시군구, 시·도 → 권역, 칸을 보일 분류."""
    units = {code: [[unit, aa.UNIT_BY_CODE[unit][0]] for unit in aa.units_in(code) if not aa.UNIT_BY_CODE[unit][2]]
             for code, _name, _short in aa.SIDO}
    return {'units': units, 'regionOfSido': REGION_OF_SIDO, 'categories': sorted(LOCATION_CATEGORIES)}


def suggestion(name, category, region=''):
    """화면 제안용. 지자체·의회가 아니거나 명칭이 비면 빈 제안."""
    name = (name or '').strip()
    if category not in LOCATION_CATEGORIES or not name:
        return {'location': '', 'sido': '', 'unit': '', 'label': '', 'institution_type': '', 'reason': '', 'region': ''}
    guess = guess_location(name, category, region or '')
    sido, unit = split_location(guess.location_code)
    return {'location': guess.location_code, 'sido': sido, 'unit': unit, 'label': format_location(guess.location_code),
            'institution_type': guess.institution_type, 'reason': guess.reason, 'region': REGION_OF_SIDO.get(sido, '')}
