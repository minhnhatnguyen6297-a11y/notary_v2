# Current dashboard

Updated: 2026-08-17
Last verified: 2026-08-17 against Git and the named source worktrees.

Active integration checkout: `D:\notary_v2-worktrees\main-integration-20260813`
Branch: `codex/main-integration-20260813`
Product-code baseline: `8e0b5ab`; this dashboard update may be uncommitted.
Checkpoint: the commit containing this `CURRENT.md`; resolve with
`git log -1 --format=%H -- memory-bank/CURRENT.md`.
Before acting, run fresh `git status --short --branch`; this docs slice may be
uncommitted.

## Goal

Reconstruct three isolated workstreams safely:

- Main keeps stable work, with the Cloud AI OCR baseline Qwen-only.
- A future clean Diagram branch receives the OCR modal -> Stage -> Pool ->
  Diagram flow and Diagram/Word work in progress.
- A future clean Zalo branch owns Zalo work separately.

Clean branch reconstruction and promotion may proceed under explicit scope.
Remote containment is required before cleanup of old sources; keep old worktrees
untouched until containment and explicit cleanup approval.

## Verified main state

- Promoted main `8e0b5ab` contains Qwen-only Cloud OCR from `42c88b3`,
  Customer hardening from `e849188`, and standalone Fast Audit.
- Local `main` and `origin/main` were both verified at
  `8e0b5ab8c502b22dc041aa2e634e331059fc8752` after fast-forward promotion.
- Fast Audit is committed at `7d2a16d` with all six contracted outputs. Its
  independent review verdict is `APPROVE`; focused tests passed 36/36.
- `python -m pytest tests -q` passed 120/120, all Node `.test.mjs` suites
  exited 0, `FULL_VERIFY=1` passed 44 OCR and 36 Fast Audit tests, and
  Graphify was refreshed to 1175 nodes and 2660 edges. Repository-root pytest
  separately collected the parked root Local OCR diagnostic: 120 passed and
  that one out-of-scope test failed.
- Local OCR/QR behavior remains a separate parked/research boundary; this
  dashboard makes no product-code change claim beyond the committed baseline.

## Tasks

| Task | State | Branch/worktree | Evidence or blocker |
| --- | --- | --- | --- |
| [Main branch reconstruction](tasks/main-branch-reconstruction.md) | `DONE` | `main` | Local and remote main verified at `8e0b5ab`; final review approved. |
| [Diagram flow](tasks/diagram-flow.md) | `TODO` | Future clean Diagram branch | Main prerequisite satisfied; acceptance/spec questions remain pending and old source stays untouched. |
| [Zalo document inbox](tasks/zalo-document-inbox.md) | `TODO` | Future clean Zalo branch | Source is `12b8695`; OCR router/tests are freshly dirty and remain separate. |

## Protected source worktrees

- Protected source `D:\notary_v2` is `codex/inheritance-diagram-v2` at `7b982d2` with
  protected dirty `docs/platform/document-intake/spec.md`,
  `routers/ocr_ai.py`, `tests/test_ocr_ai.py`, and untracked `herdr/`.
- Diagram source `D:\notary_v2-worktrees\ocr-stage-pool-diagram` is dirty at
  `42c88b3`; its uncommitted Diagram/local-OCR work is not part of main.
- Zalo source `D:\notary_v2-worktrees\task-8-integration` is
  `codex/zalo-document-inbox-v2` at `12b8695` with fresh dirty
  `routers/ocr_ai.py` and `tests/test_ocr_ai.py`.

## Branch dispositions (user decisions 2026-09-14)

- `feature/ai-ocr-qr-mrz-first` — LEGACY, development stopped; keep on remote
  for reference only. Original QR/MRZ-first AI OCR POC (Apr 2026); concepts
  since evolved into `routers/ocr_ai.py` on main. One unmerged defensive fix
  (`872ff2b`, parent_cid validation) likely moot after the cases.py rework.
  Do not resume, do not delete.
- Active branches kept: `codex/inheritance-diagram-v2` (main business),
  `codex/zalo-document-inbox-v2` (Zalo feature in development),
  `codex/markitdown-qwen-poc` (Electron shell + MarkItDown integration),
  `codex/ocr-stage-pool-diagram-v1` (handoff `a800406`, Stage/Pool/UI +
  local-OCR removal not present anywhere else).
- `codex/zalo-module` — DELETED on remote 2026-09-14 per user decision. It held
  one unmerged commit `fffdd3f` (properties multi-land-rows UI/validation/
  tests, 2026-07-29; no Zalo code despite the name). That commit is now
  unreferenced; recover by SHA `fffdd3f3454c3f164e243398b28a524eec46ae40` if
  the feature is ever wanted back.
- DELETED on remote 2026-09-14 after merge verification: all
  `codex/zalo-task-*` branches, `codex/phase-2-stage`,
  `codex/parent-agent-workflow`, `codex/local-ocr-legacy`,
  `codex/main-integration-20260813`, `codex/ocr-stage-pool-diagram-v2`, and
  `claude/review-ocr-implementation-tDmZt`.
- `codex/ocr-stage-pool-diagram-v1` head `a800406` was pushed from another PC
  as a handoff: removes the whole local OCR stack (routers/ocr_local.py,
  tasks.py, celery_app.py, ocr_qr_worker.js, GPU reqs) and adds the explicit
  Stage commit flow (POST /cases/{cid}/stage-update, case_state/engine_state
  pruning, rewritten cases/form.html) plus garbled-Excel-header matching and
  new tests. None of this is on main or the other kept branches — keep.

## Authority

- [`AGENTS.md`](../AGENTS.md)
- [Architecture index](../docs/architecture/README.md)
- [Parent-agent ADR](../docs/architecture/decisions/0002-parent-agent-orchestration.md)
- [Inheritance route](../docs/domains/inheritance/README.md)
- [Case workspace route](../docs/platform/case-workspace/README.md)
- [Document-intake route](../docs/platform/document-intake/README.md)
- [Document-generation route](../docs/platform/document-generation/README.md)
- [Fast Audit technical contract](../docs/platform/fast-text-audit/technical.md)

## Next exact action

Create the clean Diagram branch from pushed main and selectively reconcile its
protected sources; then reconstruct and verify the clean Zalo branch. Keep old
worktrees untouched until remote containment and explicit cleanup approval.
