# UI/UX sơ đồ thừa kế

> **Trạng thái:** DRAFT chờ user duyệt và chờ audit code.
> **Cập nhật:** 22/07/2026.
> **Nguồn nghiệp vụ:** `spec.md`.

File này chỉ quy định cách thao tác và hiển thị. Không định nghĩa lại nghiệp vụ.

## 1. Nguyên tắc hiển thị

- Tree tối giản, dùng phân tầng và đường huyết thống để thể hiện quan hệ.
- Card dùng một format chung, không phụ thuộc nguồn OCR, Excel hay nhập thủ công.
- Card hiển thị họ tên, ngày sinh/ngày chết, tỷ lệ cuối, nút xóa assignment và hai
  nút `Chủ đất`, `Nhận`.
- Không có dấu `★`, nút `Từ chối`, trạng thái `unset/accept/refuse` hoặc chú thích
  dài trên card.
- `Chủ đất` và `Nhận` có thể cùng bật. Tắt `Nhận` không xóa sở hữu gốc.
- Chỉ hiện slot do vòng di sản hoặc nhánh thế vị đang hoạt động yêu cầu. Với nhánh
  thế vị, sinh slot vợ/chồng của người chết trước để tạo đúng cặp cha mẹ của các
  con; card vợ/chồng này không nhận phần thế vị. Không dùng heuristic “có ngày chết
  thì mở toàn bộ gia đình”. Node đã có dữ liệu không tự biến mất khi tính lại; UI
  phải báo để user xử lý nếu quan hệ không còn hợp lệ.
- Đường huyết thống hiển thị mặc định bằng nét mảnh, màu trung tính, vuông góc: vợ
  chồng nối ngang, cha/mẹ nối xuống con. Đường này không tham gia tính tỷ lệ.
- Không vẽ mũi tên tài sản trên canvas vì một người có thể nhận từ nhiều nguồn.
- Tree tự layout theo thế hệ; cặp vợ chồng là một cụm; nhánh thế vị nằm dưới đúng
  người trung gian. Khi rộng, dùng cuộn ngang, không wrap hoặc tạo panel nhánh phụ.
- Cảnh báo hiển thị từng dòng trong một vùng chung, không chồng popup. Trường hợp
  `chưa hỗ trợ` không được hiển thị như kết quả đã tính chính xác.

## 2. Xem cách tính

Toolbar có nút thu gọn `Xem cách tính`. Khi đóng, tree chỉ hiển thị tỷ lệ cuối trên
card. Khi mở, mỗi người nhận có đúng một dòng công thức:

```text
Người A nhận: 17/40 = 3/10 (X) + 1/10 (Y) + 1/40 (Z)
Người B nhận: 1/2 = 1/4 (X) + 1/4 (A tặng cho)
Người C nhận: 1/6 = 1/6 (X, thế vị nhánh Y)
```

- Mỗi số hạng ghi nguồn trong ngoặc. Thế vị ghi nguồn di sản thật và nhánh đi qua,
  không ghi người chết trước như thể họ là nguồn di sản.
- Tặng cho/chuyển quyền phải phân biệt với thừa kế.
- Không hiển thị JSON, tên field kỹ thuật hoặc chi tiết từng vòng mặc định.
- UI chỉ đọc kết quả giải thích từ engine, không tự tính lại.

## 3. Điều kiện hoàn thành

- Card chỉ còn hai quyết định `Chủ đất`, `Nhận` và giữ đúng trạng thái sau save/reload.
- Node/slot xuất hiện đúng theo output nghiệp vụ, không theo ngày chết đơn lẻ.
- Quan hệ gia đình đọc được mà không cần mũi tên tài sản hoặc chú thích nhánh phụ.
- `Xem cách tính` giải thích đủ tổng và từng nguồn bằng một dòng cho mỗi người.
