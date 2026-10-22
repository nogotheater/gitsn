from django.apps import AppConfig
from django.db.models.signals import post_migrate


def lock_supabase_tables(using='default', **kwargs):
    """Supabase(웹 API용 anon 역할이 있는 DB)에서만: 새로 생긴 표도 웹 API로 못 읽게 막는다(2026-10-22).

    처음 옮길 때 scripts/supabase_restore.sh가 한 일(권한 회수 + 행 보안)을 migrate 때마다 다시 한다. 몇 번 해도 같다.
    이 앱은 표 주인 역할로 접속하므로 행 보안이 켜져도 그대로 읽고 쓴다. 로컬 PostgreSQL에는 anon 역할이 없어 아무것도 안 한다.
    """
    from django.db import connections
    connection = connections[using]
    if connection.vendor != 'postgresql':
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = 'anon'")
        if not cursor.fetchone():
            return
        cursor.execute("""
            DO $$ DECLARE t record; BEGIN
              REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
              REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
              FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
                EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
              END LOOP;
            END $$;""")


class DeliveryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "delivery"
    verbose_name = "납품현황"

    def ready(self):
        post_migrate.connect(lock_supabase_tables, sender=self, dispatch_uid='delivery-lock-supabase-tables')
