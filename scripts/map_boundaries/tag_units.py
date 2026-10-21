"""1a: 행정동 경계에 '면(기초자치단체)' 코드를 붙인다.
규칙: 일반구(예: 수원시장안구)는 소속 시로 합친다. 세종(36)·제주(50)는 시·도 전체를 한 면으로 둔다."""
import json, re, sys, collections
SRC, OUT, UNITS = sys.argv[1:4]
SIDO_SHORT = {'11':'서울','12':'전남광주','26':'부산','27':'대구','28':'인천','30':'대전','31':'울산','36':'세종',
              '41':'경기','43':'충북','44':'충남','47':'경북','48':'경남','50':'제주','51':'강원','52':'전북'}
WHOLE = {'36': ('36110', '세종특별자치시'), '50': ('50000', '제주특별자치도')}
GEN = re.compile(r'^(.+?시)(.+구)$')
d = json.load(open(SRC, encoding='utf8'))
units = {}
gen_map = {}
for f in d['features']:
    p = f['properties']
    s, c, n = p['sido'], p['sgg'], p['sggnm']
    if s in WHOLE:
        code, name = WHOLE[s]
    else:
        m = GEN.match(n)
        if m:
            code, name = c[:4] + '0', m.group(1)
            gen_map[c] = {'gu_name': n, 'unit': code}
        else:
            code, name = c, n
    u = units.setdefault(code, {'code': code, 'name': name, 'sido': s, 'sido_name': p['sidonm'],
                                'sido_short': SIDO_SHORT[s], 'whole_sido': s in WHOLE, 'source_sgg': set()})
    assert u['name'] == name and u['sido'] == s, (code, name, u)
    u['source_sgg'].add(c)
    f['properties'] = {'unit': code, 'sido': s}
json.dump(d, open(OUT, 'w', encoding='utf8'), ensure_ascii=False)
rows = sorted(units.values(), key=lambda u: u['code'])
for u in rows: u['source_sgg'] = sorted(u['source_sgg'])
json.dump({'units': rows, 'general_districts': gen_map,
           'sido': [{'code': k, 'name': next(u['sido_name'] for u in rows if u['sido']==k), 'short': v}
                    for k, v in sorted(SIDO_SHORT.items())]},
          open(UNITS, 'w', encoding='utf8'), ensure_ascii=False, indent=1)
c = collections.Counter(u['sido'] for u in rows)
print('units', len(rows), 'sido', len(c), 'general districts merged', len(gen_map))
print(sorted(c.items()))
