# Catalog Placeholder Word

Quy ước: `N` là số thứ tự người/tài sản, `M` là số thứ tự loại đất trong tài sản. Placeholder tầng 2 rỗng toàn bộ nếu slot tương ứng không có dữ liệu.

## 1. Hồ Sơ

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Loại văn bản]` | Tên loại văn bản | - |
| `[Tên file]` | Tên file xuất | - |
| `[Ngày]` | Ngày xuất Word | - |
| `[Tháng]` | Tháng xuất Word | - |
| `[Ngày chữ]` | Ngày xuất Word bằng chữ | - |
| `[Tháng chữ]` | Tháng xuất Word bằng chữ | - |
| `[Niêm Yết]` | Nơi lập/niêm yết văn bản | - |
| `[NIÊM YẾT]` | Alias cũ, viết hoa của `[Niêm Yết]` | - |

## 2. Người - Trường Chung

Áp dụng cho `{nhóm}`: `chủ đất chết`, `chủ đất sống`, `người nhận`, `người chưa chọn`, `người từ chối`, `hàng thừa kế`.

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Xưng hô {nhóm} N]` | Ông/Bà theo giới tính; nếu giới tính rỗng thì hiển thị thành `Ông/bà` | Theo giới tính |
| `[Họ tên {nhóm} N]` | Họ tên người N trong nhóm | - |
| `[Giới tính {nhóm} N]` | Giới tính | - |
| `[Ngày sinh {nhóm} N]` | Hiển thị ngày sinh; nếu dữ liệu chỉ có năm `yyyy` thì hiển thị `yyyy` | Parser nội bộ có thể quy `yyyy` về `01/01/yyyy` để tính, nhưng không đổi giá trị hiển thị |
| `[Ngày chết {nhóm} N]` | Hiển thị ngày chết; nếu dữ liệu chỉ có năm `yyyy` thì hiển thị `yyyy` | Parser nội bộ có thể quy `yyyy` về `01/01/yyyy` để tính, nhưng không đổi giá trị hiển thị |
| `[Loại giấy tờ {nhóm} N]` | Căn cước công dân/Căn cước/Trích lục khai tử | Nếu `[Ngày chết {nhóm} N]` rỗng: ngày cấp trước `01/07/2024` => `Căn cước công dân`, từ `01/07/2024` => `Căn cước`. Nếu có ngày chết: số giấy tờ kết thúc bằng `BS` => `Trích lục khai tử (Bản sao)`, ngược lại => `Trích lục khai tử` |
| `[Số giấy tờ {nhóm} N]` | Số giấy tờ | - |
| `[Nơi cấp {nhóm} N]` | Nơi cấp giấy tờ | Nếu người sống: ngày cấp trước `01/07/2024` => `Cục cảnh sát quản lý hành chính về trật tự xã hội`, từ `01/07/2024` => `Bộ Công an`. Nếu người chết: `[Cụm UBND niêm yết]` |
| `[Ngày cấp {nhóm} N]` | Ngày cấp giấy tờ | - |
| `[Nhãn địa chỉ {nhóm} N]` | Thường trú tại/Cư trú tại/Nơi chết | Nếu người sống: ngày cấp trước `01/07/2024` => `Thường trú tại`, từ `01/07/2024` => `Cư trú tại`. Nếu người chết: `Nơi chết` |
| `[Địa chỉ {nhóm} N]` | Địa chỉ | - |
| `[Quan hệ {nhóm} N]` | Quan hệ trong hồ sơ | - |
| `[Trạng thái {nhóm} N]` | Nhận/chưa chọn/từ chối | - |
| `[Tỷ lệ {nhóm} N]` | Tỷ lệ nhận nếu có | - |
| `[Cụm ngày chết {nhóm} N]` | Cụm ngày chết tùy chọn | `; Chết ngày: [Ngày chết {nhóm} N]`; nếu ngày chết rỗng thì cả cụm rỗng |
| `[Cụm UBND niêm yết]` | Cơ quan cấp giấy tờ khai tử | `UBND xã [Niêm Yết]` |

## 3. Chủ Đất - Tầng 2

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Chủ đất chết mở đầu 1]` | Người để lại di sản thứ nhất trong câu mở đầu | `[Xưng hô chủ đất chết 1] [Họ tên chủ đất chết 1]` |
| `[Nối chủ đất chết 2]` | Từ nối trước chủ đất chết thứ hai | ` và `; nếu không có chủ đất chết 2 thì rỗng |
| `[Chủ đất chết mở đầu 2]` | Người để lại di sản thứ hai trong câu mở đầu | `[Xưng hô chủ đất chết 2] [Họ tên chủ đất chết 2]`; nếu không có chủ đất chết 2 thì rỗng |
### Không cần 3 placeholder riêng rồi lại vẫn phải làm cụm -> Làm luôn 1 cụm [chủ đất chết] = [Xưng hô chủ đất chết 1] [Họ tên chủ đất chết 1]` và [Xưng hô chủ đất chết 2] [Họ tên chủ đất chết 2]` -> Nếu ngày chết của người nào rỗng thì bỏ người đó và chữ "và" đi
| `[Dòng khai tử chủ đất chết N]` | Một dòng thông tin chết của chủ đất N | `[Xưng hô chủ đất chết N] [Họ tên chủ đất chết N]; Sinh ngày: [Ngày sinh chủ đất chết N][Cụm ngày chết chủ đất chết N] theo [Loại giấy tờ chủ đất chết N] số [Số giấy tờ chủ đất chết N] do [Cụm UBND niêm yết] ký ngày [Ngày cấp chủ đất chết N]. [Nhãn địa chỉ chủ đất chết N]: [Địa chỉ chủ đất chết N].` |
| `[Dòng chủ đất sống tặng cho N]` | Một dòng tặng cho phần sở hữu riêng | `Đồng thời, [Xưng hô chủ đất sống N] [Họ tên chủ đất sống N] tự nguyện tặng cho phần quyền sử dụng đất thuộc quyền sử dụng của mình cho [Danh sách người nhận inline].` |

Không thêm placeholder riêng cho từng biến thể chủ đất còn sống; dùng các trường chung và logic resolver.

## 4. Người Nhận - Tầng 2

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Dòng người nhận N]` | Một block thông tin người nhận N | `N. [Xưng hô người nhận N]: [Họ tên người nhận N]; Sinh ngày: [Ngày sinh người nhận N];`<br>`[Loại giấy tờ người nhận N] số: [Số giấy tờ người nhận N] do [Nơi cấp người nhận N] cấp ngày [Ngày cấp người nhận N];`<br>`[Nhãn địa chỉ người nhận N]: [Địa chỉ người nhận N].`<br>`[Quan hệ người nhận N].` |
| `[Người nhận inline N]` | Tên người nhận trong câu liệt kê ngang | Slot đầu: `[Xưng hô người nhận N] [Họ tên người nhận N]`; slot sau tự thêm `, ` hoặc ` và ` trước cụm |
| `[Danh sách người nhận inline]` | Toàn bộ người nhận trong một câu | `[Người nhận inline 1]...[Người nhận inline 20]` |

## 5. Người Chưa Chọn - Tầng 2

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Dòng người chưa chọn N]` | Một block thông tin người chưa chọn N | `N. [Xưng hô người chưa chọn N]: [Họ tên người chưa chọn N]; Sinh ngày: [Ngày sinh người chưa chọn N];`<br>`[Loại giấy tờ người chưa chọn N] số: [Số giấy tờ người chưa chọn N] do [Nơi cấp người chưa chọn N] cấp ngày [Ngày cấp người chưa chọn N];`<br>`[Nhãn địa chỉ người chưa chọn N]: [Địa chỉ người chưa chọn N].`<br>`[Quan hệ người chưa chọn N].` |
| `[Người chưa chọn inline N]` | Tên người chưa chọn trong câu liệt kê ngang | Slot đầu: `[Xưng hô người chưa chọn N] [Họ tên người chưa chọn N]`; slot sau tự thêm `, ` hoặc ` và ` trước cụm |
| `[Danh sách người chưa chọn inline]` | Toàn bộ người chưa chọn trong một câu | `[Người chưa chọn inline 1]...[Người chưa chọn inline 20]` |
| `[Dòng tặng cho người chưa chọn N]` | Một dòng tặng cho phần được hưởng | `[Xưng hô người chưa chọn N] [Họ tên người chưa chọn N] tự nguyện tặng cho toàn bộ quyền hưởng di sản thừa kế của mình được thụ hưởng từ [Chủ đất chết mở đầu 1][Nối chủ đất chết 2][Chủ đất chết mở đầu 2] cho [Danh sách người nhận inline].` |

## 6. Người Từ Chối - Tầng 2

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Dòng người từ chối N]` | Một block thông tin người từ chối N | `N. [Xưng hô người từ chối N]: [Họ tên người từ chối N]; Sinh ngày: [Ngày sinh người từ chối N];`<br>`[Loại giấy tờ người từ chối N] số: [Số giấy tờ người từ chối N] do [Nơi cấp người từ chối N] cấp ngày [Ngày cấp người từ chối N];`<br>`[Nhãn địa chỉ người từ chối N]: [Địa chỉ người từ chối N].`<br>`[Quan hệ người từ chối N].` |
| `[Người từ chối inline N]` | Tên người từ chối trong câu liệt kê ngang | Slot đầu: `[Xưng hô người từ chối N] [Họ tên người từ chối N]`; slot sau tự thêm `, ` hoặc ` và ` trước cụm |
| `[Danh sách người từ chối inline]` | Toàn bộ người từ chối trong một câu | `[Người từ chối inline 1]...[Người từ chối inline 20]` |
| `[Dòng từ chối người từ chối N]` | Một dòng ghi nhận văn bản từ chối | `[Xưng hô người từ chối N] [Họ tên người từ chối N] đã từ chối di sản theo Văn bản từ chối nhận di sản số ......................... .` |

## 7. Hàng Thừa Kế Và Ký Tên

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[STT hàng thừa kế N]` | Số thứ tự trong bảng hàng thừa kế | - |
| `[Họ tên hàng thừa kế N]` | Họ tên dòng N | - |
| `[Ngày sinh hàng thừa kế N]` | Ngày/năm sinh dòng N | - |
| `[Địa chỉ hàng thừa kế N]` | Địa chỉ dòng N | - |
| `[Ghi chú hàng thừa kế N]` | Quan hệ + trạng thái | - |
| `[Họ tên người ký N]` | Người ký dòng N | - |
| `[Dòng hàng thừa kế N]` | Dạng text nếu không dùng bảng | `[STT hàng thừa kế N]. [Họ tên hàng thừa kế N] - [Ngày sinh hàng thừa kế N] - [Địa chỉ hàng thừa kế N] - [Ghi chú hàng thừa kế N]` |

## 8. Tài Sản - Tầng 1

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Địa chỉ đất N]` | Địa chỉ đất của tài sản N | - |
| `[Loại sổ N]` | Loại giấy chứng nhận của tài sản N | - |
| `[Serial N]` | Số serial của tài sản N | - |
| `[Số vào sổ N]` | Số vào sổ của tài sản N | - |
| `[Số thửa N]` | Số thửa đất của tài sản N | - |
| `[Số tờ N]` | Số tờ bản đồ của tài sản N | - |
| `[Diện tích N]` | Tổng diện tích của tài sản N | - |
| `[Hình thức sử dụng N]` | Hình thức sử dụng của tài sản N | - |
| `[Nguồn gốc N]` | Nguồn gốc sử dụng của tài sản N | - |
| `[Ngày cấp sổ N]` | Ngày cấp sổ của tài sản N | - |
| `[Cơ quan cấp sổ N]` | Cơ quan cấp sổ của tài sản N | - |
| `[Loại đất N.M]` | Loại đất dòng M của tài sản N | - |
| `[Diện tích loại đất N.M]` | Diện tích loại đất dòng M của tài sản N | - |
| `[Thời hạn loại đất N.M]` | Thời hạn loại đất dòng M của tài sản N | - |

## 9. Tài Sản - Tầng 2

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Dòng tài sản N]` | Dòng mở đầu tài sản N | `N. Quyền sử dụng đất tại: [Địa chỉ đất N] theo [Loại sổ N] số: [Serial N]; Số vào sổ cấp GCN: [Số vào sổ N] do [Cơ quan cấp sổ N] cấp ngày [Ngày cấp sổ N].` |
| `[Dòng thửa đất N]` | Số thửa, số tờ của tài sản N | `Thửa đất số: [Số thửa N], tờ bản đồ số: [Số tờ N].` |
| `[Dòng diện tích N]` | Diện tích tài sản N | `Diện tích: [Diện tích N] m2.` |
| `[Dòng hình thức sử dụng N]` | Hình thức sử dụng tài sản N | `Hình thức sử dụng: [Hình thức sử dụng N].` |
| `[Dòng nguồn gốc N]` | Nguồn gốc tài sản N | `Nguồn gốc sử dụng đất: [Nguồn gốc N].` |
| `[Dòng loại đất N.M]` | Một dòng loại đất trong tài sản N | `N.M. [Loại đất N.M]: [Diện tích loại đất N.M] m2; Thời hạn: [Thời hạn loại đất N.M].` |

## 10. Alias Cũ

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Tên N]` | Alias cũ: họ tên người slot N | - |
| `[Năm sinh N]` | Alias cũ: năm/ngày sinh slot N | - |
| `[Năm sinh hàng thừa kế N]` | Alias cũ của `[Ngày sinh hàng thừa kế N]` | - |
| `[CCCD N]` | Alias cũ: số giấy tờ slot N | - |
| `[Ngày cấp N]` | Alias cũ: ngày cấp giấy tờ slot N | - |
| `[Địa chỉ N]` | Alias cũ: địa chỉ slot N | - |
| `[Loại CC N]` | Alias cũ: loại giấy tờ slot N | - |
| `[Nơi cấp CC N]` | Alias cũ: nơi cấp giấy tờ slot N | - |
| `[Thường trú N]` | Alias cũ: nhãn địa chỉ slot N | - |
| `[Năm chết N]` | Alias cũ: ngày/năm chết slot N | - |
| `[Năm chết]` | Alias cũ của `[Năm chết 1]` | - |
| `[Serial]` | Alias cũ của số serial tài sản chính | - |
| `[Serial tài sản N]` | Alias cũ của `[Serial N]` | - |
| `[Địa chỉ đất]` | Alias cũ của địa chỉ tài sản chính | - |
| `[Địa chỉ tài sản N]` | Alias cũ của `[Địa chỉ đất N]` | - |
| `[Loại sổ]` | Alias cũ của loại sổ tài sản chính | - |
| `[Loại sổ tài sản N]` | Alias cũ của `[Loại sổ N]` | - |
| `[Số vào sổ]` | Alias cũ của số vào sổ tài sản chính | - |
| `[Số vào sổ tài sản N]` | Alias cũ của `[Số vào sổ N]` | - |
| `[Số thửa]` | Alias cũ của số thửa tài sản chính | - |
| `[Số thửa tài sản N]` | Alias cũ của `[Số thửa N]` | - |
| `[Số tờ]` | Alias cũ của số tờ tài sản chính | - |
| `[Số tờ tài sản N]` | Alias cũ của `[Số tờ N]` | - |
| `[Diện tích]` | Alias cũ của diện tích tài sản chính | - |
| `[Diện tích tài sản N]` | Alias cũ của `[Diện tích N]` | - |
| `[Hình thức sử dụng tài sản N]` | Alias cũ của `[Hình thức sử dụng N]` | - |
| `[Nguồn gốc tài sản N]` | Alias cũ của `[Nguồn gốc N]` | - |
| `[Ngày cấp sổ tài sản N]` | Alias cũ của `[Ngày cấp sổ N]` | - |
| `[Cơ quan cấp sổ tài sản N]` | Alias cũ của `[Cơ quan cấp sổ N]` | - |
| `[Loại đất tài sản N.M]` | Alias cũ của `[Loại đất N.M]` | - |
| `[Diện tích loại đất tài sản N.M]` | Alias cũ của `[Diện tích loại đất N.M]` | - |
| `[Thời hạn loại đất tài sản N.M]` | Alias cũ của `[Thời hạn loại đất N.M]` | - |
| `[Dòng thửa đất tài sản N]` | Alias cũ của `[Dòng thửa đất N]` | - |
| `[Dòng diện tích tài sản N]` | Alias cũ của `[Dòng diện tích N]` | - |
| `[Dòng hình thức sử dụng tài sản N]` | Alias cũ của `[Dòng hình thức sử dụng N]` | - |
| `[Dòng nguồn gốc tài sản N]` | Alias cũ của `[Dòng nguồn gốc N]` | - |
| `[Dòng loại đất tài sản N.M]` | Alias cũ của `[Dòng loại đất N.M]` | - |

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

Các placeholder này vẫn để trống vì thuộc văn bản phụ của Văn bản chính

## 12. Tầng 3

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| Chưa dùng | Cụm phức tạp để triển khai sau | - |
