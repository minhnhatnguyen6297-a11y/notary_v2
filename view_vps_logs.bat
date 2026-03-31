@echo off
setlocal
chcp 65001 >nul

set "PROJECT_DIR=%~dp0"
set "SCRIPT_PATH=%PROJECT_DIR%deploy\vps\view_vps_logs.ps1"

if not exist "%SCRIPT_PATH%" (
  echo [ERROR] Khong tim thay script xem log:
  echo         %SCRIPT_PATH%
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_PATH%" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] Xem log that bai. Ma loi: %EXIT_CODE%
  echo [INFO ] Kiem tra file deploy\vps\ssh_credentials.env
  pause
)

exit /b %EXIT_CODE%
