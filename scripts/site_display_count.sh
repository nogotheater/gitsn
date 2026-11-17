#!/bin/sh
# 설치 장소 표시 설정 세기(읽기만, 2026-11-17 형우: '실적 목록에 표시'·'총 고객사 수에 포함'을 하나로 합치기 전에).
# PC의 db 컨테이너 안에서 인터넷 서버 DB(Supabase)를 읽는다. 환경 변수: TARGET_HOST, TARGET_USER, PGPASSWORD.
set -eu
TARGET="host=$TARGET_HOST port=5432 dbname=postgres user=$TARGET_USER sslmode=require"
echo "== 조합별 개수 (목록에 표시, 총 수에 포함, 개수)"
psql "$TARGET" -At -F ' | ' -c "select show_in_list, include_in_total, count(*) from delivery_sitepresentation group by 1,2 order by 1,2"
echo "== 둘이 다른 장소 (목록에 표시, 총 수에 포함, 장소 이름, 분류)"
psql "$TARGET" -At -F ' | ' -c "select sp.show_in_list, sp.include_in_total, s.official_name, sp.category from delivery_sitepresentation sp join delivery_installationsite s on s.id = sp.site_id where sp.show_in_list <> sp.include_in_total order by 1, 2, 3"
echo "COUNT_OK"
