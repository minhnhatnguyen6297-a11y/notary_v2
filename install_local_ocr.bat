@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

echo ========================================================
echo     CAI DAT MODULE LOCAL OCR (YOLO + EasyOCR + VietOCR)
echo ========================================================
echo.
echo [CANH BAO]: Module nay nang khoang 2-3GB, phu thuoc vao C++ loi
echo va thuong xuyen xung dot Windows neu Python > 3.10. 
echo De tranh loi 'c10.dll', ban NEN dung Python 3.10.
echo.
pause

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Khong tim thay moi truong ao 'venv'. Vui long chay setup.bat truoc!
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [*] Cai dat PyTorch phien ban on dinh (CPU)...
pip install torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cpu
if !errorlevel! neq 0 echo [Loi] PyTorch... & pause & exit /b 1

echo [*] Cai dat EasyOCR (cat text box) + OpenCV + NumPy...
pip install easyocr opencv-python-headless numpy
if !errorlevel! neq 0 echo [Loi] EasyOCR/OpenCV... & pause & exit /b 1

echo [*] Cai dat VietOCR (OCR tieng Viet)...
pip install --no-deps vietocr
pip install einops gdown prefetch_generator
if !errorlevel! neq 0 echo [Loi] VietOCR... & pause & exit /b 1

echo [*] Cai dat YOLO (Ultralytics) de cat anh + nhan dien loai giay to...
pip install ultralytics
if !errorlevel! neq 0 echo [Loi] YOLO... & pause & exit /b 1

echo.
echo ========================================================
echo   CAI DAT THANH CONG! Tinh nang Local OCR da duoc mo khoa
echo ========================================================
echo.
pause
