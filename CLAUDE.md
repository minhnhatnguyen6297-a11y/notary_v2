# CLAUDE.md — notary_v2

> Đọc file này trước khi làm bất kỳ thứ gì trong project.
> Cập nhật khi có thay đổi kiến trúc hoặc fix bug xong.

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
  dia_chi, loai_dat, ngay_cap, co_quan_cap

InheritanceCase       (inheritance_cases)
  id, nguoi_chet_id (FK), tai_san_id (FK)
  loai_van_ban: "khai_nhan" | "thoa_thuan"
  trang_thai: "draft" | "locked"
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
run.bat

# Hoặc thủ công
uvicorn main:app --reload --port 8000
```

Mở: http://localhost:8000

---

## Khi bắt đầu task mới

1. Đọc phần **Bugs đã biết** → đừng tạo regression
2. Nếu sửa `form.html` → test kỹ `recalcShares()` sau khi thay đổi
3. Nếu sửa `cases.py` → check encoding chuỗi tiếng Việt (đặc biệt `_hang_for_role`)
4. Không xóa `participants.py` chưa — detail.html vẫn dùng
5. Sau khi fix bug → cập nhật bảng Bugs ở trên (đánh dấu ✅ FIXED + ngày)
