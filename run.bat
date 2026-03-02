@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM === CONFIG ===
set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%venv"
set "HOST=127.0.0.1"
set "PORT=8000"
set "MODE=%~1"

echo.
echo [RUN] Project: "%PROJECT_DIR%"
cd /d "%PROJECT_DIR%" || (echo [ERR] Khong vao duoc thu muc du an & exit /b 1)

REM 1) Ensure venv exists
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [ERR] Chua co venv. Hay chay setup.bat truoc.
  exit /b 1
)

REM 2) Single instance guard
set "EXISTING_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do (
  set "EXISTING_PID=%%a"
)

if defined EXISTING_PID (
  if /I "%MODE%"=="restart" (
    echo [RUN] Restart mode: kill PID=!EXISTING_PID! on port %PORT%
    taskkill /F /PID !EXISTING_PID! >nul 2>&1
  ) else (
    echo [RUN] Server da chay tai http://%HOST%:%PORT% ^(PID=!EXISTING_PID!^)
    echo [TIP] Neu can restart: run.bat restart
    exit /b 0
  )
)

REM 3) Run uvicorn (no reload = on dinh hon)
echo.
echo [RUN] Starting server: http://%HOST%:%PORT%
"%VENV_DIR%\Scripts\python.exe" -m uvicorn main:app --host %HOST% --port %PORT%
echo.
echo [RUN] Server da dung.
endlocal
