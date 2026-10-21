"""고객사 이름·분류·권역으로 소재지(면 또는 시·도 코드)와 기관 유형을 추정한다.

지역 현황 지도(8단계)용. DB를 쓰지 않는 순수 함수다.
- 추정은 "제안"이다. 확신할 수 없으면 소재지를 비워 두고 이유를 돌려준다. 기획팀이 고른다.
- 저장된 값을 덮어쓰지 않는다. 비어 있을 때 채우는 데만 쓴다.
"""
import re
from dataclasses import dataclass

from . import admin_areas as aa

ADMIN = 'admin'
FACILITY = 'facility'

# 고객사 권역(Region) → 해당 시·도 코드 (지금 시스템의 5권역. 제주는 권역 대응표가 아직 [확인 필요])
REGION_SIDO = {
    'capital': {'11', '28', '41'},
    'chungcheong': {'30', '36', '43', '44'},
    'honam': {'12', '52'},
    'yeongnam': {'26', '27', '31', '47', '48'},
    'gangwon': {'51'},
}

# 시·도를 가리키는 이름(정식·예전·줄임) → 시·도 코드. 긴 이름부터 맞춘다.
SIDO_NAMES = {name: code for code, name, _short in aa.SIDO}
SIDO_NAMES.update({
    '광주광역시': '12', '전라남도': '12', '전라북도': '52', '강원도': '51',
    '세종시': '36', '서울시': '11', '부산시': '26', '대구시': '27', '인천시': '28',
    '대전시': '30', '울산시': '31', '제주도': '50',
})
_SIDO_ORDER = sorted(SIDO_NAMES, key=len, reverse=True)

# 행정기관으로 보는 이름 꼬리: (없음) / 청 / 의회 / 시청·군청·구청·도청 / (○○청사)
_ADMIN_TAIL = re.compile(r'^(청|의회|시청|군청|구청|도청|본청)?\s*(\(?[가-힣]*청사\)?)?$')
# 행정기관과 시설을 '·'로 묶은 기록(예: 포항시청·포항중앙상가, 종로구·마로니에공원)은 행정기관으로 본다
_ADMIN_COMBINED = re.compile(r'^(청|의회|시청|군청|구청)?·')

_UNITS_BY_NAME = {}
for _code, _name, _sido, _whole in aa.UNITS:
    _UNITS_BY_NAME.setdefault(_name, []).append(_code)


@dataclass(frozen=True)
class Guess:
    location_code: str     # 면 코드(5자리) / 시·도 코드(2자리) / '' (모름)
    institution_type: str  # ADMIN / FACILITY
    reason: str            # 사람이 읽을 근거


def _sido_location(sido):
    """세종·제주는 시·도 전체가 한 면이라 광역 기관도 면 코드로 둔다."""
    if sido in ('36', '50'):
        return aa.units_in(sido)[0]
    return sido


def _match_unit(text, sidos):
    """text 맨 앞에서 면 이름을 찾는다. 반환: (후보 코드들, 남은 꼬리)."""
    best = None
    for name, codes in _UNITS_BY_NAME.items():
        if text.startswith(name):
            cand = [c for c in codes if sidos is None or aa.UNIT_BY_CODE[c][1] in sidos]
            if cand and (best is None or len(name) > len(best[0])):
                best = (name, cand)
    if not best:
        return [], text
    return best[1], text[len(best[0]):]


def _admin_tail(tail):
    return bool(_ADMIN_TAIL.match(tail.strip()))


def guess_location(name, category, region):
    """name: 고객사 명칭, category: 'local'/'council'/…, region: 'capital' 등 권역 코드."""
    text = re.sub(r'\s+', ' ', (name or '').strip())
    text = text.replace('특례시', '시')  # 수원·고양·용인·창원 특례시
    region_sidos = REGION_SIDO.get(region)

    # 1) 시·도 이름으로 시작하는 경우
    for sname in _SIDO_ORDER:
        if not text.startswith(sname):
            continue
        sido = SIDO_NAMES[sname]
        rest = text[len(sname):].strip()
        if _admin_tail(rest):
            return Guess(_sido_location(sido), ADMIN, f'시·도 기관: {sname}')
        codes, tail = _match_unit(rest, {sido})
        if len(codes) == 1:
            kind = ADMIN if _admin_tail(tail) else FACILITY
            return Guess(codes[0], kind, f'{sname} 안의 {aa.UNIT_BY_CODE[codes[0]][0]}')
        if sido == '28' and rest.split(' ')[0].rstrip('청의회') in ('중구', '동구', '서구'):
            old = rest.split(' ')[0].rstrip('청의회')
            new = ', '.join(aa.UNIT_BY_CODE[c][0] for c in aa.INCHEON_REORG[old])
            return Guess('', ADMIN if _admin_tail(rest[len(old):]) else FACILITY,
                         f'인천 개편(2026-07): 예전 {old} → {new} 중 선택 필요')
        return Guess(_sido_location(sido), FACILITY, f'{sname} 소속 시설·공기업(시·도 단위)')

    # 1-1) 제주 행정시(제주시·서귀포시)는 기초자치단체가 아니다. 상위기관은 제주특별자치도이고,
    #      제주 면은 도 기관으로만 칠하므로 시설·공기업으로 둔다(리뷰 40)
    for city in ('제주시', '서귀포시'):
        if text.startswith(city):
            return Guess('50000', FACILITY, f'제주 행정시({city}) 소속: 상위기관 제주특별자치도')

    # 2) 면 이름으로 시작하는 경우 (권역으로 같은 이름 구분)
    codes, tail = _match_unit(text, region_sidos)
    if not codes and region_sidos is not None:
        any_codes, any_tail = _match_unit(text, None)
        # 제주는 권역 대응표가 아직 없다([확인 필요]). 제주에만 있는 이름이면 권역과 상관없이 받아들인다
        if len(any_codes) == 1 and aa.UNIT_BY_CODE[any_codes[0]][1] == '50':
            codes, tail = any_codes, any_tail
    if not codes and region_sidos is not None:
        any_codes, _ = _match_unit(text, None)
        if any_codes:
            names = ', '.join(sorted(f'{aa.SIDO_BY_CODE[aa.UNIT_BY_CODE[c][1]][1]} {aa.UNIT_BY_CODE[c][0]}' for c in any_codes))
            return Guess('', ADMIN if _admin_tail(tail) else FACILITY, f'권역과 맞는 후보 없음(후보: {names})')
    if len(codes) == 1:
        combined = bool(_ADMIN_COMBINED.match(tail))
        if _admin_tail(tail) or combined:
            return Guess(codes[0], ADMIN, f'면 이름: {aa.UNIT_BY_CODE[codes[0]][0]}' + (' (·로 묶인 기록)' if combined else ''))
        return Guess(codes[0], FACILITY, f'{aa.UNIT_BY_CODE[codes[0]][0]} 소속 시설')
    if len(codes) > 1:
        names = ', '.join(sorted(f'{aa.SIDO_BY_CODE[aa.UNIT_BY_CODE[c][1]][1]} {aa.UNIT_BY_CODE[c][0]}' for c in codes))
        return Guess('', ADMIN if _admin_tail(tail) else FACILITY, f'후보 여러 곳: {names}')

    # 3) 이름으로 위치를 알 수 없음 → 시설로 보고 비워 둔다
    return Guess('', FACILITY, '이름에서 위치를 찾지 못함')


def format_location(code):
    """코드 → 사람이 읽는 이름. 예: '44130' → '충남 천안시', '41' → '경기'. 빈 값은 ''."""
    if not code:
        return ''
    if code in aa.SIDO_BY_CODE:
        return aa.SIDO_BY_CODE[code][1]
    if code in aa.UNIT_BY_CODE:
        name, sido, whole = aa.UNIT_BY_CODE[code]
        return aa.SIDO_BY_CODE[sido][1] if whole else f'{aa.SIDO_BY_CODE[sido][1]} {name}'
    raise ValueError(f'모르는 소재지 코드: {code}')


def parse_location(text):
    """사람이 적은 소재지 → 코드. 코드(2·5자리) 또는 '약칭 이름'(예: '충남 천안시', '인천 영종구', '서울')을 받는다.
    빈 값은 ''. 알 수 없으면 ValueError."""
    t = re.sub(r'\s+', ' ', (text or '').strip())
    if not t:
        return ''
    if t in aa.SIDO_BY_CODE or t in aa.UNIT_BY_CODE:
        return t
    short_to_sido = {short: code for code, _n, short in aa.SIDO}
    short_to_sido.update(SIDO_NAMES)
    parts = t.split(' ', 1)
    sido = short_to_sido.get(parts[0])
    if sido is None:
        raise ValueError(f'시·도를 알 수 없음: {text}')
    if len(parts) == 1:
        return _sido_location(sido)
    for code in aa.units_in(sido):
        if aa.UNIT_BY_CODE[code][0] == parts[1]:
            return code
    raise ValueError(f'{parts[0]} 안에 없는 이름: {parts[1]}')
