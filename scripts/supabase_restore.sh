#!/bin/sh
# PC DB(public 스키마) → Supabase DB로 옮기기(처음 한 번). PC의 db 컨테이너 안에서 돈다 — 2026-10-22.
# 환경 변수: TARGET_HOST, TARGET_USER, PGPASSWORD(=Supabase DB 비밀번호). PC DB는 컨테이너 안 소켓으로 읽는다.
set -eu
TARGET="host=$TARGET_HOST port=5432 dbname=postgres user=$TARGET_USER sslmode=require"
exists=$(psql "$TARGET" -tAc "select to_regclass('public.django_migrations')")
if [ -n "$exists" ]; then
  echo "RESTORE_SKIP: Supabase에 이미 자료가 있습니다(다시 넣지 않음)."
  exit 0
fi
PGPASSWORD= pg_dump --no-owner --no-privileges --schema=public -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  | sed -e '/^SET transaction_timeout/d' -e '/^CREATE SCHEMA public;/d' -e '/^COMMENT ON SCHEMA public/d' -e '/^ALTER SCHEMA public OWNER/d' \
  | psql -q -v ON_ERROR_STOP=1 "$TARGET" >/dev/null
# Supabase는 public 스키마를 웹 API(anon 키)로 열어 두므로, 우리 표는 막는다: 권한 회수 + 행 보안(RLS) 켜기(정책 없음 = 아무도 못 읽음).
psql -q -v ON_ERROR_STOP=1 "$TARGET" <<'SQL'
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
DO $$ DECLARE t record; BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
  END LOOP;
END $$;
SQL
count=$(psql "$TARGET" -tAc "select count(*) from delivery_customer")
echo "RESTORE_OK customers=$count"
