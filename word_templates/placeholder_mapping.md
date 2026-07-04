# Catalog Placeholder Word

Quy ước: `N` là số thứ tự người/tài sản, `M` là số thứ tự loại đất trong tài sản. Placeholder tầng 2 rỗng toàn bộ nếu slot tương ứng không có dữ liệu.

## 1. Hồ Sơ

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Loại văn bản]` | Tên loại văn bản | - |
| `[Ngày lập hồ sơ]` | Ngày lập hồ sơ | - |
| `[Nơi niêm yết]` | Nơi lập/niêm yết văn bản | - |
| `[Ghi chú]` | Ghi chú hồ sơ | - |
| `[Tên file]` | Tên file xuất | - |
| `[Ngày]` | Ngày xuất Word | - |
| `[Tháng]` | Tháng xuất Word | - |
| `[Ngày chữ]` | Ngày xuất Word bằng chữ | - |
| `[Tháng chữ]` | Tháng xuất Word bằng chữ | - |
| `[Niêm Yết]` | Alias cũ của `[Nơi niêm yết]` | - |
| `[NIÊM YẾT]` | Alias cũ, viết hoa | - |

## 2. Người - Tầng 1

Áp dụng cho `{nhóm}`: `chủ đất chết`, `chủ đất sống`, `người nhận`, `người chưa chọn`, `người từ chối`, `hàng thừa kế`.

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Xưng hô {nhóm} N]` | Ông/Bà/Ông bà theo giới tính | - |
| `[Họ tên {nhóm} N]` | Họ tên người N trong nhóm | - |
| `[Giới tính {nhóm} N]` | Giới tính | - |
| `[Ngày sinh {nhóm} N]` | Ngày sinh đầy đủ | - |
| `[Năm sinh {nhóm} N]` | Năm sinh hoặc ngày sinh theo dữ liệu | - |
| `[Ngày chết {nhóm} N]` | Ngày chết | - |
| `[Năm chết {nhóm} N]` | Năm/ngày chết theo dữ liệu | - |
| `[Loại giấy tờ {nhóm} N]` | CCCD/Căn cước/giấy tờ khác | - |
| `[Số giấy tờ {nhóm} N]` | Số giấy tờ | - |
| `[Nơi cấp {nhóm} N]` | Nơi cấp giấy tờ | - |
| `[Ngày cấp {nhóm} N]` | Ngày cấp giấy tờ | - |
| `[Nhãn địa chỉ {nhóm} N]` | Thường trú tại/Cư trú tại/Địa chỉ | - |
| `[Địa chỉ {nhóm} N]` | Địa chỉ | - |
| `[Quan hệ {nhóm} N]` | Quan hệ trong hồ sơ | - |
| `[Trạng thái {nhóm} N]` | Nhận/chưa chọn/từ chối | - |
| `[Tỷ lệ {nhóm} N]` | Tỷ lệ nhận nếu có | - |

## 3. Chủ Đất - Tầng 2

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Chủ đất chết mở đầu 1]` | Người để lại di sản thứ nhất trong câu mở đầu | `[Xưng hô chủ đất chết 1] [Họ tên chủ đất chết 1]` |
| `[Chủ đất chết mở đầu 2]` | Người để lại di sản thứ hai trong câu mở đầu | ` và [Xưng hô chủ đất chết 2] [Họ tên chủ đất chết 2]` |
| `[Dòng khai tử chủ đất chết N]` | Một dòng thông tin chết của chủ đất N | `[Xưng hô chủ đất chết N] [Họ tên chủ đất chết N]; Sinh năm: [Năm sinh chủ đất chết N]; chết ngày [Ngày chết chủ đất chết N] theo Trích lục khai tử số [Số giấy tờ chủ đất chết N] do UBND xã [Nơi niêm yết] ký ngày [Ngày cấp chủ đất chết N]. Nơi chết: [Địa chỉ chủ đất chết N].` |
| `[Chủ đất sống tặng cho inline N]` | Chủ đất sống tặng cho phần sở hữu riêng | `[Xưng hô chủ đất sống N] [Họ tên chủ đất sống N]` |
| `[Dòng chủ đất sống tặng cho N]` | Một dòng tặng cho phần sở hữu riêng | `Đồng thời, [Xưng hô chủ đất sống N] [Họ tên chủ đất sống N] tự nguyện tặng cho phần quyền sử dụng đất thuộc quyền sử dụng của mình cho [Danh sách người nhận inline].` |

## 4. Người Nhận - Tầng 2

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Dòng người nhận N]` | Một block thông tin người nhận N | `N. [Xưng hô người nhận N]: [Họ tên người nhận N]; Sinh ngày: [Năm sinh người nhận N];`<br>`[Loại giấy tờ người nhận N] số: [Số giấy tờ người nhận N] do [Nơi cấp người nhận N] cấp ngày [Ngày cấp người nhận N];`<br>`[Nhãn địa chỉ người nhận N]: [Địa chỉ người nhận N].`<br>`[Quan hệ người nhận N].` |
| `[Người nhận inline N]` | Tên người nhận trong câu liệt kê ngang | Slot đầu: `[Xưng hô người nhận N] [Họ tên người nhận N]`; slot sau tự thêm `, ` hoặc ` và ` trước cụm |
| `[Danh sách người nhận inline]` | Toàn bộ người nhận trong một câu | `[Người nhận inline 1]...[Người nhận inline 20]` |

## 5. Người Chưa Chọn - Tầng 2

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Dòng người chưa chọn N]` | Một block thông tin người chưa chọn N | `N. [Xưng hô người chưa chọn N]: [Họ tên người chưa chọn N]; Sinh ngày: [Năm sinh người chưa chọn N];`<br>`[Loại giấy tờ người chưa chọn N] số: [Số giấy tờ người chưa chọn N] do [Nơi cấp người chưa chọn N] cấp ngày [Ngày cấp người chưa chọn N];`<br>`[Nhãn địa chỉ người chưa chọn N]: [Địa chỉ người chưa chọn N].`<br>`[Quan hệ người chưa chọn N].` |
| `[Người chưa chọn inline N]` | Tên người chưa chọn trong câu liệt kê ngang | Slot đầu: `[Xưng hô người chưa chọn N] [Họ tên người chưa chọn N]`; slot sau tự thêm `, ` hoặc ` và ` trước cụm |
| `[Danh sách người chưa chọn inline]` | Toàn bộ người chưa chọn trong một câu | `[Người chưa chọn inline 1]...[Người chưa chọn inline 20]` |
| `[Dòng tặng cho người chưa chọn N]` | Một dòng tặng cho phần được hưởng | `[Xưng hô người chưa chọn N] [Họ tên người chưa chọn N] tự nguyện tặng cho toàn bộ quyền hưởng di sản thừa kế của mình được thụ hưởng từ [Chủ đất chết mở đầu 1][Chủ đất chết mở đầu 2] cho [Danh sách người nhận inline].` |

## 6. Người Từ Chối - Tầng 2

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Dòng người từ chối N]` | Một block thông tin người từ chối N | `N. [Xưng hô người từ chối N]: [Họ tên người từ chối N]; Sinh ngày: [Năm sinh người từ chối N];`<br>`[Loại giấy tờ người từ chối N] số: [Số giấy tờ người từ chối N] do [Nơi cấp người từ chối N] cấp ngày [Ngày cấp người từ chối N];`<br>`[Nhãn địa chỉ người từ chối N]: [Địa chỉ người từ chối N].`<br>`[Quan hệ người từ chối N].` |
| `[Người từ chối inline N]` | Tên người từ chối trong câu liệt kê ngang | Slot đầu: `[Xưng hô người từ chối N] [Họ tên người từ chối N]`; slot sau tự thêm `, ` hoặc ` và ` trước cụm |
| `[Danh sách người từ chối inline]` | Toàn bộ người từ chối trong một câu | `[Người từ chối inline 1]...[Người từ chối inline 20]` |
| `[Dòng từ chối người từ chối N]` | Một dòng ghi nhận văn bản từ chối | `[Xưng hô người từ chối N] [Họ tên người từ chối N] đã từ chối di sản theo Văn bản từ chối nhận di sản số ......................... .` |

## 7. Hàng Thừa Kế Và Ký Tên

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[STT hàng thừa kế N]` | Số thứ tự trong bảng hàng thừa kế | - |
| `[Họ tên hàng thừa kế N]` | Họ tên dòng N | - |
| `[Năm sinh hàng thừa kế N]` | Năm/ngày sinh dòng N | - |
| `[Địa chỉ hàng thừa kế N]` | Địa chỉ dòng N | - |
| `[Ghi chú hàng thừa kế N]` | Quan hệ + trạng thái | - |
| `[Họ tên người ký N]` | Người ký dòng N | - |
| `[Dòng hàng thừa kế N]` | Dạng text nếu không dùng bảng | `[STT hàng thừa kế N]. [Họ tên hàng thừa kế N] - [Năm sinh hàng thừa kế N] - [Địa chỉ hàng thừa kế N] - [Ghi chú hàng thừa kế N]` |

## 8. Tài Sản - Tầng 1

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Địa chỉ tài sản N]` | Địa chỉ tài sản N | - |
| `[Loại sổ tài sản N]` | Loại giấy chứng nhận | - |
| `[Serial tài sản N]` | Số serial | - |
| `[Số vào sổ tài sản N]` | Số vào sổ | - |
| `[Số thửa tài sản N]` | Số thửa đất | - |
| `[Số tờ tài sản N]` | Số tờ bản đồ | - |
| `[Diện tích tài sản N]` | Tổng diện tích tài sản N | - |
| `[Hình thức sử dụng tài sản N]` | Hình thức sử dụng | - |
| `[Nguồn gốc tài sản N]` | Nguồn gốc sử dụng | - |
| `[Ngày cấp sổ tài sản N]` | Ngày cấp sổ | - |
| `[Cơ quan cấp sổ tài sản N]` | Cơ quan cấp sổ | - |
| `[Loại đất tài sản N.M]` | Loại đất dòng M của tài sản N | - |
| `[Diện tích loại đất tài sản N.M]` | Diện tích loại đất dòng M | - |
| `[Thời hạn loại đất tài sản N.M]` | Thời hạn loại đất dòng M | - |

## 9. Tài Sản - Tầng 2

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Dòng tài sản N]` | Dòng mở đầu tài sản N | `N. Quyền sử dụng đất tại: [Địa chỉ tài sản N] theo [Loại sổ tài sản N] số: [Serial tài sản N]; Số vào sổ cấp GCN: [Số vào sổ tài sản N] do [Cơ quan cấp sổ tài sản N] cấp ngày [Ngày cấp sổ tài sản N].` |
| `[Dòng thửa đất tài sản N]` | Số thửa, số tờ của tài sản N | `Thửa đất số: [Số thửa tài sản N], tờ bản đồ số: [Số tờ tài sản N].` |
| `[Dòng diện tích tài sản N]` | Diện tích tài sản N | `Diện tích: [Diện tích tài sản N] m2.` |
| `[Dòng hình thức sử dụng tài sản N]` | Hình thức sử dụng tài sản N | `Hình thức sử dụng: [Hình thức sử dụng tài sản N].` |
| `[Dòng nguồn gốc tài sản N]` | Nguồn gốc tài sản N | `Nguồn gốc sử dụng đất: [Nguồn gốc tài sản N].` |
| `[Dòng loại đất tài sản N.M]` | Một dòng loại đất trong tài sản N | `N.M. [Loại đất tài sản N.M]: [Diện tích loại đất tài sản N.M] m2; Thời hạn: [Thời hạn loại đất tài sản N.M].` |

## 10. Alias Cũ

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Tên N]` | Alias cũ: họ tên người slot N | - |
| `[Năm sinh N]` | Alias cũ: năm/ngày sinh slot N | - |
| `[CCCD N]` | Alias cũ: số giấy tờ slot N | - |
| `[Ngày cấp N]` | Alias cũ: ngày cấp giấy tờ slot N | - |
| `[Địa chỉ N]` | Alias cũ: địa chỉ slot N | - |
| `[Loại CC N]` | Alias cũ: loại giấy tờ slot N | - |
| `[Nơi cấp CC N]` | Alias cũ: nơi cấp giấy tờ slot N | - |
| `[Thường trú N]` | Alias cũ: nhãn địa chỉ slot N | - |
| `[Năm chết N]` | Alias cũ: ngày/năm chết slot N | - |
| `[Năm chết]` | Alias cũ của `[Năm chết 1]` | - |
| `[Serial]` | Alias cũ của số serial tài sản chính | - |
| `[Địa chỉ đất]` | Alias cũ của địa chỉ tài sản chính | - |
| `[Loại sổ]` | Alias cũ của loại sổ tài sản chính | - |
| `[Số vào sổ]` | Alias cũ của số vào sổ tài sản chính | - |
| `[Số thửa]` | Alias cũ của số thửa tài sản chính | - |
| `[Số tờ]` | Alias cũ của số tờ tài sản chính | - |
| `[Diện tích]` | Alias cũ của diện tích tài sản chính | - |

## 11. Placeholder Để Trống

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Người ủy quyền]` | User tự điền nếu cần | - |
| `[Người ủy quyền2]` | User tự điền nếu cần | - |
| `[Số công chứng]` | User tự điền nếu cần | - |
| `[SĐT]` | User tự điền nếu cần | - |
| `[ONT]` | Alias cũ, không dùng cho template mới | - |
| `[CLN]` | Alias cũ, không dùng cho template mới | - |
| `[NTS]` | Alias cũ, không dùng cho template mới | - |
| `[LUC]` | Alias cũ, không dùng cho template mới | - |
| `[Giá chuyển nhượng]` | User tự điền nếu cần | - |

## 12. Tầng 3

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| Chưa dùng | Cụm phức tạp để triển khai sau | - |
