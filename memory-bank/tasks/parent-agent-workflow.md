# Parent-agent workflow

Task ID: `parent-agent-workflow`
State: `DONE`
Updated: 2026-08-14
Last verified: 2026-08-14 against branch, HEAD, worktree, dirty paths, local
links, whitespace, secret/session-value scans, independent review, and parent
acceptance.

## Goal and approved scope

Make the parent coordination-first and compact-safe without changing product
behavior: delegate bounded implementation, route fresh minimal context, keep
durable task state in Markdown/Git, and require parent acceptance of evidence.

Scope is locked to `AGENTS.md`, ADR-0002, Memory Bank docs and task records,
the Memory Bank design, and the existing ADR route in
`docs/architecture/README.md`. No product code, Herdr operations, task database,
model router, commit, push, or unrelated documentation is authorized.

Acceptance requires `git diff --check`, resolving local links, a secret/session
value scan, a duplication/conflict check, and a fresh-context review. The shared
boundary is repository workflow only; product behavior is unaffected.

## User decisions and non-goals

- Parent work defaults to scope, delegation, escalation, acceptance, and concise
  decision reports; direct work has only the three exceptions in ADR-0002.
- Parent personally reads required authority and verifies acceptance evidence.
- Stable docs, compact `CURRENT.md`, and substantial task records are the three
  recovery layers; task state and agent lifecycle stay separate.
- Preserve the older OCR handoff without recreating its absent source-only diff.

## Git state

- Branch: `codex/parent-agent-workflow`
- Worktree: `D:\notary_v2-worktrees\parent-agent-workflow`
- Baseline: `7b982d25b65086c1169d71f20fa72c15698c3e62`
- Existing uncommitted inputs preserved: the ADR-0002 route in `AGENTS.md` and
  `docs/architecture/README.md`, plus the untracked ADR draft.

## Agents

| Agent label | Role | Last observed lifecycle | Assignment |
| --- | --- | --- | --- |
| parent | coordinator and acceptor | acceptance completed when recorded | Scope, escalation, evidence verification, fresh review, acceptance. |
| workflow-memory-builder | builder | completed when recorded | Documentation-only implementation and focused checks. |
| fresh-context reviewer | reviewer | completed when recorded | Independent scope, spec, shared-impact, and evidence review. |

Lifecycle observations are stale after resume and must be rechecked; they do not
change task state.

## Evidence

- The approved scope, non-goals, shared boundary, and acceptance evidence are
  persisted above rather than depending on chat history.
- `git diff --check` passed; separate no-index whitespace checks passed for all
  untracked Markdown files.
- All 16 local Markdown links and routed paths checked by the builder resolve.
- Credential-assignment and session-identifier scans found no values.
- Cross-document read-through keeps the hot rule in `AGENTS.md`, workflow detail
  in ADR-0002, and recovery schema in Memory Bank docs.
- Independent fresh-context review: `SCOPE PASS`, `SPEC PASS`,
  `SHARED IMPACT PASS`, `TEST EVIDENCE SUFFICIENT` for documentation-only work,
  `VERDICT APPROVE`; no actionable findings.
- Parent accepted the evidence and marked the task `DONE`.
- Full suite: not run; this is documentation-only work.

## Blockers

None.

## Next exact action

No task work remains. Do not commit or push under this task. If the user
separately requests a checkpoint, re-verify Git and commit and/or push only as
requested.

## References

- [`AGENTS.md`](../../AGENTS.md)
- [ADR-0002](../../docs/architecture/decisions/0002-parent-agent-orchestration.md)
- [Memory Bank design](../../docs/superpowers/specs/2026-08-01-memorybank-design.md)
