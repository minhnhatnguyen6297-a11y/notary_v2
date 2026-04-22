---
description: "Claudex — debate plan giữa Planner/Critic Codex, duyệt, implement, ghi lịch sử vào CLAUDE.md"
argument-hint: "module/feature: mô tả task"
---

Bạn đang thực thi quy trình **Claudex**. Tuân theo đúng thứ tự 4 phase sau. Không được implement trước khi có xác nhận `y` của user — đây là invariant tuyệt đối.

---

## Phase 1 — NHẬP TASK

Argument là `$ARGUMENTS`. Parse theo format `"module/feature: mô tả"` hoặc dùng toàn bộ làm mô tả tự do.

**Tạo task file tạm** tại `runtime/codex_relay_task_tmp.md` với nội dung:

```
Lam gi: <mô tả task từ argument>
Sua phan nao: <hỏi user nếu không có trong argument, hoặc suy từ module/feature>
Pham vi: <suy từ module/feature nếu có, hỏi nếu không rõ>
Muc tieu: <hỏi user nếu không có>
```

Nếu argument đã đủ 4 trường → ghi file luôn. Nếu thiếu → hỏi user từng trường còn thiếu rồi ghi.

**Nếu task là `test OCR` / `debug OCR` / `kiểm thử OCR` / `OCR sai` trên case cụ thể:**
- Tuân theo mục `Vong lap kiem thu OCR bat buoc` trong `CLAUDE.md` trước khi tạo draft.
- Claude phải tự chốt đủ: `batch anh`, `expected`, `direct output`, `project/UI output`, `tang nghi ngo sai`, `muc tieu fix vong hien tai`.
- Nếu thiếu bất kỳ mục nào ở trên:
  - không được chạy `python tools/codex_relay.py draft --task runtime/codex_relay_task_tmp.md`
  - không được gọi Codex để "đoán bug"
  - phải hỏi user để chốt đầu vào hoặc báo `blocked` nếu không thể tự lấy `direct output` / `project/UI output`
- Với OCR task đã đủ điều kiện, task file tạm phải thêm các dòng sau dưới 4 trường chuẩn:
```
Batch anh: <bo anh dang debug>
Expected: <ket qua ky vong da chot>
Direct output: <ket qua lay truc tiep o tang ham/router>
Project/UI output: <ket qua khi chay project/UI>
Tang nghi ngo sai: <mot tang cu the>
Muc tieu fix vong nay: <muc tieu cua vong dang relay>
```

Sau khi có file, chạy:
```
python tools/codex_relay.py draft --task runtime/codex_relay_task_tmp.md
```

Đợi lệnh hoàn tất. Ghi lại đường dẫn `run_dir` từ dòng `Draft created at: ...` trong stdout.

---

## Phase 2 — HIỂN THỊ KẾT QUẢ DEBATE

**Mục tiêu:** user phải đọc được debate ngay trong transcript, KHÔNG cần click đi đâu. Vì `codex_relay` ghi artifact vào main repo trong khi Claude Code có thể đang ở worktree, markdown link đôi lúc không mở được — nên **LUÔN inline-preview full content**.

**Bước bắt buộc (theo thứ tự):**
1. Đọc `planner.md`, `critic.md`, `final_plan.md` bằng tool Read.
2. Tính relative path từ CWD hiện tại tới từng file (dùng `../` nếu artifact nằm ngoài worktree). Nếu không chắc, kiểm tra bằng `pwd` và so với `run_dir`.
3. Hiển thị block sau:

```
━━━ KẾT QUẢ DEBATE ━━━

📁 Artifacts (link click + bản preview dưới đây):
  • [planner.md](<relative-path>/planner.md)
  • [critic.md](<relative-path>/critic.md)
  • [final_plan.md](<relative-path>/final_plan.md)
  • Run dir (copy mở tay nếu link lỗi): `<run_dir tuyệt đối>`

────────── 🔵 PLANNER.MD ──────────
<PASTE full nội dung planner.md vào đây>

────────── 🟡 CRITIC.MD ──────────
<PASTE full nội dung critic.md vào đây>

────────── 🔵 FINAL_PLAN.MD ──────────
<PASTE full nội dung final_plan.md vào đây>
──────────────────────────────────

[g] góp ý thêm  [y] duyệt implement  [n] hủy
```

**Quy tắc bắt buộc:**
- Mỗi lần Phase 2 chạy (kể cả sau `[g]` re-draft) đều phải inline full 3 file — không tóm tắt, không bỏ.
- Nếu file dài quá (>500 dòng), vẫn paste đầy đủ; không cắt.
- Link markdown vẫn gắn (relative path) để ai muốn mở file riêng thì có, nhưng KHÔNG được dùng link thay cho inline preview.
- Bỏ option `[d] xem full final plan` vì nội dung đã hiển thị sẵn.

**Xử lý lựa chọn user:**

- `d` → đọc và in toàn bộ `final_plan.md`, rồi hỏi lại `[y/n/g]`
- `g` → hỏi: "Góp ý của bạn (sẽ tạo lại draft với feedback này):" → đọc input → thêm vào task file dưới dạng ghi chú `Note từ user: ...` → chạy lại `codex_relay.py draft ...` với cùng `--run-dir` → quay lại đầu Phase 2
- `n` → in "Đã hủy. Run lưu tại: <run_dir>" → kết thúc
- `y` → sang Phase 3

---

## Phase 3 — APPROVE VÀ IMPLEMENT

**Invariant:** Chỉ thực hiện phase này sau khi user gõ `y` ở Phase 2.

Chạy tuần tự:
```
python tools/codex_relay.py approve --run-dir "<run_dir>"
python tools/codex_relay.py execute --run-dir "<run_dir>" --with-review
```

Đợi `execute` hoàn tất. Đọc `execution_summary.md` và `review.md` (nếu có), hiển thị tóm tắt:

```
━━━ IMPLEMENTATION DONE ━━━
✅ Codex đã implement. Xem chi tiết: <run_dir>/execution_summary.md

📋 Review:
  <tóm tắt 2-3 dòng từ review.md nếu có>
```

---

## Phase 4 — KNOWLEDGE CAPTURE (ghi vào CLAUDE.md)

Tổng hợp task vừa xong thành 2 lớp:

**[Mô tả]** — 1-2 câu, ngôn ngữ thường, ai cũng hiểu:
  Chức năng này làm gì? Người dùng cuối thấy gì?

**[Tech]** — ghi kỹ thuật:
  - File/Endpoint liên quan (lấy từ execution_summary.md)
  - Công nghệ, thư viện chính
  - Quyết định kỹ thuật quan trọng từ final_plan.md
  - Bug còn lại (nếu reviewer ghi nhận)
  - Cập nhật: <ngày hôm nay dd/mm/yyyy>

**Xác định khóa entry:**
- Lấy phần `module/feature` trước dấu `:` trong argument gốc
- Normalize: trim, lowercase, `/` thành ` > `, collapse whitespace thừa
- Ví dụ: `"cases/OCR AI: fix bug"` → khóa so sánh `cases > ocr ai`, heading hiển thị `cases > OCR AI`
- Nếu argument không có `/`, dùng toàn bộ mô tả làm khóa

**Quy tắc ghi vào CLAUDE.md — chỉ sửa vùng marker:**
1. Tìm block `<!-- claudex-history-start -->` ... `<!-- claudex-history-end -->` trong CLAUDE.md
2. Nếu block chưa tồn tại → append vào cuối file:
   ```
   ## Lịch sử chức năng

   <!-- claudex-history-start -->
   <!-- claudex-history-end -->
   ```
3. Trong block, tìm heading `### <khóa-normalized>` (so sánh case-insensitive sau normalize)
4. Nếu tìm thấy → **overwrite toàn bộ entry đó** (từ heading đến trước heading tiếp theo hoặc end marker)
5. Nếu chưa có → **insert entry mới** trước `<!-- claudex-history-end -->`
6. **Tuyệt đối không sửa bất kỳ nội dung nào ngoài block marker**

**Format entry:**
```markdown
### cases > OCR AI
**[Mô tả]:** Chức năng đọc ảnh CCCD tự động, gọi AI Qwen, tự điền vào form thừa kế.
**[Tech]:**
- Endpoint: `POST /api/ocr/analyze` → `routers/ocr_ai.py`
- Công nghệ: Qwen VL, DASHSCOPE_API_KEY, regex MRZ
- Quyết định: QR hit ưu tiên hơn AI result cho cùng ảnh
- Bug còn lại: pairing lỗi batch >4 ảnh — ghi nhận, chưa fix
- Cập nhật: 22/04/2026
```

Sau khi ghi xong, in:
```
📚 CLAUDE.md đã được cập nhật — entry: <heading>
```

Xóa file tạm `runtime/codex_relay_task_tmp.md` nếu tồn tại.

---

## Xử lý lỗi

**`codex_relay.py draft` fail:**
- In lỗi đầy đủ từ stderr
- Không chuyển sang Phase 2
- Gợi ý: kiểm tra `codex` CLI đã login chưa (`cmd /c codex.cmd --version`)

**`execute` fail sau khi đã approve:**
- In lỗi, nhắc user: "Run đã được approve. Chạy lại thủ công: `python tools/codex_relay.py execute --run-dir <run_dir>`"
- Không ghi CLAUDE.md vì chưa có execution_summary.md

**Codex không ghi đúng file artifact (planner.md / critic.md / final_plan.md vắng):**
- Báo rõ file nào thiếu
- Dừng, không tiếp tục Phase 2
