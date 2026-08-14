# Current dashboard

Updated: 2026-08-14
Last verified: 2026-08-14 against current Git, independent reviewer approval,
and parent acceptance; re-run Git checks after resume or compaction.
Branch: `codex/parent-agent-workflow`
Worktree: `D:\notary_v2-worktrees\parent-agent-workflow`
HEAD: `7b982d25b65086c1169d71f20fa72c15698c3e62`
Dirty state: authorized workflow and Memory Bank documentation only; verify with
`git status --short --branch`.

## Tasks

| Task | State | Owner | Evidence or blocker |
| --- | --- | --- | --- |
| [Parent-agent workflow](tasks/parent-agent-workflow.md) | `DONE` | parent + builder + reviewer | Reviewer approved with no findings; parent accepted; no blockers. |
| [Shared OCR review](tasks/shared-ocr-review.md) | `BLOCKED` | unassigned | Historical source-machine diff is absent here and has no approved task scope. |

## Required authority

- [`AGENTS.md`](../AGENTS.md)
- [ADR-0002](../docs/architecture/decisions/0002-parent-agent-orchestration.md)
- [Memory Bank design](../docs/superpowers/specs/2026-08-01-memorybank-design.md)

## Next exact action

No parent-agent workflow work remains. Do not commit or push under this task. If
the user separately requests a checkpoint, re-verify Git and commit and/or push
only as requested.
