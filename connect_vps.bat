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
set "RAW_TERMINAL=0"
set "OPEN_BROWSER=1"
set "CLEAN_SHELL_CMD="
set "VPS_APP_SCHEME=http"
set "VPS_APP_PORT=8000"
set "VPS_APP_PATH=/"

if /I "%~1"=="--app" (
  set "MODE=app"
  if not "%~2"=="" set "CONFIG_FILE=%~f2"
) else if /I "%~1"=="--raw" (
  set "RAW_TERMINAL=1"
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
if "%VPS_APP_SCHEME%"=="" set "VPS_APP_SCHEME=http"
if "%VPS_APP_PORT%"=="" set "VPS_APP_PORT=8000"
if "%VPS_APP_PATH%"=="" set "VPS_APP_PATH=/"
if "%VPS_REPO_DIR%"=="" set "VPS_REPO_DIR=~/notary_v2"
if not "%VPS_APP_PATH:~0,1%"=="/" set "VPS_APP_PATH=/%VPS_APP_PATH%"
call :APPLY_BROWSER_FLAG "%VPS_AUTO_OPEN_BROWSER%"
call :BUILD_CLEAN_SHELL_CMD
set "APP_URL=%VPS_APP_SCHEME%://%VPS_HOST%:%VPS_APP_PORT%%VPS_APP_PATH%"

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
if "%RAW_TERMINAL%"=="1" (
  echo [RUN] Raw terminal mode: giu shell mac dinh cua VPS.
) else (
  echo [RUN] Clean shell mode: vao thang repo %VPS_REPO_DIR% va an xterm control sequence tren Windows console.
)
if not "%OPEN_BROWSER%"=="0" (
  echo [RUN] Dang mo trinh duyet: %APP_URL%
  start "" "%APP_URL%" >nul 2>&1
)
if "%VPS_HOSTKEY%"=="" (
  if "%RAW_TERMINAL%"=="1" (
    "%PLINK_PATH%" -ssh "%VPS_USER%@%VPS_HOST%" -P "%VPS_PORT%" -pw "%VPS_PASSWORD%" -t -no-antispoof
  ) else (
    "%PLINK_PATH%" -ssh "%VPS_USER%@%VPS_HOST%" -P "%VPS_PORT%" -pw "%VPS_PASSWORD%" -t -no-antispoof "%CLEAN_SHELL_CMD%"
  )
) else (
  if "%RAW_TERMINAL%"=="1" (
    "%PLINK_PATH%" -ssh "%VPS_USER%@%VPS_HOST%" -P "%VPS_PORT%" -pw "%VPS_PASSWORD%" -hostkey "%VPS_HOSTKEY%" -t -no-antispoof
  ) else (
    "%PLINK_PATH%" -ssh "%VPS_USER%@%VPS_HOST%" -P "%VPS_PORT%" -pw "%VPS_PASSWORD%" -hostkey "%VPS_HOSTKEY%" -t -no-antispoof "%CLEAN_SHELL_CMD%"
  )
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
if /I "%~1"=="VPS_APP_SCHEME" set "VPS_APP_SCHEME=%~2"
if /I "%~1"=="VPS_APP_PORT" set "VPS_APP_PORT=%~2"
if /I "%~1"=="VPS_APP_PATH" set "VPS_APP_PATH=%~2"
if /I "%~1"=="VPS_AUTO_OPEN_BROWSER" set "VPS_AUTO_OPEN_BROWSER=%~2"
if /I "%~1"=="VPS_REPO_DIR" set "VPS_REPO_DIR=%~2"
goto :eof

:BUILD_CLEAN_SHELL_CMD
set "CLEAN_SHELL_CMD=REPO_DIR='%VPS_REPO_DIR%'; if [ "${REPO_DIR#~/}" != "$REPO_DIR" ]; then REPO_DIR="$HOME/${REPO_DIR#~/}"; fi; if [ -d "$REPO_DIR" ]; then cd "$REPO_DIR"; else echo "[WARN] Khong tim thay repo dir: $REPO_DIR"; fi; exec env TERM=dumb bash -li"
goto :eof

:APPLY_BROWSER_FLAG
if /I "%~1"=="0" set "OPEN_BROWSER=0"
if /I "%~1"=="false" set "OPEN_BROWSER=0"
if /I "%~1"=="no" set "OPEN_BROWSER=0"
if /I "%~1"=="off" set "OPEN_BROWSER=0"
goto :eof
