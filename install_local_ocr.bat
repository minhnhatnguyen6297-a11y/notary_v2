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
echo      CAI DAT MODULE LOCAL OCR (YOLO + RapidOCR)
echo ========================================================
echo.
echo [CANH BAO]: Module nay nang khoang 2-3GB, phu thuoc vao C++ loi
echo va thuong xuyen xung dot Windows neu Python > 3.10.
echo De tranh loi 'c10.dll', ban NEN dung Python 3.10.
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

echo [*] Cai dat PyTorch phien ban on dinh (CPU) cho YOLO...
"%VENV_PIP%" install torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
    echo [Loi] PyTorch...
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo [*] Cai dat RapidOCR + ONNX Runtime + OpenCV...
"%VENV_PIP%" install rapidocr-onnxruntime onnxruntime opencv-python==4.10.0.84 "numpy<2"
if errorlevel 1 (
    echo [Loi] RapidOCR/OpenCV...
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo [*] Cai dat YOLO (Ultralytics) de cat anh + nhan dien loai giay to...
"%VENV_PIP%" install ultralytics
if errorlevel 1 (
    echo [Loi] YOLO...
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo [*] Khoa lai baseline NumPy de tranh xung dot voi Torch...
"%VENV_PIP%" install "numpy<2"
if errorlevel 1 (
    echo [Loi] NumPy baseline...
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo.
echo ========================================================
echo   CAI DAT THANH CONG! Tinh nang Local OCR da duoc mo khoa
echo ========================================================
echo.

if "%AUTO_MODE%"=="0" pause
