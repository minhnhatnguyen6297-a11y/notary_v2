# Zalo document inbox

Task ID: `zalo-document-inbox`
State: `TODO`
Updated: 2026-08-17
Last verified: 2026-08-17 against the named Zalo source worktree.

## Goal and approved scope

Keep Zalo reconstruction isolated on a future clean Zalo branch. Do not merge
Zalo work into the main or Diagram reconstruction until its own scope and
acceptance evidence are ready.

## User decisions and non-goals

- Zalo work belongs on a future clean Zalo branch.
- The current dirty OCR files are protected evidence and are excluded from clean
  reconstruction; selective reconstruction is allowed after the clean branch
  is created.
- This record documents the approved separate scope; it does not expand it.
- Do not store secrets, credentials, session values, customer data, or raw
  documents here.

## Git state

- Branch: `codex/zalo-document-inbox-v2`
- Worktree: `D:\notary_v2-worktrees\task-8-integration`
- Baseline/checkpoint: source HEAD `12b8695`; current worktree is dirty.
- Fresh dirty paths: `routers/ocr_ai.py` and `tests/test_ocr_ai.py`.
- The committed source is `12b8695`; the two dirty OCR files remain protected
  and excluded from reconstruction.

## Agents

| Agent label | Role | Last observed lifecycle | Assignment |
| --- | --- | --- | --- |
| none | unassigned | none verified | Wait for a clean-branch task and separate Zalo acceptance scope. |

## Evidence

- The source branch is separate from the main integration checkout.
- Its current dirty changes are limited to the shared OCR router and tests;
  they are protected and excluded from reconstruction.
- The main integration baseline already records Qwen-only Cloud OCR separately.
- Inherit `shape_cached_ocr` from `e849188`: it is a no-model cache parser, not
  QR behavior.

## Blockers

- Rebuilt and pushed main is required before clean-branch reconstruction.
- Selective reconstruction requires focused, full, and live acceptance gates.
- The dirty source is not a reconstruction blocker; remote containment gates
  only its later cleanup.

## Next exact action

Finish/review/push rebuilt main, create a clean Zalo branch from it, selectively
reconstruct protected sources, and run the focused, full, and live acceptance
gates under a separate Zalo scope.

## References

- [`AGENTS.md`](../../AGENTS.md)
- [Document intake route](../../docs/platform/document-intake/README.md)
