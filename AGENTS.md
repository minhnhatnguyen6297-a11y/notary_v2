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
- New business content must pass the Business-spec gate in section 2 before any non-spec work.
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

### Business-spec gate

When the user introduces a new business rule, term, workflow, or expected behavior:

1. Read only the routed module entrypoint and linked spec index needed to locate existing coverage.
2. Before research, planning, coding, or other non-spec work, tell the user exactly one of:
   - `SPEC STATUS: DA CO - <APPROVED/DRAFT> - <path and section>`
   - `SPEC STATUS: CHUA CO/CHUA BAO PHU - can tao hoac cap nhat draft spec`
   - `SPEC STATUS: MAU THUAN - <conflicting paths or interpretations>`
3. If no approved spec covers the new content, stop non-spec work and create or update a draft using `docs/templates/spec-template.md` in the routed domain/platform location. Do not create a parallel source of truth.
4. Ask one business question at a time. Mark unresolved items `[NEEDS CLARIFICATION]`; do not create an implementation plan or edit code while any marker remains.
5. Only the user's explicit approval may authorize changing a business spec from `DRAFT` to `APPROVED`. If implementation later exposes a spec gap or conflict, return the spec to `DRAFT` and ask the user before continuing.

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
- QR is no longer part of the active OCR AI path. QR may be developed as a separate capability later, but the direction is not finalized yet.

## 5. Read routing

Read `docs/README.md` only when the task area is not obvious. Then read the matching module entrypoint:

| Task area | Read first |
| --- | --- |
| Hồ sơ thừa kế / inheritance rules | `docs/domains/inheritance/README.md` |
| Stage / Pool / inheritance case UX | `docs/domains/inheritance/README.md` |
| Cloud AI OCR / property OCR | `docs/platform/document-intake/README.md` |
| Local OCR | `docs/platform/document-intake/README.md`; parked, separate redesign required |
| Shared Stage / Pool capability | `docs/platform/case-workspace/README.md` |
| Word renderer / placeholder engine | `docs/platform/document-generation/README.md` |
| Fast text audit CLI | `docs/platform/fast-text-audit/README.md` |
| Architecture or module boundaries | `docs/architecture/README.md` |
| Cross-session technical context / handoff | `memory-bank/README.md`; then `PROJECT-CONTEXT.md`, `PROGRESS.md`, `CURRENT.md` |

Source precedence: `AGENTS.md` hard rules -> accepted architecture ADR -> domain spec -> platform contract -> technical/UX docs -> active plan -> research.

If code conflicts with a normative spec or contract, stop and report the conflict. Do not silently change either side.

`memory-bank/` is operational context only. It must not override `AGENTS.md`, accepted ADRs, domain specs, or platform contracts.

## 6. Graphify code graph

- A Graphify scan exists in `graphify-out/` for code navigation.
- For non-trivial code changes, bug hunts, cross-file impact checks, or "where is X?" tasks, consult the graph before broad file search.
- Useful commands from repo root:
  - `D:\graphify\.venv\Scripts\graphify.exe query "question" --graph graphify-out/graph.json`
  - `D:\graphify\.venv\Scripts\graphify.exe explain "NodeName" --graph graphify-out/graph.json`
  - `D:\graphify\.venv\Scripts\graphify.exe path "A" "B" --graph graphify-out/graph.json`
- Do not use Graphify as the source of truth for business rules; routed docs and touched code still win.
- After meaningful code changes, refresh with `D:\graphify\.venv\Scripts\graphify.exe update .`.

## 7. Project red lines

- Stage is the UI source of truth for people in a case; Pool/Diagram must not mutate Stage person data.
- OCR modal `x` must not save, clear, reset, flush, or auto-stage.
- Cloud AI OCR is active default; Local OCR is parked/research unless explicitly scoped.
- QR is out of scope for the active OCR AI path. If a task wants QR behavior, stop and confirm the intended separate direction first.
- Detailed invariants belong in the routed spec/plan files.

## 8. Run / smoke

```bash
run.bat
python -m uvicorn main:app --port 8000
.\verify.bat
```

Default URL: `http://127.0.0.1:8000`.
