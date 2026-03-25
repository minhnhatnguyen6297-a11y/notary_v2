# Bảng Mapping Placeholder — Văn bản thừa kế

> Chỉnh sửa trực tiếp file này để xác nhận hoặc điều chỉnh mapping.
> Ký hiệu: ✅ Đã hoạt động | ❌ Sai / Cần sửa | ❓ Cần xem lại | 💬 Ghi chú

---

## NHÓM 1 — Tài sản / Giấy chứng nhận

| Placeholder | Dữ liệu điền vào | Nguồn | Trạng thái |
|---|---|---|---|
| `[Loại sổ]` | Loại Giấy chứng nhận (xem 3 loại bên dưới) | `Property.loai_so` — dropdown | ✅ |
| `[Serial]` | Số phát hành GCN | `Property.so_serial` | ✅ |
| `[Số vào sổ]` | Số vào sổ cấp GCN | `Property.so_vao_so` | ✅ |
| `[Ngày cấp sổ]` | Ngày cấp GCN | `Property.ngay_cap` | ✅ |
| `[Cơ quan cấp sổ]` | UBND huyện / Sở TN&MT ... | `Property.co_quan_cap` | ✅ |
| `[Số thửa]` | Số thửa đất | `Property.so_thua_dat` | ✅ |
| `[Số tờ]` | Số tờ bản đồ | `Property.so_to_ban_do` | ✅ |
| `[Địa chỉ đất]` | Địa chỉ thửa đất | `Property.dia_chi` | ✅ |
| `[Diện tích]` | **Tổng** diện tích tất cả loại đất (m², số) | Tính tổng từ bảng loại đất; fallback `Property.dien_tich` | ✅ |
| `[Diện tích chữ]` | Tổng diện tích bằng chữ tiếng Việt | Tính từ `[Diện tích]` | ✅ |
| `[Hình thức sử dụng]` | Ví dụ: Riêng / Chung vợ chồng | `Property.hinh_thuc_su_dung` — nhập tay tự do | ✅ |
| `[Nguồn gốc]` | Nguồn gốc sử dụng đất | `Property.nguon_goc` | ✅ |

### Loại đất theo từng dòng — N = 1, 2, 3... (tối đa 10)

> Dữ liệu từ bảng "Loại đất – Diện tích – Thời hạn" trong form hồ sơ.

| Placeholder | Dữ liệu điền vào | Ví dụ |
|---|---|---|
| `[Loại đất N]` | Tên loại đất dòng N | `Đất ở tại nông thôn` |
| `[Diện tích N]` | Diện tích dòng N (số, đơn vị m²) | `80` |
| `[Thời hạn N]` | Thời hạn sử dụng dòng N | `Lâu dài` |

> `[Thời hạn 1]` đồng thời là fallback cho các mẫu cũ dùng `[Thời hạn 1]` không theo dòng.

---

## NHÓM 2 — Ngày tháng (lấy từ ngày hiện tại khi xuất file)

| Placeholder | Dữ liệu điền vào | Ví dụ |
|---|---|---|
| `[Ngày]` | Ngày (số nguyên) | `3` |
| `[Tháng]` | Tháng (2 chữ số) | `03` |
| `[Ngày chữ]` | Ngày bằng chữ tiếng Việt | `ba` |
| `[Tháng chữ]` | Tháng bằng chữ tiếng Việt | `ba` |

---

## NHÓM 3 — Hồ sơ

| Placeholder | Dữ liệu điền vào | Nguồn |
|---|---|---|
| `[Niêm Yết]` | Tên xã / thị trấn nơi niêm yết | `InheritanceCase.noi_niem_yet` (fallback: địa chỉ đất) |
| `[NIÊM YẾT]` | Như trên, IN HOA | Tính từ `noi_niem_yet` |
| `[Tên file]` | Tên file khi tải xuống | `ho_so_thua_ke_{id}` |

---

## NHÓM 4 — Thông tin người (N = 1 → 20)

### Thứ tự người

| N | Ai |
|---|---|
| 1 | Chủ đất (người đã mất) — **bắt buộc** |
| 2 | Vợ / Chồng chủ đất |
| 3, 4, 5... | Người **nhận** di sản (từ cao đến thấp theo tỉ lệ) |
| tiếp theo | Người **không nhận** di sản |

> Ví dụ: 3 người nhận + 2 người từ chối → N=3,4,5 nhận; N=6,7 không nhận.

### Các trường thông tin (thay N = số thứ tự)

| Placeholder | Dữ liệu điền vào | Nguồn | Ghi chú |
|---|---|---|---|
| `[Tên N]` | Họ tên đầy đủ | `Customer.ho_ten` | |
| `[Năm sinh N]` | Ngày / năm sinh | `Customer.ngay_sinh` | Nếu nhập 01/01/YYYY → chỉ in năm |
| `[Loại CC N]` | Loại giấy tờ | Tính từ `Customer.ngay_cap` | Trước 01/10/2024 → `Căn cước công dân`; từ 01/10/2024 → `Căn cước` |
| `[CCCD N]` | Số giấy tờ tùy thân | `Customer.so_giay_to` | |
| `[Nơi cấp CC N]` | Cơ quan cấp | Tính từ `Customer.ngay_cap` | Trước 01/10/2024 → `Cục cảnh sát QLHC về TTXH`; từ 01/10/2024 → `Bộ Công an` |
| `[Ngày cấp N]` | Ngày cấp giấy tờ | `Customer.ngay_cap` | |
| `[Thường trú N]` | Cụm từ mở đầu địa chỉ | Tính từ `Customer.ngay_cap` | Trước 01/10/2024 → `Thường trú tại`; từ 01/10/2024 → `Cư trú tại` |
| `[Địa chỉ N]` | Địa chỉ thường trú / cư trú | `Customer.dia_chi` | |
| `[Năm chết N]` | Ngày mất (định dạng ngày đầy đủ) | `Customer.ngay_chet` | Để trống nếu còn sống |

---

## NHÓM 5 — Placeholder điền tay (hệ thống để trống)

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

## PHỤ LỤC — 3 loại Giấy chứng nhận (`[Loại sổ]`)

| Giá trị | Hiển thị trong dropdown |
|---|---|
| `Giấy chứng nhận quyền sử dụng đất` | GCN quyền sử dụng đất |
| `Giấy chứng nhận quyền sử dụng đất, quyền sở hữu nhà ở và tài sản khác gắn liền với đất` | GCN QSDĐ + nhà ở + tài sản khác |
| `Giấy chứng nhận quyền sử dụng đất, quyền sở hữu tài sản gắn liền với đất` | GCN QSDĐ + tài sản gắn liền |
