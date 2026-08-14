# Memorybank kỹ thuật đồng bộ đa máy

**Status:** IMPLEMENTED — người dùng chốt hướng `CURRENT.md`-first ngày 2026-08-06 và mở rộng orchestration-first ngày 2026-08-14
**Date:** 2026-08-01; revised 2026-08-14
**Scope:** Ngữ cảnh kỹ thuật và trạng thái làm việc của dự án `notary_v2`

## 1. Mục tiêu

Cho phép tiếp tục công việc trên máy nhà, máy công ty hoặc sau khi compact context mà không phải giải thích lại ngữ cảnh, quyết định, nghiên cứu, trạng thái đang làm và bước tiếp theo.

Git là nguồn sự thật duy nhất. Memorybank chứa ngữ cảnh vận hành; các business spec, architecture ADR và platform contract hiện hữu vẫn là nguồn sự thật theo thứ tự trong `AGENTS.md`.

## 2. Quyết định thiết kế

- Đặt Memorybank trong cùng repository tại `memory-bank/`, theo naming phổ biến của các coding agent.
- Dùng Markdown thuần; không thêm database, ứng dụng web, dependency hoặc daemon đồng bộ.
- Đồng bộ qua Git private repository, có lịch sử, diff, rollback và dùng được offline.
- Chỉ lưu ngữ cảnh kỹ thuật; không lưu secret, credential hoặc dữ liệu khách hàng.
- Dùng ba lớp ngữ cảnh: rule ổn định trong `AGENTS.md`/ADR/docs; dashboard ngắn trong `CURRENT.md`; trạng thái phục hồi của task lớn trong `tasks/<task-id>.md`.
- `CURRENT.md` là entrypoint khi chuyển máy, tiếp tục việc dở hoặc sau compaction; file này chỉ route tới task đang liên quan và giữ Git state, blocker, next action đã kiểm chứng.
- Task record lưu goal/scope đã duyệt, quyết định của user, branch/worktree, agent, evidence, blocker, next action và thời điểm kiểm chứng gần nhất. Task state không suy ra từ lifecycle của agent.
- `PROGRESS.md` chỉ tổng hợp milestone và được đọc khi `CURRENT.md` dẫn tới; nó không phải lớp active task state thứ tư.
- Không sao chép nội dung normative từ `docs/`; Memorybank chỉ dẫn link hoặc ghi tóm tắt vận hành không có tính thay thế.
- Không bắt agent đọc Memorybank ở task mới không liên quan việc dở.

## 3. Cấu trúc

```text
memory-bank/
├── README.md
├── CURRENT.md
├── PROGRESS.md
└── tasks/
    ├── README.md
    └── <task-id>.md
```

### `README.md`

Mô tả ba lớp ngữ cảnh, nguồn sự thật, quy tắc cập nhật và quy trình bắt đầu/kết thúc phiên làm việc.

### `CURRENT.md`

Dashboard bàn giao hiện tại, được cập nhật sau milestone, blocker, compaction và trước khi push:

- thời điểm kiểm chứng gần nhất, branch, HEAD và worktree;
- dirty state đã kiểm chứng;
- link tới task đang làm hoặc đang block;
- blocker ngắn;
- bước tiếp theo cụ thể, có thể thực hiện ngay.

File này được cập nhật tại chỗ; không biến thành nhật ký dài hạn.

### `tasks/<task-id>.md`

Chỉ tạo cho task đủ lớn để parent sau này không thể phục hồi an toàn từ dashboard. Mỗi record giữ tối thiểu:

- task ID, task state, thời điểm cập nhật và kiểm chứng gần nhất;
- goal, scope đã duyệt, quyết định của user và non-goal;
- branch, worktree, baseline/checkpoint;
- agent label, vai trò, lifecycle quan sát gần nhất và assignment;
- evidence, blocker, next action và link tới authority/plan liên quan.

Task state dùng `TODO`, `DOING`, `BLOCKED`, `DONE`, `CANCELLED`. Lifecycle như working, idle, failed hoặc done chỉ là evidence; chỉ parent đổi task state sau khi kiểm tra Git, evidence và review gate. Không lưu session value tạm thời.

### `PROGRESS.md`

Tóm tắt trạng thái theo milestone: đã hoàn tất, đang làm, còn lại, known issues và các hướng đã bỏ. File này không phải changelog chi tiết; chi tiết nằm trong Git history hoặc tài liệu chuẩn được dẫn link.

## 4. Quy trình vận hành

### Bắt đầu trên một máy

1. Đồng bộ branch dự định dùng, rồi đọc `memory-bank/CURRENT.md` trước.
2. Kiểm tra branch, HEAD, worktree, dirty state và test claims với Git/source hiện tại.
3. Kiểm tra live-agent state bằng cơ chế điều khiển agent đang hoạt động; lifecycle trong task record chỉ là quan sát cũ.
4. Chỉ đọc task record và tài liệu chuẩn mà `CURRENT.md` dẫn tới.
5. Đối chiếu hoặc báo mọi state lỗi thời/mâu thuẫn trước khi tiếp tục `Next exact action`.

### Trong phiên

- Không để quyết định user, scope đã duyệt, evidence, blocker hoặc next action chỉ tồn tại trong chat/trí nhớ cục bộ.
- Cập nhật task record sau milestone, blocker, thay đổi hướng hoặc agent handoff; cập nhật `CURRENT.md` khi dashboard/next action đổi.
- Cập nhật `PROGRESS.md` chỉ khi milestone làm thay đổi tổng quan.

### Kết thúc phiên

1. Cập nhật task record với trạng thái thật, evidence, agent và bước tiếp theo.
2. Rút gọn `CURRENT.md` thành dashboard/link hiện tại; cập nhật `PROGRESS.md` nếu milestone đổi.
3. Cập nhật tài liệu chuẩn tương ứng nếu có quyết định lâu dài.
4. Chạy verify phù hợp với thay đổi và ghi rõ focused/full-suite status.
5. Commit và push toàn bộ checkpoint cần chuyển máy.

Trạng thái chưa commit không được xem là đã đồng bộ. Với công việc dở dang, dùng WIP commit để chuyển máy an toàn.

## 5. Tích hợp với coding agent

`AGENTS.md` có route ngắn tới `memory-bank/CURRENT.md` cho chuyển máy, tiếp tục việc dở hoặc phục hồi sau compaction. Memorybank chỉ cung cấp ngữ cảnh vận hành; các hard rule trong `AGENTS.md` vẫn được ưu tiên.

Parent chỉ nạp `AGENTS.md`, authority được route và active task state; sau đó tự kiểm tra Git và live-agent state. Worker nhận prompt mới, tối thiểu và khóa scope, đồng thời phải tự đọc authority áp dụng. Reviewer nhận original request, authority, base-to-head diff, production caller bị ảnh hưởng và test output thật trong context mới. Output giữa các agent là evidence/quyết định ngắn, không phải transcript.

Không bắt buộc agent đọc `README.md` hoặc `PROGRESS.md` ở mọi phiên. Chỉ mở khi `CURRENT.md` hoặc task hiện tại dẫn tới. Quy tắc orchestration ổn định thuộc [ADR-0002](../../architecture/decisions/0002-parent-agent-orchestration.md), không lặp lại chi tiết ở Memorybank.

## 6. Quy tắc tránh lệch ngữ cảnh

- Chỉ một file `CURRENT.md` làm handoff hiện tại.
- `CURRENT.md` là dashboard, không nhân bản nội dung chi tiết của task record; task record không nhân bản plan/spec.
- Task state và agent lifecycle là hai dữ kiện riêng; sau resume/compaction phải kiểm chứng cả Git lẫn live agent trước khi tiếp tục.
- Không dùng Memorybank để override `AGENTS.md`, ADR, domain spec hoặc platform contract.
- Mọi mục có thời hạn phải có ngày cập nhật; thông tin lỗi thời được thay thế hoặc xóa, còn lịch sử nằm trong Git.
- Không đưa secret vào Markdown; `.env` và credential vẫn theo cơ chế riêng.
- Nếu hai máy cùng sửa Memorybank, pull/rebase và giải quyết conflict trước khi tiếp tục; không tự động ghi đè.

## 7. Tiêu chí hoàn thành thiết kế

- Một checkout hoặc parent context mới có thể xác định task và hành động tiếp theo từ `CURRENT.md`, sau đó kiểm chứng với Git/live agent và đọc link cần thiết.
- `CURRENT.md` đủ ngắn để đọc nhanh; task lớn giữ recovery state trong một record được route, còn lịch sử chi tiết nằm trong Git.
- Quyết định user, approved scope, branch/worktree, agent, evidence, blocker, next action và last-verified của task lớn sống sót qua compaction mà không tạo task database.
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
