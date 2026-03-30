@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

set "PROJECT_DIR=%~dp0"
set "VENV_PYTHON=%PROJECT_DIR%venv\Scripts\python.exe"
set "VENV_PIP=%PROJECT_DIR%venv\Scripts\pip.exe"
set "AUTO_MODE=0"

if /I "%~1"=="--auto" set "AUTO_MODE=1"

cd /d "%PROJECT_DIR%"

echo ========================================================
echo      CAI DAT MODULE LOCAL OCR (RapidOCR-Only)
echo ========================================================
echo.
echo [INFO ] Goi cai dat nay toi uu cho RapidOCR + ONNX Runtime.
echo [INFO ] Local OCR da duoc toi gian theo RapidOCR-only.
echo.

if "%AUTO_MODE%"=="0" pause

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Khong tim thay moi truong ao 'venv'. Vui long chay setup.bat truoc!
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

if not exist "%VENV_PIP%" (
    echo [ERROR] Khong tim thay pip trong venv. Vui long chay setup.bat truoc!
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo [*] Don dependency OCR cu (neu co)...
"%VENV_PIP%" uninstall -y easyocr vietocr opencv-python opencv-python-headless >nul 2>&1

echo [*] Cai dat RapidOCR + ONNX Runtime + OpenCV...
"%VENV_PIP%" install rapidocr-onnxruntime onnxruntime opencv-python==4.10.0.84 "numpy<2"
if errorlevel 1 (
    echo [Loi] RapidOCR/OpenCV...
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo [*] Khoa lai baseline NumPy de dam bao on dinh ONNX/OpenCV...
"%VENV_PIP%" install "numpy<2"
if errorlevel 1 (
    echo [Loi] NumPy baseline...
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo.
echo ========================================================
echo   CAI DAT THANH CONG! Local OCR RapidOCR da san sang
echo ========================================================
echo.

if "%AUTO_MODE%"=="0" pause
