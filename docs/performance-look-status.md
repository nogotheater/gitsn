# 납품현황(/performance/) 룩 적용 + 권역별 섹션 — 2026-10-21

지역 현황(지도)의 룩을 납품현황 목록 화면에 옮겼다. 동작·데이터는 그대로이고, 형우가 추가로 정한 C2(권역별 섹션)만 화면 동작이 바뀐다.

## 확정된 결정 (형우, 하나씩 확인)
| 항목 | 결정 |
|---|---|
| 카드 | 룩만 바꾸기. 로고 → 이름 → 분류 → 마킹 배치 그대로. 마킹은 원형 유지(지역 현황과 같게) |
| 폰 상단 메뉴 | ☰ 한 줄(지역 현황과 같은 모양·같은 폭 기준 900px / 세로 1100px) |
| 제목 | CUSTOMER REFERENCES / 지슨의 보안 솔루션과 함께하는 고객사 유지. 안내 줄 '계약 기준 실적 · 직원/파트너사 열람' 삭제. 폰(≤639px)은 '지슨 고객사' 22px |
| 유리 질감 | 지역 현황 값 그대로(유리 .35, blur 28px saturate 1.4, 셀 .62, 둥금 8/6/4px) |
| 인쇄 버튼·선택 칩 색 | 기존 브랜드 파랑 유지(지역 현황 파랑 #4E7CC7은 흰 글씨 대비 4.5:1 미달) |
| C2 권역 기준 | 고객사에 입력된 5권역(지역 값) 그대로 |
| C2 표시 | '지방자치단체(수도권)' 형식 섹션 |
| C2 순서 | 수도권 → 충청권 → 호남권 → 영남권 → 강원권 |
| C2 제목 숫자 | 고객사 수(권역 합 = 분류 합) |
| C2 적용 범위 | 카드 섹션 + 인쇄·PDF 섹션. 분류 탭·요약 칸·인쇄 합계 줄은 분류 단위 그대로 |

## 파일
- `static/delivery/performance-look.css` (새 파일, 이 페이지만. 제목 축약 외 모든 규칙은 @media screen)
- `templates/portal/performance.html` (스타일 연결, 안내 줄 삭제, 제목 두 가지, 섹션 id/데이터)
- `static/delivery/performance.js` (☰ 버튼)
- `delivery/services/sections.py` (새 파일, 섹션 구성), `delivery/domain/audience.py` (분류·지역별 수), `delivery/portal_views.py`, `delivery/services/printing.py`
- 검사: `delivery/tests/test_performance_look.py` (새 파일)

## 바뀐 기존 검사 기준
- `test_portal_db.test_partner_response_has_only_public_rows_and_same_total_without_private_metadata`:
  '계약 기준 실적'이 있어야 한다 → '파트너사 열람'이 없어야 한다. 이유: 형우가 안내 줄 삭제를 결정(2026-10-21).
