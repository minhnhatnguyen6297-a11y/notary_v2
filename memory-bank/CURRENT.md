# Current handoff

Updated: 2026-08-06T14:10:00+07:00
Source machine: MAY3
Branch: `codex/inheritance-diagram-v2`
Handoff checkpoint: the commit containing this file; resolve with
`git log -1 --format=%H -- memory-bank/CURRENT.md`.
Code baseline before workflow docs: `2a7957e7660737682b2920ae0d547b433a809580`.
Verify current upstream state with `git status -sb`; do not trust cached
ahead/behind counts.

## Goal

Use the completed cross-machine Memory Bank and thin-prompt/thick-review
workflow. Do not silently absorb pending shared OCR work into another module
task.

## Completed

- Zalo QR login and connector setup committed as `2a7957e`.
- `AGENTS.md` keeps authority/routing in the hot prompt and requires independent
  per-slice scope/spec/shared-impact review.
- The `CURRENT.md`-first Memory Bank is implemented and independently reviewed.
- Memory Bank design is tracked at
  `docs/superpowers/specs/2026-08-01-memorybank-design.md`.

## Source-machine-only uncommitted work

Always run `git status --short` on the current machine before acting. At this
handoff's source machine, these older changes existed outside the documentation
checkpoint:

- `docs/platform/document-intake/spec.md`, `routers/ocr_ai.py`, and
  `tests/test_ocr_ai.py`: shared OCR changes from 2026-08-04. They alter Qwen/QR
  behavior and document parsing for both Hồ sơ and Zalo. They remain unapproved
  as a separate shared-core task and are deliberately excluded from this
  checkpoint.

Their content is **not transferred** by the Memory Bank commit. On another
machine they may be absent; do not recreate, commit, revert, or extend them
without a separately authorized OCR task and current source evidence.

## Verification

- Focused: Git branch/code-baseline checks matched this file; all implemented
  and routed paths exist; secret-pattern scan found no values in `memory-bank/`.
- Fresh-checkout simulation passed: a new agent can resolve the handoff commit,
  recover the unapproved OCR state, evidence class, and next exact action.
- `git diff --check` passed for the final workflow/Memory Bank documentation
  diff and the existing dirty OCR files.
- Full suite: not run for the documentation-only workflow/Memory Bank task.
- The older OCR implementation has no current acceptance verdict for the Hồ sơ
  module; previous test output must not be treated as approval.

## Blockers and open decisions

- Decide the three-file OCR diff in its own task: review and approve, revise, or
  revert. First trace every production consumer of shared `ocr_ai` behavior.
- A handoff is available on another machine only after the branch containing
  this file is pushed and fetched there.

## Normative references

- `AGENTS.md`
- `docs/platform/zalo-document-inbox/spec.md`
- `docs/platform/document-intake/README.md`
- `docs/platform/document-intake/spec.md` — currently modified; compare with
  `HEAD` before treating the worktree version as normative.

## Next exact action

On a resumed machine, verify the branch, resolve the handoff checkpoint, and
run `git status --short`. If the three OCR diffs are absent, do not recreate
them. Open a separately authorized OCR task before changing shared `ocr_ai`
behavior.
