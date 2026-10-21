"""Load the generated local KEY=VALUE file; environment variables take precedence."""
import os

def load_local_env(path):
    if not path.is_file():
        return
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid .env line {number}; expected KEY=VALUE.")
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if not name.isidentifier():
            raise ValueError(f"Invalid .env key on line {number}.")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name, value)
