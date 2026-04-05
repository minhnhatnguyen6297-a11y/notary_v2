# Audit: Field hệ thống ↔ Placeholder Word

> Cập nhật: 2026-04-03  
> Mục đích: Đối chiếu field trong DB/code với placeholder trong file Word mẫu để tìm chỗ thiếu và chỗ lạ.

---

## PHẦN 1 — Field DB hiện có và placeholder tương ứng

### 1a. Bảng `properties` (Tài sản đất)

| Field DB | Placeholder Word | Trạng thái |
|---|---|---|
| `loai_so` | `[Loại sổ]` | ✅ Đã map |
| `so_serial` | `[Serial]` | ✅ Đã map |
| `so_vao_so` | `[Số vào sổ]` | ✅ Đã map |
| `so_thua_dat` | `[Số thửa]` | ✅ Đã map |
| `so_to_ban_do` | `[Số tờ]` | ✅ Đã map |
| `dia_chi` | `[Địa chỉ đất]` | ✅ Đã map |
| `land_rows_json[].loai_dat` | `[Loại đất N]` (N=1-10) | ✅ Đã map |
| `land_rows_json[].dien_tich` | `[Diện tích N]` (N=1-10) | ✅ Đã map |
| `land_rows_json[].thoi_han` | `[Thời hạn N]` (N=1-10) | ✅ Đã map |
| `hinh_thuc_su_dung` | `[Hình thức sử dụng]` | ✅ Đã map |
| `nguon_goc` | `[Nguồn gốc]` | ✅ Đã map |
| `ngay_cap` | `[Ngày cấp sổ]` | ✅ Đã map |
| `co_quan_cap` | `[Cơ quan cấp sổ]` | ✅ Đã map |
| *(tính toán)* | `[Diện tích]` | ✅ Đã map (tổng từ land_rows) |
| *(tính toán)* | `[Diện tích chữ]` | ✅ Đã map (tính từ tổng diện tích) |

---

### 1b. Bảng `customers` (Người)

> Mỗi người chiếm 1 slot N (N=1..20). Xem quy ước thứ tự ở Phần 3.

| Field DB / Property | Placeholder Word | Trạng thái |
|---|---|---|
| `ho_ten` | `[Tên N]` | ✅ Đã map |
| `ngay_sinh` | `[Năm sinh N]` | ✅ Đã map (01/01/YYYY → chỉ in năm) |
| `so_giay_to` | `[CCCD N]` | ✅ Đã map |
| `ngay_cap` | `[Ngày cấp N]` | ✅ Đã map |
| `dia_chi` | `[Địa chỉ N]` | ✅ Đã map |
| `ngay_chet` | `[Năm chết N]` | ✅ Đã map |
| `loai_giay_to` *(computed)* | `[Loại CC N]` | ✅ Đã map (tự tính từ ngày_cap) |
| `noi_cap` *(computed)* | `[Nơi cấp CC N]` | ✅ Đã map (tự tính từ ngày_cap) |
| `loai_dia_chi` *(computed)* | `[Thường trú N]` | ✅ Đã map (tự tính từ ngày_cap) |
| `gioi_tinh` | `[Giới tính N]` | ⚠️ File Word mẫu hiện thiếu — giữ lại placeholder, cần bổ sung vào Word khi cần |

---

### 1c. Bảng `inheritance_cases` (Hồ sơ)

| Field DB | Placeholder Word | Trạng thái |
|---|---|---|
| `noi_niem_yet` | `[Niêm Yết]`, `[NIÊM YẾT]` | ✅ Đã map |

---

### 1d. Bảng `inheritance_participants` (Người tham gia hồ sơ)

> Chức năng vai trò phụ — tính năng mới, file Word cũ chỉ dùng `[Placeholder N]` (N=1-10).  
> Vai trò phụ sẽ được **hệ thống tự gán** từ sơ đồ diagram, không phải người dùng nhập tay.

| Vai trò phụ | Ký hiệu | Ý nghĩa |
|---|---|---|
| `chu_dat` | Chủ đất | Người có sẵn tài sản trước khi xảy ra thừa kế. Nếu 3 người cùng là `chu_dat` thì đất chia 3; khi 1 người chết, chỉ 1/3 đi vào di sản được phân chia xuống hàng thừa kế. |
| `nhan_di_san` | Người nhận di sản | Người chấp nhận nhận phần thừa kế được phân chia. |
| `tu_choi` | Người từ chối nhận | Người từ chối không nhận di sản. |

> Một người có thể có nhiều vai trò phụ cùng lúc. Ví dụ: người 1 vừa là `chu_dat` (có đất chung), vừa là `nhan_di_san` (nhận thêm phần của người vợ đã mất).

---

### 1e. Giá trị tính toán / hệ thống (không phải từ DB trực tiếp)

| Nguồn | Placeholder Word | Trạng thái |
|---|---|---|
| Ngày hôm nay (số) | `[Ngày]` | ✅ Đã map |
| Tháng hôm nay (2 chữ số) | `[Tháng]` | ✅ Đã map |
| Ngày bằng chữ | `[Ngày chữ]` | ✅ Đã map |
| Tháng bằng chữ | `[Tháng chữ]` | ✅ Đã map |

---

### 1f. Placeholder điền tay (hệ thống để trống "")

> Những trường này phục vụ **Văn bản phụ** — sẽ bổ sung đầy đủ sau.  
> Người dùng tự điền vào file Word sau khi xuất.

| Placeholder | Ý nghĩa |
|---|---|
| `[Người ủy quyền]` | Tên người được ủy quyền ký |
| `[Người ủy quyền2]` | Người ủy quyền thứ 2 |
| `[Số công chứng]` | Số văn bản chứng thực |
| `[SĐT]` | Số điện thoại |
| `[ONT]` | Diện tích đất ở nông thôn (nếu dùng riêng) |
| `[CLN]` | Diện tích đất cây lâu năm |
| `[NTS]` | Diện tích đất nuôi trồng thủy sản |
| `[LUC]` | Diện tích đất lúa |
| `[Giá chuyển nhượng]` | Giá trị chuyển nhượng |

---

## PHẦN 2 — Placeholder lạ trong file Word mẫu

> Phân tích từ `xa_PCDS_template.md` (bản text của mẫu Word thực tế)

### 2a. Placeholder SAI (không match với mapping hệ thống)

| Placeholder trong Word | Vấn đề | Hậu quả |
|---|---|---|
| `[Năm chết]` (line 48, không có số) | Hệ thống chỉ map `[Năm chết N]` có số. `[Năm chết]` không có trong mapping → không được thay thế | ⚠️ **Để trống** khi xuất — cần sửa thành `[Năm chết 1]` trong Word |

---

## PHẦN 3 — Quy ước thứ tự người (slot N)

| Slot N | Ai | Nguồn |
|---|---|---|
| 1 | Người để lại di sản (chủ đất, đã mất) | `InheritanceCase.nguoi_chet` |
| 2 | Vợ hoặc chồng của người để lại | Participant có vai_tro = Vợ/Chồng |
| 3 | Người thứ 3 (participant có `co_nhan_tai_san=True`, sắp theo ty_le giảm dần) | Participants |
| 4..20 | Tiếp tục người nhận → rồi người từ chối | Participants |

---

## PHẦN 4 — Tóm tắt hành động cần làm

| Vấn đề | Action |
|---|---|
| `[Năm chết]` (không số) trong Word | Sửa thủ công trong file Word: thành `[Năm chết 1]` |
| `[Giới tính N]` chưa có trong Word mẫu | Thêm vào Word khi cần, hệ thống đã sẵn sàng map |
| `system_placeholder_reference.md` (draft cũ) | Đã xóa |
