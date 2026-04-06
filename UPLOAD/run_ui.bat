@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "VENV_PY=%PROJECT_ROOT%\venv\Scripts\python.exe"

if exist "%VENV_PY%" (
  "%VENV_PY%" "%SCRIPT_DIR%ui_runner.py"
) else (
  python "%SCRIPT_DIR%ui_runner.py"
)

endlocal
