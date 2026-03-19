@echo off
title Notary Server :8000
cd /d D:\notary_app\notary_v2
python -m uvicorn main:app --reload --port 8000
pause
