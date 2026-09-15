from __future__ import annotations

import secrets
import sys
from pathlib import Path


def main() -> int:
    env_path = Path(sys.argv[1])
    quota_bytes = sys.argv[2]
    retention_hours = sys.argv[3]
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    values = {
        line.split("=", 1)[0]: line.split("=", 1)[1].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    defaults = {
        "ZALO_INBOX_BOOTSTRAP_SECRET": secrets.token_urlsafe(32),
        "ZALO_INBOX_WEBHOOK_SECRET": secrets.token_urlsafe(32),
        "ZALO_CONNECTOR_QUOTA_BYTES": quota_bytes,
        "ZALO_CONNECTOR_RETENTION_HOURS": retention_hours,
    }
    additions = [f"{name}={value}" for name, value in defaults.items() if not values.get(name)]
    if additions:
        separator = "" if not text or text.endswith("\n") else "\n"
        env_path.write_text(text + separator + "\n".join(additions) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())