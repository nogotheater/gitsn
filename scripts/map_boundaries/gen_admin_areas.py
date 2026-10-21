"""units.json → delivery/domain/admin_areas.py (생성 파일. 직접 고치지 않는다)"""
import json, sys
u = json.load(open(sys.argv[1], encoding='utf8'))
L = ['"""행정구역 목록 — 지역 현황 지도의 면(기초자치단체)과 시·도.',
     '',
     '생성 파일이다. 직접 고치지 말고 scripts/build_map_boundaries.py로 다시 만든다.',
     '출처: 통계청 SGIS → vuski/admdongkor ver20260701 (2026-07-01 시행, CC BY 4.0).',
     '규칙: 일반구는 소속 시로 합친다. 세종·제주는 시·도 전체를 한 면으로 둔다.',
     '면 229 = 기초자치단체 227 + 세종 1 + 제주 1. 시·도 16.',
     '"""',
     'BOUNDARY_VERSION = "admdongkor-ver20260701"',
     '',
     '# (코드, 정식 이름, 약칭) — 행정코드 순',
     'SIDO = (']
for s in u['sido']:
    L.append(f'    ({s["code"]!r}, {s["name"]!r}, {s["short"]!r}),')
L += [')', '', '# (면 코드, 이름, 시·도 코드, 시·도 전체가 한 면인지) — 코드 순', 'UNITS = (']
for x in u['units']:
    L.append(f'    ({x["code"]!r}, {x["name"]!r}, {x["sido"]!r}, {x["whole_sido"]!r}),')
L += [')', '', '# 일반구 행정 코드 → 소속 시의 면 코드', 'GENERAL_DISTRICTS = {']
for k, v in sorted(u['general_districts'].items()):
    L.append(f'    {k!r}: {v["unit"]!r},  # {v["gu_name"]}')
L += ['}', '',
      '# 예전 시·도 이름 → 현재 시·도 코드 (2026-07-01 전남광주 통합, 특별자치도 개칭 반영)',
      'OLD_SIDO_NAMES = {',
      "    '광주광역시': '12', '전라남도': '12', '전라북도': '52', '강원도': '51',",
      '}', '',
      '# 2026-07-01 인천 개편: 예전 구 이름 → 현재 면 코드 후보 (둘 이상이면 사람이 고른다)',
      'INCHEON_REORG = {',
      "    '중구': ('28155', '28125'),  # 영종구(영종·용유) / 제물포구(내륙)",
      "    '동구': ('28125',),          # 제물포구",
      "    '서구': ('28275', '28290'),  # 서해구 / 검단구",
      '}', '',
      'SIDO_BY_CODE = {code: (name, short) for code, name, short in SIDO}',
      'UNIT_BY_CODE = {code: (name, sido, whole) for code, name, sido, whole in UNITS}',
      '', '',
      'def is_sido_code(code):',
      '    return code in SIDO_BY_CODE',
      '', '',
      'def is_unit_code(code):',
      '    return code in UNIT_BY_CODE',
      '', '',
      'def sido_of(code):',
      '    """면 코드나 시·도 코드 → 시·도 코드. 모르는 코드는 None."""',
      '    if code in SIDO_BY_CODE:',
      '        return code',
      '    unit = UNIT_BY_CODE.get(code)',
      '    return unit[1] if unit else None',
      '', '',
      'def units_in(sido_code):',
      '    return [code for code, _name, sido, _whole in UNITS if sido == sido_code]',
      '']
open(sys.argv[2], 'w', encoding='utf8').write('\n'.join(L))
print('written', sys.argv[2])
