# Rule Tạm Thời Cho 3 Loại Văn Bản

Ngày tổng kết: 2026-04-07

Phạm vi hiện tại chỉ áp dụng cho:
- Hợp đồng chuyển nhượng
- Văn bản cam kết tài sản riêng
- Văn bản hủy bỏ hợp đồng chuyển nhượng

Các loại văn bản khác sẽ bổ sung rule riêng sau.

## Nguồn mẫu đã quét

Các rule dưới đây được rút ra từ chính các file đã bôi đỏ phần `tài_sản` hoặc các file cùng mẫu:
- `UPLOAD/tháng 3 Phương/31.03 Dũng/1.Hợp đồng chuyển nhượng Tài Đào.doc`
- `UPLOAD/tháng 3 Phương/25.03 Nam Hoàng Thu/1.Hợp đồng chuyển nhượng Thu Nam - Copy.doc`
- `UPLOAD/tháng 3 Phương/25.03 Nam Hoàng Thu/1.Hợp đồng chuyển nhượng Thu Hoàng.doc`
- `UPLOAD/tháng 3 Phương/23.03 Thành Hưng/1.Hợp đồng chuyển nhượngThành hưng.doc`
- `UPLOAD/tháng 3 Phương/19.03 Thìn Lý/1.Hợp đồng chuyển nhượng Tài Đào.doc`
- `UPLOAD/tháng 3 Phương/16.03 Đức Lan/1.Hợp đồng chuyển nhượng Tài Đào.doc`
- `UPLOAD/tháng 3 Phương/09.03 Cao Huongw/1.Hợp đồng chuyển nhượng Tài Đào.doc`
- `UPLOAD/tháng 3 Phương/05.03.2026 Sinh Vinh/1.Hợp đồng chuyển nhượng Tài Đào.doc`
- `UPLOAD/tháng 3 Phương/04.03 Tích lượng/1.Hợp đồng chuyển nhượng  BP 04.doc`
- `UPLOAD/tháng 3 Phương/04.03 Tích lượng/1.Hợp đồng chuyển nhượng  87.doc`
- `UPLOAD/tháng 3 Phương/04.03 Tích lượng/HĐCN (QSHNO và QSDĐƠ).doc`
- `UPLOAD/tháng 3 Phương/03.31cam kết tài sản riêng ngân hàng Huệ Dũng.doc`
- `UPLOAD/tháng 3 Phương/04.03 Tích lượng/23.hủy HĐ Mua bán nhà và chuyển nhượng quyền sử dụng đất.doc`
- `UPLOAD/tháng 3 Phương/04.03 Tích lượng/23.hủy  đất.doc`
- `UPLOAD/tháng 3 Phương/04.03 Tích lượng/23.hủy  cnhà.doc`
- `UPLOAD/tháng 3 Phương/04.03 Tích lượng/23.hủy  chuyển nhượng quyền sử dụng đất.doc`

## Kết luận chung từ phần bôi đỏ

Phần bôi đỏ cho thấy `tài_sản` không phải lúc nào cũng là cả một điều khoản giống nhau.

Có 3 pattern khác nhau:
- `Hợp đồng chuyển nhượng`: phần đỏ là một block mô tả tài sản tương đối đầy đủ, thường bắt đầu từ câu `Đối tượng của Hợp đồng này là...`
- `Cam kết tài sản riêng`: phần đỏ là block mô tả tài sản riêng và các quyền liên quan đến tài sản đó
- `Hủy bỏ hợp đồng chuyển nhượng`: phần đỏ chỉ là đoạn tham chiếu ngắn tới tài sản của hợp đồng cũ, không phải full block như hợp đồng chuyển nhượng

Vì vậy phải tách rule theo loại văn bản, không dùng chung một regex cắt `tài_sản` cho cả 3 nhóm.

## 1. Hợp Đồng Chuyển Nhượng

### Rule nhận diện `ten_hop_dong`

Ưu tiên lấy đúng tiêu đề ngay sau quốc hiệu.

Các title thực tế đã thấy:
- `HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT`
- `HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT VÀ TÀI SẢN GẮN LIỀN VỚI ĐẤT`
- Biến thể cũ: mô tả `nhà ở và quyền sử dụng đất ở`

Rule chuẩn hóa tạm thời:
- Nếu title có `và tài sản gắn liền với đất` thì giữ nguyên full title đó
- Nếu title chỉ có `quyền sử dụng đất` thì giữ `Hợp đồng chuyển nhượng quyền sử dụng đất`
- Nếu body mô tả `nhà ở và quyền sử dụng đất ở` thì xếp cùng nhóm chuyển nhượng và coi là biến thể có tài sản gắn liền với đất

### Rule lấy `tài_sản`

#### Điểm bắt đầu

Ưu tiên các anchor sau:
- `Đối tượng của Hợp đồng này là`
- `1.1 Đối tượng của Hợp đồng này là`

Trong thực tế, câu mở đầu của block đỏ thường rơi vào một trong các dạng:
- `Đối tượng của Hợp đồng này là toàn bộ quyền sử dụng đất...`
- `Đối tượng của Hợp đồng này là một phần quyền sử dụng đất...`
- `Đối tượng của Hợp đồng này là toàn bộ quyền sử dụng đất và tài sản gắn liền với đất...`
- `Đối tượng của Hợp đồng này là chủ sở hữu nhà ở và quyền sử dụng đất ở...`

#### Nội dung cần lấy

Lấy trọn block mô tả tài sản, bao gồm đoạn mở đầu và các dòng chi tiết phía dưới.

Các nhánh cấu trúc đã thấy:
- Dạng bullet:
  - `- Thửa đất số`
  - `- Địa chỉ`
  - `- Diện tích`
  - `- Hình thức sử dụng`
  - `- Mục đích sử dụng`
  - `- Thời hạn sử dụng`
  - `- Nguồn gốc sử dụng`
- Dạng a/b/c/d/đ/e:
  - `a. Thửa đất số`
  - `b. Diện tích`
  - `c. Loại đất`
  - `d. Thời hạn sử dụng`
  - `đ. Hình thức sử dụng`
  - `e. Địa chỉ`
- Dạng nhà ở + đất ở cũ:
  - `Nhà ở:`
  - `Địa chỉ`
  - `Tổng diện tích sử dụng`
  - `Diện tích xây dựng`
  - `Kết cấu nhà`
  - `Số tầng`
  - `Đất ở:`
  - rồi đến các dòng bảng / nhãn như `Số tờ bản đồ`, `Số thửa`, `Diện tích`, `Mục đích sử dụng`, `Thời gian sử dụng`, `Phần ghi thêm`

#### Điểm kết thúc

Ưu tiên dừng tại marker gần nhất sau block tài sản:
- `1.2`
- `Bằng Hợp đồng này`
- `ĐIỀU 2`

Với mẫu cũ không có marker rõ, dừng khi:
- hết chuỗi các dòng chi tiết tài sản
- hoặc sang đoạn nói về giá chuyển nhượng, thanh toán, giao nhận

### Gợi ý rule code

- Sau khi xác định đúng title là chuyển nhượng, ưu tiên cắt `tài_sản` bằng anchor start/end thay vì regex quá ngắn
- Nếu body có `Nhà ở:` hoặc `tài sản gắn liền với đất` thì `loai_tai_san` nên là `Đất đai có tài sản`
- Nếu body chỉ có `quyền sử dụng đất` và không có nhánh nhà ở / tài sản gắn liền thì `loai_tai_san` là `Đất đai không có tài sản`

## 2. Văn Bản Cam Kết Tài Sản Riêng

### Rule nhận diện `ten_hop_dong`

Title mẫu đã thấy:
- `VĂN BẢN CAM KẾT TÀI SẢN RIÊNG`

Rule chuẩn hóa:
- `Văn bản cam kết tài sản riêng`

### Rule lấy `tài_sản`

#### Điểm bắt đầu

Anchor mở đầu trong mẫu hiện tại:
- `Ông ... hiện đang sở hữu Tài Sản là ...`

Block đỏ không bắt đầu từ `Chúng tôi gồm có` mà bắt đầu từ đoạn xác định tài sản cụ thể.

#### Nội dung cần lấy

Lấy đầy đủ 3 phần sau nếu có:
- Đoạn mô tả tài sản chính:
  - `... hiện đang sở hữu Tài Sản là quyền sử dụng đất ...`
  - rồi đến các dòng `Thửa đất số`, `Địa chỉ`, `Diện tích`, `Hình thức sử dụng`, `Mục đích sử dụng`, `Thời hạn sử dụng`, `Nguồn gốc sử dụng`
- Đoạn mở rộng về tài sản gắn liền với đất:
  - `Tài sản gắn liền với thửa đất nói trên...`
- Đoạn mở rộng về quyền, lợi ích, khoản thanh toán:
  - `Các quyền, lợi ích, khoản thanh toán mà ... có thể nhận được liên quan tới quyền sử dụng đất...`

#### Điểm kết thúc

Dừng trước đoạn kết luận/cam đoan, ưu tiên các anchor:
- `Bằng văn bản này chúng tôi xác định:`
- `Hai vợ chồng chúng tôi cam đoan:`
- `Chúng tôi công nhận`

### Gợi ý rule code

- Không dùng parser `BÊN A/B` cho loại này như hợp đồng chuyển nhượng
- `tài_sản` ở loại này có thể dài hơn 1 block đất vì còn bao gồm:
  - tài sản gắn liền với đất
  - quyền, lợi ích, khoản thanh toán liên quan

## 3. Văn Bản Hủy Bỏ Hợp Đồng Chuyển Nhượng

### Rule nhận diện `ten_hop_dong`

Title mẫu đã thấy:
- `VĂN BẢN THOẢ THUẬN VỀ VIỆC HUỶ BỎ HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT VÀ TÀI SẢN GẮN LIỀN VỚI ĐẤT`
- Các biến thể rút gọn trong tên file:
  - `hủy đất`
  - `hủy cnhà`
  - `hủy chuyển nhượng quyền sử dụng đất`

Rule chuẩn hóa tạm thời:
- Nếu title có `HUỶ BỎ` hoặc `HỦY BỎ` và có `HỢP ĐỒNG CHUYỂN NHƯỢNG` thì giữ nguyên title văn bản hủy bỏ
- Nếu body nói rõ `thoả thuận huỷ bỏ ... Hợp đồng chuyển nhượng ...` nhưng title OCR chưa ổn, vẫn xếp vào nhóm `văn bản hủy bỏ hợp đồng chuyển nhượng`

### Rule lấy `tài_sản`

#### Bản chất khác với hợp đồng chuyển nhượng

Ở loại này, phần đỏ không phải block tài sản đầy đủ kiểu `Đối tượng của Hợp đồng`.
Nó chỉ là đoạn tham chiếu tới tài sản của hợp đồng cũ.

#### Điểm bắt đầu

Anchor thường nằm trong điều 1 hoặc điều 2:
- `... chuyển nhượng quyền sử dụng đất có địa chỉ tại:`
- `... mua bán nhà ở và chuyển nhượng quyền sử dụng đất có địa chỉ tại:`

#### Nội dung cần lấy

Lấy đoạn tham chiếu tài sản từ chỗ `có địa chỉ tại:` đến hết phần thông tin giấy chứng nhận / ngày cấp / cập nhật biến động.

Các thành phần thực tế được bôi đỏ:
- địa chỉ tài sản
- câu `(nay là ...)` nếu có
- `Giấy chứng nhận quyền sử dụng đất...`
- `số: ...`
- `Số vào sổ cấp GCN: ...`
- `cấp ngày ...`
- `cập nhật biến động ngày ...` nếu có

#### Điểm kết thúc

Dừng trước một trong các đoạn sau:
- `và được Công chứng viên`
- `và được ... chứng nhận`
- `số công chứng ...`
- phần giải thích về việc hai bên muốn hủy / thỏa thuận lại

### Gợi ý rule code

- Không tái dùng rule `Đối tượng của Hợp đồng này là ...`
- Với loại hủy bỏ, `tài_sản` nên là đoạn tham chiếu ngắn gọn
- Nếu cần chi tiết sâu như hợp đồng gốc, phải truy về hợp đồng gốc, không suy ra từ văn bản hủy bỏ

## Rule ưu tiên theo loại văn bản

Khi extract, nên đi theo thứ tự:
1. Nhận diện loại văn bản từ title thật sau quốc hiệu
2. Chọn rule `tài_sản` riêng cho loại đó
3. Chỉ fallback sang heuristic chung nếu title không rõ

Thứ tự nhận diện tạm thời:
1. Nếu title chứa `cam kết tài sản riêng` -> dùng rule `Cam kết tài sản riêng`
2. Nếu title chứa `hủy bỏ` và `hợp đồng chuyển nhượng` -> dùng rule `Văn bản hủy bỏ hợp đồng chuyển nhượng`
3. Nếu title chứa `hợp đồng chuyển nhượng` -> dùng rule `Hợp đồng chuyển nhượng`

## Điểm cần lưu ý khi implement

- Không dùng chung 1 regex ngắn cho mọi loại văn bản
- `tài_sản` phải là block theo anchor, không chỉ là 1 dòng
- Với văn bản hủy bỏ, block `tài_sản` ngắn hơn rõ rệt
- Với cam kết tài sản riêng, block `tài_sản` còn bao gồm cả tài sản gắn liền với đất và các quyền/lợi ích liên quan
- Các marker stop quan trọng cần ưu tiên:
  - `1.2`
  - `ĐIỀU 2`
  - `Bằng Hợp đồng này`
  - `Bằng văn bản này chúng tôi xác định`
  - `Hai vợ chồng chúng tôi cam đoan`
  - `và được Công chứng viên`

## Hướng dùng file này

File này là bản tổng kết rule nghiệp vụ tạm thời.

Khi bạn bôi đỏ thêm cho các loại văn bản khác, chỉ cần:
- bổ sung nguồn mẫu
- thêm section mới theo đúng format:
  - rule nhận diện `ten_hop_dong`
  - rule lấy `tài_sản`
  - anchor bắt đầu
  - anchor kết thúc
  - ngoại lệ
