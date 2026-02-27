@echo off
setlocal EnableExtensions
chcp 65001 >nul

REM === CONFIG ===
set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%venv"
set "PY=py -3.13"

echo.
echo ==============================
echo       NOTARY_V2 SETUP
echo ==============================
echo.

cd /d "%PROJECT_DIR%" || (
  echo [ERR] Khong vao duoc thu muc du an
  pause
  exit /b 1
)

REM 1) Tao venv neu chua co
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [SETUP] Dang tao virtual environment...
  %PY% -m venv "%VENV_DIR%" || (
    echo [ERR] Tao venv that bai
    pause
    exit /b 1
  )
) else (
  echo [SETUP] Virtual environment da ton tai.
)

REM 2) Nang cap pip
echo [SETUP] Nang cap pip...
"%VENV_DIR%\Scripts\python.exe" -m pip install -U pip

REM 3) Cai thu vien (pin phien ban on dinh)
echo [SETUP] Dang cai thu vien...
"%VENV_DIR%\Scripts\python.exe" -m pip install ^
  SQLAlchemy==2.0.47 ^
  fastapi==0.133.1 ^
  uvicorn[standard]==0.41.0 ^
  jinja2==3.1.6 ^
  aiosqlite==0.22.1 ^
  openpyxl==3.1.5 ^
  python-multipart

REM 4) In version de kiem tra
echo.
echo [SETUP] Kiem tra phien ban:
"%VENV_DIR%\Scripts\python.exe" -c "import sqlalchemy,fastapi,uvicorn,jinja2,aiosqlite,openpyxl; print('SQLAlchemy',sqlalchemy.__version__); print('FastAPI',fastapi.__version__); print('Uvicorn',uvicorn.__version__); print('Jinja2',jinja2.__version__); print('aiosqlite',aiosqlite.__version__); print('openpyxl',openpyxl.__version__)"

echo.
echo ==============================
echo      SETUP HOAN TAT
echo ==============================
echo.
pause
endlocal