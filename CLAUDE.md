# CLAUDE.md — notary_v2

> Đọc file này trước khi làm bất kỳ thứ gì trong project.
> Cập nhật khi có thay đổi kiến trúc hoặc fix bug xong.
| 6 | 🟡 MED | `celery_app.py` | n/a | Worker báo `Received unregistered task 'process_ocr_job'` → job treo (✅ FIXED 26/03/2026: import tường minh `tasks` trong `celery_app.py`, cần restart worker) |

---

## Tổng quan project

Hệ thống quản lý hồ sơ **thừa kế đất đai** cho văn phòng công chứng (Việt Nam).
- Luồng chính: tạo hồ sơ → kéo-thả cây thừa kế → tính tỉ lệ → xuất Word
- Ngôn ngữ giao diện: **Tiếng Việt**
- Chạy local (Windows), không có production server

---

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.13 + FastAPI 0.111 + Uvicorn |
| ORM | SQLAlchemy 2.0 + SQLite (`notary.db` trong project dir) |
| Template | Jinja2 3.1 + Bootstrap 5 + Vanilla JS (không có bundler) |
| Office | python-docx 1.1.2 (xuất Word), openpyxl 3.1.2 (import Excel) |
| Drag-drop | SortableJS (CDN) |

**Không có:** migrations, .env, build tool, test suite.

## 🎯 Triết lý & Tiêu chí Dự án (Project Philosophy)
1. **Gọn nhẹ & Dễ cài đặt**: Ưu tiên tối đa cho việc cài đặt "1 click" đối với người mới (nhân viên văn phòng, công chứng viên). Hệ thống phải chạy mượt mà ngay lập tức trên các cấu hình máy tính trạm khác nhau (Windows cũ/mới) thông qua `setup.bat`.
2. **Hạn chế xung đột môi trường**: Tránh 100% việc nhúng các mô hình AI/Deep Learning nặng nề (như PyTorch, YOLO, PaddleOCR) chạy trực tiếp tại Local nếu gây ra lỗi C++ hoặc DLL.
3. **Ưu tiên API Cloud AI**: Sẵn sàng dùng dịch vụ Online (như OpenAI API) cho các tác vụ nặng (OCR, parsing) để đổi lấy sự nhẹ nhàng, không lỗi vặt, thay vì "cố đấm ăn xôi" bắt máy cá nhân chịu tải.

---

## Cấu trúc thư mục

```
notary_v2/
├── main.py                  # Entry point, mount routes
├── database.py              # SQLite setup, get_db()
├── models.py                # SQLAlchemy models
├── requirements.txt
├── notary.db                # Auto-tạo khi chạy lần đầu
│
├── routers/
│   ├── cases.py             # ★ Logic chính (999 dòng)
│   ├── customers.py         # CRUD người + import Excel (499 dòng)
│   ├── properties.py        # CRUD bất động sản (280 dòng)
│   └── participants.py      # LEGACY — xung đột với form.html (71 dòng)
│
├── templates/
│   ├── base.html
│   ├── cases/
│   │   ├── form.html        # ★★ File lớn nhất (~1750 dòng, 1300 dòng JS)
│   │   ├── detail.html      # LEGACY — có xung đột (332 dòng)
│   │   └── list.html, preview.html, _document_template.html
│   ├── customers/           # form, detail, list, upload_result
│   └── properties/          # form, detail, list
│
└── word_templates/
    └── custom/              # Template .docx do user upload
```

---

## Database schema

```
Customer              (customers)
  id, ho_ten, gioi_tinh, ngay_sinh, ngay_chet (NULL = còn sống)
  so_giay_to (unique), ngay_cap, dia_chi

Property              (properties)
  id, so_serial (unique), so_thua_dat, so_to_ban_do
  dia_chi, dien_tich (Float m²), loai_dat, hinh_thuc_su_dung
  thoi_han, nguon_goc, ngay_cap, co_quan_cap, so_vao_so

InheritanceCase       (inheritance_cases)
  id, nguoi_chet_id (FK), tai_san_id (FK)
  loai_van_ban: "khai_nhan" | "thoa_thuan"
  trang_thai: "draft" | "locked"
  noi_niem_yet (String) — tên xã/thị trấn lập văn bản
  ngay_lap_ho_so, ghi_chu

InheritanceParticipant (inheritance_participants)
  id, ho_so_id (FK cascade-delete), customer_id (FK)
  vai_tro (String), hang_thua_ke (1|2|3)
  co_nhan_tai_san (Bool), ty_le (Float), ghi_chu

WordTemplate          (word_templates)
  id, ten_mau, ten_file_goc, duong_dan_file, is_active
```

---

## Routes tóm tắt

```
GET/POST  /cases/                   list / create form
GET/POST  /cases/{id}/edit          edit form
POST      /cases/{id}/lock|unlock   đổi trạng thái
GET       /cases/{id}/export-word   ★ xuất .docx (active)
GET       /cases/{id}/export-word-legacy  DEPRECATED — dead link
POST      /cases/live-preview       live preview endpoint

GET/POST  /customers/               list / create
POST      /customers/upload-excel   batch import
POST      /properties/inline-create JSON — quick add từ form

POST      /participants/add         LEGACY
POST      /participants/{id}/edit   LEGACY
POST      /participants/{id}/delete LEGACY
```

---

## File quan trọng nhất: `form.html`

File ~1750 dòng, phần JS từ dòng ~425 đến cuối:

| Function | Mục đích |
|----------|----------|
| `recalcShares()` | ★ Engine tính tỉ lệ thừa kế — đụng vào cẩn thận |
| `placeExistingParticipants()` | Load participant đã lưu vào UI |
| `createChildCard()` | Tạo card UI cho từng người |
| `initSlotSortable()` | Khởi tạo SortableJS cho các slot |
| `validateMove()` | Kiểm tra vị trí kéo hợp lệ |
| `survivesAt(person, date)` | Người còn sống tại ngày X? |
| `isOptedIn(person)` | Người có tham gia nhận tài sản không? |
| `putDataBackToPool()` | Trả người về pool khi xóa khỏi slot |
| `rebuildLandRowsValue()` | Serialize BĐS vào hidden field |
| `handleNativeDragStart()` | Drag event handler |

**Cấu trúc UI:**
- Trái: form fields (chủ sở hữu, BĐS, ngày)
- Giữa: people pool (nguồn kéo-thả)
- Phải: cây sơ đồ thừa kế (slot cố định theo hàng)

---

## Flow xử lý chính

```
1. User mở /cases/create hoặc /cases/{id}/edit
2. JS load danh sách khách hàng → hiển thị pool
3. User kéo-thả vào cây → recalcShares() chạy tự động
4. Submit form → POST → cases.py
   → _build_temp_participants() parse form data
   → Lưu InheritanceCase + InheritanceParticipant vào DB
   → CHÚ Ý: chỉ lưu người có ty_le > 0
5. User lock hồ sơ → POST /cases/{id}/lock
6. Export Word → GET /cases/{id}/export-word
   → _pick_core_people() trích xuất người
   → _build_template_mapping() tạo dict placeholder
   → python-docx thay thế {{placeholder}} trong template
   → Trả file .docx
```

---

## Tích hợp OCR (Optical Character Recognition)

Hệ thống có 2 luồng trích xuất dữ liệu thẻ và giấy tờ chạy song song để A/B Testing:
1. **Cloud OCR (OpenAI / Gemini 2.0 Flash) - Khuyên dùng**: 
   - Route: `POST /api/ocr/analyze`
   - Model: `gpt-4o-mini` hoặc `gemini-2.0-flash` (tự động fallback).
   - Ưu điểm: Hiểu ngữ cảnh, trích xuất JSON chính xác cao, không tốn RAM server.
   - Cấu hình: Key trong `.env`, model mặc định `gemini-2.0-flash`.
2. **Local OCR (YOLO + RapidOCR) - Chạy Offline**:
   - Route: `POST /api/ocr/analyze-local` (code trong `ocr_local.py`).
   - Pipeline chuẩn hóa:
     - Quét **QR trước** (multi-pass, xoay 0/90/180/270).
     - Nếu QR hợp lệ (`CCCD + name/birth/gender`): **tin QR 100% và dừng OCR text** cho ảnh đó.
     - Nếu không có QR: chạy OCR fallback, ghép theo CCCD và áp dụng luật cứng địa chỉ theo vị trí mặt thẻ.
   - Luật địa chỉ:
     - CCCD cũ (trước 01/07/2024): lấy từ block `Nơi thường trú` ở **dưới cùng mặt trước**.
     - CCCD mới (sau 01/07/2024): lấy từ block `Nơi cư trú` ở **trên cùng mặt sau**.
   - Luật tên: ưu tiên `QR > mặt trước > MRZ`; MRZ chỉ dùng khi thiếu hoàn toàn.
   - UI local hiển thị nguồn theo `QR/OCR + loại mặt`, không dùng nhãn `AI`.
   - Ưu điểm: 100% miễn phí, chạy CPU, có thêm phân loại giấy tờ/mặt và ưu tiên QR tuyệt đối.
   - Nhược điểm: vẫn cần OpenCV/ONNX Runtime; nếu còn bật YOLO thì vẫn phụ thuộc weights YOLO và Torch cho bước crop/phân loại.

**Lưu ý UI**: Kết quả của cả 2 luồng đều đổ về Cùng Một Vùng `Staging Area` (`ocr-staging-area` trên `form.html`) để người dùng dò lại và quyết định trước khi đẩy vào People Pool.

---

## Môi trường & Hệ thống

- Để cài đặt nhanh repo này trên máy tính Windows mới, chạy file: **`setup.bat`**
- File này tự động tạo `venv`, cài thư viện `requirements.txt` và tạo `.env` từ `.env.example`.
- Sau đó chỉ cần chạy **`run.bat`**: script này sẽ tự kiểm tra Local OCR và tự gọi `install_local_ocr.bat --auto` nếu máy còn thiếu dependency.

---

## ⚠️ Bugs đã biết (CHƯA FIX)

| # | Mức độ | File | Dòng | Mô tả |
|---|--------|------|------|-------|
| 1 | 🔴 HIGH | `cases.py` | ~21-27 | `_hang_for_role()` và `_pick_core_people()` dùng chuỗi UTF-8 bị mojibake → `hang_thua_ke` luôn = 1, Word export sai |
| 2 | 🔴 HIGH | `form.html` | 629 | `cardEl` undefined trong `putDataBackToPool(force=false)` → crash JS |
| 3 | 🟡 MED | `form.html` | 1210 | `isOptedIn()` loại nhầm người chết SAU owner → tính sai tỉ lệ |
| 4 | 🟡 MED | `properties.py` | 113-121 | `inline-create` không trả `ngay_cap` trong JSON → joint asset bị lỗi |
| 5 | 🟢 LOW | `detail.html` | 266-271 | Alert trong block `not is_locked` không bao giờ hiện (dead code) |

---

## ⚠️ Conflict kiến trúc cần biết

**Hai luồng participant xung đột:**
- `form.html` drag-drop: xóa toàn bộ participants rồi insert lại khi save → **đây là luồng chính**
- `detail.html` + `participants.py`: legacy add/edit/delete từng người → **nên xóa về sau**

**Hậu quả:** người ở Hàng 1 (cha/mẹ vợ/chồng) bị mất sau khi edit nếu `ty_le = 0`

---

## Conventions & gotchas

- **Date display:** ngày `01/01/YYYY` → chỉ hiển thị năm (`YYYY`)
- **Giới tính:** `"Nam"` / `"Nữ"` (có dấu)
- **Loại văn bản:** `"khai_nhan"` / `"thoa_thuan"` (snake_case, không dấu)
- **Trang thái:** `"draft"` / `"locked"`
- **Encoding:** file Python phải là UTF-8 BOM-free; chuỗi tiếng Việt trong code → kiểm tra kỹ trước khi lưu
- **SQLite:** không hỗ trợ `ALTER COLUMN` → nếu cần đổi schema thì phải drop/recreate hoặc migration thủ công
- **Word template:** placeholder dạng `{{ten_nguoi}}`, `{{ngay_sinh}}`, v.v. — xem `word_templates/system_placeholder_reference.md`

---

## Chạy project

```bash
# Windows
run.bat   # khoi dong ca server FastAPI va Celery worker Local OCR

# Hoặc thủ công
python -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO
python -m uvicorn main:app --port 8000
```

Mở: http://localhost:8000

---

## Khi bắt đầu task mới

1. Đọc phần **Bugs đã biết** → đừng tạo regression
2. Nếu sửa `form.html` → test kỹ `recalcShares()` sau khi thay đổi
3. Nếu sửa `cases.py` → check encoding chuỗi tiếng Việt (đặc biệt `_hang_for_role`)
4. Không xóa `participants.py` chưa — detail.html vẫn dùng
5. Sau khi fix bug → cập nhật bảng Bugs ở trên (đánh dấu ✅ FIXED + ngày)

---

## 🛠 Nhật ký tiến độ Local OCR (Update 26/03/2026)

### ✅ Đã hoàn thành (Done)
- [x] Fix lỗi 404 `/api/ocr/config` (xóa duplicate prefix trong `ocr.py`).
- [x] Fix lỗi Jinja2 syntax error trong `form.html` (thiếu `}}`).
- [x] Hiện nút "Local OCR" bị ẩn/disabled trong giao diện.
- [x] Đồng bộ trạng thái Enable/Disable của nút AI và Local theo queue ảnh.
- [x] Thu nhỏ ảnh trước khi gửi lên Cloud OCR để tiết kiệm token và tránh limit size.
- [x] Triển khai pipeline Local OCR mới: tiền xử lý → **YOLO** cắt/nhận diện → **QR** → **RapidOCR** nhận dạng → regex lọc trường.
- [x] Tối ưu Startup: warmup Local OCR (RapidOCR/YOLO) ở `main.py` để giảm crash/lỗi lần gọi đầu.
- [x] Cập nhật `install_local_ocr.bat` + `LOCAL_AI_INSTALL_GUIDE.md` theo pipeline mới.
- [x] Tích hợp kiểm tra/cài Local OCR trực tiếp vào `run.bat`, không cần khởi động/cài riêng bằng tay ở lần đầu.

### 🚧 Đang làm dở (Doing / Pending)
- [ ] Kiểm tra độ chính xác pipeline mới trên ảnh CCCD thật (nhiều góc chụp).
- [ ] Tinh chỉnh Regex trong `ocr_local.py` để bóc tách địa chỉ/họ tên chính xác hơn.
- [ ] Xử lý trường hợp Server bị "Connection Reset" khi uvicorn tự reload trong lúc đang tải model.
- [ ] Thêm thanh loading ProgressBar cho Local OCR vì nó chạy trên CPU nên sẽ chậm hơn Cloud (~5-10s/ảnh).

---

## ⚠️ Ghi chú quan trọng: CPU không hỗ trợ AVX (Torch / YOLO crash)

**Triệu chứng:** Khi bật Local OCR có YOLO, worker Celery có thể bị tắt đột ngột. Log thường hiển thị:
- `Windows fatal exception: code 0xc000001d`
- `Fatal Python error: Illegal instruction`
- Stack trace đi vào `torch` hoặc thư viện phụ trợ của YOLO

**Nguyên nhân gốc:** Một số CPU cũ không hỗ trợ AVX/AVX2. PyTorch CPU wheel hiện tại thường được build với AVX, nên khi nhánh YOLO dùng Torch để cắt ảnh / phân loại giấy tờ, process có thể crash cứng.

**Phạm vi ảnh hưởng hiện tại:** Sau khi chuyển sang **RapidOCR**, lỗi này **không còn nằm ở text OCR nữa**. RapidOCR vẫn chạy được trên CPU thông thường; phần rủi ro còn lại chủ yếu nằm ở **YOLO + Torch**.

### Hướng xử lý đã thống nhất
1. **Ưu tiên chế độ an toàn trên máy không có AVX**:
   - đặt `LOCAL_OCR_DISABLE_TORCH=1`
   - hệ thống vẫn chạy Local OCR bằng **RapidOCR trên full image**
   - đổi lại sẽ mất bước crop / phân loại bằng YOLO
2. **Chỉ bật YOLO trên máy có AVX ổn định**:
   - khi cần độ chính xác cao hơn ở bước cắt ảnh
   - khi đã xác nhận máy chạy Torch ổn
3. **Không tùy biến Torch theo từng máy nếu chưa được phép**:
   - vì rất dễ tạo chênh lệch môi trường giữa các máy trạm
   - khó bảo trì khi force pull repo sang máy khác

### Note bắt buộc cho agent sau này
**Trước khi sửa PyTorch / YOLO theo máy**, hãy hỏi người dùng:
- Có muốn **tùy biến theo đúng cấu hình CPU hiện tại** không?
- Hay ưu tiên **giữ Local OCR ở chế độ RapidOCR an toàn**?
- Nếu cần YOLO nhưng máy không hỗ trợ AVX, có chấp nhận phương án **VPS / Docker riêng cho OCR** không?

### Hướng triển khai nếu gặp lại lỗi AVX
**Option 1: Giữ local theo hướng ổn định**
- Xác định CPU có AVX hay không.
- Nếu không có AVX:
  - bật `LOCAL_OCR_DISABLE_TORCH=1`
  - chạy `RapidOCR` trên full image
  - không cố ép cài thêm Torch / YOLO trên máy đó

**Option 2: Tách YOLO sang môi trường riêng**
- Chạy YOLO / OCR nặng trong VPS hoặc Docker ổn định hơn.
- Máy trạm chỉ gọi API nội bộ.
- Ưu điểm: ít phụ thuộc phần cứng local.
- Nhược điểm: cần hạ tầng và chi phí vận hành.
