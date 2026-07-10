# AGENTS.md - notary_v2

Source of truth for agents working in `notary_v2`.
Updated: 2026-07-09.

Keep this file short. It should prevent bad edits and route agents to the right docs, not duplicate plans/history.

## 1. Hard rules

- Read this file before planning or editing.
- Do not scan the whole repo by default. Route to the right docs, then inspect only touched code.
- Do not edit, format, revert, move, or delete unrelated user changes.
- Do not change API contracts, router signatures, Celery contracts, DB schema, OCR flow, or business rules without explicit scope.
- If a business rule is ambiguous, state the case and ask the user. Do not guess.
- Prefer the smallest behavior-preserving change. Reuse existing code/patterns before adding new code.
- Use Ponytail/Superpowers discipline if available; do not duplicate those workflows here.

## 2. Scope discipline

Before editing code, state:

```text
TASK:
FILES TO TOUCH:
FILES NOT TO TOUCH:
RISK:
TEST:
SCOPE: LOCKED
```

Rules:
- Do not edit outside `FILES TO TOUCH`.
- If another file or broader change becomes necessary, stop and ask with `SCOPE BREAK REQUEST`.
- No new helper/class/module/abstraction unless needed and scoped.

## 3. Verify / report

- Run `.\verify.bat` for non-trivial code changes unless docs-only or explicitly out of scope.
- For concrete OCR/image bugs, use the OCR loop in the relevant OCR plan.
- Do not report success if verification failed.

Every file-changing task ends with:

```text
BAO CAO HOAN THANH:
- File changed/added/deleted:
- Verify:
- Scope match:
- Remaining risk/test:
```

## 4. Project overview

- App: notary/case-management system for inheritance land cases.
- Backend: FastAPI + SQLAlchemy + SQLite.
- Frontend: Jinja2 + Bootstrap + Vanilla JS.
- Diagram UI: ReactFlow embedded from `frontend/static/ReactFlowApp.jsx`.
- Active default OCR: Cloud AI OCR. Local OCR is parked/research code unless a task explicitly targets it.

## 5. Read routing

Before editing, read only the matching docs:

| Task area | Read first |
| --- | --- |
| Cloud OCR / AI OCR | `docs/plans/ocr_ai.md` |
| Local OCR parked engine / research | `docs/plans/ocr_local.md` |
| Case UX flow / Stage / Pool / Diagram interaction | `docs/specs/case_user_flow.md` |
| Case data-flow refactor | `docs/plans/cases_dataflow_v2.md` |
| Diagram inheritance engine / inheritance math | `docs/plans/inheritance_diagram.md` |
| Diagram visual / edges / connectors | `docs/plans/diagram_visual_v2.md` |
| Word template | `docs/plans/word_template_v2.md` |
| Feature plan index | `docs/plans/_INDEX.md` |

If a plan/spec conflicts with this file, stop and ask unless the newer source explicitly supersedes the older one.

## 6. Project red lines

- Stage is the UI source of truth for people in a case; Pool/Diagram must not mutate Stage person data.
- OCR modal `x` must not save, clear, reset, flush, or auto-stage.
- Cloud AI OCR is active default; Local OCR is parked/research unless explicitly scoped.
- Detailed invariants belong in the routed spec/plan files.

## 7. Run / smoke

```bash
run.bat
python -m uvicorn main:app --port 8000
.\verify.bat
```

Default URL: `http://127.0.0.1:8000`.
