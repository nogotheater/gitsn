"""Wait up to 30 seconds for the configured PostgreSQL database."""
from pathlib import Path
import os
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.db import DatabaseError, connection

def wait_for_db():
    deadline = time.monotonic() + 30
    while True:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone() == (1,):
                    print("PostgreSQL is ready.")
                    return
        except DatabaseError:
            connection.close()
        if time.monotonic() >= deadline:
            raise SystemExit("PostgreSQL did not become ready; check host and local DB service.")
        time.sleep(1)

if __name__ == "__main__":
    wait_for_db()
