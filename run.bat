@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "PROJECT_DIR=%~dp0"
set "VENV=%PROJECT_DIR%venv"
set "PORT=8000"
set "HOST=127.0.0.1"
set "PROJECT_DIR_F=%PROJECT_DIR:\=/%"
set "CELERY_BROKER_URL=sqlalchemy+sqlite:///%PROJECT_DIR_F%ocr_jobs.db"
set "CELERY_RESULT_BACKEND=db+sqlite:///%PROJECT_DIR_F%ocr_jobs.db"

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

:: 3. Dong tat ca process cu (server + worker)
echo [RUN] Dong cac process cu...
taskkill /F /FI "WINDOWTITLE eq Celery Worker" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Server: Notary" >nul 2>&1
taskkill /F /FI "IMAGENAME eq uvicorn.exe" >nul 2>&1

:: 4. Kill ALL processes on port (lap 3 lan de kill ca reloader + worker cua uvicorn)
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

:: 5. Khoi dong Celery worker (Local OCR)
echo [RUN] Khoi dong Celery worker...
if not exist "logs" mkdir logs
if not exist "tmp" mkdir tmp
if not exist "tmp\ocr" mkdir tmp\ocr
del /q "logs\celery_worker.log" >nul 2>&1
del /q "tmp\ocr\*" >nul 2>&1
set PYTHONFAULTHANDLER=1
set TORCH_SHOW_CPP_STACKTRACES=1
start "Celery Worker" /D "%PROJECT_DIR%" cmd /k ""%VENV%\Scripts\python.exe" -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO --logfile=logs\celery_worker.log"
timeout /t 2 /nobreak >nul
if not exist "logs\celery_worker.log" (
  echo [WARN] Worker chua tao log. Neu cua so worker trong, vui long chay lai run.bat.
)

:: 6. Chay server
echo.
echo  +------------------------------------------+
echo  ^|  Server: http://%HOST%:%PORT%               ^|
echo  ^|  Nhan Ctrl+C de dung server              ^|
echo  +------------------------------------------+
echo.

start "Server: Notary" "%VENV%\Scripts\python.exe" -m uvicorn main:app --host %HOST% --port %PORT% --reload

:: Cho server khoi dong hoan toan roi moi mo trinh duyet
echo [RUN] Dang cho server san sang...
set /A WAIT_COUNT=0
:WAIT_SERVER
set /A WAIT_COUNT+=1
set "FOUND_PORT="
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":%PORT% " ^| findstr /V "TIME_WAIT"') do set FOUND_PORT=1
if defined FOUND_PORT (
  start "" "http://%HOST%:%PORT%"
  goto :SERVER_READY
)
if %WAIT_COUNT% GEQ 20 (
  echo [WARN] Server khoi dong cham, hay mo thu cong: http://%HOST%:%PORT%
  goto :SERVER_READY
)
timeout /t 1 /nobreak >nul
goto :WAIT_SERVER

:SERVER_READY

echo.
echo [INFO] He thong da khoi dong (server + worker).
echo        Mo trinh duyet: http://%HOST%:%PORT%
echo        Log worker: logs\celery_worker.log
echo        De dung: dong 2 cua so Server va Celery Worker.
echo.
pause

echo.
echo [INFO] Server da dung.
pause
endlocal
