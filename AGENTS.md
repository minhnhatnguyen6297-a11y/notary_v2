# AGENTS.md — notary_v2

Quy định quyền quyết định, phạm vi, nơi tra cứu và điều kiện hoàn tất. Quy tắc nghiệp vụ nằm trong đặc tả, không chép lại ở đây.

## 1. Quyền quyết định và phạm vi

- Giữ nguyên thay đổi của người dùng và trạng thái bên ngoài; không sửa, hoàn tác, commit hoặc xuất bản việc ngoài yêu cầu.
- Chỉ thay đổi hành vi đã được người dùng cho phép. Nghiệp vụ, API/data contract, schema DB, luồng OCR và hành vi dùng chung phải có phạm vi rõ cho mọi mô-đun bị ảnh hưởng.
- Nếu yêu cầu, đặc tả, contract hoặc hành vi thực tế mâu thuẫn: báo bằng chứng, dừng phần liên quan và hỏi người dùng nguồn nào được ưu tiên; không tự sửa một phía.
- Trước khi sửa, xác định: mục tiêu, hành vi được phép, tệp/mô-đun dự kiến, ranh giới dùng chung và bằng chứng nghiệm thu; đánh dấu `SCOPE: LOCKED`.
- Nếu cần mở rộng sang mô-đun, lõi dùng chung, contract hoặc nghiệp vụ khác: gửi `SCOPE BREAK REQUEST`, nêu phụ thuộc, hành vi ảnh hưởng và lý do không thể tiếp tục an toàn. Chỉ người dùng được mở rộng phạm vi; không sửa kế hoạch để hợp thức hóa việc đã làm.
- Chỉ người dùng duyệt đặc tả nghiệp vụ. Thiếu đặc tả, còn nháp, mơ hồ hoặc lệch thực tế thì chưa được triển khai hành vi nghiệp vụ mới/thay đổi.

## 2. Nguồn chuẩn và tài liệu tham chiếu

Thứ tự: `AGENTS.md` → ADR đã chấp nhận → đặc tả nghiệp vụ đã duyệt → platform contract → tài liệu kỹ thuật/UX → kế hoạch đang làm → nghiên cứu/lịch sử.

Chỉ đọc `docs/README.md` khi chưa rõ khu vực công việc; nếu đã rõ, đi thẳng tới:

| Công việc | Đọc trước |
| --- | --- |
| Thừa kế và UX hồ sơ | `docs/domains/inheritance/README.md` |
| Tiếp nhận tài liệu, Cloud AI OCR | `docs/platform/document-intake/README.md` |
| OCR cục bộ — cần phạm vi riêng | `docs/platform/document-intake/README.md` |
| Stage/Pool dùng chung | `docs/platform/case-workspace/README.md` |
| Sinh văn bản Word | `docs/platform/document-generation/README.md` |
| Kiểm tra văn bản nhanh | `docs/platform/fast-text-audit/README.md` |
| Quyết định kiến trúc | `docs/architecture/README.md` |

- Tiếp tục việc gián đoạn/chuyển máy: đọc `memory-bank/CURRENT.md` trước, đối chiếu Git rồi chỉ theo liên kết liên quan. Memory Bank không thay thế nguồn chuẩn hoặc bằng chứng mới.
- Issue và đặc tả cục bộ: `docs/agents/issue-tracker.md`; cách dùng domain docs và ADR: `docs/agents/domain.md`.

### Tài liệu chung giữa các repo: chỉ đọc khi cần

`D:\systemdocs` dùng chung cho `notary_v2`, `upload_lab`, `notaryoffice`; ba dự án sẽ dùng chung một DB.

- Khi chạm ranh giới sản phẩm, khóa định danh chung (CCCD, số sê-ri GCN, thửa đất, số công chứng) hoặc tích hợp: chỉ đọc tệp cần thiết — `PROJECTS.md`, `contracts/entities.md` (chuẩn hóa khóa), `OPEN_DECISIONS.md` (không tự chốt).
- Trước khi chọn công nghệ mới (nhà cung cấp OCR, ORM, hàng đợi, UI framework…) hoặc quyết định kiến trúc: bắt buộc đọc `D:\systemdocs\TECH_STACK.md`.
- Tài liệu chung không ghi đè quy định nội bộ repo; gặp mâu thuẫn phải báo, không âm thầm chọn một bên.

## 3. Tra cứu mã và đánh giá ảnh hưởng

- Biết file/symbol/chuỗi cần tìm: tìm, đọc có mục tiêu hoặc dùng LSP; không gọi graph/index cho sửa đổi cục bộ đã rõ vị trí.
- Chưa rõ quan hệ giữa các file hoặc ownership: dùng graph Graphify hiện có, bắt đầu ở độ sâu 1–2 và chỉ mở rộng khi thiếu bằng chứng:
  `D:\graphify\.venv\Scripts\graphify.exe query "<câu hỏi>" --graph graphify-out/graph.json`
- Graph chỉ dẫn đường; luôn đọc mã hiện tại trước khi sửa hoặc kết luận hành vi. Graph thiếu/cũ/không đủ thì đọc mã trực tiếp; chỉ cập nhật khi cần, không dựng lại toàn bộ cho sửa đổi thường lệ.
- Log/dữ liệu lớn: dùng `ctx_execute`/`ctx_batch_execute` nếu có để lọc, giữ exit code và đường dẫn tới dữ liệu đầy đủ. Kết quả nhỏ đọc trực tiếp; `ctx_search` chỉ dùng sau `ctx_index`.

## 4. Quy trình thực hiện

Chỉ dẫn repo/người dùng ưu tiên hơn skill. Ưu tiên thay đổi nhỏ nhất, giữ hành vi hiện có và tận dụng mã sẵn có.

- **Làm rõ yêu cầu (discovery)** (tính năng mới, tái cấu trúc lớn, yêu cầu chưa rõ): dùng `grill-with-docs` hoặc `grilling` + `domain-modeling`; không dùng `brainstorming` khi discovery theo Matt Pocock đang diễn ra. Có thể dùng `prototype`, nhưng phải xóa mã thử trước khi duyệt đặc tả và triển khai thật.
- **Đặc tả**: kết thúc discovery bằng `to-spec`, lưu ở `docs/superpowers/specs/<feature>.md` hoặc issue. Người dùng duyệt tài liệu này là đủ điều kiện thiết kế; không làm lại discovery hoặc đổi nghiệp vụ đã duyệt nếu chưa được người dùng cho phép rõ ràng. Ưu tiên phiên mới/`handoff` sau khi lưu và được duyệt; tính năng lớn có thể dùng `to-tickets` để chia thành các task độc lập.
- **Kế hoạch và triển khai**: dùng `writing-plans`, lưu bước TDD, đường dẫn chính xác, lệnh và tiêu chí kiểm chứng ở `docs/superpowers/plans/<feature>.md`; thực hiện bằng `subagent-driven-development` hoặc `executing-plans`.
- **Workspace riêng và verification**: dùng `using-git-worktrees` khi cần workspace riêng; nếu Windows khóa tệp, dùng nhánh riêng. Tuân thủ `test-driven-development`, `systematic-debugging` khi sửa lỗi và `verification-before-completion`; dùng `finishing-a-development-branch` sau khi đã kiểm chứng xong.
- **Sửa lỗi**: bỏ qua discovery; đi thẳng từ `systematic-debugging` → test hồi quy thất bại → sửa nguyên nhân gốc → kiểm chứng lại.
- **Agent**: mặc định tắt `dispatching-parallel-agents` trừ khi được yêu cầu rõ; tối đa 2 subagent đồng thời và chỉ một bên ghi trên mỗi worktree/nhánh.

## 5. Review và hoàn tất

Mỗi task/slice hoàn thành phải được người hoặc agent độc lập, với context riêng, review trước khi làm phần phụ thuộc hoặc commit. Người thực hiện không tự duyệt. Reviewer phải đọc yêu cầu gốc, đặc tả có thẩm quyền, diff từ base đến bản hiện tại, production caller bị ảnh hưởng và kết quả kiểm tra thực tế; không chỉ dựa vào tóm tắt của người thực hiện.

Review phải kết luận:

```text
SCOPE: PASS/FAIL — có thiếu, thừa hoặc hiểu sai yêu cầu không
SPEC: PASS/FAIL — có khớp đặc tả không
SHARED IMPACT: PASS/FAIL — đã kiểm tra consumer và contract bị ảnh hưởng chưa
TEST EVIDENCE: SUFFICIENT/INSUFFICIENT — kiểm tra theo từng mô-đun; báo riêng full test suite
VERDICT: APPROVE/BLOCK
```

Hành vi chưa được duyệt, ảnh hưởng dùng chung chưa rõ hoặc mâu thuẫn đặc tả/thực tế đều chặn việc tiếp theo và commit, dù test đạt.

Sau sửa mã, chạy kiểm tra/hồi quy liên quan; với sửa mã không đơn giản, chạy thêm `.\verify.bat` trừ khi ngoài phạm vi. Chỉ tuyên bố hoàn tất khi có bằng chứng mới; không gọi focused checks là full test suite đã đạt.

Báo cáo cuối phải nêu: **tệp đã đổi; phạm vi đạt/không đạt; có/không đổi hành vi dùng chung và mô-đun ảnh hưởng; focused checks; trạng thái full test suite; rủi ro còn lại.**
