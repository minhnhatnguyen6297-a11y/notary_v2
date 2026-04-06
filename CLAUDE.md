# CLAUDE.md - notary_v2

Tai lieu van hanh nhanh cho team khi lam viec voi du an `notary_v2`.
Cap nhat: 01/04/2026.

## Nguyen tac van hanh mac dinh - VPS first
- Mac dinh moi thao tac van hanh, kiem tra, restart service, xem log va sua truc tiep ban dang chay deu thuc hien tren VPS, khong lam tren local.
- Nguon su that uu tien la repo tren VPS: `/root/notary_v2`.
- Chi sua/chay local khi nguoi dung noi ro la muon lam local, hoac khi can chuan bi commit/push de dong bo len VPS.
- Tai lieu workflow chinh: `docs/VPS_WORKFLOW.md`.
- Truoc khi sua code, uu tien:
  1. SSH vao VPS.
  2. `cd /root/notary_v2`
  3. Kiem tra `git status --short --branch`
  4. Kiem tra service `bash deploy/vps/manage_services.sh status`
- Sau khi sua/cai dat tren VPS, phai uu tien restart va kiem tra lai:
  - `bash install_vps.sh --skip-system-packages` neu co doi dependency
  - `bash deploy/vps/manage_services.sh restart`
  - `bash deploy/vps/manage_services.sh logs`
- Neu commit local va VPS bi lech nhau, phai xac minh ro ben nao la ban moi nhat truoc khi tiep tuc, khong duoc mac dinh local la nguon dung.

## Tong quan
- Ung dung quan ly ho so thua ke dat dai cho van phong cong chung.
- Backend: FastAPI + SQLAlchemy + SQLite.
- Frontend: Jinja2 + Bootstrap + Vanilla JS.
- Local OCR: RapidOCR detection + VietOCR recognition (CPU-only).

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
- Workflow van hanh/mac dinh: `docs/VPS_WORKFLOW.md`
- Windows wrappers:
  - `launch_vps_app.bat`
  - `connect_vps.bat`
  - `view_vps_logs.bat`
- Log file tren VPS: `logs/web.log`, `logs/worker.log`

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
   - RapidOCR chi dung cho text detection, khong dung recognition.
   - VietOCR `vgg_transformer` doc batch cac dong chu da cat tu bounding boxes.
   - ROI loc theo `triage_state` (`front_old`, `front_new`, `back_new`, `back_old`, `unknown`) thay vi crop cung.
   - Regex MRZ: `IDVNM\\d{10}(\\d{12})`.
6. Deterministic merge:
   - Ghep cap tuyet doi theo CCCD 12 so.
   - Anh khong co ID dua vao `unpaired` + warning.
   - Delta merge bo sung field thieu theo side/profile.
7. Wide fallback:
   - Neu triage `unknown`, he thong thu `id_front` -> `id_back` -> `detail` ROI rong.
   - Khong con legacy fallback va khong con score rollback.
8. Tra ket qua + warnings cho frontend de human-in-the-loop.
9. Co log timing/telemetry chi tiet theo stage.

### Engine / nhan dang
- `summary.local_engine`: `RapidOCR det + VietOCR rec (CPU)`
- `summary.rec_model_mode`: `vgg_transformer`
- Bien moi truong Local OCR chinh:
  - `LOCAL_OCR_DET_MAX_SIDE_LEN`
  - `LOCAL_OCR_VIETOCR_MODEL`
  - `LOCAL_OCR_VIETOCR_BATCH_SIZE`
  - `LOCAL_OCR_TORCH_THREADS`
  - `LOCAL_OCR_DENOISE`
  - `LOCAL_OCR_REC_PAD_RATIO`
  - `LOCAL_OCR_REC_MIN_HEIGHT`
  - `LOCAL_OCR_REC_MAX_SCALE`

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
  - Local Windows qua `run.bat`: `python -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO`
  - VPS Linux/systemd: `python -m celery -A celery_app.celery_app worker --pool=prefork --concurrency=3 --loglevel=INFO`

## Script setup/run
- `run.bat`: script local duy nhat. Tu tao venv, tao `.env`, cai dependency app + PyTorch CPU + VietOCR/RapidOCR, khoi dong worker/server.
- `install_vps.sh`: script VPS duy nhat cho one-click install/start service.
- `requirements-gpu.txt`: optional cho may NVIDIA (onnxruntime-gpu).

## Bien moi truong lien quan Local OCR
- `LOCAL_OCR_SMART_CROP_MIN_CONF`
- `LOCAL_OCR_DET_MAX_SIDE_LEN`
- `LOCAL_OCR_VIETOCR_MODEL`
- `LOCAL_OCR_VIETOCR_BATCH_SIZE`
- `LOCAL_OCR_TORCH_THREADS`
- `LOCAL_OCR_DENOISE`
- `LOCAL_OCR_TIMING_LOG`
- `LOCAL_OCR_TIMING_SLOW_MS`
- `LOCAL_OCR_DEBUG_LOG`
- `LOCAL_OCR_DEBUG_MAX_BOX_LOG`
- `LOCAL_OCR_REC_PAD_RATIO`
- `LOCAL_OCR_REC_MIN_HEIGHT`
- `LOCAL_OCR_REC_MAX_SCALE`
- `LOCAL_OCR_TRIAGE_V2`
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
rg -n "rapidocr|onnxruntime|opencv-python|LOCAL_OCR_TRIAGE" .env.example CLAUDE.md run.bat
```
