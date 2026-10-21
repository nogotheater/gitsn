"""Run the complete stage-1 checks on a machine with Docker Compose."""
from pathlib import Path
import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent

def compose(*args, capture=False):
    return subprocess.run(
        ["docker", "compose", *args], cwd=ROOT, check=True,
        text=True, capture_output=capture,
    )

def shell(code):
    return compose("exec", "-T", "web", "python", "manage.py", "shell", "-c", code, capture=True).stdout.strip().splitlines()[-1]

def http_ready(port):
    for attempt in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready/", timeout=3) as result:
                if result.status == 200 and json.load(result)["status"] == "ok":
                    return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise SystemExit("Readiness endpoint did not recover after restart.")

def main():
    if shutil.which("docker") is None:
        raise SystemExit("Docker is not installed; these checks were NOT run.")
    if not (ROOT / ".env").is_file():
        raise SystemExit("Run python scripts/bootstrap_env.py first.")
    compose("version")
    compose("config", "--quiet")
    compose("up", "--detach", "--build", "--wait", "--wait-timeout", "180")
    compose("exec", "-T", "web", "python", "manage.py", "check", "--database", "default")
    compose("exec", "-T", "web", "python", "scripts/check_database.py")
    compose("exec", "-T", "web", "python", "manage.py", "test", "--noinput")
    compose("exec", "-T", "web", "python", "scripts/check_browser.py")
    token = secrets.token_hex(12)
    code = (
        "from django.contrib.sessions.backends.db import SessionStore; "
        "from django.conf import settings; "
        f"s=SessionStore(); s['stage1_probe']={token!r}; s.save(); "
        f"(settings.MEDIA_ROOT / {('.stage1-' + token)!r}).write_text({token!r}); "
        "print(s.session_key)"
    )
    session_key = shell(code)
    compose("restart", "db", "web")
    port = "8000"
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("WEB_PORT="):
            port = line.split("=", 1)[1]
    port = os.environ.get("WEB_PORT", port)
    http_ready(port)
    check = (
        "from django.contrib.sessions.backends.db import SessionStore; "
        "from django.conf import settings; "
        f"s=SessionStore({session_key!r}); assert s.get('stage1_probe')=={token!r}; "
        f"p=settings.MEDIA_ROOT / {('.stage1-' + token)!r}; assert p.read_text()=={token!r}; "
        "s.delete(); p.unlink(); print('DB and media persisted after restart.')"
    )
    print(shell(check))
    print("All stage-1 checks passed. No customer data or application accounts were created.")

if __name__ == "__main__":
    main()
