# DỰ ÁN PHẦN MỀM CÔNG CHỨNG V2 - KIẾN TRÚC & LỘ TRÌNH PHÁT TRIỂN CUỐI CÙNG (AI_CONTEXT)

> **Ghi chú cho các AI sessions sau:** Ưu tiên đọc file này đầu tiên để nắm bắt toàn diện bức tranh của dự án, các luồng nghiệp vụ lõi (đặc biệt là Hồ Sơ Thừa Kế) và các dự định công nghệ sắp thực hiện. 

## I. TỔNG QUAN HỆ THỐNG
- **Dự án:** Quản lý và tự động hóa sinh tờ khai/văn bản công chứng (Notary App).
- **Core Tech Stack:**
  - **Backend:** Python + FastAPI (sử dụng APIRouter).
  - **Database:** SQLite + SQLAlchemy (tương tác trực tiếp qua ORM db.query).
  - **Frontend:** Jinja2 Templates (Render tĩnh) + Vanilla JavaScript (Vanilla JS cho DOM manipulation, Drag & Drop). 
  - **Styling:** Bootstrap (với class CSS thuần).
  - **Document Auto-gen:** Sử dụng thư viện Python thao tác file (Hiện tại: `python-docx`, Dự định nâng cấp: `docxtpl`).

## II. LỘ TRÌNH TRIỂN KHAI (ROADMAP) SẮP TỚI

### Giai đoạn 1: Cải tổ UX/UI Nhập Hồ sơ Thừa Kế (Module Cases)
- **Thiết kế lại Drag & Drop:**
  - Chuyển "Pool người tham gia" từ dạng tải toàn bộ DB sang dạng **Empty Pool** (Khởi tạo rỗng). Người dùng tìm kiếm hoặc thêm mới người rồi mới đưa vào Pool.
  - Thu gọn (Compact) các thẻ Person Card để giao diện cây phả hệ nhỏ gọn, không cần cuộn trang nhiều.
- **Bypass Trang Chi Tiết:**
  - Nhập cây gia phả xong -> Bấm "Lưu" -> Bypass màn hình Dashboard -> Đi thẳng đến trang **Live Preview Sinh Văn Bản**.

### Giai đoạn 2: Trình Soạn Thảo Trực Tiếp trên Web (Live Word Editor)
- **Tạo trang `/cases/<id>/preview`:** 
  - Sinh mã HTML văn bản thừa kế thông minh dựa trên logic Cây Gia Phả (VD: Tự động phân tích có con chết trước/chết sau để sinh đoạn văn tương ứng).
  - Đưa HTML vào một Rich Text Editor (CKEditor / TinyMCE) để người dùng có thể tự do gõ thêm, in đậm, xóa bớt ngay trên trình duyệt trước khi xuất file.
- **Xuất file:**
  - Bấm "Tải Word" -> Convert nội dung Rich Text sang file `.docx` và tải về máy.

### Giai đoạn 3: Nâng cấp Máy Sinh Văn Bản (Word Template Engine)
- **Chuyển đổi sang `docxtpl`:**
  - Thay vì hardcode `[Tên 1]`, `[Tên 2]` bằng Python, cho phép nhân viên pháp chế tạo file `.docx` mẫu với các **Smart Tags Tiếng Việt**.
  - Ví dụ: `[BẮT ĐẦU: TRƯỜNG HỢP CÓ CON CHẾT TRƯỚC]` -> Backend sẽ dịch ngầm thành cú pháp điều kiện Jinja `{% if co_con_chet_truoc %}`.
  - Xóa bỏ tình trạng mất format (in đậm, cỡ chữ) của file template gốc.

### Giai đoạn 4: Các Module Vệ Tinh (Customers & Properties)
- **Customers:** Triển khai tính năng Merge Duplicates (gộp khách hàng trùng CCCD) và OCR đọc thẻ CCCD tự động điền form.
- **Properties:** Đổi cấu trúc Database hỗ trợ 1 Hồ sơ thừa kế (Case) liên kết với Nhiều Tài sản (1-N), và hiện Lịch sử mua bán của từng Sổ Đỏ.

---

## III. CHI TIẾT TỪNG MODULE NGHIỆP VỤ

### 1. MODULE HỒ SƠ THỪA KẾ (Cases) -> 🔴 CORE CỦA DỰ ÁN
*Quản lý vòng đời lập văn bản Thừa Kế (Khai nhận / Thỏa thuận phân chia).*
- **Các file liên quan:** `routers/cases.py`, `templates/cases/form.html`, `detail.html`, `list.html`.
- **Logic quan trọng đã Fix:** Logic `_pick_core_people` để xử lý Vợ/Chồng trùng giới tính và không bỏ sót các nhánh thừa kế vị trí > 3.

### 2. MODULE KHÁCH HÀNG (Customers)
*Quản lý danh bạ các bên tham gia (CMND, Khai sinh, Chứng tử).*
- **Các file liên quan:** `routers/customers.py`, `templates/customers/*`.

### 3. MODULE TÀI SẢN (Properties)
*Quản lý Sổ Đỏ (Giấy chứng nhận QSDĐ, Ô tô).*
- **Các file liên quan:** `routers/properties.py`, `templates/properties/*`.

### 4. MODULE MÁY SINH VĂN BẢN (Word Templates Engine)
*Xử lý thuật toán "Phả hệ biến thành Văn bản".*
- **Các file liên quan:** `word_templates/`, `routers/cases.py` (hàm `_replace_in_doc`, `_replace_in_paragraph`).

---
**Tài liệu này được tạo vào ngày: 2026-03-09**
**Cập nhật lần cuối bởi:** AI Assistant (Antigravity). Lộ trình đã được chốt với User, ưu tiên Giai đoạn 1 & 2 vào phiên làm việc tiếp theo.
