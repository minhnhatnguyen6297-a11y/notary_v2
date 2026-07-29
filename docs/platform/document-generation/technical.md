# DOCX generation — Technical contract

Status: active
Owner: platform/document-generation
Source of truth: shared DOCX renderer and placeholder-engine technical contract

Cập nhật: 20/07/2026

## Phạm vi tài liệu

- This document defines the shared DOCX renderer and placeholder engine contract.
- Rule thừa kế và danh sách chủ đất/người nhận: `docs/domains/inheritance/spec.md`.
- Ý nghĩa placeholder nghiệp vụ thừa kế thuộc `docs/domains/inheritance/word-export.md`.
- UX và flow xuất Word: `docs/domains/inheritance/word-export.md`.
- Danh mục placeholder đang hỗ trợ: `word_templates/placeholder_mapping.md`.
- Resolver và thay DOCX: `services/word_engine.py`.
- Router chỉ điều phối request/response, không sở hữu logic dựng văn bản.

## Quy tắc implementation V1

- V1 xuất từ một đến năm tài sản đã liên kết với hồ sơ trong cùng một văn bản.
- Tài sản chính là tài sản số 1; tài sản còn lại theo thứ tự liên kết.
- Loại đất dùng chỉ số `N.M`: N là số tài sản, M là số dòng loại đất trong tài sản đó.
- Các tài sản dùng chung danh sách chủ đất/người nhận từ Diagram; chưa gán người nhận riêng theo tài sản.
- User dùng placeholder tiếng Việt trong dấu `[]`.
- Quy tắc public: `[Tên danh sách N - Trường]`.
- N của `[Người N - Trường]` là số người trên Diagram.
- N của các danh sách lọc là thứ tự trong danh sách đó.
- Nguồn người, quan hệ, chủ đất và người nhận lấy từ Stage/Diagram đã lưu.
- Người từ chối chỉ có dữ liệu khi hồ sơ có đầu vào pháp lý xác nhận riêng;
  không suy ra từ người không nhận trên Diagram.
- Không để resolver đoán rule từ tên placeholder; mọi placeholder phải có mapping rõ.
- Tầng 1 là trường dữ liệu trực tiếp.
- Tầng 2 là câu/dòng dựng sẵn, rỗng toàn bộ khi điều kiện không áp dụng.
- Chưa làm block engine `if/for` trong Word.

## WordExportContext

Resolver chỉ phân loại người một lần khi dựng context:

| Danh sách | Công thức |
|---|---|
| `Người` | Tất cả node người đang hoạt động trên Diagram, theo thứ tự node |
| `Chủ đất sống` | `Người` có dấu `Chủ đất` và chưa chết |
| `Chủ đất chết` | `Người` có dấu `Chủ đất` và đã chết |
| `Người nhận` | `Người` có `willReceive = true` |
| `Người từ chối` | Dữ liệu pháp lý xác nhận riêng; hiện để trống |

Một người có thể đồng thời thuộc `Chủ đất sống` và `Người nhận`. Không có
nhóm hoặc trạng thái public `chưa chọn`. `inheritanceDecision` chỉ được đọc để
migrate hồ sơ cũ khi node chưa có `willReceive`.

## Tương thích

- Giữ alias cũ như `[Tên 1]`, `[CCCD 1]` nếu template cũ còn sử dụng.
- Alias cũ không phải quy tắc đặt tên cho template mới.
- Không đổi API/router/DB contract chỉ để đổi tên placeholder.

## Thứ tự triển khai

1. Chốt `docs/domains/inheritance/word-export.md`.
2. Tạo fixture nghiệp vụ và expected mapping.
3. Đổi resolver theo danh sách `Người`, `Chủ đất sống`, `Chủ đất chết`, `Người nhận`, `Người từ chối`.
4. Cập nhật catalog và template PCDS.
5. Test resolver, DOCX và dữ liệu thật.

## Kiểm thử

- Unit test resolver và các danh sách mapping.
- Test paragraph, table, header/footer và placeholder bị tách thành nhiều run.
- Test người sống/chết, một/nhiều chủ đất, một/nhiều người nhận.
- Test owner sống là người nhận, owner sống không là người nhận và đồng sở hữu.
- Test một đến năm tài sản, tài sản chính đứng trước và loại đất đánh số `N.M`.
- Test template PCDS thật với hai tài sản trong cùng một DOCX.
- Test alias cũ và placeholder chưa được thay.
- Render DOCX thật để kiểm tra dòng trống, dấu câu và layout.
- Chạy `.\verify.bat` trước khi bàn giao code.
