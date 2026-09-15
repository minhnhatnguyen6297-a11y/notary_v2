# Project progress

Updated: 2026-08-06

## Completed milestones

- Core inheritance/case workflow and document-generation work are tracked by
  their routed domain/platform specs and Git history.
- Zalo Document Inbox foundation, QR login, and connector setup are committed
  at `2a7957e`.
- Repository workflow now uses a thin always-loaded prompt and an independent
  scope/spec/shared-impact review gate after each meaningful task slice.

## Active milestone

- Establish a Git-tracked, `CURRENT.md`-first handoff so another machine can
  recover the exact branch, dirty work, evidence, blockers, and next action.

## Remaining milestones

- Review and checkpoint the Memory Bank/workflow documentation.
- Resolve the pending shared OCR diff in a separately authorized task with
  regression evidence for every affected module.
- Continue Zalo UI/feature work only from its approved spec and a locked task
  boundary.

## Known issues

- Local branch is ahead of its remote; another machine cannot see unpushed
  commits or uncommitted work.
- Shared OCR worktree changes are not yet accepted for the Hồ sơ module.

Detailed history belongs in Git and routed specs, not in this file.
