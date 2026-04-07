@echo off
chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
set "BOOTSTRAP=%SCRIPT_DIR%bootstrap_ui.py"
set "VENV_PY=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "EXIT_CODE=0"

cd /d "%SCRIPT_DIR%"

if exist "%VENV_PY%" (
  "%VENV_PY%" "%BOOTSTRAP%"
  set "EXIT_CODE=%ERRORLEVEL%"
  goto :DONE
)

python --version >nul 2>&1
if not errorlevel 1 (
  python "%BOOTSTRAP%"
  set "EXIT_CODE=%ERRORLEVEL%"
  goto :DONE
)

py -3.10 --version >nul 2>&1
if not errorlevel 1 (
  py -3.10 "%BOOTSTRAP%"
  set "EXIT_CODE=%ERRORLEVEL%"
  goto :DONE
)

py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 "%BOOTSTRAP%"
  set "EXIT_CODE=%ERRORLEVEL%"
  goto :DONE
)

echo [LOI] Khong tim thay Python 3.10+ de bootstrap UPLOAD UI.
echo       Hay cai Python roi chay lai file nay.
set "EXIT_CODE=1"

:DONE
if not "%EXIT_CODE%"=="0" pause
endlocal & exit /b %EXIT_CODE%
