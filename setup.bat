@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

echo ========================================================
echo        TOOL CAI DAT HE THONG CONG CHUNG HO SO
echo ========================================================
echo.

:: 1. Kiem tra Python
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Khong tim thay Python! Vui long cai dat Python 3.10 tro len.
    echo Hay the duong dan Python vao System PATH khi cai dat.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version') do set PY_VER=%%v
echo [OK] Da tim thay Python phien ban %PY_VER%

:: 2. Khoi tao Virtual Environment
echo.
if exist "venv\Scripts\python.exe" goto :VenvK
echo [*] Dang tao moi truong ao python 'venv'...
python -m venv venv
if !errorlevel! neq 0 (
    echo [ERROR] Tao venv that bai.
    pause
    exit /b 1
)
echo [OK] Tao xong.
goto :SkipVenv

:VenvK
echo [OK] Moi truong ao 'venv' da ton tai.

:SkipVenv
:: 3. Kich hoat va nang cap pip
echo.
echo [*] Dang nang cap pip...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1

:: 4. Cai dat thu vien requirements.txt
echo.
echo [*] Dang cai dat cac thu vien can thiet tu requirements.txt...
pip install -r requirements.txt
if !errorlevel! neq 0 (
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
    echo [!] Da tao file .env. VUI LONG MO FILE NAY DE DIEN OPENAI_API_KEY!
) else (
    echo [OK] File .env da xay dung.
)

:: Hoan tat
echo.
echo ========================================================
echo    CAI DAT THANH CONG! TREN MAY MOI SE KHONG CON LOI
echo ========================================================
echo De khoi dong may chu Web, ban hay nhay dup vao file:
echo "run.bat"
echo.
pause