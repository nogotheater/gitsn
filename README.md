# GITSN 납품현황 — 1단계 프로젝트 준비

이 파일은 실제 개발을 이어갈 수 있는 프로젝트의 실행 안내다.
현재는 설정과 상태 확인 페이지만 있다. 고객사·계약 화면은 아직 만들지 않았다.
1단계의 환경 제한과 실제 검증 결과는 docs/stage1-status.md를 먼저 확인한다.

## 고정 구성
Python 3.12.14 / Django 5.2.18 / PostgreSQL 17.11.
의존성 전체 버전은 requirements.txt, 대응 Chromium 버전은 docs/versions.md에 기록했다.
화면은 Django Templates·HTML·CSS를 사용한다.
현재 실행 명령은 로컬 개발용이며 운영 배포 명령이 아니다.

## 처음 실행하기
준비물: Python 3.12와 Docker Desktop(Compose 포함). Python은 최초 .env 생성에 사용한다.
Windows는 프로젝트 폴더에서 PowerShell을 열고 python 대신 py -3.12를 사용할 수 있다.

1. 압축을 풀고 프로젝트 폴더에서 터미널을 연다.
2. 아래 명령으로 로컬 비밀값을 만든다. 기존 .env는 덮어쓰지 않는다.

```bash
python scripts/bootstrap_env.py
```

3. Docker Desktop을 켜고 실행한다.

```bash
docker compose up --detach --build --wait --wait-timeout 180
```

최초 빌드는 패키지와 Chromium을 받으므로 시간이 걸릴 수 있다.
브라우저 다운로드나 Docker 빌드가 실패하면 실행 성공으로 처리하지 말고 로그를 확인한다.
앱 시작 시 기본 Django 테이블만 준비하며 계정은 생성하지 않는다.
http://localhost:8000 에서 준비 페이지를 확인한다.

- /health/live/ : 앱 실행 확인. DB 연결 성공을 의미하지 않는다.
- /health/ready/ : 실제 PostgreSQL SELECT 1 성공 시 200, 실패 시 503.

포트 8000이 사용 중이면 .env의 WEB_PORT를 비어 있는 포트로 바꾼다.
DB는 외부 호스트 포트로 공개하지 않는다. web 포트는 로컬 컴퓨터에서만 접근한다.
다른 컴퓨터·휴대폰에서 접속하는 설정은 이후 접속 환경 결정 때 진행한다.

## 검증
Docker가 있는 환경에서 다음을 실행한다.

```bash
python scripts/verify_stage1.py
```

다음을 실제로 확인한다.
- Compose 구성과 이미지 빌드, DB 준비, Django 시스템 검사
- PostgreSQL 17 연결, 빈 프로젝트 테스트 실행
- 패키지 대응 Chromium 실행과 임시 PDF 생성 가능 여부
- DB·web 재시작 전후 임시 세션 및 미디어 파일 유지

검증용 세션·파일은 확인 뒤 제거하고 실제 사용자 계정이나 고객사 자료는 만들지 않는다.
1단계 최초 검증에서는 업무 테스트가 없어 0개였다. 현재 작업본에는 2단계 DB 비의존 검증 사례 21개를 추가했다.
기본 프로젝트 검증이 업무 기능 검증을 대신하지 않는다.

## 로그·종료·다시 시작
```bash
docker compose logs --tail 100 web db
docker compose down
docker compose up --detach --wait
```

일반 종료는 DB·미디어 볼륨을 유지한다. 자료 보존이 필요하면 down에 -v를 붙이지 않는다.
비밀번호를 바꾸면 기존 DB 볼륨의 DB 사용자 비밀번호가 자동 변경되지 않으므로 무작정 .env를 재생성하지 않는다.
DB·미디어의 실제 백업 방식은 아직 결정하지 않았다.

## Docker 없이 명령을 검사할 때
동일 패키지를 별도 가상환경에 설치할 수 있다. DB는 PostgreSQL 17만 사용하며 SQLite로 바꾸지 않는다.

```bash
python -m venv .venv
```

Windows:
```powershell
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts/bootstrap_env.py
.venv\Scripts\python manage.py check
.venv\Scripts\python manage.py test
```

macOS/Linux:
```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/bootstrap_env.py
.venv/bin/python manage.py check
.venv/bin/python manage.py test
```

실제 DB 연결 확인은 PostgreSQL 17을 준비한 뒤 .env의 POSTGRES_HOST와 포트를 실제 위치에 맞춘 다음 한다.
```bash
python scripts/check_database.py
```

Django 시스템 검사·빈 테스트 통과만으로 DB 연결을 확인했다고 보지 않는다.
이번 환경에서는 Docker·실제 DB 연결 미검증이며 상세 결과는 상태 문서를 따른다.

## 다음 단계
2단계는 고객사·계약·설치 장소의 관계 및 집계 선택 조합을 확정하는 작업이다.
기존 PRD와 구현 지시문은 docs/source/에 포함했다.
출처는 메일 제목·수신일·발신자 모두 선택, 수량은 1 이상 정수로 확정했다. 목록 표시와 집계 여부는 각각 저장한다. 남은 미정 규칙은 임의로 정하지 않았다.
디자인 시스템의 색·폰트·화면 시안은 1단계 범위가 아니므로 아직 적용하지 않았다.

## 2단계 진행 상황
기본 모델·초기 마이그레이션 파일과 DB 비의존 검증 21개를 추가했다. 남은 정책 확인과 실제 DB 적용·통합 검증은 미완료다.
설계: docs/stage2-data-design.md / 모델: docs/stage2-schema.md / 상태: docs/stage2-status.md
전체 DB 비의존 검증: python manage.py test --noinput
이 테스트 통과는 PostgreSQL 통합 검증을 대신하지 않는다.
