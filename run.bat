@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "PROJECT_DIR=%~dp0"
set "VENV=%PROJECT_DIR%venv"
set "VENV_PYTHON=%VENV%\Scripts\python.exe"
set "VENV_PIP=%VENV%\Scripts\pip.exe"
set "PORT=8000"
set "HOST=127.0.0.1"

cd /d "%PROJECT_DIR%"

echo.
echo  =====================================
echo    NOTARY V2 - Quan ly Ho so Thua ke
echo  =====================================
echo.

:: ============================
::  1. KIEM TRA PYTHON
:: ============================
set "PYTHON_CMD="

where python >nul 2>&1 && python --version 2>nul | find "3." >nul && (
    set "PYTHON_CMD=python"
) || (
    where py >nul 2>&1 && (
        for /L %%v in (11,-1,10) do (
            py -3.%%v --version >nul 2>&1 && set "PYTHON_CMD=py -3.%%v" && goto :FOUND_PYTHON
        )
        py -3 --version >nul 2>&1 && set "PYTHON_CMD=py -3"
    )
)
:FOUND_PYTHON

if not defined PYTHON_CMD (
    echo [LOI] Khong tim thay Python 3.10+.
    echo.
    echo       Tai Python tai: https://www.python.org/downloads/
    echo       Khi cai nho tick "Add Python to PATH" roi chay lai file nay.
    echo.
    pause
    exit /b 1
)

%PYTHON_CMD% --version
echo [OK] Tim thay Python.
echo.

:: ============================
::  2. TAO VENV + CAI DAT
:: ============================
if not exist "%VENV_PYTHON%" (
    echo [1/3] Tao moi truong ao venv...
    %PYTHON_CMD% -m venv "%VENV%"
    if errorlevel 1 (
        echo [LOI] Khong tao duoc venv.
        pause & exit /b 1
    )

    echo [2/3] Nang cap pip...
    "%VENV_PYTHON%" -m pip install --upgrade pip --quiet
    if errorlevel 1 (
        echo [LOI] Nang cap pip that bai.
        pause & exit /b 1
    )

    echo [3/3] Cai dat thu vien tu requirements.txt...
    "%VENV_PIP%" install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [LOI] Cai dat thu vien that bai. Doc log ben tren de biet chi tiet.
        pause & exit /b 1
    )

    echo.
    echo [OK] Cai dat hoan tat.
)

:: ============================
::  3. TAO .env (neu chua co)
:: ============================
if not exist ".env" (
    if exist ".env.example" (
        echo [SETUP] Tao .env tu .env.example...
        copy ".env.example" ".env" >nul
        if errorlevel 1 (
            echo [LOI] Khong tao duoc .env.
            pause & exit /b 1
        )
        echo [OK] Da tao .env. Vui long mo file .env va nhap API key truoc khi dung OCR.
    ) else (
        echo [WARN] Khong tim thay .env.example. Tao file .env trang...
        echo # Notary V2 - .env > .env
        echo # Can nhap QWEN_API_KEY de dung Cloud OCR >> .env
    )
)

"%VENV_PYTHON%" scripts\ensure_zalo_env.py ".env" 5368709120 168
if errorlevel 1 (
    echo [LOI] Khong the chuan bi cau hinh Zalo connector.
    pause & exit /b 1
)

:: ============================
::  4. DON DEP PROCESS CU
:: ============================
echo [RUN] Don process cu...
taskkill /F /IM uvicorn.exe >nul 2>&1
for /L %%i in (1,1,3) do (
    for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":%PORT% "') do (
        if "%%p" neq "0" (
            taskkill /F /T /PID %%p >nul 2>&1
        )
    )
    timeout /t 1 /nobreak >nul
)
echo [OK] Port %PORT% da duoc giai phong.

:: ============================
::  5. CHUAN BI THU MUC
:: ============================
if not exist "logs" mkdir logs
if not exist "tmp"   mkdir tmp

set PYTHONFAULTHANDLER=1

:: ============================
::  6. KHOI DONG UVICORN SERVER
:: ============================
echo.
echo  +-----------------------------------------------+
echo  ^|  Server:   http://%HOST%:%PORT%                  ^|
echo  ^|  De dung:  dong cua so Server                   ^|
echo  +-----------------------------------------------+
echo.

start "Server: Notary" "%VENV_PYTHON%" -m uvicorn main:app --host %HOST% --port %PORT%

:: ============================
::  7. CHO SERVER ROI MO BROWSER
:: ============================
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
    echo [WARN] Server khoi dong cham. Mo thu cong: http://%HOST%:%PORT%
    goto :SERVER_READY
)
timeout /t 1 /nobreak >nul
goto :WAIT_SERVER

:SERVER_READY
echo.
echo [INFO] He thong da san sang.
echo        Server:   http://%HOST%:%PORT%
echo        Local OCR worker khong tu khoi dong; day la research path rieng.
echo        De dung:  dong cua so Server hoac tat cmd.
echo.

pause
echo [INFO] Server da dung.
pause
endlocal
