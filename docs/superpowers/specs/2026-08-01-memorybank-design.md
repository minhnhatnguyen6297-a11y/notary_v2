# Memorybank kỹ thuật đồng bộ đa máy

**Status:** IMPLEMENTED — người dùng chốt hướng `CURRENT.md`-first ngày 2026-08-06
**Date:** 2026-08-01  
**Scope:** Ngữ cảnh kỹ thuật và trạng thái làm việc của dự án `notary_v2`

## 1. Mục tiêu

Cho phép tiếp tục công việc trên máy nhà hoặc máy công ty mà không phải giải thích lại ngữ cảnh, quyết định, nghiên cứu, trạng thái đang làm và bước tiếp theo.

Git là nguồn sự thật duy nhất. Memorybank chứa ngữ cảnh vận hành; các business spec, architecture ADR và platform contract hiện hữu vẫn là nguồn sự thật theo thứ tự trong `AGENTS.md`.

## 2. Quyết định thiết kế

- Đặt Memorybank trong cùng repository tại `memory-bank/`, theo naming phổ biến của các coding agent.
- Dùng Markdown thuần; không thêm database, ứng dụng web, dependency hoặc daemon đồng bộ.
- Đồng bộ qua Git private repository, có lịch sử, diff, rollback và dùng được offline.
- Chỉ lưu ngữ cảnh kỹ thuật; không lưu secret, credential hoặc dữ liệu khách hàng.
- `CURRENT.md` là entrypoint khi chuyển máy hoặc tiếp tục việc dở; `PROGRESS.md` chỉ tổng hợp milestone và được đọc khi `CURRENT.md` dẫn tới.
- Không sao chép nội dung normative từ `docs/`; Memorybank chỉ dẫn link hoặc ghi tóm tắt vận hành không có tính thay thế.
- Không bắt agent đọc Memorybank ở task mới không liên quan việc dở.

## 3. Cấu trúc

```text
memory-bank/
├── README.md
├── CURRENT.md
└── PROGRESS.md
```

### `README.md`

Mô tả mục đích, nguồn sự thật, quy tắc cập nhật và quy trình bắt đầu/kết thúc phiên làm việc.

### `CURRENT.md`

Trạng thái bàn giao hiện tại, được cập nhật sau mỗi milestone và trước khi push:

- thời điểm, máy, branch;
- mục tiêu hiện tại;
- việc đã hoàn tất;
- file đã thay đổi;
- lệnh verify và kết quả;
- blocker/câu hỏi mở;
- bước tiếp theo cụ thể, có thể thực hiện ngay.

File này được cập nhật tại chỗ; không biến thành nhật ký dài hạn.

### `PROGRESS.md`

Tóm tắt trạng thái theo milestone: đã hoàn tất, đang làm, còn lại, known issues và các hướng đã bỏ. File này không phải changelog chi tiết; chi tiết nằm trong Git history hoặc tài liệu chuẩn được dẫn link.

## 4. Quy trình vận hành

### Bắt đầu trên một máy

1. `git pull --rebase`.
2. Đọc `memory-bank/CURRENT.md` trước.
3. Kiểm tra branch, commit, worktree và test claims trong file với Git hiện tại.
4. Chỉ đọc tài liệu chuẩn hoặc file Memorybank mà `CURRENT.md` dẫn tới.
5. Tiếp tục từ `Next exact action` nếu bằng chứng vẫn khớp.

### Trong phiên

- Không để thông tin quan trọng chỉ tồn tại trong chat hoặc trí nhớ cục bộ.
- Cập nhật `CURRENT.md` sau milestone, blocker hoặc thay đổi hướng; cập nhật `PROGRESS.md` khi milestone làm thay đổi tổng quan.

### Kết thúc phiên

1. Cập nhật `CURRENT.md` với trạng thái thật và bước tiếp theo.
2. Cập nhật `PROGRESS.md` nếu có thay đổi milestone.
3. Cập nhật tài liệu chuẩn tương ứng nếu có quyết định lâu dài.
4. Chạy verify phù hợp với thay đổi code.
5. Commit và push toàn bộ checkpoint cần chuyển máy.

Trạng thái chưa commit không được xem là đã đồng bộ. Với công việc dở dang, dùng WIP commit để chuyển máy an toàn.

## 5. Tích hợp với coding agent

`AGENTS.md` có một route ngắn tới `memory-bank/CURRENT.md` chỉ cho trường hợp chuyển máy hoặc tiếp tục việc dở. Memorybank chỉ cung cấp ngữ cảnh vận hành; các hard rule trong `AGENTS.md` vẫn được ưu tiên.

Không bắt buộc agent đọc `README.md` hoặc `PROGRESS.md` ở mọi phiên. Chỉ mở khi `CURRENT.md` hoặc task hiện tại dẫn tới.

## 6. Quy tắc tránh lệch ngữ cảnh

- Chỉ một file `CURRENT.md` làm handoff hiện tại.
- Không dùng Memorybank để override `AGENTS.md`, ADR, domain spec hoặc platform contract.
- Mọi mục có thời hạn phải có ngày cập nhật; thông tin lỗi thời được thay thế hoặc xóa, còn lịch sử nằm trong Git.
- Không đưa secret vào Markdown; `.env` và credential vẫn theo cơ chế riêng.
- Nếu hai máy cùng sửa Memorybank, pull/rebase và giải quyết conflict trước khi tiếp tục; không tự động ghi đè.

## 7. Tiêu chí hoàn thành thiết kế

- Một checkout mới có thể xác định mục tiêu và hành động tiếp theo từ `CURRENT.md`, sau đó kiểm chứng với Git và đọc link cần thiết.
- File handoff và progress đủ ngắn để đọc nhanh; lịch sử chi tiết chỉ được mở theo link khi cần.
- Ngữ cảnh kỹ thuật quan trọng có diff và lịch sử Git.
- Máy thứ hai có thể khôi phục trạng thái sau `git pull --rebase`.
- Không tạo nguồn sự thật song song cho business rule, architecture hoặc platform contract.
- Không cần service hoặc dependency mới.

## 8. Ngoài phạm vi

- Tự động đồng bộ nền.
- Giao diện web để duyệt Memorybank.
- Semantic search/vector database.
- Đồng bộ secret hoặc dữ liệu nghiệp vụ.
- Thay thế hệ thống tài liệu hiện hữu của dự án.

## 9. Căn cứ tham khảo

- Cline Memory Bank: dùng các file core tách theo foundation, context, active state và progress; khuyến nghị `activeContext` chỉ giữ trạng thái hiện tại, còn `progress` là bản tổng hợp ngắn. Xem [Cline Memory Bank](https://www.mintlify.com/cline/cline/features/memory-bank).
- Roo Code Memory Bank: cũng tách `activeContext`, `progress`, `decisionLog`, `projectBrief` và `systemPatterns`, cho thấy cấu trúc này phù hợp với workflow coding agent khác. Xem [Roo Code Memory Bank](https://github.com/GreatScottyMac/roo-code-memory-bank).

Thiết kế này giữ phần cốt lõi tương thích với các mẫu trên nhưng giản lược theo repo hiện tại: không thêm product-context riêng vì `docs/domains/` và `docs/platform/` đã là nguồn tài liệu chuẩn.

## 10. Câu hỏi còn lại

Không có. Nếu implementation phát hiện thiếu hoặc mâu thuẫn với spec hiện hữu, phải dừng và cập nhật design/spec trước khi mở rộng phạm vi.
