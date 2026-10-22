"""지자체·지자체 의회 나열 순서(2026-10-22 형우 확정). 권역 섹션 안에서:

시·도 차례(행정표준코드 순: 서울 → 인천 → 경기 …)로 묶고, 각 시·도 안에서
  ① 광역자치단체(의회) 자신 → ② 그 시·도 소속 시설·공기업(시·도 단위) → ③ 기초자치단체(시·군·구)와 그 소속, 가나다.
소재지를 모르면 섹션 맨 끝(가나다). DB를 쓰지 않는다.
"""
from . import admin_areas as aa

SIDO_RANK = {code: index for index, (code, _name, _short) in enumerate(aa.SIDO)}
ADMIN, FACILITY = 'admin', 'facility'


def local_sort_key(name, location_code, institution_type):
    """(시·도 차례, 층(0 광역 / 1 광역 소속 시설·공기업 / 2 기초), 이름)."""
    normal = ' '.join((name or '').split()).casefold()
    code = location_code or ''
    sido = aa.sido_of(code) if code else None
    if not sido:
        return (len(SIDO_RANK) + 1, 9, normal)
    unit = aa.UNIT_BY_CODE.get(code)
    sido_level = code == sido or bool(unit and unit[2])   # 세종·제주처럼 시·도 전체가 한 면이면 면 코드도 시·도 단위
    if sido_level:
        tier = 1 if institution_type == FACILITY else 0
    else:
        tier = 2
    return (SIDO_RANK.get(sido, len(SIDO_RANK)), tier, normal)
