# 지역 현황 지도 경계 만들기 (8단계 1a·1b)

경계 자료가 바뀌면(행정구역 개편) 아래 순서로 다시 만든다. 개발 PC에서 Python 3, Node(mapshaper 0.6.102), shapely·pyproj가 필요하다. 앱 실행에는 필요 없다.

1. 원자료 받기: `git clone --depth 1 --filter=blob:none --sparse https://github.com/vuski/admdongkor && git sparse-checkout set ver20260701`
2. 면 코드 붙이기: `python tag_units.py <원자료.geojson> dong_tagged.geojson units.json`
   - 일반구는 소속 시로, 세종·제주는 시·도 전체를 한 면으로.
3. 합치기: `mapshaper -i dong_tagged.geojson -dissolve2 unit copy-fields=sido name=units -o format=geojson units_full.geojson`
4. 검증: `python check_units.py units_full.geojson dong_tagged.geojson` → 면 229, 겹침 0, 시·도 면적 차이 0%
5. 단순화(위상 보존):
   - 전국용: `mapshaper -i units_full.geojson -proj EPSG:5179 -simplify visvalingam weighted 4% keep-shapes -o format=geojson precision=10 units_s4.geojson`
   - 세밀: 같은 명령에 `20%` → `units_s20.geojson`
   - 시·도 경계: 위 두 명령에 `-dissolve sido` → `sido_s4.geojson`, `sido_s20.geojson`
   - 울릉군(독도 포함): `mapshaper -i units_full.geojson -filter "unit=='47940'" -proj EPSG:5179 -simplify visvalingam weighted 30% keep-shapes -filter-islands min-area=0 -o format=geojson precision=10 ulleung_full.geojson`
6. SVG 경로 파일: `python to_svg_paths.py units_s4.geojson sido_s4.geojson units_s20.geojson sido_s20.geojson units.json <static/delivery/map> ulleung_full.geojson`
7. 행정구역 모듈: `python gen_admin_areas.py units.json <delivery/domain/admin_areas.py>`
8. 9월 짝짓기 대응표(일회성, 3단계 대조용): `python old_to_new.py units.json white-tiles-data.json sept_to_new.json`

좌표계: EPSG:5179를 1단위 = 500m로 줄이고, 원점을 전국 경계 왼쪽 위로 옮겼다. 전국용과 시·도별 파일이 같은 좌표계라, 확대는 SVG viewBox만 바꾸면 된다.
