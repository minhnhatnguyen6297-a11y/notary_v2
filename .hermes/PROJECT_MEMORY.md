# PROJECT_MEMORY.md - notary_v2

Purpose: compact Hermes-local project memory that does **not** override `AGENTS.md`.

## Source of truth

- `AGENTS.md` is the only source of truth for agent rules in this repo.
- Do not create `.hermes.md` unless the user intentionally wants Hermes-specific rules to shadow/augment repo behavior.
- Read `AGENTS.md` first, then relevant `docs/plans/` or domain/spec docs for the module being touched.

## Project character

- Business-rule-heavy notary/case-management app.
- Correctness means preserving domain behavior, workflow state, API contracts, OCR contracts, Celery task contracts, and data/schema expectations.
- Prefer the smallest safe change; avoid helper/class/module abstractions for Normal tasks unless the user approves.

## Stable stack facts

- Backend: FastAPI + SQLAlchemy + SQLite.
- Frontend: Jinja2 + Bootstrap + Vanilla JS; ReactFlow is embedded for diagram UI.
- OCR: Cloud AI OCR and Local RapidOCR/VietOCR are separate pipelines and should stay independently debuggable.
- Async OCR jobs use Celery and `tasks.py`.

## Working discipline

- For Normal/Major code edits, follow the `AGENTS.md` scope-lock workflow before editing.
- For bug fixes: reproduce or explain why reproduction is blocked, trace root cause, identify blast radius, and add/update regression coverage where possible.
- For OCR tasks with concrete images/expected output, follow the mandatory OCR comparison loop in `AGENTS.md`.
- Run `.\verify.bat` for Normal/Major edits unless the task is docs-only or explicitly out of scope.

## Token/cost discipline

- Do not scan the whole repo by default.
- Start from `AGENTS.md`, `docs/plans/_INDEX.md`, and the specific plan/spec named for the module.
- Avoid reading `venv/`, `.git/`, `runtime/`, logs, DB files, and generated assets unless needed for the task.
