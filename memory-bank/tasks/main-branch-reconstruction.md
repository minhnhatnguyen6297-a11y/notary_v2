# Main branch reconstruction

Task ID: `main-branch-reconstruction`
State: `DOING`
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
- Local `main` is `ff9e50a`; `origin/main` is `1192154`; promotion is pending.
- Fast Audit implementation/review is pending against the active contract's
  six outputs: `run_meta.json`, `ocr_pages.json`, `documents.json`,
  `word_extract.json`, `report.json`, and `report.md`.
- Keep old worktrees untouched until remote containment and explicit cleanup
  approval; containment gates cleanup, not clean-branch reconstruction or
  promotion.
- Do not store secrets, session values, customer data, or raw documents here.

## Git state

- Branch: `codex/main-integration-20260813`
- Worktree: `D:\notary_v2-worktrees\main-integration-20260813`
- Product-code baseline: `e849188`.
- Checkpoint: the commit containing this task record; after resume, verify
  `git status --short --branch` and the task checkpoint instead of assuming
  current documentation dirt.

## Agents

| Agent label | Role | Last observed lifecycle | Assignment |
| --- | --- | --- | --- |
| parent | coordinator and acceptor | not recorded | Decide promotion and acceptance; track containment for cleanup. |

## Evidence

- Product-code baseline `e849188` was clean before this authorized docs slice;
  at last verification, current dirt was limited to authorized governance
  files. Recheck Git after every checkpoint.
- `42c88b3` is in the integration history and is the Qwen-only Cloud OCR
  baseline.
- `main` and `origin/main` remain separate refs and are not promoted by this
  record.

## Blockers

- Fast Audit implementation/review against the active six-output contract is
  pending.
- Fast Audit implementation/review and governance review must finish before
  full verify/review/push of rebuilt main.

## Next exact action

Implement/review Fast Audit against its six-output contract and finish/review
governance; run full verify/review/push rebuilt main, then create clean Diagram
and Zalo branches from pushed main. Keep old worktrees untouched until remote
containment and explicit cleanup approval.

## References

- [`AGENTS.md`](../../AGENTS.md)
- [Document intake route](../../docs/platform/document-intake/README.md)
- [Architecture index](../../docs/architecture/README.md)
- [Fast Audit technical contract](../../docs/platform/fast-text-audit/technical.md)
