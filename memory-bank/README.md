# Memory Bank

Git-tracked handoff for continuing `notary_v2` on another machine or after an
interrupted task. It is operational context, not a source of business truth.

## Resume

1. Pull/rebase the intended branch.
2. Read `CURRENT.md` first.
3. Verify its branch, commit, worktree, and test claims against current Git.
4. Read only the normative documents and optional Memory Bank files linked by
   `CURRENT.md`.
5. Continue from `Next exact action` only after the evidence still matches.

## Update

Update `CURRENT.md` before switching machines, stopping mid-task, or pushing a
handoff checkpoint. Update `PROGRESS.md` only when a milestone changes.

- Keep `CURRENT.md` short and replace stale state instead of appending history.
- Link to specs, commits, diffs, tests, decisions, or research; do not copy them.
- Distinguish committed/pushed work from uncommitted work.
- Distinguish focused verification from full-suite status.
- Record uncertainty and unapproved changes explicitly.
- Never store secrets, credentials, customer data, or raw customer documents.

Precedence remains: `AGENTS.md`, accepted ADRs, approved specs, platform
contracts, current Git/source, and fresh verification. If Memory Bank conflicts
with any of them, report the conflict and trust the stronger current evidence.
