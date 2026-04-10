# Index: Feature Plans

Mỗi chức năng lớn có 1 file plan riêng. **Đọc plan trước khi sửa code.**

| Chức năng | File | Trạng thái | Files code liên quan |
|---|---|---|---|
| OCR AI (Cloud) | [ocr_ai.md](ocr_ai.md) | active | `routers/ocr.py` |
| OCR Local (CPU) | [ocr_local.md](ocr_local.md) | active | `routers/ocr_local.py`, `tasks.py` |
| OCR Local Handoff 2026-04-10 | [ocr_local_handoff_2026-04-10.md](ocr_local_handoff_2026-04-10.md) | handoff | `routers/ocr_local.py`, `tests/test_ocr_local_v4.py`, `frontend/templates/cases/form.html`, `tasks.py` |

---

## Cách dùng

1. Trước khi làm việc với chức năng nào → mở file plan tương ứng.
2. Sau khi có quyết định thiết kế mới hoặc chốt plan → cập nhật file plan.
3. Khi deprecated một approach → ghi vào mục "Những thứ đã thử và thất bại".
