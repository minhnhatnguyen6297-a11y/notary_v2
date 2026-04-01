@echo off
setlocal DisableDelayedExpansion
title VPS SSH 1-Click

set "PROJECT_DIR=%~dp0"
set "SCRIPT_DIR=%PROJECT_DIR%deploy\vps"
set "PS_SCRIPT=%SCRIPT_DIR%\connect_vps.ps1"
set "CONFIG_FILE=%SCRIPT_DIR%\ssh_credentials.env"
set "BIN_DIR=%SCRIPT_DIR%\bin"
set "PLINK_PATH=%BIN_DIR%\plink.exe"
set "MODE=interactive"

if /I "%~1"=="--app" (
  set "MODE=app"
  if not "%~2"=="" set "CONFIG_FILE=%~f2"
) else if not "%~1"=="" (
  set "CONFIG_FILE=%~f1"
)

if /I "%MODE%"=="app" goto RUN_APP

if not exist "%CONFIG_FILE%" goto MISSING_CONFIG

for /f "usebackq eol=# tokens=1* delims==" %%A in ("%CONFIG_FILE%") do (
  call :SET_CFG "%%~A" "%%~B"
)

if "%VPS_HOST%"=="" goto BAD_CONFIG
if "%VPS_USER%"=="" goto BAD_CONFIG
if "%VPS_PASSWORD%"=="" goto BAD_CONFIG
if "%VPS_PORT%"=="" set "VPS_PORT=22"

if not exist "%PLINK_PATH%" (
  echo [RUN] Dang tai plink.exe...
  if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Invoke-WebRequest -UseBasicParsing -Uri 'https://the.earth.li/~sgtatham/putty/latest/w64/plink.exe' -OutFile '%PLINK_PATH%'"
  if errorlevel 1 (
    echo [LOI] Khong tai duoc plink.exe
    goto END_FAIL
  )
)

echo [RUN] Dang ket noi toi %VPS_USER%@%VPS_HOST%:%VPS_PORT% ...
if "%VPS_HOSTKEY%"=="" (
  "%PLINK_PATH%" -ssh "%VPS_USER%@%VPS_HOST%" -P "%VPS_PORT%" -pw "%VPS_PASSWORD%"
) else (
  "%PLINK_PATH%" -ssh "%VPS_USER%@%VPS_HOST%" -P "%VPS_PORT%" -pw "%VPS_PASSWORD%" -hostkey "%VPS_HOSTKEY%"
)

set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo [LOI] SSH ket thuc voi ma loi %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%

:RUN_APP
if not exist "%PS_SCRIPT%" (
  echo [LOI] Khong tim thay script:
  echo       %PS_SCRIPT%
  goto END_FAIL
)

if "%~2"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -ConfigPath "%CONFIG_FILE%"
)
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo [LOI] Che do --app that bai voi ma loi %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%

:MISSING_CONFIG
echo [LOI] Khong tim thay file cau hinh:
echo       %CONFIG_FILE%
echo.
echo [GOI Y] Tao file bang lenh:
echo        copy deploy\vps\ssh_credentials.example deploy\vps\ssh_credentials.env
goto END_FAIL

:BAD_CONFIG
echo [LOI] File cau hinh VPS thieu thong tin bat buoc.
echo       Can co: VPS_HOST, VPS_USER, VPS_PASSWORD
echo       File: %CONFIG_FILE%
goto END_FAIL

:END_FAIL
echo.
pause
exit /b 1

:SET_CFG
if /I "%~1"=="VPS_HOST" set "VPS_HOST=%~2"
if /I "%~1"=="VPS_PORT" set "VPS_PORT=%~2"
if /I "%~1"=="VPS_USER" set "VPS_USER=%~2"
if /I "%~1"=="VPS_PASSWORD" set "VPS_PASSWORD=%~2"
if /I "%~1"=="VPS_HOSTKEY" set "VPS_HOSTKEY=%~2"
goto :eof
