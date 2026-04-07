# Plan: OCR Local (CPU-only)

**Trạng thái:** active  
**Cập nhật:** 2026-04-07  
**Files liên quan:** `routers/ocr_local.py`, `tasks.py`  
**API endpoints:**
- `POST /api/ocr/local/submit` — submit 1 ảnh, nhận job_id
- `POST /api/ocr/local/submit-batch` — submit nhiều ảnh, nhận job_id
- `GET /api/ocr/local/status/{job_id}` — poll kết quả

---

## Tinh thần / Mục tiêu

OCR Local là pipeline **không phụ thuộc API key, chạy hoàn toàn offline trên CPU**. Tối ưu cho máy Windows văn phòng. Mục tiêu: xử lý CCCD Việt Nam đủ tốt để staff chỉ cần verify, không phải nhập lại từ đầu.

Không cố gắng 100% tự động — thiết kế có **human-in-the-loop**: trả về `warnings[]` khi có trường thiếu hoặc không chắc, để UI hiển thị cảnh báo đỏ cho người dùng tự sửa.

---

## Architecture tổng quan

```
[HTTP Request] → [FastAPI router: ocr_local.py]
    → Lưu file tạm → tạo OCRJob DB record → enqueue Celery task
    → Response ngay: {"job_id": "...", "status": "pending"}

[Celery Worker: tasks.py]
    → process_ocr_job / process_ocr_batch_job
    → Đọc file từ disk → gọi local_ocr_from_bytes() / local_ocr_batch_from_inputs()
    → Lưu kết quả vào OCRJob.result_json
    → Xóa file tạm

[Frontend poll GET /status/{job_id}]
    → Trả về kết quả khi status = "completed"
```

---

## Pipeline xử lý chi tiết (V4)

### Bước 1: Smart Crop
- Dùng OpenCV Canny edge + contour detection tìm vùng giấy tờ trong ảnh.
- Nếu không tìm được contour đủ tin cậy (`confidence < LOCAL_OCR_SMART_CROP_MIN_CONF = 0.22`) → fallback dùng full image.
- Tạo 2 version: `img_native` (full res để rotate sau) và `img_ocr` (chuẩn hóa max_side_len cho OCR).

### Bước 2: Preprocess nhẹ
- Sharpen kernel: `[[0,-1,0],[-1,5,-1],[0,-1,0]]` — tăng độ nét cạnh chữ.
- **Không dùng bilateral filter** (từng dùng, bỏ vì chậm 3x mà không cải thiện).
- Denoise toggle qua `LOCAL_OCR_DENOISE` (default: on).

### Bước 3: Triage V2
**Mục đích:** xác định ảnh là mặt nào của loại CCCD nào → chọn ROI đúng.

- Tạo proxy image nhỏ (max 720px).
- Thử 4 hướng (0°, 90°, 180°, 270°).
- Mỗi hướng: detect Face (Haar cascade) + QR + tính MRZ score (regex `IDVNM\d{10}(\d{12})`).
- **Logic phân loại:**
  - Có Face + QR → `front_new` (CCCD mới mặt trước, có cả Face lẫn QR)
  - Có Face, không QR → `front_old` (CCCD cũ mặt trước)
  - Có QR, không Face → `back_new` (CCCD mới mặt sau, có QR)
  - Có MRZ score cao → `back_old` (CCCD cũ mặt sau)
  - Không detect được gì → `unknown`
- Rotate ảnh gốc high-res theo hướng tốt nhất.

**Tại sao quan trọng:** ROI extraction sau đó phụ thuộc hoàn toàn vào `triage_state`. Sai triage → sai ROI → miss field.

### Bước 4: QR rescue
Dù frontend đã thử QR (và báo `client_qr_failed`), backend **vẫn thử lại QR** sau khi đã rotate ảnh đúng hướng. Lý do: ảnh bị xoay ngang thường làm QR decode thất bại ở frontend.

`client_qr_failed` chỉ là **telemetry**, không phải lệnh "bỏ qua QR".

### Bước 5: Targeted Extraction

**ROI presets theo triage_state:**
| State | ROI (x1, y1, x2, y2 dạng tỷ lệ) |
|---|---|
| `front_old:detail` | (0.22, 0.20, 0.98, 0.92) |
| `front_new:detail` | (0.22, 0.20, 0.98, 0.80) |
| `back_new:detail` | (0.06, 0.18, 0.98, 0.94) |
| `back_old:detail` | (0.06, 0.18, 0.98, 0.96) |
| `unknown:detail` | (0.08, 0.14, 0.98, 0.96) |

**Engine:**
1. **RapidOCR** (det only): Detect bounding boxes vùng text. **Không dùng RapidOCR recognition** — từng dùng, bỏ vì tiếng Việt kém.
2. **VietOCR** (`vgg_transformer`): Crop từng bbox → batch recognition → ra text tiếng Việt.

Sau đó dùng regex + heuristic để map text → fields (so_giay_to, ho_ten, ngay_sinh, ...).

### Bước 6: Deterministic Merge (Batch only)
- Ghép cặp ảnh theo **số CCCD 12 chữ số** (key tuyệt đối).
- Ảnh không có ID → vào `unpaired[]` + warning.
- **Delta merge**: nếu mặt trước có `ho_ten` nhưng không có `dia_chi`, lấy `dia_chi` từ mặt sau.
- Ưu tiên field theo profile: `front_old > front_new > back_new > back_old > unknown`.

### Bước 7: Wide Fallback (chỉ khi triage = unknown)
Thử lần lượt: ROI `id_front` → `id_back` → `detail` rộng hơn.  
**Không còn legacy fallback và không còn score rollback.**

---

## Luật dữ liệu nghiệp vụ

- **Tên**: ưu tiên QR > mặt trước > MRZ (MRZ chỉ là fallback cuối).
- **Địa chỉ**:
  - CCCD **cũ** (trước 01/07/2024): lấy từ block `Nơi thường trú` ở **mặt trước**.
  - CCCD **mới** (sau 01/07/2024): lấy từ block `Nơi cư trú` ở **mặt sau**.
- **`ngay_het_han`**: **không đưa vào dữ liệu participant nghiệp vụ** (chỉ lưu metadata, không dùng trong hợp đồng).

---

## Task Celery — KHÔNG ĐỔI TÊN

```python
@celery_app.task(name="process_ocr_job")       # single image
@celery_app.task(name="process_ocr_batch_job") # batch
```

Task name là **contract cứng** — nếu đổi tên, các job đang pending trong queue sẽ bị mồ côi.

---

## Các trường hợp đặc biệt / Gotchas

- **`client_qr_failed` = True từ frontend**: Backend vẫn thử QR, không bỏ qua. Đây chỉ là hint để log, không phải skip flag.
- **CCCD 9 số cũ**: Pipeline nhận dạng nhưng không ghép cặp được (key ghép cặp yêu cầu 12 số).
- **Ảnh chụp nghiêng**: Smart crop có thể fail, fallback về full image. Triage vẫn thử 4 hướng.
- **Batch manifest**: File `manifest.json` trong thư mục temp batch phải có field `items[].index`, `items[].filename`, `items[].stored_name`.

---

## Những thứ đã thử và thất bại

- **Full RapidOCR (det + rec)**: Bỏ recognition của RapidOCR vì model nhận dạng tiếng Việt kém. Chỉ giữ detection.
- **Bilateral filter trong preprocess**: Chậm 3x, không cải thiện kết quả thực tế.
- **LLM fallback tự động sửa lỗi**: Tạm tắt để tối ưu tốc độ. Thay bằng cảnh báo đỏ trên UI để staff sửa tay. Sẽ làm lại sau.
- **Score rollback**: Từng có cơ chế "nếu score thấp thì dùng fallback kết quả cũ". Đã bỏ — phức tạp mà không rõ ràng hơn.

---

## Env variables

| Var | Default | Ý nghĩa |
|---|---|---|
| `LOCAL_OCR_DET_MAX_SIDE_LEN` | `3000` | Max side len cho RapidOCR det |
| `LOCAL_OCR_VIETOCR_MODEL` | `vgg_transformer` | Model VietOCR |
| `LOCAL_OCR_VIETOCR_BATCH_SIZE` | `24` | Batch size recognition |
| `LOCAL_OCR_TORCH_THREADS` | `2` | Số thread PyTorch |
| `LOCAL_OCR_DENOISE` | `1` | Bật/tắt denoise |
| `LOCAL_OCR_SMART_CROP_MIN_CONF` | `0.22` | Ngưỡng confidence Smart Crop |
| `LOCAL_OCR_TRIAGE_PROXY_MAX_SIDE` | `720` | Size proxy image cho triage |
| `LOCAL_OCR_TRIAGE_MRZ_MIN_SCORE` | `0.20` | Ngưỡng MRZ score để classify back_old |
| `LOCAL_OCR_REC_PAD_RATIO` | `0.10` | Padding khi crop bbox cho VietOCR |
| `LOCAL_OCR_REC_MIN_HEIGHT` | `48` | Min height bbox để nhận dạng |
| `LOCAL_OCR_REC_MAX_SCALE` | `3.0` | Max scale khi upscale bbox |
| `LOCAL_OCR_TIMING_LOG` | `1` | Bật log timing |
| `LOCAL_OCR_TIMING_SLOW_MS` | `1500` | Ngưỡng log slow warning |
| `LOCAL_OCR_DEBUG_LOG` | `1` | Bật debug log |

---

## Khi cần debug

1. Bật `LOCAL_OCR_DEBUG_LOG=1` và `LOCAL_OCR_TIMING_LOG=1`.
2. Xem log: `logs/worker.log` (VPS) hoặc console (local).
3. Tìm `[OCR_LOCAL_TIMING]` và `[OCR_LOCAL_DEBUG]` trong log.
4. Trường `triage_state` trong response cho biết pipeline đã classify ảnh thế nào.
5. Trường `timing_ms` breakdown từng phase: triage / targeted_extract / merge / fallback.

---

## Checklist trước khi sửa file này

- [ ] Đọc plan này xong rồi mới sửa.
- [ ] Không đổi tên Celery task.
- [ ] Không thay đổi DB schema trừ khi bắt buộc.
- [ ] Sau khi sửa: `python -m py_compile routers/ocr_local.py tasks.py`
- [ ] Test regression với ít nhất 10 ảnh CCCD.
