"""투영 좌표(EPSG:5179) GeoJSON → SVG 경로 JSON.
좌표계: 1단위 = 500m, 원점 = 전국 경계 왼쪽 위. 전국용과 시·도별 파일이 같은 좌표계를 쓴다(확대 = viewBox 변경)."""
import json, sys, os, math
units_lite, sido_lite, units_det, sido_det, unitsmeta, outdir, ulleung = sys.argv[1:8]
M = 500.0
def load(p): return json.load(open(p, encoding='utf8'))['features']
UL, SL, UD, SD = map(load, (units_lite, sido_lite, units_det, sido_det))
# 울릉군: 일반 단순화에서는 독도가 사라진다. 독도를 포함한 별도 단순화본(섬 제거 없음)으로 바꿔 쓴다.
ULLEUNG = load(ulleung)[0]
UD = [ULLEUNG if f['properties']['unit'] == '47940' else f for f in UD]
xs, ys = [], []
def walk(g, fn):
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    for poly in polys:
        for ring in poly: fn(ring)
for f in UD: walk(f['geometry'], lambda r: (xs.extend(p[0] for p in r), ys.extend(p[1] for p in r)))
X0, Y1 = min(xs), max(ys)
W, H = (max(xs) - X0) / M, (Y1 - min(ys)) / M
def path(g, prec):
    out = []
    def ring(r):
        q = 10 ** prec
        pts = [(round((p[0] - X0) / M * q), round((Y1 - p[1]) / M * q)) for p in r]
        ded = [pts[0]] + [b for a, b in zip(pts, pts[1:]) if a != b]
        if len(ded) < 4: return
        s = [f'M{ded[0][0]/q:g} {ded[0][1]/q:g}']
        px, py = ded[0]
        rel = []
        for x, y in ded[1:-1]:
            rel.append(f'{(x-px)/q:g} {(y-py)/q:g}'.replace(' -', '-'))
            px, py = x, y
        out.append(s[0] + 'l' + ' '.join(rel) + 'z')
    walk(g, ring)
    return ''.join(out)
def bbox(g):
    bx, by = [], []
    walk(g, lambda r: (bx.extend((p[0]-X0)/M for p in r), by.extend((Y1-p[1])/M for p in r)))
    return [round(min(bx),1), round(min(by),1), round(max(bx),1), round(max(by),1)]
meta = json.load(open(unitsmeta, encoding='utf8'))
names = {u['code']: u for u in meta['units']}
os.makedirs(os.path.join(outdir, 'sido'), exist_ok=True)
# 울릉군(독도 포함)은 다른 면과 경계를 나누지 않는 섬이라, 전국용에도 위의 독도 포함본을 그대로 쓴다.
DETAIL_IN_LITE = {'47940'}
UD_BY = {f['properties']['unit']: f for f in UD}
UL = [UD_BY[f['properties']['unit']] if f['properties']['unit'] in DETAIL_IN_LITE else f for f in UL]
lite = {'version': 'admdongkor-ver20260701', 'unit_m': M, 'viewBox': [0, 0, round(W, 1), round(H, 1)],
        'units': [{'code': f['properties']['unit'], 'sido': f['properties']['sido'], 'd': path(f['geometry'], 1)} for f in UL],
        'sido': [{'code': f['properties']['sido'], 'd': path(f['geometry'], 1), 'bbox': bbox(f['geometry'])} for f in SL]}
json.dump(lite, open(os.path.join(outdir, 'korea-lite.json'), 'w', encoding='utf8'), separators=(',', ':'))
for sf in SD:
    sc = sf['properties']['sido']
    det = {'version': lite['version'], 'sido': sc, 'bbox': bbox(sf['geometry']), 'outline': path(sf['geometry'], 1),
           'units': [{'code': f['properties']['unit'], 'd': path(f['geometry'], 1), 'bbox': bbox(f['geometry'])}
                     for f in UD if f['properties']['sido'] == sc]}
    json.dump(det, open(os.path.join(outdir, 'sido', f'{sc}.json'), 'w', encoding='utf8'), separators=(',', ':'))
print('viewBox', lite['viewBox'], 'lite units', len(lite['units']), 'sido', len(lite['sido']))
