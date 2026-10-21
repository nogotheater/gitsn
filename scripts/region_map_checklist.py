"""지역 현황 지도 실제 데이터 점검표(8단계 10단계). 읽기만 한다.
사용: python scripts/region_map_checklist.py [시·도 코드 ...]  (기본: 44 41 28)"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django  # noqa: E402
django.setup()

from delivery.services.region_map import basis_date, region_map_payload  # noqa: E402

codes = sys.argv[1:] or ['44', '41', '28']
p = region_map_payload()
names = {c: u['name'] for c, u in p['units'].items()}
fam = {f['key']: f['label'] for f in p['families']}
tgt = {t['key']: t['label'] for t in p['targets']}
print(f'지역 현황 지도 점검표 · {basis_date():%Y.%m.%d} 기준')
for key, combo in p['combos'].items():
    print(f"  전국 {fam[key.split(':')[0]]} × {tgt[key.split(':')[1]]}: 도입 {combo['national']['adopted']} / {combo['national']['total']}"
          f", 지도에 올리지 못한 기관 {len(combo['unassigned'])}")
for code in codes:
    for key, combo in p['combos'].items():
        s = [x for x in combo['sido'] if x['code'] == code][0]
        f, t = key.split(':')
        print(f"\n■ {s['name']} · {fam[f]} × {tgt[t]} — 도입 {s['adopted']} / {s['total']}")
        wide = ', '.join(o['name'] for o in s['wide_orgs']) or '미도입'
        print(f"  광역: {wide}")
        if s['wide_facilities']:
            print('  광역 시설·공기업: ' + ', '.join(o['name'] for o in s['wide_facilities']))
        for u in s['adopted_units']:
            for o in combo['units'][u]['orgs']:
                print(f"  도입  {names[u]:<6} {o['name']} · {o['products']} · {o['year']}")
        for u, slot in combo['units'].items():
            if p['units'][u]['sido'] == code and slot['facilities']:
                print(f"  시설  {names[u]:<6} " + ', '.join(o['name'] for o in slot['facilities']))
        print('  빠진 곳: ' + (', '.join(names[u] for u in s['missing']) or '없음'))
