# CLAUDE.md — Hệ thống Quản lý Hồ sơ Công chứng (notary_v2)

## Mô tả dự án
Ứng dụng web quản lý hồ sơ thừa kế đất đai tại phòng công chứng Việt Nam.
Cho phép tạo hồ sơ, phân bổ tỷ lệ thừa kế tự động, và xuất văn bản Word.

## Tech stack
- **Backend:** Python 3.13, FastAPI, SQLAlchemy (ORM), SQLite (`notary.db`)
- **Frontend:** Jinja2 templates, Bootstrap 5, Vanilla JS (no bundler)
- **Thư viện:** python-docx (xuất Word), openpyxl (import Excel)
- **Chạy:** `uvicorn main:app --reload` (xem `run.bat`)

## Cấu trúc thư mục
```
notary_v2/
├── main.py                  # FastAPI app, mount routers
├── models.py                # SQLAlchemy models (Customer, Property, InheritanceCase, InheritanceParticipant)
├── database.py              # SQLite engine, SessionLocal, get_db
├── routers/
│   ├── customers.py         # CRUD + Excel import + inline-create
│   ├── properties.py        # CRUD + inline-create
│   ├── cases.py             # CRUD + lock/unlock + Word export (MAIN MODULE)
│   └── participants.py      # Add/edit/delete participant (legacy flow)
├── templates/
│   ├── base.html            # Layout chung, sidebar, CSS variables
│   ├── cases/
│   │   ├── form.html        # Form tạo/sửa hồ sơ + JS drag-drop + recalcShares()
│   │   ├── detail.html      # Chi tiết hồ sơ + add participant form (legacy)
│   │   └── list.html
│   ├── customers/           # CRUD customers
│   └── properties/          # CRUD properties
└── word_templates/
    └── xa_PCDS_template.docx  # Template Word với placeholders [Tên 1], [CCCD 1]...
```

## Models quan trọng

```python
Customer          # Người (sống hoặc đã chết). ngay_chet=NULL → còn sống
Property          # Giấy chứng nhận QSD đất (sổ đỏ)
InheritanceCase   # Hồ sơ thừa kế. trang_thai: "draft" | "locked"
InheritanceParticipant  # Người tham gia hồ sơ. vai_tro, hang_thua_ke, ty_le
```

## Logic nghiệp vụ chính

### Tính tỷ lệ thừa kế (JS — form.html: recalcShares)
1. **Tài sản chung:** nếu `ngay_cap GCN >= ngay_ket_hon` → tài sản chung → vợ/chồng được 50% base
2. **Estate pool:** 50% (tài sản chung) hoặc 100% (tài sản riêng)
3. **Chia đều theo branch:** cha/mẹ + vợ/chồng + mỗi con = 1 unit
4. **Con đã chết trước owner:** chỉ cháu nhận phần của con
5. **Con đã chết sau owner:** vợ/chồng con + cháu nhận phần của con

### Word export (Python — cases.py)
- Template: `word_templates/xa_PCDS_template.docx` (ưu tiên) hoặc đường dẫn mạng
- Placeholders: `[Tên 1]`, `[CCCD 1]`, `[Năm sinh 1]`, `[Địa chỉ 1]`... (slots 1-20)
- `_pick_core_people()`: xác định ai là person1 (nam), person2 (nữ), person3 (thừa kế chính)
- `_build_template_mapping()`: tạo dict placeholder → giá trị
- `_replace_in_doc()`: thay thế trong tất cả paragraphs, tables, headers/footers

### Inline-create (AJAX)
- `POST /customers/inline-create` → JSON `{ok, customer}`
- `POST /properties/inline-create` → JSON `{ok, property}`
- Cho phép tạo người/tài sản ngay trong form hồ sơ mà không cần rời trang

## CÁC LỖI ĐÃ BIẾT (cần sửa)

### CRITICAL — Encoding mojibake trong cases.py
File `routers/cases.py` bị lưu sai encoding tại một số hàm:
- `_hang_for_role()` (dòng 20-26): chuỗi tiếng Việt bị garbled → luôn return 1
- `_pick_core_people()` (dòng 387-393): không match được "Vợ/Chồng", "Nữ" → Word export sai
- `vai_tro_options` trong `detail()` (dòng 211): chuỗi garbled → dropdown hiển thị ký tự rác
- **Cách sửa:** mở file bằng editor hỗ trợ UTF-8, gõ lại các chuỗi tiếng Việt

### CRITICAL JS — ReferenceError: `cardEl` undefined
`form.html:629` — hàm `putDataBackToPool()` tham chiếu biến `cardEl` không tồn tại trong scope:
```javascript
// BUG: cardEl không được định nghĩa trong putDataBackToPool
const stillUsedElsewhere = Array.from(...).some(n => n !== cardEl);
```
→ crash khi gọi `putBackToPool(card)` không có `force=true`

### Logic — isOptedIn() sai với người chết sau owner
`form.html:1210`: `if (!!card.dataset.death) return false` — loại bỏ mọi người có ngày chết,
kể cả người chết SAU chủ đất (vẫn được nhận theo luật)

### Logic — inline-create property thiếu ngay_cap trong response
`properties.py:113-121`: không trả về `ngay_cap` → JS không tính được tài sản chung
cho tài sản mới thêm inline

### Dead code
- `detail.html:266-271`: alert "Hồ sơ đã khoá" nằm trong `{% if not case.is_locked %}` → không bao giờ hiện
- `export-word-legacy` endpoint: không có link nào trỏ vào
- `placeExistingParticipants` dòng 1025: role 'Cha/Mẹ' cho mẹ không bao giờ chạy do `return` sớm

## Hai luồng participant song song (CONFLICT)

**Luồng A — Form drag-drop** (`/cases/create` hoặc `/cases/{id}/edit`):
- Xóa toàn bộ participant cũ, insert lại từ hidden inputs
- Chỉ lưu người có `share > 0`

**Luồng B — Detail page** (`/participants/add`, `/participants/{id}/edit`):
- Thêm/sửa từng người một

**Conflict:** Edit qua Luồng A sẽ xóa tất cả thay đổi từ Luồng B

## Conventions trong codebase

### Date display
```python
# Python: hiển thị chỉ năm nếu ngày=01/01 (quy ước chỉ biết năm)
if d.day == 1 and d.month == 1:
    return str(d.year)
else:
    return d.strftime("%d/%m/%Y")
```
```javascript
// JS: tương tự — yyyy → parse là 01/01/yyyy
const yyyy = raw.match(/^(\d{4})$/);
if (yyyy) return new Date(Number(yyyy[1]), 0, 1);
```

### Form pattern
- GET handler: render template với `form={...}`, `errors=[]`, `field_errors={}`
- POST handler: validate → nếu lỗi render lại form với data posted
- Redirect after POST: `RedirectResponse(url, status_code=302)`

### Vietnamese ID logic
```python
# Từ 01/07/2024: "Căn cước" (Bộ Công an), trước đó: "Căn cước công dân" (Cục CSQLHC)
# Từ 01/07/2024: "Cư trú tại", trước đó: "Thường trú tại"
```

## Lệnh thường dùng

```bash
# Khởi động server
cd D:/notary_app/notary_v2
.venv/Scripts/activate
uvicorn main:app --reload --port 8000

# Cài dependencies
pip install -r requirements.txt

# Xem DB (SQLite)
sqlite3 notary.db ".tables"
sqlite3 notary.db "SELECT * FROM inheritance_cases LIMIT 5;"
```

## Template Word placeholders

Slots 1-20, mỗi slot có:
`[Tên N]`, `[Năm sinh N]`, `[CCCD N]`, `[Ngày cấp N]`, `[Địa chỉ N]`,
`[Loại CC N]`, `[Nơi cấp CC N]`, `[Thường trú N]`, `[Năm chết N]`

Slots đặc biệt:
`[Serial]`, `[Số vào sổ]`, `[Số thửa]`, `[Số tờ]`, `[Địa chỉ đất]`,
`[Ngày]`, `[Tháng]`, `[Cơ quan cấp sổ]`, `[Ngày cấp sổ]`

Person1 = chủ đất (nam), Person2 = vợ/chồng (nữ), Person3 = thừa kế chính nhất.

## Điều không nên làm
- Không dùng `force=false` với `putBackToPool()` trong JS cho đến khi fix Bug cardEl
- Không thêm người qua detail page rồi edit qua form drag-drop → mất dữ liệu
- Không sửa encoding file cases.py bằng editor không hỗ trợ UTF-8 BOM
- Không xóa Customer khi đã có InheritanceCase liên kết (cascade delete sẽ xóa participant)
