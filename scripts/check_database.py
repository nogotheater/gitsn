"""Actually query PostgreSQL; fail instead of silently using SQLite."""
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.db import connection

if connection.vendor != "postgresql":
    raise SystemExit("Unexpected database vendor.")
with connection.cursor() as cursor:
    cursor.execute("SELECT current_database(), current_setting('server_version_num')")
    name, version = cursor.fetchone()
if int(version) // 10000 != 17:
    raise SystemExit("Expected PostgreSQL major version 17.")
print("PostgreSQL 17 connection verified:", name)
