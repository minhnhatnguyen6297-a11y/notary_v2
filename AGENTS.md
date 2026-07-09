# AGENTS.md - notary_v2

Source of truth for agents working in `notary_v2`.
Updated: 2026-07-09.

This file is intentionally short. It should route agents to the right domain docs, not duplicate every plan/history detail.

## 1. Hard rules

- Read this file before planning or editing.
- Do not scan the whole repo by default. Read the task, route to the right docs, then inspect only touched code.
- Do not edit, format, revert, move, or delete unrelated user changes.
- Do not change API contracts, router signatures, Celery task names/contracts, DB schema, OCR flow, or business rules without explicit scope.
- If a business rule is ambiguous, state the case and ask the user. Do not guess.
- Prefer the smallest behavior-preserving change. Reuse existing code/patterns before adding new code.
- No new helper/class/module/abstraction for a Normal task unless the user approves.
- For bug fixes: reproduce or explain why blocked, trace root cause, identify blast radius, and leave focused regression coverage when non-trivial.
- Use Ponytail/Superpowers discipline if available; do not reimplement those workflows in this file.

## 2. Tier / scope

`TRIVIAL`:
- Max 1 file and max 20 net lines.
- Text/log/comment/doc-only changes.
- Must not touch router signatures, `models.py`, `tasks.py`, DB schema, OCR flow, Celery task, API contract, or business behavior.

`NORMAL`:
- Max 3 files and max 100 net lines.
- Small bugfix/feature.
- No schema/router/Celery/OCR/cross-module contract changes.
- No new abstraction unless user approves.

`MAJOR`:
- Anything beyond Normal, or anything touching OCR flow, router signature, DB schema, `models.py`, `tasks.py`, migrations, dependencies, refactors, or cross-module contracts.

Before editing code in Normal/Major tasks, print:

```text
TASK:
TIER:
FILES TO TOUCH:
FILES NOT TO TOUCH:
RISK:
TEST:
SCOPE: LOCKED
```

If scope changes after lock, stop and print:

```text
SCOPE BREAK REQUEST
- Reason:
- Extra file/tier needed:
- Risk if not included:
- Extra test:
```

## 3. Verify / report

- `TRIVIAL`: run a relevant check if available; otherwise say why not.
- `NORMAL` / `MAJOR`: run `.\verify.bat` unless the task is docs-only or explicitly out of scope.
- OCR with concrete images/expected output: follow `docs/procedures/ocr_debug_loop.md` if present; otherwise follow the OCR loop in the relevant OCR plan.
- Do not report success if verification failed. Report the failed step and next action.

Every completed file-changing task must end with:

```text
BAO CAO HOAN THANH:
- File changed/added/deleted:
- Symbols added/removed:
- Verify:
- Scope match:
- Remaining risk/test:
```

## 4. Project overview

- App: notary/case-management system for inheritance land cases.
- Backend: FastAPI + SQLAlchemy + SQLite.
- Frontend: Jinja2 + Bootstrap + Vanilla JS.
- Diagram UI: ReactFlow embedded from `frontend/static/ReactFlowApp.jsx`.
- Async jobs: Celery in `tasks.py`.
- OCR: Cloud AI OCR and Local RapidOCR/VietOCR are separate pipelines.

Core files:

- `main.py`: app startup, env, migrations, routers, OCR warmup.
- `database.py`: engine/session/light migrations.
- `models.py`: `Customer`, `Property`, `InheritanceCase`, `OCRJob`, `ExtractedDocument`.
- `routers/cases.py`: case screen, stage/diagram persistence, preview/template flow.
- `routers/ocr_ai.py`: Cloud OCR / AI OCR.
- `routers/ocr_local.py`: Local OCR.
- `tasks.py`: Celery worker for Local OCR jobs.
- `frontend/templates/cases/form.html`: main case UI and OCR/stage bridge.
- `frontend/static/ReactFlowApp.jsx`: diagram UI.

## 5. Read routing

Before editing, read only the matching docs:

| Task area | Read first |
| --- | --- |
| Cloud OCR / AI OCR | `docs/plans/ocr_ai.md` |
| Local OCR / Celery OCR | `docs/plans/ocr_local.md` |
| Case UX flow / Stage / Pool / Diagram interaction | `docs/specs/case_user_flow.md` |
| Case data-flow refactor | `docs/plans/cases_dataflow_v2.md` |
| Diagram inheritance engine / inheritance math | `docs/plans/inheritance_diagram.md` |
| Diagram visual / edges / connectors | `docs/plans/diagram_visual_v2.md` |
| Word template | `docs/plans/word_template_v2.md` |
| Feature plan index | `docs/plans/_INDEX.md` |

If a plan/spec conflicts with this file, stop and ask unless the newer source is explicitly marked as superseding the older one.

## 6. Critical invariants

### Case flow

- Stage is the UI source of truth for people in a case.
- Pool is computed from committed Stage minus Diagram assignments.
- Diagram stores assignments, relationships, engine/render state; it must not mutate Stage person data.
- OCR modal is temporary. Only user `Luu` pushes OCR result to Stage.
- OCR modal `x` only hides/minimizes; it must not save, clear, reset, flush, or auto-stage.
- Stage `Cap nhat` commits Stage and syncs related views.
- Pool/Diagram actions must not delete Stage people.

### OCR

- OCR correctness is final business JSON over a batch, not pretty raw text.
- Batch OCR may involve mixed order, front/back images, multiple CCCDs, and non-CCCD images.
- Cloud OCR prioritizes latency; do not add fallback by habit.
- Local OCR prioritizes research/accuracy/pairing.
- Keep AI OCR and Local OCR independently debuggable. Do not casually share QR/parser helpers across them.

### Persistence/contracts

- Keep existing API contracts unless scope explicitly says otherwise.
- Keep Celery task names stable: `process_ocr_job`, `process_ocr_batch_job`.
- Avoid DB schema changes unless the task is explicitly Major.
- If Stage deletes a person and user commits, Diagram/Pool must cascade from Stage, not invent a separate truth.

## 7. Run / smoke

```bash
run.bat
python -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO
python -m uvicorn main:app --port 8000
.\verify.bat
```

Default URL: `http://127.0.0.1:8000`.
