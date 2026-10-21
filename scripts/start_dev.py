"""Container entrypoint for LOCAL development, not a production server."""
from pathlib import Path
import os
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
subprocess.run([sys.executable, str(root / "scripts/wait_for_db.py")], cwd=root, check=True)
subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], cwd=root, check=True)
os.chdir(root)
os.execv(sys.executable, [sys.executable, "manage.py", "runserver", "0.0.0.0:8000", "--noreload"])
