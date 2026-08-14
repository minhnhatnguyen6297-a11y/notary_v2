# Memory Bank

Git-tracked recovery context for continuing `notary_v2` after compaction,
interruption, or a machine change. It is operational state, not business or
architecture authority.

## Layers

1. Stable rules stay in `AGENTS.md`, accepted ADRs, and routed documentation.
2. `CURRENT.md` stays a short dashboard of verified Git state, task links,
   blockers, and the next action.
3. `tasks/<task-id>.md` holds recovery-critical state for a substantial active
   task.

`PROGRESS.md` remains an optional milestone summary, not another active task
tracker. Read it only when `CURRENT.md` links to it.

## Resume

1. Sync the intended branch, then read `CURRENT.md` first.
2. Verify branch, HEAD, worktree, dirty state, and every verification claim
   against current Git and source.
3. Verify live-agent state with the active agent-control mechanism; recorded
   lifecycle is only a last observation.
4. Open only the linked task records and their routed normative authority.
5. Reconcile or report stale/conflicting state before continuing the recorded
   next action.

## Update

Use a task record when a later parent could not safely recover the approved
scope and evidence from the dashboard alone. Keep tiny or completed work out of
`tasks/` unless a handoff still depends on it.

- Keep `CURRENT.md` short and replace stale state instead of appending history.
- Record each substantial task's goal, approved scope, user decisions, task
  state, branch/worktree, agents, evidence, blockers, next action, and last
  verified time.
- Keep task state (`TODO`, `DOING`, `BLOCKED`, `DONE`, `CANCELLED`) separate from
  agent lifecycle; only the parent changes task state after checking evidence.
- Link to specs, plans, commits, diffs, tests, decisions, or research instead of
  copying them.
- Distinguish committed/pushed work, uncommitted work, focused checks, and
  full-suite status.
- Update recovery state before switching machines, stopping mid-task, or
  publishing a handoff checkpoint.
- Never store secrets, credentials, customer data, raw customer documents, or
  ephemeral session values.

Precedence remains: `AGENTS.md`, accepted ADRs, approved specs, platform
contracts, current Git/source, and fresh verification. Report any conflict and
trust the stronger current evidence.
