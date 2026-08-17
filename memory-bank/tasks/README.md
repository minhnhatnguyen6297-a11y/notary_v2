# Task records

Create one file per substantial active task when `CURRENT.md` is not enough for
safe recovery. `CURRENT.md` links the records that matter now; Git retains
removed or replaced history.

Task state is `TODO`, `DOING`, `BLOCKED`, `DONE`, or `CANCELLED`. Keep it
separate from agent lifecycle. A worker becoming idle, failed, or done is
evidence for the parent, not a task-state transition.

## Template

```markdown
# <Task title>

Task ID: `<task-id>`
State: `TODO | DOING | BLOCKED | DONE | CANCELLED`
Updated: YYYY-MM-DD
Last verified: YYYY-MM-DD plus evidence checked

## Goal and approved scope

## User decisions and non-goals

## Git state

- Branch:
- Worktree:
- Baseline/checkpoint:

## Agents

| Agent label | Role | Last observed lifecycle | Assignment |
| --- | --- | --- | --- |

## Evidence

## Blockers

## Next exact action

## References
```

Use stable agent labels, never credentials, access tokens, or ephemeral session
values. After resume or compaction, verify Git and live-agent state before
trusting the record.
