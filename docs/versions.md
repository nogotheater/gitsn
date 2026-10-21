# 버전 기록
확인일: 2026-10-15

| 구성 | 고정 버전 | 이번 환경 상태 |
|---|---|---|
| Python | 3.12.14 | 사용 중 |
| Django | 5.2.18 | 설치 완료 |
| PostgreSQL | 17.11 | Compose 이미지 고정, 서버 실행 미검증 |
| psycopg / psycopg-binary | 3.3.6 | 설치 완료 |
| Pillow | 12.3.0 | 설치 완료 |
| Playwright Python | 1.64.0 | 설치 완료 |
| Playwright Chromium | 156.0.8078.4 / revision 1248 | 패키지 메타데이터 확인, 브라우저 설치 실패 |

전체 Python 의존성은 requirements.txt에 정확한 버전으로 기록했다.
Playwright 브라우저의 정확한 대응 버전은 설치된 패키지의 browsers.json에서 확인했다.
Chromium 실행 성공과 Docker 이미지 빌드 성공을 확인한 상태는 아니다.

## 확인 출처
- Django 지원 버전: https://www.djangoproject.com/download/
- PostgreSQL 17 지원 및 패치: https://www.postgresql.org/support/versioning/
- PostgreSQL 공식 패키지 색인: https://apt.postgresql.org/pub/repos/apt/dists/noble-pgdg/main/binary-amd64/Packages.gz
- Python 패키지: PyPI에서 설치한 버전과 pip freeze 결과
