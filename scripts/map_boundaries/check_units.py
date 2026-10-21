"""경계 검증: 면 개수, 겹침, 시·도 면적 = 소속 면 면적 합"""
import json, sys, collections
from shapely.geometry import shape
from shapely.ops import unary_union, transform
from shapely.strtree import STRtree
from pyproj import Transformer
path, src = sys.argv[1], sys.argv[2]
tr = Transformer.from_crs(4326, 5179, always_xy=True).transform
feats = json.load(open(path, encoding='utf8'))['features']
geoms = [transform(tr, shape(f['geometry'])).buffer(0) for f in feats]
codes = [f['properties']['unit'] for f in feats]
print('features', len(feats), 'unique codes', len(set(codes)))
tree = STRtree(geoms); overl = []
for i, g in enumerate(geoms):
    for j in tree.query(g):
        if j <= i: continue
        a = g.intersection(geoms[j]).area
        if a > 1.0: overl.append((codes[i], codes[j], round(a, 1)))
print('overlap pairs (>1 m2)', len(overl), overl[:5])
# sido area from source dongs vs unit sum
dong = json.load(open(src, encoding='utf8'))['features']
sa = collections.defaultdict(list)
for f in dong: sa[f['properties']['sido']].append(transform(tr, shape(f['geometry'])).buffer(0))
us = collections.defaultdict(float)
for f, g in zip(feats, geoms): us[f['properties']['sido']] += g.area
worst = 0
for s, gs in sorted(sa.items()):
    A = unary_union(gs).area; diff = abs(A - us[s]) / A * 100; worst = max(worst, diff)
    print(s, f'{A/1e6:,.0f} km2', f'diff {diff:.4f}%')
print('max diff %', round(worst, 4))
