@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

set "PROJECT_DIR=%~dp0"
set "VENV=%PROJECT_DIR%venv"
set "VENV_PYTHON=%VENV%\Scripts\python.exe"
set "VENV_PIP=%VENV%\Scripts\pip.exe"
set "PYTHON_CMD="
set "PYTHON_VER="
set "PYTHON_VER_RAW="

cd /d "%PROJECT_DIR%"

echo ========================================================
echo        TOOL CAI DAT HE THONG CONG CHUNG HO SO
echo ========================================================
echo.

:: 1. Tim Python hop le
if exist "%VENV_PYTHON%" (
    set "PYTHON_CMD=%VENV_PYTHON%"
    for /f "tokens=2" %%v in ('"%VENV_PYTHON%" --version 2^>nul') do set "PYTHON_VER_RAW=%%v"
    echo [OK] Da tim thay moi truong ao 'venv' san co.
    goto :CHECK_PY_VERSION
)

python --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    for /f "tokens=2" %%v in ('python --version 2^>nul') do set "PYTHON_VER_RAW=%%v"
)

if not defined PYTHON_CMD (
    py -3.10 --version >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3.10"
        for /f "tokens=2" %%v in ('py -3.10 --version 2^>nul') do set "PYTHON_VER_RAW=%%v"
    )
)

if not defined PYTHON_CMD (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3"
        for /f "tokens=2" %%v in ('py -3 --version 2^>nul') do set "PYTHON_VER_RAW=%%v"
    )
)

if not defined PYTHON_CMD (
    echo [ERROR] Khong tim thay Python 3.10+.
    echo [ERROR] Hay cai Python 3.10.11 64-bit va tick Add python.exe to PATH.
    echo [INFO ] Xem them: LOCAL_AI_INSTALL_GUIDE.md
    echo.
    pause
    exit /b 1
)

:CHECK_PY_VERSION
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VER_RAW%") do (
    set "PY_MAJ=%%a"
    set "PY_MIN=%%b"
)

if not defined PY_MAJ set "PY_MAJ=0"
if not defined PY_MIN set "PY_MIN=0"

if %PY_MAJ% LSS 3 (
    echo [ERROR] Python %PYTHON_VER_RAW% qua cu. Can Python 3.10 tro len.
    pause
    exit /b 1
)
if %PY_MAJ% EQU 3 if %PY_MIN% LSS 10 (
    echo [ERROR] Python %PYTHON_VER_RAW% qua cu. Can Python 3.10 tro len.
    pause
    exit /b 1
)

set "PYTHON_VER=%PYTHON_VER_RAW%"
echo [OK] Da tim thay Python phien ban %PYTHON_VER%
if %PY_MAJ% EQU 3 if %PY_MIN% GTR 10 (
    echo [WARN] Local OCR on dinh nhat tren Python 3.10.x.
    echo [WARN] Neu can YOLO + RapidOCR, uu tien Python 3.10.11 de tranh loi DLL/wheel.
)

:: 2. Khoi tao Virtual Environment
echo.
if exist "%VENV_PYTHON%" goto :VENV_READY
echo [*] Dang tao moi truong ao python 'venv'...
%PYTHON_CMD% -m venv "%VENV%"
if errorlevel 1 (
    echo [ERROR] Tao venv that bai.
    pause
    exit /b 1
)
echo [OK] Tao xong.

:VENV_READY
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Khong tim thay %VENV_PYTHON%
    pause
    exit /b 1
)
if not exist "%VENV_PIP%" (
    echo [ERROR] Khong tim thay %VENV_PIP%
    pause
    exit /b 1
)

:: 3. Nang cap pip
echo.
echo [*] Dang nang cap pip...
"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Nang cap pip that bai.
    pause
    exit /b 1
)

:: 4. Cai dat thu vien requirements.txt
echo.
echo [*] Dang cai dat cac thu vien can thiet tu requirements.txt...
"%VENV_PIP%" install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Cai dat thu vien that bai. Vui long kiem tra ket noi mang.
    pause
    exit /b 1
)
echo [OK] Cai dat thu vien thanh cong.

:: 5. Khoi tao file bien moi truong .env
echo.
if not exist ".env" (
    echo [*] Phat hien chua co file .env, dang sao chep tu .env.example...
    copy .env.example .env >nul
    if errorlevel 1 (
        echo [ERROR] Khong tao duoc file .env
        pause
        exit /b 1
    )
    echo [!] Da tao file .env. VUI LONG MO FILE NAY DE DIEN OPENAI_API_KEY neu can Cloud OCR.
) else (
    echo [OK] File .env da ton tai.
)

:: 6. Goi y Local OCR baseline
echo.
echo ========================================================
echo    CAI DAT THANH CONG! WEB APP DA SAN SANG
echo ========================================================
echo De khoi dong Web + worker OCR:
echo "run.bat"
echo.
echo run.bat se tu kiem tra va cai Local OCR ^(YOLO + RapidOCR^) neu may dang thieu.
echo.
echo Ghi chu:
echo - Local OCR on dinh nhat tren Python 3.10.11
echo - install_local_ocr.bat van co the chay tay neu ban muon cai truoc
echo - Script install_local_ocr.bat se tu ghim numpy^<2 de tranh xung dot voi Torch
echo.
pause
