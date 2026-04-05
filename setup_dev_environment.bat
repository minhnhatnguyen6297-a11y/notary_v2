@echo off
setlocal EnableDelayedExpansion
title Setup Claude Code + Codex - notary_v2
color 0A

echo.
echo ============================================================
echo   SETUP TU DONG - Claude Code + Codex MCP
echo   Danh cho du an notary_v2
echo ============================================================
echo.

:: ============================================================
:: BUOC 1 - Kiem tra quyen Admin
:: ============================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Can chay voi quyen Administrator!
    echo       Click phai vao file nay > Run as administrator
    echo.
    pause
    exit /b 1
)
echo [OK] Dang chay voi quyen Administrator

:: ============================================================
:: BUOC 2 - Kiem tra Node.js
:: ============================================================
echo.
echo [1/6] Kiem tra Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Node.js chua duoc cai. Dang tai va cai dat...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "Invoke-WebRequest -Uri 'https://nodejs.org/dist/v20.11.0/node-v20.11.0-x64.msi' -OutFile '%TEMP%\nodejs.msi'"
    msiexec /i "%TEMP%\nodejs.msi" /quiet /norestart
    if %errorlevel% neq 0 (
        echo [LOI] Cai Node.js that bai. Vui long cai thu cong tai nodejs.org
        pause
        exit /b 1
    )
    echo [OK] Node.js da duoc cai dat
) else (
    for /f "tokens=*" %%v in ('node --version') do echo [OK] Node.js %%v da co san
)

:: ============================================================
:: BUOC 3 - Set PATH vinh vien
:: ============================================================
echo.
echo [2/6] Thiet lap PATH he thong...
setx PATH "%PATH%;C:\Program Files\nodejs;%APPDATA%\npm" /M >nul 2>&1
set "PATH=%PATH%;C:\Program Files\nodejs;%APPDATA%\npm"
echo [OK] PATH da duoc cap nhat

:: ============================================================
:: BUOC 4 - Cai Claude Code
:: ============================================================
echo.
echo [3/6] Cai dat Claude Code...
call npm install -g @anthropic-ai/claude-code >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Cai Claude Code that bai
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('claude --version 2^>nul') do echo [OK] Claude Code %%v da san sang

:: ============================================================
:: BUOC 5 - Cai Codex CLI
:: ============================================================
echo.
echo [4/6] Cai dat Codex CLI...
call npm install -g @openai/codex >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Cai Codex CLI that bai
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('codex --version 2^>nul') do echo [OK] Codex %%v da san sang

:: ============================================================
:: BUOC 6 - Thiet lap PowerShell Execution Policy
:: ============================================================
echo.
echo [5/6] Thiet lap PowerShell Execution Policy...
powershell -NoProfile -Command "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force"
echo [OK] PowerShell da duoc cau hinh

:: ============================================================
:: BUOC 7 - Thiet lap MCP Codex cho du an
:: ============================================================
echo.
echo [6/6] Ket noi Codex MCP vao Claude Code...

:: Tim thu muc du an (cung cap qua tham so hoac nhap tay)
set "PROJECT_DIR=%~1"
if "%PROJECT_DIR%"=="" (
    echo.
    echo Nhap duong dan thu muc du an notary_v2:
    echo Vi du: D:\notary_app\notary_v2
    set /p PROJECT_DIR="Thu muc: "
)

if not exist "%PROJECT_DIR%" (
    echo [LOI] Khong tim thay thu muc: %PROJECT_DIR%
    echo       Vui long kiem tra lai duong dan
    pause
    exit /b 1
)

:: Tao file .mcp.json dung cau hinh stdio
echo { > "%PROJECT_DIR%\.mcp.json"
echo   "mcpServers": { >> "%PROJECT_DIR%\.mcp.json"
echo     "codex": { >> "%PROJECT_DIR%\.mcp.json"
echo       "command": "codex", >> "%PROJECT_DIR%\.mcp.json"
echo       "args": ["mcp-server"] >> "%PROJECT_DIR%\.mcp.json"
echo     } >> "%PROJECT_DIR%\.mcp.json"
echo   } >> "%PROJECT_DIR%\.mcp.json"
echo } >> "%PROJECT_DIR%\.mcp.json"

echo [OK] File .mcp.json da duoc tao tai: %PROJECT_DIR%

:: ============================================================
:: HOAN THANH
:: ============================================================
echo.
echo ============================================================
echo   CAI DAT HOAN TAT!
echo ============================================================
echo.
echo   Buoc tiep theo:
echo   1. Dang nhap Claude:  cd %PROJECT_DIR% ^&^& claude
echo      (trinh duyet tu mo, dang nhap Claude Pro)
echo.
echo   2. Dang nhap Codex:   codex login
echo      (trinh duyet tu mo, dang nhap ChatGPT Plus)
echo.
echo   3. Mo VS Code:        code %PROJECT_DIR%
echo      Cai extension: Claude Code for VS Code
echo.
echo   4. Vao chatgpt.com/codex de giao task cho Codex
echo      Claude se tu dong review code
echo.
echo ============================================================
echo.
set /p OPEN_VSCODE="Mo VS Code ngay bay gio? (Y/N): "
if /i "%OPEN_VSCODE%"=="Y" (
    code "%PROJECT_DIR%" 2>nul
    if %errorlevel% neq 0 (
        echo [!] VS Code chua duoc cai. Tai tai: https://code.visualstudio.com
    )
)

echo.
echo Nhan phim bat ky de dong...
pause >nul
exit /b 0
