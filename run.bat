@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "PROJECT_DIR=%~dp0"
set "VENV=%PROJECT_DIR%venv"
set "PORT=8000"
set "HOST=127.0.0.1"

cd /d "%PROJECT_DIR%"

echo.
echo  Cong chung -- Quan ly Ho so Thua ke
echo  =====================================

:: 1. Kiem tra Python
python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo [LOI] Khong tim thay Python trong PATH.
  echo       Cai Python 3.10+ tu python.org va thu lai.
  echo.
  pause
  exit /b 1
)

:: 2. Tao venv neu chua co
if not exist "%VENV%\Scripts\python.exe" (
  echo [SETUP] Tao moi truong ao (venv^)...
  python -m venv "%VENV%"
  if errorlevel 1 (
    echo [LOI] Khong tao duoc venv.
    pause & exit /b 1
  )
  echo [SETUP] Cai dat thu vien tu requirements.txt...
  "%VENV%\Scripts\pip.exe" install -r requirements.txt --quiet
  if errorlevel 1 (
    echo [LOI] Cai dat thu vien that bai.
    pause & exit /b 1
  )
  echo [SETUP] Hoan tat.
)

:: 3. Kill ALL processes on port (lap 3 lan de kill ca reloader + worker cua uvicorn)
echo [RUN] Kiem tra port %PORT%...
for /L %%i in (1,1,3) do (
  for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":%PORT% "') do (
    if "%%p" neq "0" (
      echo [RUN]   - Dong PID %%p /T ...
      taskkill /F /T /PID %%p >nul 2>&1
    )
  )
  timeout /t 1 /nobreak >nul
)
echo [RUN] Port %PORT% san sang.

:: 4. Chay server
echo.
echo  +------------------------------------------+
echo  ^|  Server: http://%HOST%:%PORT%               ^|
echo  ^|  Nhan Ctrl+C de dung server              ^|
echo  +------------------------------------------+
echo.

"%VENV%\Scripts\python.exe" -m uvicorn main:app --host %HOST% --port %PORT% --reload

echo.
echo [INFO] Server da dung.
pause
endlocal
