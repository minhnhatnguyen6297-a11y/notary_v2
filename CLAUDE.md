# CLAUDE.md - notary_v2

Tai lieu van hanh nhanh cho team khi lam viec voi du an `notary_v2`.
Cap nhat: 31/03/2026.

## Tong quan
- Ung dung quan ly ho so thua ke dat dai cho van phong cong chung.
- Backend: FastAPI + SQLAlchemy + SQLite.
- Frontend: Jinja2 + Bootstrap + Vanilla JS.
- Local OCR: RapidOCR-only (khong dung stack deep-learning cu trong runtime).

## Chay du an
```bash
# Windows
run.bat

# Hoac chay tay
python -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO
python -m uvicorn main:app --port 8000
```

URL mac dinh: `http://127.0.0.1:8000`

## VPS one-click
```bash
bash install_vps.sh
```

Sau khi cai dat:
- Quan ly service: `bash deploy/vps/manage_services.sh status|restart|logs`
- Tai lieu chi tiet: `docs/VPS_ONE_CLICK_SETUP.md`

## SSH 1-click cho team Windows
- Tao file `deploy/vps/ssh_credentials.env` tu mau `deploy/vps/ssh_credentials.example`
- Double-click `connect_vps.bat` de vao VPS
- Tai lieu: `docs/VPS_CONNECT_ONE_CLICK.md`

## Local OCR - RapidOCR Only

### Muc tieu
- On dinh tren may Windows local.
- Giam phu thuoc nang.
- Uu tien toc do va kha nang debug.

### Pipeline xu ly hien tai
1. Nhan anh tu client.
2. Tien xu ly nhe:
   - sharpen kernel `[[0,-1,0],[-1,5,-1],[0,-1,0]]`.
   - Khong dung bilateral filter.
3. Cat tai lieu:
   - Smart Crop OpenCV (Canny + contour) voi soft fallback ve full image.
   - Chuan hoa anh OCR voi `max_side_len=1200`.
4. Triage V2 (feature flag):
   - Tao proxy image, thu 4 huong `0/90/180/270`.
   - Detect nhanh Face + QR + MRZ-score.
   - Gan state: `front_old`, `front_new`, `back_new`, `back_old` (hoac `unknown`).
   - Xoay anh goc high-res theo huong da chon.
5. Targeted extraction:
   - Front ROI `0..55%` de lay ID/field mat truoc.
   - Back ROI `70..100%` de uu tien MRZ mat sau.
   - Regex MRZ: `IDVNM\\d{10}(\\d{12})`.
6. Deterministic merge:
   - Ghep cap tuyet doi theo CCCD 12 so.
   - Anh khong co ID dua vao `unpaired` + warning.
   - Delta merge bo sung field thieu theo side/profile.
7. Hybrid fallback:
   - Neu triage/extract V2 thieu tin cay, fallback legacy khi `LOCAL_OCR_TRIAGE_FALLBACK_LEGACY=1`.
8. Tra ket qua + warnings cho frontend de human-in-the-loop.
9. Co log timing/telemetry chi tiet theo stage.

### Engine / nhan dang
- `summary.local_engine`: `RapidOCR (CPU)` hoac `RapidOCR (GPU)`
- Co ho tro custom rec model qua env:
  - `LOCAL_OCR_REC_MODEL_PATH`
  - `LOCAL_OCR_REC_KEYS_PATH`

### Luat du lieu quan trong
- Ten: uu tien QR > mat truoc > MRZ (MRZ chi fallback).
- Dia chi:
  - CCCD cu (truoc 01/07/2024): block `Noi thuong tru` o mat truoc.
  - CCCD moi (sau 01/07/2024): block `Noi cu tru` o mat sau.
- `ngay_het_han` khong dua vao du lieu participant nghiep vu.

## API Local OCR
- `POST /api/ocr/local/submit`
- `POST /api/ocr/local/submit-batch`
- `GET /api/ocr/local/status/{job_id}`

### Co `client_qr_failed`
- `client_qr_failed` la telemetry tu frontend; backend van co quyen QR rescue.
- Batch dung `client_qr_failed_json` (list bool theo thu tu file).

## Task worker
- Task name giu nguyen:
  - `process_ocr_job`
  - `process_ocr_batch_job`
- Worker startup chuan:
  - `python -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO`

## Script setup/run
- `setup.bat`: tao venv + cai dependency chinh + tao `.env`.
- `run.bat`: check dependency Local OCR RapidOCR stack.
- `install_local_ocr.bat`: cai RapidOCR stack toi gian cho local.
- `requirements-gpu.txt`: optional cho may NVIDIA (onnxruntime-gpu).

## Bien moi truong lien quan Local OCR
- `LOCAL_OCR_MIN_BOX_SCORE`
- `LOCAL_OCR_REC_MODEL_PATH`
- `LOCAL_OCR_REC_KEYS_PATH`
- `LOCAL_OCR_SMART_CROP_MIN_CONF`
- `LOCAL_OCR_MAX_SIDE_LEN`
- `LOCAL_OCR_TIMING_LOG`
- `LOCAL_OCR_TIMING_SLOW_MS`
- `LOCAL_OCR_TRIAGE_V2`
- `LOCAL_OCR_TRIAGE_FALLBACK_LEGACY`
- `LOCAL_OCR_TRIAGE_PROXY_MAX_SIDE`
- `LOCAL_OCR_TRIAGE_MRZ_MIN_SCORE`
- `OCR_TEXT_LLM_MODEL`

## Backlog / Roadmap
- LLM Fallback (tu dong sua dau / bu truong) dang tam tat de toi uu toc do Local OCR.
- Da chuyen sang co che canh bao do tren UI de nguoi dung tu sua tay.
- Se phat trien lai LLM Fallback o giai doan sau.

## Quy uoc khi sua code
- Uu tien fix theo huong giu contract API hien tai.
- Khong doi ten task Celery.
- Khong thay doi schema DB neu khong bat buoc.
- Neu sua flow OCR, phai test lai bo anh regression 10 anh CCCD.

## Kiem tra nhanh truoc khi ban giao
```bash
python -m py_compile routers/ocr_local.py tasks.py
rg -n "rapidocr|onnxruntime|opencv-python|LOCAL_OCR_TRIAGE" .env.example CLAUDE.md run.bat install_local_ocr.bat
```
