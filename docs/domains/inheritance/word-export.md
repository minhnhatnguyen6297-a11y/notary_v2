# Word Export UX và Flow

Cập nhật: 22/07/2026

## 1. Mục đích

User công chứng có thể tự chỉnh file Word theo văn phong riêng bằng các
placeholder có sẵn. User không phải viết code, không tự tạo rule nghiệp vụ và
không phải chọn lại người trong màn hình xuất Word.

Word là nơi trình bày văn bản. Diagram là nơi xác định quan hệ, chủ đất và
người nhận. Code là nơi khóa nghiệp vụ và dựng các câu có điều kiện. Catalog là
nơi giải thích placeholder đang hỗ trợ.

## 2. Nguồn dữ liệu và thẩm quyền

| Nội dung | Nguồn chuẩn |
|---|---|
| Thông tin cá nhân | Stage |
| Quan hệ huyết thống/vợ chồng | Diagram |
| Chủ đất | Nút `Chủ đất` trên Diagram |
| Người nhận | Lựa chọn `Nhận` trên Diagram |
| Người không nhận | `Tất cả người trên Diagram - Chủ đất - Người nhận` |
| Người từ chối | Dữ liệu pháp lý được xác nhận riêng; không suy ra từ `Nhận` |
| Tài sản | Dữ liệu tài sản của hồ sơ |
| Câu chữ pháp lý | Resolver và hàm dựng cụm |
| Placeholder được phép | Catalog |

Không suy ra rule thừa kế từ tên placeholder hoặc từ câu chữ cố định trong
template.

## 3. Phạm vi V1

- Một văn bản xuất từ một đến năm tài sản đã liên kết với hồ sơ.
- Tài sản chính đứng trước; các tài sản còn lại theo thứ tự liên kết trong hồ sơ.
- Một tài sản tương ứng một thửa đất và có thể chứa nhiều dòng loại đất.
- Danh sách chủ đất, người nhận và người không nhận áp dụng chung cho toàn bộ tài sản trong văn bản.
- Danh sách người từ chối, nếu có dữ liệu pháp lý riêng, cũng áp dụng theo phạm vi văn bản được xác nhận.
- Các nhóm tự động gồm: `Người`, `Chủ đất sống`, `Chủ đất chết`,
  `Người nhận`, `Người không nhận`.
- `Người từ chối` chỉ có dữ liệu khi hồ sơ có đầu vào pháp lý được xác nhận;
  hệ thống hiện không suy ra nhóm này từ Diagram.
- Không có trạng thái public `từ chối trước`, `từ chối sau`, `chưa chọn`.
- Không có block engine `if/for` trong Word.
- Hỗ trợ placeholder trường lẻ và cụm tầng 2 dựng sẵn.

## 4. Quy tắc placeholder

Placeholder mới dùng dạng:

```text
[Tên danh sách N - Trường]
```

Ví dụ:

```text
[Người 3 - Họ tên]
[Người 3 - Quan hệ]
[Người nhận 1 - Họ tên]
[Chủ đất chết 1 - Ngày chết]
```

- `[Người 3 - ...]`: `3` là số người trên Diagram.
- `[Người nhận 1 - ...]`: `1` là thứ tự của người nhận trong danh sách.
- Trường dùng chung: họ tên, xưng hô, giới tính, ngày sinh, ngày chết,
  giấy tờ, ngày/nơi cấp, địa chỉ, quan hệ, vai trò, tỷ lệ.
- Alias cũ được giữ để mở template cũ nhưng không dùng làm mẫu mới.

## 5. UX xuất Word

Điều kiện trước khi xuất:

- Stage đã có người.
- Diagram đã lưu quan hệ.
- Có ít nhất một chủ đất.
- Có ít nhất một người nhận.
- Hồ sơ có tài sản.

Luồng thao tác:

1. User mở màn hình xuất Word.
2. User chọn một template trong bảng mini `Mẫu Word`.
3. App dùng toàn bộ tài sản đã liên kết với hồ sơ; không chọn lại người hoặc tài sản tại màn hình này.
4. App lấy snapshot Stage, Diagram và danh sách tài sản.
5. App dựng `WordExportContext`, resolver thay placeholder và tạo DOCX.
6. App trả file để trình duyệt tải xuống. Thư mục lưu cuối cùng theo cấu hình
   tải xuống của trình duyệt.

Màn hình xuất Word chỉ có bảng chọn template và nút `Xuất`. Không có bảng chọn
người nhận, người không nhận, người từ chối, người ký hoặc thư mục lưu. Người
nhận/người không nhận được xác định từ Diagram; người từ chối chỉ lấy từ dữ liệu
pháp lý riêng nếu có; danh sách tài sản lấy từ hồ sơ.

Khi có nhiều tài sản, `[Đoạn mô tả di sản]` bắt đầu bằng `Các quyền sử
dụng đất như sau:`, sau đó đánh số tài sản `1`, `2`, ... Các dòng loại đất của
tài sản N đánh số `N.1`, `N.2`, ...

## 6. Tầng placeholder

### Tầng 1 — trường trực tiếp

Lấy một giá trị từ snapshot:

```text
[Người 3 - Họ tên]
[Tài sản - Địa chỉ]
[Chủ đất sống 1 - Số giấy tờ]
```

### Tầng 2 — câu/dòng dựng sẵn

Một placeholder tầng 2 bao trọn câu hoặc dòng có dấu câu. Nếu điều kiện không
đúng, toàn bộ placeholder rỗng.

Ví dụ:

```text
[Dòng người không nhận 3]
[Dòng người từ chối 3]
[Dòng chủ đất sống tặng cho 1]
[Dòng mô tả quan hệ người 5]
```

`[Dòng người không nhận N]` lấy từ quyết định trên Diagram. `[Dòng người từ
chối N]` chỉ có giá trị khi hồ sơ có dữ liệu từ chối pháp lý được xác nhận; nó
không được resolver tự điền từ danh sách người không nhận.

Không để user tự ghép nhiều placeholder điều kiện với dấu câu rời nếu có thể
dùng một dòng tầng 2.

### Tầng 3

Chưa triển khai. Chỉ thêm khi cần đối chiếu nhiều đoạn trong cùng văn bản và
được chốt bằng một case nghiệp vụ cụ thể.

## 7. Luồng xử lý kỹ thuật

```text
Stage
  -> Diagram state
  -> Asset snapshot
  -> WordExportContext
  -> explicit resolver
  -> placeholder mapping
  -> DOCX
  -> browser download
```

Router chỉ nhận request, chọn template và trả file. Logic phân loại người,
dựng câu và thay placeholder nằm trong service Word.

## 8. Kiểm tra trước khi trả file

- Báo lỗi nếu thiếu tài sản, chủ đất hoặc người nhận.
- Báo lỗi nếu hồ sơ có quá năm tài sản.
- Báo lỗi placeholder không được resolver hỗ trợ.
- Không trả DOCX còn placeholder chưa thay; route trả lỗi để user sửa template.
- Cụm tầng 2 không được để lại dấu phẩy, dấu chấm, dấu nối hoặc dòng rác.
- Kiểm tra paragraph, table, header/footer và placeholder bị tách thành nhiều
  Word run.
- Test bằng template `word_templates/1. PCDS .docx` và các fixture nghiệp vụ.

## 9. Ngoài phạm vi

- Gán danh sách người nhận riêng cho từng tài sản. V1 dùng một danh sách người
  nhận chung từ Diagram cho tất cả tài sản trong văn bản.
- Block lặp/điều kiện `if/for` trong Word.
- User tự khai báo placeholder mới.
- Word tự suy luận quan hệ hoặc tỷ lệ.
- Thay đổi Stage, OCR hoặc DB schema.
