from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_zalo_env_setup_backfills_missing_values_without_overwriting(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("QWEN_API_KEY=keep-me\nZALO_CONNECTOR_QUOTA_BYTES=123\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/ensure_zalo_env.py",
            str(env_file),
            "5368709120",
            "168",
            "104857600",
            "168",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "keep-me" not in result.stdout
    assert "SECRET" not in result.stdout
    values = dict(
        line.split("=", 1)
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    assert values["QWEN_API_KEY"] == "keep-me"
    assert values["ZALO_CONNECTOR_QUOTA_BYTES"] == "123"
    assert values["ZALO_CONNECTOR_RETENTION_HOURS"] == "168"
    assert values["ZALO_INBOX_TEXT_QUOTA_BYTES"] == "104857600"
    assert values["ZALO_INBOX_TEXT_RETENTION_HOURS"] == "168"
    assert len(values["ZALO_INBOX_BOOTSTRAP_SECRET"]) >= 32
    assert len(values["ZALO_INBOX_WEBHOOK_SECRET"]) >= 32
    assert values["ZALO_INBOX_BOOTSTRAP_SECRET"] != values["ZALO_INBOX_WEBHOOK_SECRET"]