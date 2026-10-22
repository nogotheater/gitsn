# 인터넷 주소 + 폰 앱(사용성 테스트) — 2026-10-22 형우 확정

## 결정
- 목적: 사내 서버로 옮기기 전에 인터넷 주소로 열어 보고 폰에서 앱처럼 써 보며 사용성 확인.
- 방식: 클라우드, 무료, 카드 없이 → GitHub(비공개 코드, nogotheater/gitsn) + Render(실행, 싱가포르, 무료) + Supabase(DB·로고, 싱가포르, 무료).
  - 오라클 무료 서버는 검토 후 제외(형우). Cloudflare Pages·GitHub Pages는 Python 서버를 못 돌리고 무료 공개라 제외.
- 실제 고객 데이터를 올림(형우 결정 — 이번부터 PC 밖으로 나감). GitHub에는 코드만, 자료는 Supabase에만.
- 폰 앱: 웹 앱(PWA). 주소를 열고 '홈 화면에 추가' → 아이콘·전체 화면. 앱스토어 없음.
- 주소: https://gitsn.onrender.com (이름이 이미 있으면 Render가 뒤에 글자를 붙임). 회사 도메인은 사내 서버로 갈 때.

## 보호
- 모든 화면 로그인(PC 계정 그대로 — DB를 옮김), https만, DEBUG 끔.
- Supabase: public 스키마 표의 anon·authenticated 권한 회수 + 행 보안(RLS) 켜기(정책 없음) → Supabase 웹 API로는 못 읽음. 로고는 비공개 버킷(logos), 화면에는 로그인한 사람에게만 서버가 내려줌.
- 비밀 값(DB 비밀번호·저장소 키)은 저장소에 없음 — Render 화면과 PC의 _cloud\supabase.txt에만.
- 서비스 워커는 고객 자료를 폰에 저장하지 않음(끊기면 안내 화면만).

## 무료라서 생기는 것
- Render: 15분 안 쓰면 잠듦, 다시 열 때 1분쯤. 메모리 512MB라 PDF 만들기는 시험 필요.
- Supabase: DB 500MB, 일주일 안 쓰면 일시정지(화면에서 재개).

## 구성
- render.yaml(Render 설정), scripts/start_prod.py(gunicorn), config/settings.py(서버 환경에서만: Render 주소, 프록시 https, WhiteNoise, Supabase 암호화 연결, S3 저장소).
- scripts/supabase_restore.sh(PC DB → Supabase, 처음 한 번), scripts/upload_media.py(로고 → Supabase 저장소).
- PC 쪽: _map_tasks/160(검사·기록·GitHub 올리기), 161(PC 자료 → Supabase).

## 진행
1. GitHub 비공개 저장소 nogotheater/gitsn ✔
2. 160: 검사 → 기록 → GitHub 올리기
3. Supabase 가입·프로젝트(싱가포르) → 값 6개를 _cloud\supabase.txt에 → 161
4. Render: GitHub 저장소 연결(Blueprint, render.yaml) → 비밀 값 입력 → 배포
5. 주소 열기 → 폰 홈 화면에 추가
