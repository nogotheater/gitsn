"""Generate only local random values. Never overwrite an existing .env."""
from pathlib import Path
import os
import secrets

root = Path(__file__).resolve().parent.parent
target = root / ".env"
template = (root / ".env.example").read_text(encoding="utf-8")
if target.exists():
    raise SystemExit(".env already exists; no changes made.")
template = template.replace("DJANGO_SECRET_KEY=GENERATE_WITH_BOOTSTRAP_SCRIPT", "DJANGO_SECRET_KEY=" + secrets.token_urlsafe(64))
template = template.replace("POSTGRES_PASSWORD=GENERATE_WITH_BOOTSTRAP_SCRIPT", "POSTGRES_PASSWORD=" + secrets.token_urlsafe(32))
descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as output:
    output.write(template)
print("Created local .env with random development credentials. No application accounts were created.")
