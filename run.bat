@echo off
setlocal EnableExtensions
chcp 65001 >nul

REM === CONFIG ===
set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%venv"
set "HOST=127.0.0.1"
set "PORT=8000"

echo.
echo [RUN] Project: "%PROJECT_DIR%"
cd /d "%PROJECT_DIR%" || (echo [ERR] Khong vao duoc thu muc du an & pause & exit /b 1)

REM 1) Ensure venv exists
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [ERR] Chua co venv. Hay chay setup.bat truoc.
  pause
  exit /b 1
)

REM 2) Free port if stuck
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do (
  echo [RUN] Port %PORT% dang bi chiem boi PID=%%a -> kill
  taskkill /F /PID %%a >nul 2>&1
)

REM 3) Run uvicorn (no reload = on dinh hon)
echo.
echo [RUN] Starting server: http://%HOST%:%PORT%
"%VENV_DIR%\Scripts\python.exe" -m uvicorn main:app --host %HOST% --port %PORT%
echo.
echo [RUN] Server da dung.
pause
endlocal