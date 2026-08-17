# Main branch reconstruction

Task ID: `main-branch-reconstruction`
State: `DONE`
Updated: 2026-08-17
Last verified: 2026-08-17 against the integration checkout and named refs.

## Goal and approved scope

Keep stable work on main while reconstructing the promoted baseline from the
clean integration checkout. The committed Cloud AI OCR path is Qwen-only.

Scope includes stable main work and Fast Audit implementation/review against
the active six-output technical contract. Diagram, Zalo, and Local OCR are
excluded. This record documents the approved scope; it does not expand it.

## User decisions and non-goals

- Integration baseline is `e849188`, containing Qwen-only OCR `42c88b3` and
  Customer hardening from `e849188`.
- Local `main` and `origin/main` were verified at
  `8e0b5ab8c502b22dc041aa2e634e331059fc8752` after fast-forward promotion.
- Fast Audit is committed at `7d2a16d` with all six contracted outputs:
  `run_meta.json`, `ocr_pages.json`, `documents.json`, `word_extract.json`,
  `report.json`, and `report.md`.
- Keep old worktrees untouched until remote containment and explicit cleanup
  approval; containment gates cleanup, not clean-branch reconstruction or
  promotion.
- Do not store secrets, session values, customer data, or raw documents here.

## Git state

- Branch: `codex/main-integration-20260813`
- Worktree: `D:\notary_v2-worktrees\main-integration-20260813`
- Product-code baseline: `8e0b5ab`.
- Checkpoint: the commit containing this task record; after resume, verify
  `git status --short --branch` and the task checkpoint instead of assuming
  current documentation dirt.

## Agents

| Agent label | Role | Last observed lifecycle | Assignment |
| --- | --- | --- | --- |
| parent | coordinator and acceptor | active | Verified promotion and acceptance; track containment for cleanup. |

## Evidence

- Product-code baseline `e849188` was clean before this authorized docs slice;
  at last verification, current dirt was limited to authorized governance
  files. Recheck Git after every checkpoint.
- `42c88b3` is in the integration history and is the Qwen-only Cloud OCR
  baseline.
- Fast Audit independent review ended with `SCOPE`, `SPEC`, and `SHARED IMPACT`
  passing, sufficient test evidence, and `VERDICT: APPROVE`.
- Fresh `python -m pytest tests -q` passed 120/120, all Node `.test.mjs`
  suites passed, and `FULL_VERIFY=1` passed 44 OCR and 36 Fast Audit tests,
  Ruff, compile, and diff checks. Graphify refreshed to 1175 nodes and 2660
  edges. Repository-root pytest separately collected the parked root Local OCR
  diagnostic: 120 passed and that one out-of-scope test failed.
- `main` and `origin/main` were both verified at
  `8e0b5ab8c502b22dc041aa2e634e331059fc8752` after promotion.

## Blockers

- None for main reconstruction. Diagram, Zalo, Local OCR, and old-worktree
  cleanup remain separate tasks/scopes.

## Next exact action

Create the clean Diagram branch from pushed main and selectively reconcile its
protected sources; then reconstruct and verify the clean Zalo branch. Keep old
worktrees untouched until remote containment and explicit cleanup approval.

## References

- [`AGENTS.md`](../../AGENTS.md)
- [Document intake route](../../docs/platform/document-intake/README.md)
- [Architecture index](../../docs/architecture/README.md)
- [Fast Audit technical contract](../../docs/platform/fast-text-audit/technical.md)
