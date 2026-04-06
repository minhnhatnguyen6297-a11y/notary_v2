@echo off
setlocal DisableDelayedExpansion
title VPS Logs

set "PROJECT_DIR=%~dp0"
set "SCRIPT_DIR=%PROJECT_DIR%deploy\vps"
set "PS_SCRIPT=%SCRIPT_DIR%\view_vps_logs.ps1"
set "CONFIG_FILE=%SCRIPT_DIR%\ssh_credentials.env"

if not "%~1"=="" (
  set "CONFIG_FILE=%~f1"
)

if not exist "%PS_SCRIPT%" (
  echo [LOI] Khong tim thay script:
  echo       %PS_SCRIPT%
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -ConfigPath "%CONFIG_FILE%"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo [LOI] Xem log VPS that bai voi ma loi %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
