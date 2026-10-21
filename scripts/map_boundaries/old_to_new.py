"""9월 짝짓기 목록(white-tiles-data.json, 2026-07 개편 이전 이름) → ver20260701 면 코드 대응표"""
import json, sys, collections
units = json.load(open(sys.argv[1], encoding='utf8'))['units']
tiles = json.load(open(sys.argv[2], encoding='utf8'))
OLD_SIDO = {'서울특별시':'11','부산광역시':'26','대구광역시':'27','인천광역시':'28','광주광역시':'12','대전광역시':'30',
            '울산광역시':'31','세종특별자치시':'36','경기도':'41','충청북도':'43','충청남도':'44','전라남도':'12',
            '전북특별자치도':'52','전라북도':'52','경상북도':'47','경상남도':'48','강원특별자치도':'51','강원도':'51','제주특별자치도':'50'}
# 2026-07-01 인천 개편: 중구 → 영종구(영종·용유) + 제물포구(내륙), 동구 → 제물포구, 서구 → 서해구 + 검단구
# 9월 타일맵의 이름 오류: 광주광역시에는 중구가 없다. 위치상 동구 칸이 '중구'로 적혀 있었다.
FIX = {('12','중구'): '동구'}
SPLIT = {('28','중구'): ['영종구','제물포구'], ('28','동구'): ['제물포구'], ('28','서구'): ['서해구','검단구']}
by = collections.defaultdict(list)
for u in units: by[(u['sido'], u['name'])].append(u['code'])
rows, used = [], collections.Counter()
for t in tiles:
    prov = t.get('province') or ''
    full = t.get('fullName') or t['name']
    s = OLD_SIDO.get(prov)
    name = full[len(prov):].strip() if full.startswith(prov) else t['name']
    if (s, name) in FIX:
        new = by[(s, FIX[(s, name)])]; kind = 'sept_name_error'
    elif s in ('36', '50'):
        new = [u['code'] for u in units if u['sido'] == s]; kind = 'whole_sido'
    elif (s, name) in SPLIT:
        new = [c for n in SPLIT[(s, name)] for c in by[(s, n)]]; kind = 'incheon_reorg'
    else:
        new = by.get((s, name), []); kind = 'same' if len(new) == 1 else 'NOT_FOUND'
    for c in new: used[c] += 1
    rows.append({'tile_id': t['id'], 'old_sido': prov, 'old_name': name, 'new_codes': new, 'kind': kind})
cnt = collections.Counter(r['kind'] for r in rows)
print('tiles', len(rows), dict(cnt))
print('not found', [(r['old_sido'], r['old_name']) for r in rows if r['kind'] == 'NOT_FOUND'])
print('incheon', [(r['old_name'], r['new_codes']) for r in rows if r['kind'] == 'incheon_reorg'])
missing = [ (u['code'], u['sido_short'], u['name']) for u in units if used[u['code']] == 0]
print('units with no 9월 tile', missing)
json.dump(rows, open(sys.argv[3], 'w', encoding='utf8'), ensure_ascii=False, indent=1)
