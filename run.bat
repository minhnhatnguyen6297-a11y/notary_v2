@echo off
chcp 65001 >nul
setlocal

set "PROJECT_DIR=%~dp0"
set "VENV=%PROJECT_DIR%venv"
set "PYTHON=%VENV%\Scripts\python.exe"
cd /d "%PROJECT_DIR%"

if not exist "%PYTHON%" (
  py -3 -m venv "%VENV%" || goto :error
  "%PYTHON%" -m pip install --upgrade pip --quiet || goto :error
  "%PYTHON%" -m pip install -r requirements.txt || goto :error
)

if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul
"%PYTHON%" scripts\ensure_zalo_env.py ".env" 5368709120 168 104857600 168

echo Server: http://127.0.0.1:8000
"%PYTHON%" -m uvicorn main:app --host 127.0.0.1 --port 8000
exit /b %errorlevel%

:error
echo [LOI] Khong the khoi dong ung dung.
exit /b 1
