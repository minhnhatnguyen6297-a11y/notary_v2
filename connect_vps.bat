@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "PS_SCRIPT=%PROJECT_DIR%deploy\vps\connect_vps.ps1"

if not exist "%PS_SCRIPT%" (
  echo [LOI] Khong tim thay script ket noi VPS:
  echo       %PS_SCRIPT%
  exit /b 1
)

if "%~1"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -ConfigPath "%~1"
)

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [GOI Y] Neu chua co file cau hinh, hay tao:
  echo        copy deploy\vps\ssh_credentials.example deploy\vps\ssh_credentials.env
)

exit /b %EXIT_CODE%
