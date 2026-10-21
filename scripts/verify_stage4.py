"""Run all current tests, including Chromium, on a unique temporary PostgreSQL DB."""
from pathlib import Path
import os
import sys
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.db import connection


def main():
    if not settings.DEBUG or connection.vendor != 'postgresql':
        raise SystemExit('Local DEBUG PostgreSQL environment required.')
    call_command('migrate', interactive=False, verbosity=1)
    call_command('check', databases=['default'])
    previous = connection.settings_dict['TEST']['NAME']
    connection.settings_dict['TEST']['NAME'] = 'test_gitsn_stage4_' + uuid4().hex[:16]
    os.environ['GITSN_RUN_BROWSER_TESTS'] = '1'
    try:
        call_command('test', 'delivery', interactive=False, verbosity=2)
    finally:
        connection.settings_dict['TEST']['NAME'] = previous
    print('STAGE4_PORTAL_CHECKS_OK', flush=True)
    print('All test accounts and customer records stayed in a separate test DB.', flush=True)


if __name__ == '__main__':
    main()
