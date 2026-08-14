# Shared OCR review

Task ID: `shared-ocr-review`
State: `BLOCKED`
Updated: 2026-08-14
Last verified: 2026-08-14 in the `parent-agent-workflow` worktree; the original
source-machine working tree was not available for re-verification.

## Goal and approved scope

Preserve the prior handoff for a possible future decision on an older shared OCR
diff. There is no approved implementation scope in the current task. Do not
recreate, modify, commit, revert, or extend the recorded OCR changes without a
separately authorized shared-core task.

## User decisions and non-goals

- The OCR change must be considered separately because it affects shared Qwen/QR
  behavior and document parsing for both Hồ sơ and Zalo.
- A future task must trace every production consumer before deciding whether to
  approve, revise, or revert the diff.
- Previous test output is not an acceptance verdict for the Hồ sơ module.

## Git state

- Historical source record: machine `MAY3`, branch
  `codex/inheritance-diagram-v2`, updated 2026-08-06.
- Historical code baseline before the earlier workflow docs:
  `2a7957e7660737682b2920ae0d547b433a809580`.
- The source-only uncommitted paths were
  `docs/platform/document-intake/spec.md`, `routers/ocr_ai.py`, and
  `tests/test_ocr_ai.py`.
- Those dirty paths are absent from this worktree's 2026-08-14 status. Their
  content was never transferred by the earlier Memory Bank checkpoint.

## Agents

| Agent label | Role | Last observed lifecycle | Assignment |
| --- | --- | --- | --- |
| none | unassigned | none verified | Await user-authorized task and recoverable source evidence. |

## Evidence

- The 2026-08-06 handoff recorded Zalo QR login and connector setup at `2a7957e`
  and classified the three OCR paths as unapproved shared work.
- That handoff reported branch/baseline checks, path checks, a secret scan, a
  fresh-checkout simulation, and `git diff --check` as passing; these are
  historical claims, not fresh verification of the missing OCR diff.
- Full suite was not run for the earlier documentation-only Memory Bank work.

## Blockers

- No current authorized OCR task.
- Original uncommitted content is not present in this worktree; another machine
  cannot recover it from Git unless it was separately checkpointed and fetched.

## Next exact action

Only if the user opens a shared OCR task: locate current source evidence, read
the document-intake authority, inspect the diff against HEAD, use Graphify plus
focused search for every production consumer, then lock affected-module scope.

## References

- [`AGENTS.md`](../../AGENTS.md)
- [Document intake route](../../docs/platform/document-intake/README.md)
- [Zalo Document Inbox spec](../../docs/platform/zalo-document-inbox/spec.md)
