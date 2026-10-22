# 4단계: 고객사 소재지·기관 유형 입력 + 고객사 삭제 — 2026-10-22

## 결정 (형우, 하나씩 확인)
| 항목 | 결정 |
|---|---|
| 자동 채움 | 입력하면 바로 제안. 명칭·분류·지역 → 소재지·기관 유형. 저장 전 확인·수정 |
| 보이는 분류 | 지방자치단체·의회만. 다른 분류에선 칸 숨김, 기존 값 유지 |
| 기관 유형 | 자동 제안 + 고칠 수 있게(행정기관 / 시설·공기업) |
| 지역(권역) | 소재지를 고르면 자동으로 맞춤(서버도 맞춤). 제주는 권역이 없어 직접 선택 |
| 미입력 표시 | 고객사 상세 안내 + 고객사 관리 목록 배지 |
| 고객사 삭제 | 계약이 있어도 삭제 가능, 확인 화면 한 번. 관리자만 |

## 동작
- 제안은 `guess_location` 한 곳에서 계산(`/planning/location-guess/`, 관리자 전용 JSON).
- 소재지가 비어 있거나 제안으로 채운 값이면 명칭을 바꿀 때 다시 채운다. 직접 고른 값·저장된 값은 '명칭 기준 제안 [적용]'만 보여준다.
- 시·도를 고르면 그 시·도의 시군구만 보이고, 시군구 '(시·도 전체)'는 도청·광역 의회용.
- 삭제 범위: 고객사, 모든 계약(유효·종료)과 제품·설치 장소 연결, 통합된 중복 고객사, 이 계약에만 쓰인 설치 장소, 쓰이지 않게 된 기관·심볼. 다른 계약에도 쓰이는 장소·계약 상대 기관과 제품 목록은 남긴다.

## 파일
- 새 파일: `delivery/services/customer_location.py`, `delivery/services/customer_delete.py`, `templates/planning/customer_delete.html`, `static/delivery/customer-location.js`, `static/delivery/customer-location.css`
- 수정: `delivery/forms.py`(PresentationForm with_location), `delivery/services/planning.py`, `delivery/planning_views.py`, `config/urls.py`, `templates/planning/presentation_form.html`, `customer_detail.html`, `customer_list.html`
- 검사: `delivery/tests/test_customer_location.py`, `delivery/tests/test_customer_delete.py`
