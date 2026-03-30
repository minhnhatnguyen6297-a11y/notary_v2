@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "PROJECT_DIR=%~dp0"
set "VENV=%PROJECT_DIR%venv"
set "VENV_PYTHON=%VENV%\Scripts\python.exe"
set "VENV_PIP=%VENV%\Scripts\pip.exe"
set "PORT=8000"
set "HOST=127.0.0.1"
set "PROJECT_DIR_F=%PROJECT_DIR:\=/%"
set "CELERY_BROKER_URL=sqlalchemy+sqlite:///%PROJECT_DIR_F%ocr_jobs.db"
set "CELERY_RESULT_BACKEND=db+sqlite:///%PROJECT_DIR_F%ocr_jobs.db"
set "PYTHON_CMD="

cd /d "%PROJECT_DIR%"

echo.
echo  Cong chung -- Quan ly Ho so Thua ke
echo  =====================================

:: 1. Xac dinh Python
if exist "%VENV_PYTHON%" (
  set "PYTHON_CMD=%VENV_PYTHON%"
) else (
  python --version >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
  py -3.10 --version >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=py -3.10"
)
if not defined PYTHON_CMD (
  py -3 --version >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
  echo.
  echo [LOI] Khong tim thay Python 3.10+ de khoi tao moi truong.
  echo       Neu da cai Python, hay tick Add python.exe to PATH roi chay lai.
  echo.
  pause
  exit /b 1
)

:: 2. Tao venv neu chua co
if not exist "%VENV_PYTHON%" (
  echo [SETUP] Tao moi truong ao (venv^)...
  %PYTHON_CMD% -m venv "%VENV%"
  if errorlevel 1 (
    echo [LOI] Khong tao duoc venv.
    pause & exit /b 1
  )
  echo [SETUP] Cai dat thu vien tu requirements.txt...
  "%VENV_PIP%" install -r requirements.txt --quiet
  if errorlevel 1 (
    echo [LOI] Cai dat thu vien that bai.
    pause & exit /b 1
  )
  echo [SETUP] Hoan tat.
)

:: 3. Kiem tra Local OCR dependency
echo [RUN] Kiem tra Local OCR...
"%VENV_PYTHON%" -c "import cv2, numpy, onnxruntime; from rapidocr_onnxruntime import RapidOCR; assert int(numpy.__version__.split('.')[0]) < 2"
if errorlevel 1 (
  echo [RUN] Thieu hoac lech dependency Local OCR. Dang tu cai dat...
  call "%PROJECT_DIR%install_local_ocr.bat" --auto
  if errorlevel 1 (
    echo [LOI] Khong the cai dat Local OCR tu dong.
    pause & exit /b 1
  )
  "%VENV_PYTHON%" -c "import cv2, numpy, onnxruntime; from rapidocr_onnxruntime import RapidOCR; assert int(numpy.__version__.split('.')[0]) < 2"
  if errorlevel 1 (
    echo [LOI] Local OCR van chua san sang sau khi cai dat.
    pause & exit /b 1
  )
)
echo [RUN] Local OCR san sang.

:: 3.1 Tu dong bat model OCR rec tieng Viet/Latin neu co san local
set "OCR_MODEL_DIR=%PROJECT_DIR%models\rapidocr"
if not exist "%OCR_MODEL_DIR%" mkdir "%OCR_MODEL_DIR%"
set "OCR_REC_MODEL="
set "OCR_REC_KEYS="

if defined LOCAL_OCR_REC_MODEL_PATH (
  if exist "%LOCAL_OCR_REC_MODEL_PATH%" set "OCR_REC_MODEL=%LOCAL_OCR_REC_MODEL_PATH%"
)
if defined LOCAL_OCR_REC_KEYS_PATH (
  if exist "%LOCAL_OCR_REC_KEYS_PATH%" set "OCR_REC_KEYS=%LOCAL_OCR_REC_KEYS_PATH%"
)

if not defined OCR_REC_MODEL (
  for %%f in (
    "%OCR_MODEL_DIR%\vi_PP-OCRv4_rec_infer.onnx"
    "%OCR_MODEL_DIR%\vi_PP-OCRv3_rec_infer.onnx"
    "%OCR_MODEL_DIR%\latin_PP-OCRv5_mobile_rec.onnx"
    "%OCR_MODEL_DIR%\latin_PP-OCRv4_mobile_rec.onnx"
    "%OCR_MODEL_DIR%\latin_PP-OCRv3_rec_infer.onnx"
    "%OCR_MODEL_DIR%\latin_PP-OCRv3_mobile_rec.onnx"
  ) do (
    if not defined OCR_REC_MODEL if exist "%%~f" set "OCR_REC_MODEL=%%~f"
  )
)

if not defined OCR_REC_MODEL (
  echo [RUN] Chua co OCR rec model local. Dang thu tai tu dong Latin model...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ProgressPreference='SilentlyContinue'; $ErrorActionPreference='Stop';" ^
    "$dir='%OCR_MODEL_DIR%'; New-Item -ItemType Directory -Force -Path $dir | Out-Null;" ^
    "Invoke-WebRequest -UseBasicParsing -Uri 'https://huggingface.co/breezedeus/cnocr-ppocr-latin_PP-OCRv3/resolve/main/latin_PP-OCRv3_rec_infer.onnx' -OutFile (Join-Path $dir 'latin_PP-OCRv3_rec_infer.onnx');" ^
    "Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/dict/latin_dict.txt' -OutFile (Join-Path $dir 'latin_dict.txt');"
  if not errorlevel 1 (
    if exist "%OCR_MODEL_DIR%\latin_PP-OCRv3_rec_infer.onnx" set "OCR_REC_MODEL=%OCR_MODEL_DIR%\latin_PP-OCRv3_rec_infer.onnx"
    if exist "%OCR_MODEL_DIR%\latin_dict.txt" set "OCR_REC_KEYS=%OCR_MODEL_DIR%\latin_dict.txt"
    echo [RUN] Da tai xong OCR rec model vao %OCR_MODEL_DIR%.
  ) else (
    echo [WARN] Tai model OCR tu dong that bai. Se fallback model mac dinh.
  )
)

if not defined OCR_REC_KEYS (
  for %%f in (
    "%OCR_MODEL_DIR%\vi_dict.txt"
    "%OCR_MODEL_DIR%\latin_dict.txt"
    "%OCR_MODEL_DIR%\ppocr_keys_v1.txt"
  ) do (
    if not defined OCR_REC_KEYS if exist "%%~f" set "OCR_REC_KEYS=%%~f"
  )
)

if defined OCR_REC_MODEL (
  set "LOCAL_OCR_REC_MODEL_PATH=%OCR_REC_MODEL%"
  if defined OCR_REC_KEYS (
    set "LOCAL_OCR_REC_KEYS_PATH=%OCR_REC_KEYS%"
  ) else (
    set "LOCAL_OCR_REC_KEYS_PATH="
  )
  echo [RUN] Bat OCR rec model: %LOCAL_OCR_REC_MODEL_PATH%
  if defined LOCAL_OCR_REC_KEYS_PATH (
    echo [RUN] OCR rec keys      : %LOCAL_OCR_REC_KEYS_PATH%
  ) else (
    echo [RUN] OCR rec keys      : ^<khong can/khong tim thay^>
  )
) else (
  set "LOCAL_OCR_REC_MODEL_PATH="
  set "LOCAL_OCR_REC_KEYS_PATH="
  echo [WARN] Chua tim thay model rec tieng Viet/Latin trong:
  echo [WARN]   %OCR_MODEL_DIR%
  echo [WARN] He thong se fallback model mac dinh - de mat dau tieng Viet.
)

:: 4. Dong tat ca process cu (server + worker)
echo [RUN] Dong cac process cu...
taskkill /F /FI "WINDOWTITLE eq Celery Worker" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Server: Notary" >nul 2>&1
taskkill /F /FI "IMAGENAME eq uvicorn.exe" >nul 2>&1

:: 5. Kill ALL processes on port (lap 3 lan de kill ca reloader + worker cua uvicorn)
echo [RUN] Kiem tra port %PORT%...
for /L %%i in (1,1,3) do (
  for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":%PORT% "') do (
    if "%%p" neq "0" (
      echo [RUN]   - Dong PID %%p /T ...
      taskkill /F /T /PID %%p >nul 2>&1
    )
  )
  timeout /t 1 /nobreak >nul
)
echo [RUN] Port %PORT% san sang.

:: 6. Khoi dong Celery worker (Local OCR)
echo [RUN] Khoi dong Celery worker...
if not exist "logs" mkdir logs
if not exist "tmp" mkdir tmp
if not exist "tmp\ocr" mkdir tmp\ocr
del /q "ocr_jobs.db" >nul 2>&1
del /q "tmp\ocr\*" >nul 2>&1
set PYTHONFAULTHANDLER=1
echo [RUN] Da don broker local cu (ocr_jobs.db) truoc khi boot worker.
start "Celery Worker" /D "%PROJECT_DIR%" cmd /k ""%VENV_PYTHON%" -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO"
timeout /t 2 /nobreak >nul

:: 7. Chay server
echo.
echo  +------------------------------------------+
echo  ^|  Server: http://%HOST%:%PORT%               ^|
echo  ^|  Nhan Ctrl+C de dung server              ^|
echo  +------------------------------------------+
echo.

start "Server: Notary" "%VENV_PYTHON%" -m uvicorn main:app --host %HOST% --port %PORT%

:: Cho server khoi dong hoan toan roi moi mo trinh duyet
echo [RUN] Dang cho server san sang...
set /A WAIT_COUNT=0
:WAIT_SERVER
set /A WAIT_COUNT+=1
set "FOUND_PORT="
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":%PORT% " ^| findstr /V "TIME_WAIT"') do set FOUND_PORT=1
if defined FOUND_PORT (
  start "" "http://%HOST%:%PORT%"
  goto :SERVER_READY
)
if %WAIT_COUNT% GEQ 20 (
  echo [WARN] Server khoi dong cham, hay mo thu cong: http://%HOST%:%PORT%
  goto :SERVER_READY
)
timeout /t 1 /nobreak >nul
goto :WAIT_SERVER

:SERVER_READY

echo.
echo [INFO] He thong da khoi dong (server + worker).
echo        Mo trinh duyet: http://%HOST%:%PORT%
echo        Xem log worker truc tiep tren cua so "Celery Worker".
echo        De dung: dong 2 cua so Server va Celery Worker.
echo.
pause

echo.
echo [INFO] Server da dung.
pause
endlocal
