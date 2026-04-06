@echo off
setlocal
call "%~dp0connect_vps.bat" --app %*
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
