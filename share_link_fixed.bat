@echo off
setlocal EnableExtensions
chcp 65001 >nul

REM === CONFIG ===
set "PROJECT_DIR=%~dp0"
set "HOST=127.0.0.1"
set "PORT=8000"
set "CF_BIN=%PROJECT_DIR%cloudflared.exe"
set "TOKEN_FILE=%PROJECT_DIR%cloudflared_token.txt"

cd /d "%PROJECT_DIR%" || (echo [ERR] Khong vao duoc thu muc du an & exit /b 1)

if not exist "%CF_BIN%" (
  echo [ERR] Khong tim thay cloudflared.exe tai: %CF_BIN%
  exit /b 1
)

if not exist "%TOKEN_FILE%" (
  echo [ERR] Chua co token.
  echo [TIP] Tao file cloudflared_token.txt va dan Tunnel Token vao dong dau tien.
  exit /b 1
)

set /p TUNNEL_TOKEN=<"%TOKEN_FILE%"
if "%TUNNEL_TOKEN%"=="" (
  echo [ERR] Tunnel token rong trong %TOKEN_FILE%
  exit /b 1
)

echo.
echo [RUN] Kiem tra server local tai http://%HOST%:%PORT% ...
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul
if errorlevel 1 (
  echo [ERR] Chua co server o cong %PORT%.
  echo [TIP] Chay run.bat truoc, sau do chay lai share_link_fixed.bat
  exit /b 1
)

echo.
echo [RUN] Bat Named Tunnel (link co dinh tren hostname da cau hinh).
echo [INFO] Nhan Ctrl + C de dong tunnel khi dung xong.
echo.
"%CF_BIN%" tunnel run --token "%TUNNEL_TOKEN%"

endlocal
