from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


BOOTSTRAP_VERSION = 2
PYTHON_MIN_VERSION = (3, 10)
PLAYWRIGHT_BROWSER = "chromium"
BASE_DIR = Path(__file__).resolve().parent
REQUIREMENTS_PATH = BASE_DIR / "requirements.txt"
SETUP_STAMP_PATH = BASE_DIR / ".ui_setup_state.json"
UI_RUNNER_PATH = BASE_DIR / "ui_runner.py"
RUNTIME_DIRS = ("output", "runs", "logs", "downloads", "upload_runs")

if sys.platform.startswith("win"):
    VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
else:  # pragma: no cover
    VENV_PYTHON = BASE_DIR / ".venv" / "bin" / "python"


def log(message: str) -> None:
    print(message, flush=True)


def run_command(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    capture_output: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        cmd,
        cwd=str(cwd or BASE_DIR),
        capture_output=capture_output,
        text=True,
        encoding="utf-8",
    )
    if check and completed.returncode:
        rendered = subprocess.list2cmdline(cmd)
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout
        if detail:
            raise RuntimeError(f"Command failed ({completed.returncode}): {rendered}\n{detail}")
        raise RuntimeError(f"Command failed ({completed.returncode}): {rendered}")
    return completed


def ensure_runtime_layout() -> None:
    for name in RUNTIME_DIRS:
        (BASE_DIR / name).mkdir(parents=True, exist_ok=True)


def load_setup_state() -> dict:
    if not SETUP_STAMP_PATH.exists():
        return {}
    try:
        return json.loads(SETUP_STAMP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_setup_state(requirements_mtime_ns: int, runtime: dict) -> None:
    version = runtime.get("version") or [0, 0, 0]
    payload = {
        "bootstrap_version": BOOTSTRAP_VERSION,
        "requirements_mtime_ns": requirements_mtime_ns,
        "playwright_browser": PLAYWRIGHT_BROWSER,
        "python_version": ".".join(str(part) for part in version[:2]),
        "python_executable": runtime.get("executable", ""),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    SETUP_STAMP_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_python_identity(python_exe: Path) -> dict:
    completed = run_command(
        [
            str(python_exe),
            "-c",
            (
                "import json, sys; "
                "print(json.dumps({'version': list(sys.version_info[:3]), 'executable': sys.executable}))"
            ),
        ],
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        return {"ok": False, "error": completed.stderr.strip() or completed.stdout.strip()}
    try:
        payload = json.loads(completed.stdout.strip())
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    payload["ok"] = True
    return payload


def probe_runtime(python_exe: Path) -> dict:
    probe_script = """
import importlib.util as util
import json
import os
import sys

mods = {name: bool(util.find_spec(name)) for name in ("docx", "dotenv", "playwright", "openpyxl")}
chromium_ready = False
if mods["playwright"]:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            chromium_ready = os.path.exists(pw.chromium.executable_path)
    except Exception:
        chromium_ready = False

print(json.dumps({
    "version": list(sys.version_info[:3]),
    "executable": sys.executable,
    "prefix": sys.prefix,
    "base_prefix": getattr(sys, "base_prefix", sys.prefix),
    "modules": mods,
    "chromium_ready": chromium_ready,
}))
"""
    completed = run_command(
        [str(python_exe), "-c", probe_script],
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        return {
            "ok": False,
            "version": [0, 0, 0],
            "modules": {"docx": False, "dotenv": False, "playwright": False, "openpyxl": False},
            "chromium_ready": False,
            "probe_error": completed.stderr.strip() or completed.stdout.strip(),
        }
    payload = json.loads(completed.stdout.strip())
    payload["ok"] = True
    return payload


def is_python_compatible(runtime: dict) -> bool:
    version = tuple(runtime.get("version") or [0, 0, 0])
    return runtime.get("ok", False) and version[:2] >= PYTHON_MIN_VERSION


def _current_process_uses_venv() -> bool:
    try:
        return VENV_PYTHON.exists() and Path(sys.executable).resolve() == VENV_PYTHON.resolve()
    except Exception:
        return False


def should_recreate_venv(state: dict, venv_runtime: dict, bootstrap_python: Path) -> bool:
    if not VENV_PYTHON.exists():
        return True
    if not is_python_compatible(venv_runtime):
        return True
    if _current_process_uses_venv():
        return False

    bootstrap_identity = get_python_identity(bootstrap_python)
    if bootstrap_identity.get("ok"):
        bootstrap_version = ".".join(str(part) for part in bootstrap_identity.get("version", [0, 0])[:2])
        current_venv_version = ".".join(str(part) for part in venv_runtime.get("version", [0, 0])[:2])
        if current_venv_version and current_venv_version != bootstrap_version:
            return True
    return False


def recreate_venv(bootstrap_python: Path) -> None:
    if (BASE_DIR / ".venv").exists():
        log("[SETUP] Phat hien .venv cu/khong hop le. Dang tao lai...")
        try:
            shutil.rmtree(BASE_DIR / ".venv")
        except PermissionError as exc:
            raise RuntimeError(
                "Khong the tao lai .venv vi dang co tien trinh khac giu file trong thu muc nay. "
                "Hay dong Upload Tool/cac tien trinh Python dang dung tool roi chay lai."
            ) from exc
    else:
        log("[SETUP] Tao moi truong ao rieng (.venv)...")
    run_command([str(bootstrap_python), "-m", "venv", str(BASE_DIR / ".venv")], cwd=BASE_DIR)


def ensure_venv() -> Path:
    bootstrap_python = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
    bootstrap_identity = get_python_identity(bootstrap_python)
    if not is_python_compatible(bootstrap_identity):
        detail = bootstrap_identity.get("error") or bootstrap_identity.get("version")
        raise RuntimeError(f"Python hien tai khong dat yeu cau >= {PYTHON_MIN_VERSION[0]}.{PYTHON_MIN_VERSION[1]}: {detail}")

    state = load_setup_state()
    venv_runtime = probe_runtime(VENV_PYTHON) if VENV_PYTHON.exists() else {"ok": False, "version": [0, 0, 0]}
    if should_recreate_venv(state, venv_runtime, bootstrap_python):
        recreate_venv(bootstrap_python)
    if not VENV_PYTHON.exists():
        raise RuntimeError("Khong tao duoc .venv cho tool.")
    return VENV_PYTHON


def should_install_requirements(state: dict, runtime: dict, requirements_mtime_ns: int) -> bool:
    if state.get("bootstrap_version") != BOOTSTRAP_VERSION:
        return True
    if state.get("requirements_mtime_ns") != requirements_mtime_ns:
        return True
    modules = dict(runtime.get("modules") or {})
    return not all(modules.get(name, False) for name in ("docx", "dotenv", "playwright", "openpyxl"))


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

    if not is_python_compatible(runtime):
        raise RuntimeError("Python trong .venv khong con hop le. Hay bootstrap lai.")

    if should_install_requirements(state, runtime, requirements_mtime_ns):
        log("[SETUP] Cai dat dependency tu requirements.txt...")
        try:
            run_command([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], cwd=BASE_DIR)
            run_command([str(python_exe), "-m", "pip", "install", "-r", str(REQUIREMENTS_PATH)], cwd=BASE_DIR)
        except Exception:
            if _current_process_uses_venv():
                raise
            log("[SETUP] .venv hien tai thieu pip hoac bi hong. Dang tao lai...")
            recreate_venv(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
            python_exe = VENV_PYTHON
            run_command([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], cwd=BASE_DIR)
            run_command([str(python_exe), "-m", "pip", "install", "-r", str(REQUIREMENTS_PATH)], cwd=BASE_DIR)
        runtime = probe_runtime(python_exe)

    modules = dict(runtime.get("modules") or {})
    missing_modules = [name for name in ("docx", "dotenv", "playwright", "openpyxl") if not modules.get(name)]
    if missing_modules:
        probe_error = runtime.get("probe_error")
        detail = f" Missing: {', '.join(missing_modules)}."
        if probe_error:
            detail += f" Probe error: {probe_error}"
        raise RuntimeError("Bootstrap chua san sang." + detail)

    if should_install_browser(state, runtime):
        log("[SETUP] Cai Playwright Chromium (chi can 1 lan)...")
        run_command([str(python_exe), "-m", "playwright", "install", PLAYWRIGHT_BROWSER], cwd=BASE_DIR)
        runtime = probe_runtime(python_exe)
        if not runtime.get("chromium_ready"):
            raise RuntimeError("Playwright da cai package nhung Chromium van chua san sang.")

    save_setup_state(requirements_mtime_ns, runtime)


def launch_ui(python_exe: Path) -> int:
    log("[RUN] Mo giao dien...")
    ui_python = VENV_PYTHON if VENV_PYTHON.exists() else python_exe
    completed = run_command([str(ui_python), str(UI_RUNNER_PATH)], cwd=BASE_DIR, check=False)
    return completed.returncode


def main() -> int:
    log("UPLOAD UI bootstrap")
    log("===================")
    ensure_runtime_layout()
    python_exe = ensure_venv()
    ensure_dependencies(python_exe)
    return launch_ui(python_exe)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"[LOI] {exc}")
        raise SystemExit(1)
