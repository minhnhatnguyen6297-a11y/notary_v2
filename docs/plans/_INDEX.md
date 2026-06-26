# Index: Feature Plans

Mỗi chức năng lớn có 1 file plan riêng. **Đọc plan trước khi sửa code.**

| Chức năng | File | Trạng thái | Files code liên quan |
|---|---|---|---|
| OCR AI (Cloud) | [ocr_ai.md](ocr_ai.md) | active | `routers/ocr_ai.py` |
| OCR Local (CPU) | [ocr_local.md](ocr_local.md) | active | `routers/ocr_local.py`, `tasks.py` |
| Cases data flow V2 | [cases_dataflow_v2.md](cases_dataflow_v2.md) | PLANNED (12/05/2026) | `routers/cases.py`, `models.py`, `frontend/templates/cases/form.html`, `frontend/static/ReactFlowApp.jsx`, `frontend/static/case_state.js` (mới) |
| Diagram Visual V2 | [diagram_visual_v2.md](diagram_visual_v2.md) | PLANNED (26/06/2026) | `frontend/static/ReactFlowApp.jsx`, `frontend/static/diagram_edges.js`, `frontend/templates/cases/form.html` |

---

## Cách dùng

1. Trước khi làm việc với chức năng nào → mở file plan tương ứng.
2. Sau khi có quyết định thiết kế mới hoặc chốt plan → cập nhật file plan.
3. Khi deprecated một approach → ghi vào mục "Những thứ đã thử và thất bại".
