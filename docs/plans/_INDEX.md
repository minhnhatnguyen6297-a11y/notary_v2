# Index: Feature Plans (legacy; pending Task 5 deletion)

Mỗi chức năng lớn có 1 file plan riêng. **Đọc plan trước khi sửa code.**

| Chức năng | File | Trạng thái | Files code liên quan |
|---|---|---|---|
| OCR AI (Cloud) | [spec.md](../platform/document-intake/spec.md) | active | `routers/ocr_ai.py` |
| OCR Local (CPU) | [ocr_local.md](ocr_local.md) | active | `routers/ocr_local.py`, `tasks.py` |
| Cases data flow V2 | [case-state.md](../domains/inheritance/technical/case-state.md) | PLANNED (12/05/2026) | `routers/cases.py`, `models.py`, `frontend/templates/cases/form.html`, `frontend/static/ReactFlowApp.jsx`, `frontend/static/case_state.js` (mới) |
| Quy tắc nghiệp vụ thừa kế | [spec.md](../domains/inheritance/spec.md) | DRAFT REVIEW (22/07/2026) | Source of truth nghiệp vụ |
| Inheritance case catalog | [case-catalog.md](../domains/inheritance/research/case-catalog.md) | DRAFT REVIEW (22/07/2026) | Fixture và acceptance |
| Diagram UI/UX | [ux.md](../domains/inheritance/ux.md) | DRAFT REVIEW (22/07/2026) | `frontend/static/ReactFlowApp.jsx`, `frontend/static/diagram_edges.js`, `frontend/templates/cases/form.html` |
| Inheritance Engine V2 implementation | [inheritance-engine.md](../domains/inheritance/technical/inheritance-engine.md) | DRAFT REVIEW (22/07/2026) | Backend engine, React adapter, persistence, Word và test |
| Word Template V2 | [technical.md](../platform/document-generation/technical.md) | active | `services/word_engine.py`, `routers/cases.py`, `word_templates/placeholder_mapping.md` |
| Fast text audit | [technical.md](../platform/fast-text-audit/technical.md) | active | `tools/run_fast_audit.py`, `services/fast_audit/` |
| Word Export UX | [word-export.md](../domains/inheritance/word-export.md) | SPEC | `services/word_engine.py`, `routers/cases.py`, `word_templates` |

---

## Cách dùng

1. Trước khi làm việc với chức năng nào → mở file plan tương ứng.
2. Sau khi có quyết định thiết kế mới hoặc chốt plan → cập nhật file plan.
3. Khi deprecated một approach → ghi vào mục "Những thứ đã thử và thất bại".
