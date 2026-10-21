# 8단계 — 지역 현황(지자체·의회 지도) 진행 기록

기준 문서: intent.md(2026-10-21 확정), spec.md v3, plan.md v2 (프로젝트 밖 작업 폴더).
10월 20일의 8단계 설계·시안(stage8-map-*.html, stage8-map-design.md)은 이번 작업에서 쓰지 않는다.

## 단계별 기록
| 단계 | 내용 | 결과 |
|---|---|---|
| 0 | 백업 `backups/gitsn-delivery_backup_2026-10-21`, 복원 확인(고객사 514·계약 919·계약 제품 948 일치), 로컬 git | 통과 |
| 0.5 | 개발 전용 `compose.map-dev.yaml`(코드 폴더만 연결, 브라우저 검사 켬) | 기준 검사 118/118, 건너뜀 0 |
| 1a·1b | 경계: admdongkor ver20260701 → 면 229(기초 227 + 세종 + 제주), 시·도 16. `static/delivery/map/`, `delivery/domain/admin_areas.py`, `scripts/map_boundaries/` | 겹침 0, 면적 차이 0%, 전국용 173KB |
| 2 | Customer.location_code / institution_type(선택 입력, 마이그레이션 0006), 추정 규칙 `delivery/domain/locations.py` | 적용·되돌리기·재적용 통과, 검사 135/135 |
| 3 | `fill_locations` 대조표 → 형우 확인 → 반영(177곳, 불일치 0). 소재지 원칙: 물리적 위치가 아니라 상위기관. 시스템 데이터 수정(형우): 광양시 Alpha-C 계약 종료, 상주은모래비치 계약 종료 | 전국 대조 차이 4건: 9월 이후 신규 2(고창군 C, 경산시 S), 9월 PDF 오류 2(광주 남구·광산구를 '의회'로 표시 — 실제는 지자체 고객이며 의회 고객은 없음, 형우 확인 13:21). 데이터 누락 0 |
| 5 | 지도 계산 `delivery/domain/region_map.py`, `delivery/services/region_map.py` | 검사 161/161. 실데이터: 도청×지자체 91면, 불법촬영×지자체 25면(+시설 아이콘 4면), 도청×의회 34면, 불법촬영×의회 0면(광역의회 2곳은 광역 줄) |

## 고객사(Customer)가 만들어지거나 바뀌는 경로 (2단계 조사)
| 경로 | 위치 | 소재지·기관 유형 처리 |
|---|---|---|
| 기획팀 고객사 등록·수정 | `delivery/services/planning.py` `save_presentation` | 4단계에서 자동 채움·수정 칸 추가 예정. 그 전까지 새 고객사는 비어 있고 지도에 "지도에 올리지 못한 기관"으로 안내된다 |
| 고객사 생성 함수 | `delivery/services/presentations.py` `new_customer` | 위 경로와 검증 스크립트가 쓴다. 지도용 칸은 기본값(빈 값) |
| 중복 통합 | `delivery/services/duplicates.py` | 유지 고객사의 값이 남는다. 통합된 고객사는 집계·목록에서 빠지므로 지도에도 나오지 않는다. 4단계에서 "유지 고객사 소재지가 비면 통합 대상 값으로 채움"을 검토 |
| 일회성 자료 입력 | 7단계 `import_to_db.py`(프로젝트에 없음) | 다시 쓰면 3단계 `fill_locations`를 이어서 돌린다 |
| Django admin | 설치돼 있으나 URL에 연결되지 않음 | 해당 없음 |
