# Current dashboard

Updated: 2026-08-17
Last verified: 2026-08-17 against Git and the named source worktrees.

Active integration checkout: `D:\notary_v2-worktrees\main-integration-20260813`
Branch: `codex/main-integration-20260813`
Product-code baseline: `e849188`, clean before this authorized docs slice.
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

- Integration baseline `e849188` contains Qwen-only Cloud OCR from `42c88b3`
  and the Customer hardening in `e849188`.
- Local `main` is `ff9e50a`; `origin/main` is `1192154`. Neither has been
  promoted to the integration baseline.
- Fast Audit implementation/review is pending against the active technical
  contract's six outputs: `run_meta.json`, `ocr_pages.json`, `documents.json`,
  `word_extract.json`, `report.json`, and `report.md`.
- Local OCR/QR behavior remains a separate parked/research boundary; this
  dashboard makes no product-code change claim beyond the committed baseline.

## Tasks

| Task | State | Branch/worktree | Evidence or blocker |
| --- | --- | --- | --- |
| [Main branch reconstruction](tasks/main-branch-reconstruction.md) | `DOING` | `codex/main-integration-20260813` | Product-code baseline `e849188`; promotion and Fast Audit implementation/review pending. |
| [Diagram flow](tasks/diagram-flow.md) | `TODO` | Future clean Diagram branch | Rebuilt/pushed main and acceptance/spec questions are pending; old source remains untouched. |
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

Implement/review Fast Audit against its six-output contract and finish/review
governance; run full verify/review/push rebuilt main, then create clean Diagram
and Zalo branches from pushed main. Keep old worktrees untouched until remote
containment and explicit cleanup approval.
