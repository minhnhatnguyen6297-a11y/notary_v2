@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

echo ==============================================
echo        CELERY WORKER - LOCAL OCR
echo ==============================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Khong tim thay moi truong ao 'venv'.
    echo Hay chay setup.bat truoc!
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [*] Dang chay Celery worker (concurrency = 1)...
if not exist "logs" mkdir logs
echo [*] Log se duoc ghi vao logs\celery_worker.log
celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO --logfile=logs\celery_worker.log

pause
