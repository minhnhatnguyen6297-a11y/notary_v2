from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


BOOTSTRAP_VERSION = 1
PLAYWRIGHT_BROWSER = "chromium"
BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
REQUIREMENTS_PATH = BASE_DIR / "requirements.txt"
SETUP_STAMP_PATH = BASE_DIR / ".ui_setup_state.json"
UI_RUNNER_PATH = BASE_DIR / "ui_runner.py"

if sys.platform.startswith("win"):
    VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
else:  # pragma: no cover
    VENV_PYTHON = BASE_DIR / ".venv" / "bin" / "python"


def log(message: str) -> None:
    print(message, flush=True)


def run_command(cmd: list[str], *, cwd: Path | None = None) -> None:
    completed = subprocess.run(cmd, cwd=str(cwd or REPO_ROOT))
    if completed.returncode:
        rendered = subprocess.list2cmdline(cmd)
        raise RuntimeError(f"Command failed ({completed.returncode}): {rendered}")


def ensure_venv() -> Path:
    if VENV_PYTHON.exists():
        return VENV_PYTHON

    log("[SETUP] Tao moi truong ao rieng cho UPLOAD (.venv)...")
    run_command([sys.executable, "-m", "venv", str(BASE_DIR / ".venv")], cwd=REPO_ROOT)
    return VENV_PYTHON


def probe_runtime(python_exe: Path) -> dict:
    probe_script = """
import importlib.util as util
import json
import os

mods = {name: bool(util.find_spec(name)) for name in ("docx", "win32com", "dotenv", "playwright")}
chromium_ready = False
if mods["playwright"]:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            chromium_ready = os.path.exists(pw.chromium.executable_path)
    except Exception:
        chromium_ready = False

print(json.dumps({"modules": mods, "chromium_ready": chromium_ready}))
"""
    completed = subprocess.run(
        [str(python_exe), "-c", probe_script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode:
        return {
            "modules": {"docx": False, "win32com": False, "dotenv": False, "playwright": False},
            "chromium_ready": False,
            "probe_error": completed.stderr.strip() or completed.stdout.strip(),
        }
    return json.loads(completed.stdout.strip())


def load_setup_state() -> dict:
    if not SETUP_STAMP_PATH.exists():
        return {}
    try:
        return json.loads(SETUP_STAMP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_setup_state(requirements_mtime_ns: int) -> None:
    payload = {
        "bootstrap_version": BOOTSTRAP_VERSION,
        "requirements_mtime_ns": requirements_mtime_ns,
        "playwright_browser": PLAYWRIGHT_BROWSER,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    SETUP_STAMP_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def should_install_requirements(state: dict, runtime: dict, requirements_mtime_ns: int) -> bool:
    if state.get("bootstrap_version") != BOOTSTRAP_VERSION:
        return True
    if state.get("requirements_mtime_ns") != requirements_mtime_ns:
        return True
    modules = dict(runtime.get("modules") or {})
    return not all(modules.get(name, False) for name in ("docx", "win32com", "dotenv", "playwright"))


def should_install_browser(state: dict, runtime: dict) -> bool:
    if state.get("playwright_browser") != PLAYWRIGHT_BROWSER:
        return True
    return not bool(runtime.get("chromium_ready"))


def ensure_dependencies(python_exe: Path) -> None:
    if not REQUIREMENTS_PATH.exists():
        raise FileNotFoundError(f"Khong tim thay requirements: {REQUIREMENTS_PATH}")

    requirements_mtime_ns = REQUIREMENTS_PATH.stat().st_mtime_ns
    state = load_setup_state()
    runtime = probe_runtime(python_exe)

    if should_install_requirements(state, runtime, requirements_mtime_ns):
        log("[SETUP] Cai dat dependency tu UPLOAD/requirements.txt...")
        run_command([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], cwd=REPO_ROOT)
        run_command([str(python_exe), "-m", "pip", "install", "-r", str(REQUIREMENTS_PATH)], cwd=REPO_ROOT)
        runtime = probe_runtime(python_exe)

    modules = dict(runtime.get("modules") or {})
    missing_modules = [name for name in ("docx", "win32com", "dotenv", "playwright") if not modules.get(name)]
    if missing_modules:
        probe_error = runtime.get("probe_error")
        detail = f" Missing: {', '.join(missing_modules)}."
        if probe_error:
            detail += f" Probe error: {probe_error}"
        raise RuntimeError("Bootstrap UPLOAD chua san sang." + detail)

    if should_install_browser(state, runtime):
        log("[SETUP] Cai Playwright Chromium (chi can 1 lan)...")
        run_command([str(python_exe), "-m", "playwright", "install", PLAYWRIGHT_BROWSER], cwd=REPO_ROOT)
        runtime = probe_runtime(python_exe)
        if not runtime.get("chromium_ready"):
            raise RuntimeError("Playwright da cai package nhung Chromium van chua san sang.")

    save_setup_state(requirements_mtime_ns)


def launch_ui(python_exe: Path) -> int:
    log("[RUN] Mo giao dien UPLOAD...")
    completed = subprocess.run([str(python_exe), str(UI_RUNNER_PATH)], cwd=str(REPO_ROOT))
    return completed.returncode


def main() -> int:
    log("UPLOAD UI bootstrap")
    log("===================")
    python_exe = ensure_venv()
    ensure_dependencies(python_exe)
    return launch_ui(python_exe)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"[LOI] {exc}")
        raise SystemExit(1)
