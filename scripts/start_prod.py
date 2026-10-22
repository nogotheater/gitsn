"""인터넷 테스트 서버(Render)용 시작(2026-10-22): DB 대기 → 마이그레이션 → 정적 파일 모으기 → gunicorn. PC 개발 실행은 start_dev.py."""
from pathlib import Path
import os
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
os.chdir(root)
subprocess.run([sys.executable, "scripts/wait_for_db.py"], check=True)
subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], check=True)
subprocess.run([sys.executable, "manage.py", "collectstatic", "--noinput", "--verbosity", "0"], check=True)
port = os.environ.get("PORT", "8000")   # Render는 PORT를 정해 준다
# 무료 서버 메모리(512MB)에 맞춰 작업자 2개. PDF 만들기(크롬)가 메모리를 많이 쓴다.
os.execvp("gunicorn", ["gunicorn", "config.wsgi:application", "--bind", f"0.0.0.0:{port}",
                       "--workers", os.environ.get("WEB_CONCURRENCY", "2"), "--timeout", "120", "--access-logfile", "-"])
