# Catalog Placeholder Word - Ho so thua ke

File nay la danh sach placeholder Word chinh thuc cho nguoi dung cong chung.
Nguoi dung chi can chen dung placeholder trong dau ngoac vuong, vi du `[Họ tên chủ đất]`.
Neu can placeholder moi, hay mo ta nghiep vu cho dev/agent de cap nhat catalog, resolver va test.

Quy uoc:
- Placeholder chuan dung tieng Viet co dau trong dau `[]`.
- He thong van chap nhan mot so alias cu nhu `[Ten 1]`, `[CCCD 1]` de template hien tai khong hong.
- App khong tu doan nghiep vu tu ten placeholder moi. Placeholder moi phai duoc them trong code.
- V1 chi ho tro truong le va doan du lieu dung san. Chua ho tro block `if/for` trong Word.

## 1. Ho so

| Placeholder | Noi dung dien vao | Nguon |
|---|---|---|
| `[Loại văn bản]` | Ten loai van ban dang lap | `InheritanceCase.loai_van_ban` |
| `[Ngày lập hồ sơ]` | Ngay lap ho so | `InheritanceCase.ngay_lap_ho_so` |
| `[Nơi niêm yết]` | Noi niem yet | `InheritanceCase.noi_niem_yet`, fallback dia chi dat |
| `[Ghi chú]` | Ghi chu ho so | `InheritanceCase.ghi_chu` |
| `[Tên file]` | Ten file xuat | `ho_so_thua_ke_{id}` |
| `[Ngày]` | Ngay hien tai khi xuat | Ngay he thong |
| `[Tháng]` | Thang hien tai khi xuat | Ngay he thong |
| `[Ngày chữ]` | Ngay hien tai bang chu | Ngay he thong |
| `[Tháng chữ]` | Thang hien tai bang chu | Ngay he thong |

Alias cu con ho tro:

| Alias cu | Tuong duong |
|---|---|
| `[Niêm Yết]` | `[Nơi niêm yết]` |
| `[NIÊM YẾT]` | `[Nơi niêm yết]` viet hoa |

## 2. Tai san

| Placeholder | Noi dung dien vao | Nguon |
|---|---|---|
| `[Loại sổ]` | Loai giay chung nhan | `Property.loai_so` |
| `[Số serial]` | So phat hanh GCN | `Property.so_serial` |
| `[Số vào sổ]` | So vao so cap GCN | `Property.so_vao_so` |
| `[Số thửa]` | So thua dat | `Property.so_thua_dat` |
| `[Số tờ]` | So to ban do | `Property.so_to_ban_do` |
| `[Số tờ bản đồ]` | So to ban do | `Property.so_to_ban_do` |
| `[Địa chỉ đất]` | Dia chi thua dat | `Property.dia_chi` |
| `[Loại đất]` | Loai dat tong hop | `Property.loai_dat` |
| `[Diện tích]` | Tong dien tich bang so | `Property.land_rows_json`, fallback `Property.dien_tich` |
| `[Diện tích chữ]` | Tong dien tich bang chu | Tinh tu dien tich |
| `[Hình thức sử dụng]` | Hinh thuc su dung | `Property.hinh_thuc_su_dung` |
| `[Thời hạn]` | Thoi han su dung | `Property.thoi_han` |
| `[Nguồn gốc]` | Nguon goc su dung dat | `Property.nguon_goc` |
| `[Ngày cấp sổ]` | Ngay cap GCN | `Property.ngay_cap` |
| `[Cơ quan cấp sổ]` | Co quan cap GCN | `Property.co_quan_cap` |

Alias cu con ho tro:

| Alias cu | Tuong duong |
|---|---|
| `[Serial]` | `[Số serial]` |
| `[Địa chỉ đất]` | `[Địa chỉ đất]` |
| `[Loại sổ]` | `[Loại sổ]` |
| `[Số vào sổ]` | `[Số vào sổ]` |
| `[Số thửa]` | `[Số thửa]` |
| `[Số tờ]` | `[Số tờ]` |
| `[Diện tích]` | `[Diện tích]` |
| `[Diện tích chữ]` | `[Diện tích chữ]` |
| `[Hình thức sử dụng]` | `[Hình thức sử dụng]` |
| `[Loại đất]` | `[Loại đất]` |
| `[Nguồn gốc]` | `[Nguồn gốc]` |
| `[Ngày cấp sổ]` | `[Ngày cấp sổ]` |
| `[Cơ quan cấp sổ]` | `[Cơ quan cấp sổ]` |

## 3. Dong loai dat

Dung `N = 1..10` theo thu tu cac dong trong bang loai dat cua ho so.

| Placeholder | Noi dung dien vao |
|---|---|
| `[Loại đất N]` | Loai dat dong N |
| `[Diện tích N]` | Dien tich dong N |
| `[Thời hạn N]` | Thoi han dong N |

Alias cu co dau nhu `[Loại đất 1]`, `[Diện tích 1]`, `[Thời hạn 1]` van duoc ho tro.

## 4. Vai tro diagram

| Ma vai tro | Y nghia | Ghi chu Word |
|---|---|---|
| `chu_dat` | Chu dat / nguoi de lai di san chinh | Dung cho placeholder `chu dat` |
| `vo_chong` | Vo/chong cua chu dat | Dung cho placeholder `vo/chong` |
| `cha` | Cha cua chu dat | Dung cho placeholder `cha` |
| `me` | Me cua chu dat | Dung cho placeholder `me` |
| `cha_vo_chong` | Cha cua vo/chong | Dung cho placeholder `cha vo/chong` |
| `me_vo_chong` | Me cua vo/chong | Dung cho placeholder `me vo/chong` |
| `con` | Con cua chu dat | Co the dung dang danh sach `con 1`, `con 2` |
| `anh_chi_em` | Anh/chi/em theo nhanh phat sinh | Co the dung dang danh sach |
| `chau` | Chau / nguoi the vi theo nhanh | Co the dung dang danh sach |
| `vo_chong_nhanh` | Vo/chong cua nguoi trong nhanh | Chu yeu bieu dien quan he, khong mac dinh huong di san |

## 5. Truong thong tin nguoi

Mau chung: thay `{nhom}` bang `chu dat`, `vo/chong`, `con 1`, `nguoi nhan 1`,
`nguoi tu choi 1`, `nguoi thua ke 1`, `chau 1`, ...

| Placeholder mau | Noi dung dien vao |
|---|---|
| `[Họ tên {nhom}]` | Ho ten day du |
| `[Giới tính {nhom}]` | Gioi tinh |
| `[Ngày sinh {nhom}]` | Ngay sinh day du |
| `[Năm sinh {nhom}]` | Nam sinh hoac ngay sinh theo du lieu |
| `[Ngày chết {nhom}]` | Ngay mat |
| `[Năm chết {nhom}]` | Ngay mat theo cach hien tai |
| `[Số giấy tờ {nhom}]` | So CCCD/giay to |
| `[Loại giấy tờ {nhom}]` | Loai giay to |
| `[Ngày cấp {nhom}]` | Ngay cap giay to |
| `[Nơi cấp {nhom}]` | Noi cap giay to |
| `[Địa chỉ {nhom}]` | Dia chi |
| `[Nhãn địa chỉ {nhom}]` | Cum tu mo dau dia chi |
| `[Vai trò {nhom}]` | Vai tro trong ho so |
| `[Hàng thừa kế {nhom}]` | Hang thua ke |
| `[Trạng thái nhận/từ chối {nhom}]` | Nhan hoac tu choi nhan di san |
| `[Tỷ lệ nhận {nhom}]` | Ty le nhan |

Vi du hay dung:

| Placeholder | Noi dung dien vao |
|---|---|
| `[Họ tên chủ đất]` | Ho ten chu dat |
| `[Số giấy tờ người nhận 1]` | So giay to cua nguoi nhan thu nhat |
| `[Tỷ lệ nhận người nhận 1]` | Ty le nhan cua nguoi nhan thu nhat |
| `[Họ tên người từ chối 1]` | Ho ten nguoi tu choi thu nhat |

## 6. Alias nguoi kieu cu

Alias cu danh so theo thu tu template hien tai. `N = 1..20`.

| Alias cu | Noi dung |
|---|---|
| `[Ten N]` / `[Tên N]` | Ho ten nguoi o slot N |
| `[Nam sinh N]` / `[Năm sinh N]` | Ngay hoac nam sinh |
| `[CCCD N]` | So giay to |
| `[Ngay cap N]` / `[Ngày cấp N]` | Ngay cap giay to |
| `[Dia chi N]` / `[Địa chỉ N]` | Dia chi |
| `[Loai CC N]` / `[Loại CC N]` | Loai giay to |
| `[Noi cap CC N]` / `[Nơi cấp CC N]` | Noi cap giay to |
| `[Thuong tru N]` / `[Thường trú N]` | Nhan dia chi |
| `[Nam chet N]` / `[Năm chết N]` | Ngay mat |
| `[Nam chet]` / `[Năm chết]` | Alias cua slot 1 |

Thu tu slot cu:
- `1`: chu dat / nguoi de lai di san.
- `2`: vo/chong cua chu dat neu co.
- `3+`: nguoi nhan di san, sau do nguoi tu choi.

## 7. Doan du lieu dung san

V1 chi dung cac doan nay de liet ke du lieu da co, khong tu them logic phap ly moi.

| Placeholder | Noi dung dien vao |
|---|---|
| `[Danh sách ngườ nhận]` | Danh sach nguoi nhan di san |
| `[Danh sách ngườ từ chối]` | Danh sach nguoi tu choi nhan di san |
| `[Danh sách ngườ thừa kế]` | Danh sach nguoi lien quan trong ho so |
| `[Đoạn mô tả quan hệ]` | Tom tat du lieu quan he dang co |
| `[Đoạn phân chia di sản]` | Tom tat loai van ban va danh sach nguoi nhan |

## 8. Doan PCDS V2 (template `1. PCDS .docx`)

Cac placeholder doan dung san cho mau PCDS moi. Du lieu lay tu `case_state_json` uu tien, fallback tu `case.participants`.

| Placeholder | Noi dung dien vao |
|---|---|
| `[Cụm ngườ để lại di sản]` | Ten cac chu dat da chet (chi chu dat chet) |
| `[Danh sách ngườ nhận và chưa chọn]` | Danh sach nguoi nhan (accept) va nguoi chua chon (unset) trong mo dau |
| `[Đoạn ngườ chết là chủ đất]` | Doan khai tu cho chu dat da chet |
| `[Đoạn quan hệ gia đình]` | Vo/chong va danh sach con cua chu dat chet |
| `[Đoạn mô tả di sản]` | Mo ta toi da 5 tai san, danh so 1.1, 1.2, ... |
| `[Đoạn phân chia di sản]` | Doan thoa thuan phan chia day du theo accept/unset/refuse |
| `[Danh sách ngườ ký]` | Danh sach nguoi ky van ban |
| `[Danh sách hàng thừa kế]` | Danh sach hang thua ke (text) |

### 8.1. Bang nguoi ky (20 dong)

`N = 1..20`.

| Placeholder | Noi dung |
|---|---|
| `[Họ tên ngườ ký N]` | Ho ten nguoi ky thu N |

### 8.2. Bang hang thua ke (20 dong)

`N = 1..20`.

| Placeholder | Noi dung |
|---|---|
| `[Họ tên hàng thừa kế N]` | Ho ten nguoi thu N trong bang |
| `[Năm sinh hàng thừa kế N]` | Nam/ngay sinh |
| `[Địa chỉ hàng thừa kế N]` | Dia chi |
| `[Ghi chú hàng thừa kế N]` | Vai tro + trang thai nhan/tu choi |

### 8.3. Tai san (toi da 5 tai san)

`N = 1..5`, `M` la dong loai dat trong tai san do.

| Placeholder | Noi dung |
|---|---|
| `[Địa chỉ tài sản N]` | Dia chi thua dat |
| `[Loại sổ tài sản N]` | Loai GCN |
| `[Serial tài sản N]` | So serial |
| `[Số vào sổ tài sản N]` | So vao so |
| `[Số thửa tài sản N]` | So thua dat |
| `[Số tờ tài sản N]` | So to ban do |
| `[Diện tích tài sản N]` | Tong dien tich |
| `[Loại đất tài sản N.M]` | Loai dat dong M |
| `[Diện tích loại đất tài sản N.M]` | Dien tich dong M |
| `[Thờ hạn loại đất tài sản N.M]` | Thoi han dong M |

## 9. Placeholder de trong cho mau cu

| Placeholder | Ghi chu |
|---|---|
| `[Nguoi uy quyen]` / `[Người ủy quyền]` | De trong |
| `[Nguoi uy quyen2]` / `[Người ủy quyền2]` | De trong |
| `[So cong chung]` / `[Số công chứng]` | De trong |
| `[SDT]` / `[SĐT]` | De trong |
| `[ONT]`, `[CLN]`, `[NTS]`, `[LUC]` | De trong neu khong duoc gan rieng |
| `[Gia chuyen nhuong]` / `[Giá chuyển nhượng]` | De trong |
