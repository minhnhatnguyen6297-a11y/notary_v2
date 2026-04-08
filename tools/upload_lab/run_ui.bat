@echo off
chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
set "BOOTSTRAP=%SCRIPT_DIR%bootstrap_ui.py"
set "PYTHON_INSTALLER=%SCRIPT_DIR%install_python_windows.ps1"
set "VENV_PY=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "EXIT_CODE=0"

cd /d "%SCRIPT_DIR%"

call :TRY_FILE "%VENV_PY%"
if not errorlevel 1 goto :DONE

call :TRY_COMMAND python
if not errorlevel 1 goto :DONE

call :TRY_COMMAND py -3
if not errorlevel 1 goto :DONE

call :TRY_WINGET
if not errorlevel 1 goto :DONE

call :TRY_POWERSHELL_INSTALL
if not errorlevel 1 goto :DONE

echo [LOI] Khong bootstrap duoc Python 3.10+ cho tool.
set "EXIT_CODE=1"
goto :DONE

:TRY_FILE
if not exist "%~1" exit /b 1
"%~1" -c "import sys, pip; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
"%~1" "%BOOTSTRAP%"
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%

:TRY_COMMAND
%* -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
%* "%BOOTSTRAP%"
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%

:TRY_WINGET
winget --version >nul 2>&1
if errorlevel 1 exit /b 1
echo [SETUP] Khong tim thay Python 3.10+. Dang thu cai qua winget...
winget install --id Python.Python.3 --exact --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo [SETUP] Winget khong cai duoc Python, se thu fallback python.org...
  exit /b 1
)
call :TRY_COMMAND py -3
if not errorlevel 1 exit /b 0
call :TRY_COMMAND python
if not errorlevel 1 exit /b 0
exit /b 1

:TRY_POWERSHELL_INSTALL
if not exist "%PYTHON_INSTALLER%" exit /b 1
echo [SETUP] Dang thu cai Python tu python.org...
set "FOUND_PY="
for /f "usebackq delims=" %%I in (`powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PYTHON_INSTALLER%"`) do set "FOUND_PY=%%I"
if not defined FOUND_PY exit /b 1
call :TRY_FILE "%FOUND_PY%"
if not errorlevel 1 exit /b 0
exit /b 1

:DONE
if not "%EXIT_CODE%"=="0" pause
endlocal & exit /b %EXIT_CODE%
