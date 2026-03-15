# Đặc tả Dự án — Notary App v2

> **Ngày cập nhật:** 2026-03-15 | **Trạng thái:** Đã xác nhận, sẵn sàng implement

---

## 1. Mục tiêu tổng thể

Xây dựng web nội bộ phục vụ nghiệp vụ công chứng, hướng tới thương mại hóa.

**Đối tượng dữ liệu cốt lõi:** Giấy tờ pháp lý về **Người** (CCCD, khai sinh, khai tử) và **Tài sản** (Sổ đỏ).

**Lộ trình tự động hóa 100%:**
```
Ảnh giấy tờ → OCR → Text → Trường dữ liệu cố định
    → Sơ đồ kéo thả (phả hệ / mua bán)
    → Xuất văn bản theo mẫu
```

**Phạm vi hiện tại:** Hồ sơ Thừa kế. Thiết kế mở để bổ sung Mua bán / Chuyển nhượng sau.

---

## 2. Kiến trúc tổng thể

### 2.1 Sidebar — 2 nhóm

| Nhóm | Mục |
|------|-----|
| **Thao tác Hồ sơ** | Hồ sơ Thừa kế; [Mua bán — sau] |
| **Lưu trữ** | Con người; Tài sản *(chỉ tra cứu, tự đồng bộ khi lưu hồ sơ)* |

### 2.2 Luồng 4 bước trong 1 màn hình

```
[Bước 1: Nhập liệu] → [Bước 2: Thẻ dữ liệu] → [Bước 3: Sơ đồ kéo thả] → [Bước 4: Văn bản + Export]
```

**Nguyên tắc cứng:** State giữ phía client (JS) — KHÔNG reload trang khi chuyển bước.

### 2.3 Layout màn hình

```
┌──────────┬────────────────────────────────────────────────┐
│          │  [Bước 1] Form nhập / Upload Excel              │
│ Sidebar  │────────────────────────────────────────────────│
│          │  TRÁI: Pool thẻ dữ liệu (Bước 2)               │
│ Thao tác │  PHẢI: Sơ đồ kéo thả (Bước 3)                  │
│          │        hoặc Live Editor (Bước 4)                │
│ ──────── │                                                 │
│ Lưu trữ  │  [Lưu Nháp - tự động]    [Lưu Hoàn Tất]        │
└──────────┴────────────────────────────────────────────────┘
```

---

## 3. Chi tiết từng bước

### Bước 1 — Nhập liệu

**Implement ngay:**
- Form điền tay
- Upload Excel (openpyxl — đã có sẵn)

**Chừa slot, chưa implement logic:**
- Quét QR
- Upload ảnh → OCR → map fields tự động

---

### Bước 2 — Thẻ dữ liệu

**Thẻ Người** — 2 dạng hiển thị:

| Dạng | Hiển thị | Dùng cho |
|------|---------|---------|
| **Thẻ đầy đủ** | Tất cả trường, có thể edit inline | Panel trái (xem/sửa) |
| **Thẻ ngắn** | Tên + Ngày sinh + Ngày chết | Drag vào sơ đồ Bước 3 |

**Trường của Thẻ Người (đầy đủ):**
Họ tên, Ngày sinh, Ngày chết, Số CCCD, Nơi cấp, Ngày cấp, Địa chỉ

**Thẻ Tài sản** — *Tạm thời không làm thẻ drag* (thường chỉ 1 tài sản/hồ sơ):

Số serial, Số vào sổ, Số thửa, Số tờ bản đồ, Địa chỉ, Diện tích, Loại đất, Thời hạn sử dụng, Hình thức sử dụng, Nguồn gốc, Ngày cấp sổ, Nơi cấp sổ

---

### Bước 3 — Sơ đồ kéo thả

#### Thiết kế UX (quan trọng)

**KHÔNG kéo thả tự do** — Thiết kế các hàng/ô cố định sẵn, người dùng kéo thẻ ngắn vào ô:

```
┌─────────────────────────────────────────────────────┐
│  HÀNG GỐC          [  Người để lại di sản  ]        │
├─────────────────────────────────────────────────────┤
│  HÀNG 1            [ Cha ] [ Mẹ ] [ Vợ/Chồng ]     │
│                    [ Con 1 ☑ Nhận ] [ Con 2 ☑ Nhận ]│
│                      └─[ Cháu 1 ] [ Cháu 2 ]        │
├─────────────────────────────────────────────────────┤
│  HÀNG 2 (hiện nếu H1 trống)  [ Ông ] [ Bà ] ...    │
└─────────────────────────────────────────────────────┘
```

**Checkbox "Nhận"** trên mỗi thẻ: người từ chối nhận di sản bỏ tick → engine tự tính lại.

**Hồ sơ Mua bán (sau):** Sơ đồ 2 cột Bên Bán ↔ Bên Mua, cùng cơ chế ô kéo thả.

**Thư viện:** React Flow (`reactflow`) — nhúng vào FastAPI qua CDN `esm.sh`.

---

#### Phân tích Logic tính thừa kế hiện tại (`recalcShares()`)

**Mô tả engine hiện tại** *(giữ lại, không viết lại)*:

**B1 — Xác định loại tài sản:**
- Tài sản chung (joint): `estatePool = 50%` (phần owner). Vợ/chồng nhận thêm `50%` riêng.
- Tài sản riêng: `estatePool = 100%`

**B2 — Xác định người đủ điều kiện theo hàng:**
- `eligibleParents`: Cha/mẹ owner còn sống trước ngày owner mất + tick "Nhận"
- `eligibleSpouse`: Vợ/chồng còn sống trước ngày owner mất + tick "Nhận"
- `branchUnits`: Mỗi con tạo 1 "nhánh":
  - Con còn sống + tick Nhận → nhánh = [con đó]
  - Con chết **sau** owner (thừa kế xong mới chết): vợ/chồng con + cháu thay thế
  - Con chết **trước** owner (thừa kế thế vị): chỉ cháu thay thế
  - Nhánh không có ai → fallback sang owner / spouse / anh chị em / cháu khác

**B3 — Chia phần:**
```
totalUnits = số cha/mẹ eligible + số vợ/chồng eligible + số nhánh con
unit = estatePool / totalUnits
Mỗi nhánh con nhiều người → chia đều: unit / số người trong nhánh
```

**Vấn đề hiện tại (cần fix):**
- Bug #1: encoding mojibake trong `_hang_for_role()` → `hang_thua_ke` luôn = 1
- Bug #2: `cardEl` undefined crash khi `force=false`
- Bug #3: `isOptedIn()` — đã sửa trong code (comment ghi rõ) nhưng cần verify
- Logic hàng 2 (ông bà, anh chị em) chưa có trong UI — hiện chỉ có hàng 1

**Đề xuất:** Giữ nguyên engine `recalcShares()`, chỉ thiết kế lại HTML layout + kết nối SortableJS.

---

### Bước 4 — Văn bản thông minh & Live Editor

#### Kiến trúc

```
Dữ liệu sơ đồ → JSON Flags → Backend render → HTML preview → User edit → Export .docx
```

**JSON Flags ví dụ:**
```json
{
  "co_nguoi_dai_dien": true,
  "tu_choi_nhan_di_san": ["Nguyễn Văn A"],
  "hang_thua_ke": 1,
  "so_nguoi_thua_ke": 3,
  "tai_san_chung": false
}
```

#### Template văn bản — Người dùng cuối tự quản lý

**Giải pháp đề xuất: Template Word với placeholder dạng `{{variable}}`**

Người dùng cuối chỉnh sửa file `.docx` template bằng Word, dùng cú pháp đơn giản:

| Cú pháp | Ý nghĩa |
|---------|---------|
| `{{ten_nguoi_chet}}` | Điền biến đơn |
| `{% if co_nguoi_dai_dien %}...{% endif %}` | Đoạn có/không |
| `{% for person in danh_sach_thua_ke %}...{% endfor %}` | Lặp danh sách |

**Thư viện backend:** `python-docx-template` (docxtpl) — dùng cú pháp Jinja2 ngay trong file .docx.

**Hướng dẫn sử dụng cho người dùng cuối:** 1 file README đơn giản kèm template mẫu.

#### Preview & Edit

- **Preview:** Render HTML từ template (dùng Jinja2 HTML mirror của template Word)
- **Edit thủ công:** TinyMCE hoặc Quill.js — chỉnh trực tiếp nội dung HTML
- **Export cuối:** python-docx backend (giống Word nhất, giữ font/định dạng)

---

## 4. Công nghệ

### Frontend (bổ sung)

| Thư viện | Mục đích | Cách tích hợp |
|----------|---------|--------------|
| **SortableJS 1.15** | Drag-drop pool → slot | Đã có, giữ nguyên (~30KB) |
| **TinyMCE 6** | Rich text editor Bước 4 | Đã load, giữ nguyên |
| **Vanilla JS** | State management | Giữ nguyên |
| ~~React + ReactDOM + Babel + ReactFlow~~ | ~~Không dùng~~ | **Xóa — ~1.4MB dư thừa** |

> **Lý do bỏ React Flow:** Đang load nhưng không làm gì (SortableJS mới là engine thật). React Flow dành cho flowchart tự do, không phù hợp ô cố định. Babel Standalone không dùng production. ReactFlow v11 sắp hết vòng đời.

### Backend (bổ sung)

| Thư viện | Mục đích |
|----------|---------|
| **python-docx-template** (docxtpl) | Template Word có điều kiện/vòng lặp |
| FastAPI + SQLAlchemy + SQLite | Giữ nguyên |

---

## 5. Danh sách file

### Sửa

| File | Thay đổi |
|------|---------|
| `templates/base.html` | Sidebar 2 nhóm, CSS gọn |
| `templates/cases/form.html` | Refactor: split-screen layout, xóa React/Babel/ReactFlow, fix bugs |
| `routers/cases.py` | Fix encoding bug, thêm endpoint JSON flags |
| `routers/properties.py` | Fix `ngay_cap` bug |

### Tạo mới

| File | Mục đích |
|------|---------|
| `static/js/diagram.js` | Logic cây phả hệ + kết nối SortableJS (Vanilla JS) |
| `static/js/editor.js` | Rich text editor + export |
| `word_templates/thua_ke_v2.docx` | Template mới dùng docxtpl |
| `docs/huong_dan_template.md` | Hướng dẫn cho người dùng cuối chỉnh template |

### Xóa / ngưng dùng

| File | Lý do |
|------|-------|
| `templates/cases/detail.html` | Conflict với form.html |
| `routers/participants.py` | Conflict với form.html |
| `add_live_preview.py`, `fix_html.py`, `fix_js.py`, `refactor_form.py` | Script one-time, đã dùng xong |

---

## 6. Bugs cần fix

| # | Bug | File | Ưu tiên |
|---|-----|------|---------|
| 1 | Encoding mojibake `_hang_for_role()` → hang_thua_ke = 1 | `routers/cases.py` | **Cao** |
| 2 | `cardEl` undefined crash khi `force=false` | `form.html:629` | **Cao** |
| 3 | `isOptedIn()` — người chết sau owner bị loại | `form.html:1210` | Trung bình |
| 4 | Inline-create property không trả `ngay_cap` | `properties.py:113-121` | Trung bình |
| 5 | Dead alert trong `not is_locked` block | `detail.html:266-271` | Thấp |

---

## 7. Thứ tự thực hiện

```
PHASE 1 — Fix nền tảng (unblock làm việc)
├── Fix bug #1 (encoding) + bug #2 (cardEl)
├── Sửa sidebar base.html (2 nhóm)
└── Dọn legacy: detail.html, participants.py, script files

PHASE 2 — Core UX (ƯU TIÊN CAO NHẤT theo yêu cầu)
├── Bước 2: Thẻ người 2 dạng (đầy đủ + ngắn)
├── Split-screen layout (trái: pool thẻ, phải: sơ đồ)
├── Tích hợp React Flow — cây phả hệ với ô cố định
└── Kết nối lại recalcShares() với UI mới

PHASE 3 — Văn bản
├── Cài python-docx-template
├── Tạo template .docx mới (thua_ke_v2.docx)
├── Endpoint render JSON flags → HTML preview
└── Tích hợp rich text editor + export

PHASE 4 — Mở rộng (sau)
├── Excel upload (Bước 1)
├── Hồ sơ Mua bán
└── OCR ảnh giấy tờ
```

---

## 8. Quyết định kỹ thuật đã chốt

| Vấn đề | Quyết định |
|--------|-----------|
| Giữ hay viết lại code cũ | **Refactor dần** — giữ engine recalcShares(), viết lại UI |
| React Flow CDN hay Vite | **CDN** (`esm.sh`) — đơn giản, không cần build step |
| Export format | **python-docx backend** — giống Word nhất |
| Template quản lý bởi ai | **Người dùng cuối** — file .docx + hướng dẫn đơn giản |
| Sơ đồ kéo thả kiểu gì | **Ô cố định sẵn** — không tự do, tránh nhầm lẫn |
| Tài sản có thẻ drag không | **Không** — chỉ hiện ở panel thông tin, không kéo thả |
