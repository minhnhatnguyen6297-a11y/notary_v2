# Plan: OCR Local (CPU-only)

**Trang thai:** active  
**Cap nhat:** 2026-04-14  
**Files lien quan:** `routers/ocr_local.py`, `tasks.py`  
**API endpoints:**
- `POST /api/ocr/local/submit` - submit 1 anh, nhan `job_id`
- `POST /api/ocr/local/submit-batch` - submit nhieu anh, nhan `job_id`
- `GET /api/ocr/local/status/{job_id}` - poll ket qua

---

## Tinh than / Muc tieu

OCR Local la pipeline **khong phu thuoc API key, chay hoan toan offline tren CPU**. Toi uu cho may Windows van phong. Muc tieu la xu ly CCCD Viet Nam du tot de staff chu yeu chi verify, khong phai nhap lai tu dau.

Khong co gang 100% tu dong. Thiet ke co **human-in-the-loop**:
- Tra ve `warnings[]` khi co truong thieu hoac khong chac.
- UI hien thi canh bao de nguoi dung sua tay khi can.

OCR Local van phai uu tien **dung nghiep vu truoc**:
- Khi thay output sai, phai ghi ro case sai, anh sai, field sai, va stage sai.
- Neu gap rule nghiep vu mo ho hoac mau thuan, khong duoc tu quyet.
- Phai hoi lai user de chot huong truoc khi sua logic nghiep vu.

---

## Architecture tong quan

```text
[HTTP Request] -> [FastAPI router: ocr_local.py]
    -> Luu file tam -> tao OCRJob DB record -> enqueue Celery task
    -> Response ngay: {"job_id": "...", "status": "pending"}

[Celery Worker: tasks.py]
    -> process_ocr_job / process_ocr_batch_job
    -> Doc file tu disk -> goi local_ocr_from_bytes() / local_ocr_batch_from_inputs()
    -> Luu ket qua vao OCRJob.result_json
    -> Xoa file tam

[Frontend poll GET /status/{job_id}]
    -> Tra ve ket qua khi status = "completed"
```

---

## Pipeline xu ly chi tiet (V4)

### Buoc 1: Smart Crop
- Dung OpenCV Canny edge + contour detection tim vung giay to trong anh.
- Neu khong tim duoc contour du tin cay (`confidence < LOCAL_OCR_SMART_CROP_MIN_CONF = 0.22`) thi fallback ve full image.
- Tao 2 version:
  - `img_native`: full resolution de phuc vu rotate sau
  - `img_ocr`: chuan hoa `max_side_len` de OCR

### Buoc 2: Preprocess nhe
- Sharpen kernel `[[0,-1,0],[-1,5,-1],[0,-1,0]]` de tang do net canh chu.
- Khong dung bilateral filter vi cham hon nhieu ma khong cai thien du.
- Denoise duoc dieu khien boi `LOCAL_OCR_DENOISE`.

### Buoc 3: Triage V2
Muc dich: xac dinh anh la mat nao cua loai CCCD nao de chon ROI dung.

- Tao proxy image nho, max `720px`.
- Thu 4 huong: `0`, `90`, `180`, `270` do.
- Moi huong:
  - detect face bang Haar cascade
  - detect QR
  - tinh MRZ score bang regex `IDVNM\\d{10}(\\d{12})`

Logic phan loai:
- Co face + QR -> `front_new`
- Co face, khong QR -> `front_old`
- Co QR, khong face -> `back_new`
- Co MRZ score cao -> `back_old`
- Khong detect duoc gi -> `unknown`

Anh goc se duoc rotate theo huong tot nhat.

### Buoc 4: QR rescue
- Du frontend da thu QR va gui `client_qr_failed`, backend van thu lai QR sau khi da rotate dung huong.
- `client_qr_failed` chi la telemetry, khong phai lenh bo qua QR.

### Buoc 5: Targeted Extraction

ROI presets theo `triage_state`:

| State | ROI |
|---|---|
| `front_old:detail` | `(0.22, 0.20, 0.98, 0.92)` |
| `front_new:detail` | `(0.22, 0.20, 0.98, 0.80)` |
| `back_new:detail` | `(0.06, 0.18, 0.98, 0.94)` |
| `back_old:detail` | `(0.06, 0.18, 0.98, 0.96)` |
| `unknown:detail` | `(0.08, 0.14, 0.98, 0.96)` |

Engine:
1. RapidOCR chi dung cho detection.
2. VietOCR (`vgg_transformer`) nhan bbox crops theo batch de doc text tieng Viet.

Sau do dung regex + heuristic de map text sang fields nhu `so_giay_to`, `ho_ten`, `ngay_sinh`, `dia_chi`.

### Buoc 6: Deterministic Merge (Batch only)
- Ghep cap theo **so CCCD 12 chu so**.
- Anh khong co ID vao `unpaired[]` + warning.
- Delta merge:
  - Neu mat truoc co `ho_ten` nhung thieu `dia_chi`, co the lay `dia_chi` tu mat sau.
- Thu tu uu tien profile:
  - `front_old > front_new > back_new > back_old > unknown`

### Buoc 7: Wide Fallback
- Chi chay khi `triage_state = unknown`.
- Thu lan luot ROI rong hon.
- Khong con legacy fallback va khong con score rollback.

---

## Luat du lieu nghiep vu

- Ten:
  - Uu tien `QR > mat truoc > MRZ`
  - MRZ chi la fallback cuoi.
- Dia chi:
  - CCCD cu, truoc `01/07/2024`: uu tien block `Noi thuong tru` o mat truoc.
  - CCCD moi, sau `01/07/2024`: uu tien block `Noi cu tru` o mat sau.
- `ngay_het_han`:
  - Khong dua vao participant nghiep vu.
  - Chi luu metadata neu can.

---

## Task Celery - khong doi ten

```python
@celery_app.task(name="process_ocr_job")
@celery_app.task(name="process_ocr_batch_job")
```

Task name la contract cung. Doi ten se lam job pending trong queue bi mo coi.

---

## Cac truong hop dac biet / gotchas

- `client_qr_failed = true` tu frontend:
  - Backend van thu QR.
  - Day chi la hint de log, khong phai skip flag.
- CCCD 9 so cu:
  - Co the nhan dang mot phan.
  - Khong ghep cap theo key 12 so.
- Anh chup nghieng:
  - Smart crop co the fail va fallback ve full image.
  - Triage van thu 4 huong.
- Batch manifest:
  - `manifest.json` phai co `items[].index`, `items[].filename`, `items[].stored_name`.

---

## Nhung thu da thu va that bai

- Full RapidOCR det + rec:
  - Bo recognition cua RapidOCR vi doc tieng Viet kem.
- Bilateral filter:
  - Cham hon nhieu ma khong cai thien ket qua.
- LLM fallback tu dong sua loi:
  - Tam tat de uu tien toc do.
  - Thay bang canh bao tren UI de staff sua tay.
- Score rollback:
  - Da bo vi phuc tap ma khong ro rang hon.

---

## Env variables

| Var | Default | Y nghia |
|---|---|---|
| `LOCAL_OCR_DET_MAX_SIDE_LEN` | `3000` | Max side len cho RapidOCR det |
| `LOCAL_OCR_VIETOCR_MODEL` | `vgg_transformer` | Model VietOCR |
| `LOCAL_OCR_VIETOCR_BATCH_SIZE` | `24` | Batch size recognition |
| `LOCAL_OCR_TORCH_THREADS` | `2` | So thread PyTorch |
| `LOCAL_OCR_DENOISE` | `1` | Bat/tat denoise |
| `LOCAL_OCR_SMART_CROP_MIN_CONF` | `0.22` | Nguong confidence smart crop |
| `LOCAL_OCR_TRIAGE_PROXY_MAX_SIDE` | `720` | Size proxy image cho triage |
| `LOCAL_OCR_TRIAGE_MRZ_MIN_SCORE` | `0.20` | Nguong MRZ score de classify `back_old` |
| `LOCAL_OCR_REC_PAD_RATIO` | `0.10` | Padding khi crop bbox |
| `LOCAL_OCR_REC_MIN_HEIGHT` | `48` | Min height bbox |
| `LOCAL_OCR_REC_MAX_SCALE` | `3.0` | Max scale khi upscale bbox |
| `LOCAL_OCR_TIMING_LOG` | `1` | Bat log timing |
| `LOCAL_OCR_TIMING_SLOW_MS` | `1500` | Nguong log slow warning |
| `LOCAL_OCR_DEBUG_LOG` | `1` | Bat debug log |

---

## Khi can debug

1. Bat `LOCAL_OCR_DEBUG_LOG=1` va `LOCAL_OCR_TIMING_LOG=1`.
2. Xem `logs/worker.log` hoac console local.
3. Tim `[OCR_LOCAL_TIMING]` va `[OCR_LOCAL_DEBUG]` trong log.
4. Xem `triage_state` trong response de biet pipeline classify anh the nao.
5. Xem `timing_ms` de biet phase nao cham: triage / targeted_extract / merge / fallback.
6. Neu sai nghiep vu, phai ghi ro anh nao sai, field nao sai, va sai o phase nao.
7. Neu can sua rule nghiep vu ma bang chung chua du, dung lai va hoi user truoc khi sua.

---

## Checklist truoc khi sua file nay

- [ ] Doc plan nay xong roi moi sua.
- [ ] Khong doi ten Celery task.
- [ ] Khong thay doi DB schema tru khi bat buoc.
- [ ] Sau khi sua: `python -m py_compile routers/ocr_local.py tasks.py`
- [ ] Test regression voi it nhat 10 anh CCCD.
