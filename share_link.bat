@echo off
setlocal EnableExtensions
chcp 65001 >nul

REM === CONFIG ===
set "PROJECT_DIR=%~dp0"
set "HOST=127.0.0.1"
set "PORT=8000"
set "CF_BIN=%PROJECT_DIR%cloudflared.exe"

cd /d "%PROJECT_DIR%" || (echo [ERR] Khong vao duoc thu muc du an & exit /b 1)

if not exist "%CF_BIN%" (
  echo [ERR] Khong tim thay cloudflared.exe tai: %CF_BIN%
  exit /b 1
)

echo.
echo [RUN] Kiem tra server local tai http://%HOST%:%PORT% ...
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul
if errorlevel 1 (
  echo [ERR] Chua co server o cong %PORT%.
  echo [TIP] Chay run.bat truoc, sau do chay lai share_link.bat
  exit /b 1
)

echo.
echo [RUN] Tao public link...
echo [INFO] Nhan Ctrl + C de dong tunnel khi dung xong.
echo.
"%CF_BIN%" tunnel --url http://%HOST%:%PORT%

endlocal
