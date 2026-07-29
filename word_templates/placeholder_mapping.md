# Catalog Placeholder Word

Quy ước: `N` là số thứ tự người/tài sản; `M` là số thứ tự loại đất trong tài sản. Slot không có dữ liệu trả về rỗng toàn bộ.

## 1. Hồ sơ

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Loại văn bản]` | Tên loại văn bản | - |
| `[Tên file]` | Tên file xuất | - |
| `[Ngày lập hồ sơ]` | Ngày lập hồ sơ | - |
| `[Niêm Yết]` | Nơi lập/niêm yết | - |
| `[Ghi chú]` | Ghi chú hồ sơ | - |
| `[Ngày]` | Ngày xuất Word | - |
| `[Tháng]` | Tháng xuất Word | - |
| `[Ngày chữ]` | Ngày xuất bằng chữ | Đổi số thành chữ |
| `[Tháng chữ]` | Tháng xuất bằng chữ | Đổi số thành chữ |

## 2. Người - tầng 1

Áp dụng cùng một bộ trường cho: `Người`, `Chủ đất sống`, `Chủ đất chết`, `Người nhận`, `Người từ chối`, `Hàng thừa kế`.

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Người N - Xưng hô]` | Ông/Bà của người N trên Diagram | Theo giới tính |
| `[Người N - Họ tên]` | Họ tên người N trên Diagram | - |
| `[Người N - Giới tính]` | Giới tính | - |
| `[Người N - Ngày sinh]` | Ngày sinh | - |
| `[Người N - Năm sinh]` | Ngày sinh hoặc chỉ năm sinh | Ngày `01/01/yyyy` hiển thị `yyyy` |
| `[Người N - Ngày chết]` | Ngày chết | - |
| `[Người N - Năm chết]` | Ngày chết hoặc chỉ năm chết | Ngày `01/01/yyyy` hiển thị `yyyy` |
| `[Người N - Loại giấy tờ]` | Loại giấy tờ | - |
| `[Người N - Số giấy tờ]` | Số giấy tờ | - |
| `[Người N - Ngày cấp]` | Ngày cấp giấy tờ | - |
| `[Người N - Nơi cấp]` | Nơi cấp giấy tờ | - |
| `[Người N - Nhãn địa chỉ]` | Thường trú tại/Cư trú tại/Nơi chết | - |
| `[Người N - Địa chỉ]` | Địa chỉ | - |
| `[Người N - Quan hệ]` | Quan hệ trên Diagram | Theo role/nhãn quan hệ Diagram |
| `[Người N - Vai trò]` | Role kỹ thuật trên Diagram | - |
| `[Người N - Trạng thái]` | Chủ đất sống/chủ đất chết/người nhận/người từ chối | Theo `WordExportContext` |
| `[Người N - Tỷ lệ]` | Tỷ lệ cuối cùng nếu có | Kết quả Diagram |
| `[Chủ đất sống N - Họ tên]` | Người N trong danh sách chủ đất còn sống | Lọc `Chủ đất` và chưa chết |
| `[Chủ đất chết N - Họ tên]` | Người N trong danh sách chủ đất đã chết | Lọc `Chủ đất` và đã chết |
| `[Người nhận N - Họ tên]` | Người N trong danh sách nhận | Lọc `Nhận` trên Diagram |
| `[Người từ chối N - Họ tên]` | Dành cho dữ liệu từ chối pháp lý được xác nhận | Hiện luôn rỗng vì Diagram chưa có đầu vào pháp lý này |

Các trường còn lại dùng cùng mẫu: `[Tên danh sách N - Tên trường]`.

## 3. Người - tầng 2

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Cụm chủ đất chết]` | Tên một hoặc hai người để lại di sản | `[Chủ đất chết 1 - Xưng hô] [Chủ đất chết 1 - Họ tên]` + ` và ` + `[Chủ đất chết 2 - Xưng hô] [Chủ đất chết 2 - Họ tên]`; người thứ hai rỗng thì bỏ cả người và từ nối |
| `[Nối chủ đất chết 2]` | Từ nối tương thích cho template ghép trường | ` và ` nếu có chủ đất chết 2; ngược lại rỗng |
| `[Dòng người N]` | Một block thông tin người N trên Diagram | `N. [Người N - Xưng hô] [Người N - Họ tên]; Sinh ngày: [Người N - Năm sinh].`<br>`[Người N - Loại giấy tờ] số: [Người N - Số giấy tờ] do [Người N - Nơi cấp] cấp ngày [Người N - Ngày cấp].`<br>`[Người N - Nhãn địa chỉ]: [Người N - Địa chỉ].`<br>`Là [Người N - Quan hệ].` |
| `[Dòng người nhận N]` | Một block thông tin người nhận N | Cùng cấu trúc `[Dòng người N]`, dùng trường của danh sách `Người nhận` |
| `[Dòng người từ chối N]` | Một block thông tin người từ chối N | Cùng cấu trúc `[Dòng người N]`, cuối block thêm: `[Người từ chối N - Xưng hô] [Người từ chối N - Họ tên] đã từ chối di sản theo Văn bản từ chối nhận di sản số ......................... .` |
| `[Dòng khai tử chủ đất chết N]` | Một block thông tin chủ đất chết N | Xưng hô, họ tên, sinh, chết, giấy tờ khai tử, nơi chết |
| `[Dòng chủ đất sống tặng cho N]` | Placeholder tương thích cho input chuyển quyền riêng | Hiện luôn rỗng; không suy tặng cho từ nút `Nhận` |
| `[Người nhận inline N]` | Người nhận N trong câu ngang | Tự thêm `, ` hoặc ` và ` theo vị trí |
| `[Danh sách người nhận inline]` | Tất cả người nhận trong câu ngang | Ghép `[Người nhận inline 1]` đến `[Người nhận inline 20]` |
| `[Người từ chối inline N]` | Người từ chối N trong câu ngang | Tự thêm `, ` hoặc ` và ` theo vị trí |
| `[Danh sách người từ chối inline]` | Tất cả người từ chối trong câu ngang | Ghép `[Người từ chối inline 1]` đến `[Người từ chối inline 20]` |
| `[Đoạn người chết là chủ đất]` | Toàn bộ các dòng khai tử chủ đất chết | Ghép `[Dòng khai tử chủ đất chết N]` có dữ liệu |
| `[Đoạn quan hệ gia đình]` | Quan hệ vợ/chồng, con của chủ đất chết | Theo role Diagram; chỉ ghi từ chối khi có dữ liệu pháp lý riêng |
| `[Đoạn phân chia di sản]` | Nội dung phân chia | Chỉ gồm người nhận; không tự chuyển phần sở hữu của chủ đất sống |
| `[Danh sách người ký]` | Người ký văn bản phân chia | Chủ đất sống + người nhận, không lặp người |

## 4. Bảng hàng thừa kế

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[STT hàng thừa kế N]` | Số thứ tự dòng N | - |
| `[Họ tên hàng thừa kế N]` | Họ tên dòng N | - |
| `[Ngày sinh hàng thừa kế N]` | Ngày/năm sinh dòng N | - |
| `[Địa chỉ hàng thừa kế N]` | Địa chỉ dòng N | - |
| `[Ghi chú hàng thừa kế N]` | Quan hệ và trạng thái | Theo `WordExportContext` |
| `[Dòng hàng thừa kế N]` | Dòng text nếu không dùng bảng | `[STT] . [Họ tên] - [Ngày sinh] - [Địa chỉ] - [Ghi chú]` |
| `[Họ tên người ký N]` | Người ký dòng N | - |

## 5. Tài sản - tầng 1

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Tài sản N - Địa chỉ]` | Địa chỉ tài sản N | - |
| `[Tài sản N - Loại sổ]` | Loại giấy chứng nhận | - |
| `[Tài sản N - Serial]` | Số serial | - |
| `[Tài sản N - Số vào sổ]` | Số vào sổ cấp GCN | - |
| `[Tài sản N - Số thửa]` | Số thửa đất | - |
| `[Tài sản N - Số tờ]` | Số tờ bản đồ | - |
| `[Tài sản N - Diện tích]` | Tổng diện tích | Cộng các dòng loại đất; fallback diện tích tài sản |
| `[Tài sản N - Hình thức sử dụng]` | Hình thức sử dụng | - |
| `[Tài sản N - Mục đích sử dụng]` | Các loại đất và diện tích | Ghép các dòng loại đất |
| `[Tài sản N - Thời hạn]` | Thời hạn chung | - |
| `[Tài sản N - Nguồn gốc]` | Nguồn gốc sử dụng | - |
| `[Tài sản N - Ngày cấp sổ]` | Ngày cấp giấy chứng nhận | - |
| `[Tài sản N - Cơ quan cấp sổ]` | Cơ quan cấp giấy chứng nhận | - |
| `[Loại đất N.M - Loại đất]` | Loại đất M của tài sản N | - |
| `[Loại đất N.M - Diện tích]` | Diện tích loại đất M | - |
| `[Loại đất N.M - Thời hạn]` | Thời hạn loại đất M | - |

## 6. Tài sản - tầng 2

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Dòng tài sản N]` | Dòng mở đầu tài sản N | `N. Quyền sử dụng đất tại: [Tài sản N - Địa chỉ] theo [Tài sản N - Loại sổ] số: [Tài sản N - Serial]; Số vào sổ cấp GCN: [Tài sản N - Số vào sổ] do [Tài sản N - Cơ quan cấp sổ] cấp ngày [Tài sản N - Ngày cấp sổ].` |
| `[Dòng thửa đất N]` | Số thửa, số tờ | `Thửa đất số: [Tài sản N - Số thửa], tờ bản đồ số: [Tài sản N - Số tờ].` |
| `[Dòng diện tích N]` | Tổng diện tích | `Diện tích: [Tài sản N - Diện tích] m2.` |
| `[Dòng hình thức sử dụng N]` | Hình thức sử dụng | `Hình thức sử dụng: [Tài sản N - Hình thức sử dụng].` |
| `[Dòng mục đích sử dụng N]` | Mục đích sử dụng | `Mục đích sử dụng: [Tài sản N - Mục đích sử dụng].` |
| `[Dòng thời hạn N]` | Thời hạn sử dụng | `Thời hạn sử dụng: [Tài sản N - Thời hạn].` |
| `[Dòng nguồn gốc N]` | Nguồn gốc sử dụng | `Nguồn gốc sử dụng đất: [Tài sản N - Nguồn gốc].` |
| `[Dòng loại đất N.M]` | Một dòng loại đất | `N.M. [Loại đất N.M - Loại đất]: [Loại đất N.M - Diện tích] m2; Thời hạn: [Loại đất N.M - Thời hạn].` |
| `[Đoạn mô tả di sản]` | Toàn bộ tài sản được xuất | Ghép các dòng tài sản và loại đất có dữ liệu |

## 7. Alias cũ

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| `[Tên N]`, `[Năm sinh N]`, `[CCCD N]` | Slot người của template cũ | Mapping tương thích cũ |
| `[Ngày cấp N]`, `[Nơi cấp CC N]`, `[Địa chỉ N]` | Giấy tờ, địa chỉ của slot cũ | Mapping tương thích cũ |
| `[Địa chỉ đất]`, `[Loại sổ]`, `[Serial]`, `[Số vào sổ]` | Tài sản chính của template cũ | Alias tài sản 1 |
| `[Số thửa]`, `[Số tờ]`, `[Diện tích]`, `[Nguồn gốc]` | Tài sản chính của template cũ | Alias tài sản 1 |
| `[ONT]`, `[CLN]`, `[NTS]`, `[LUC]` | Alias loại đất cũ | Để rỗng; template mới dùng `[Loại đất N.M - ...]` |

## 8. Tầng 3

| Placeholder | Chú thích | Hàm bên trong |
|---|---|---|
| Chưa dùng | Cụm phải đối chiếu nhiều phần của văn bản | - |
