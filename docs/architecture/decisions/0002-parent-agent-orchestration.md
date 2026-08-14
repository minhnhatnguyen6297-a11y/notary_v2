# ADR-0002: Parent-agent orchestration

- Status: Accepted
- Date: 2026-08-14
- Scope: Parent coordination, delegation, context routing, task state, recovery,
  escalation, and acceptance
- Approved by: User

## Context

The repository already defines authority, specification approval, scope locking,
impact discovery, review, and verification in `AGENTS.md` and routed module
documentation. `memory-bank/` already provides Git-tracked recovery context.

The missing decision was an orchestration-first parent workflow that keeps the
parent's context available for judgment, gives each worker only bounded fresh
context, and survives compaction or cross-machine continuation. Operational
agent-control commands remain a tooling concern and are not copied here.

## Decision

### Parent operating mode

The parent is the user's single interface and coordinates by default. It owns
goal understanding, repository inspection, scope locking, decomposition,
delegation, escalation, acceptance, and concise decision reporting. Helper
output is evidence, not authority.

The parent does not implement product code by default. Direct work is limited
to:

- repository/workflow policy documentation;
- genuinely tiny changes where delegation overhead is unreasonable; or
- recovery after a worker failure when reassignment cannot make progress.

These exceptions do not weaken scope, authority, write-isolation, review, or
verification gates. The parent must personally read required authority and
active task state, inspect current Git state, and verify acceptance evidence;
a worker summary cannot substitute for those checks.

### Context routing

Keep each context purpose-built:

- The parent loads `AGENTS.md`, routed normative authority, active task state,
  and current Git and live-agent evidence.
- Each worker receives a fresh, minimal, bounded prompt containing the locked
  goal, authorized behavior, expected files, shared boundaries, non-goals,
  dependencies, worktree/branch, and acceptance evidence. The worker reads its
  applicable authority directly.
- The reviewer receives fresh context: the original request, normative
  authority, base-to-head diff, affected production callers, and actual test
  output.

Workers return concise decisions, diffs, evidence, blockers, and requests, not
chat transcripts. They report to the parent unless a user decision or approval
is required.

### Delegation and write safety

Delegate bounded implementation, research, testing, debugging, and review when
the work can be isolated. Start with at most two active helpers and increase
concurrency only after the task demonstrates safe independence. Roles are
temporary capabilities, not permanent agents or fixed model routes.

Only one write-capable agent may use a worktree at a time. Multiple read-only
helpers may inspect it. Parallel builders require disjoint scope, separate Git
worktrees, and separate branches. Do not create surprising worktrees or merge
worker branches unless that topology is already authorized.

### Escalation

A worker that cannot safely continue ends with:

```text
PARENT REQUEST:
TYPE: QUESTION | SCOPE_BREAK | CONFLICT | APPROVAL | BLOCKER
NEEDED:
EVIDENCE:
SAFE WORK THAT CAN CONTINUE:
```

The parent answers from repository or approved-spec evidence when possible.
Only the user may decide desired behavior, business judgment, scope expansion,
conflicting authority, or destructive, costly, publishing, or other external
action.

After a failed worker, inspect the evidence and classify the cause. Narrow or
clarify once when useful, then reassign a better-bounded worker or escalate. The
parent may implement recovery directly only when reassignment cannot progress.

### Task state and compact-safe memory

Recovery context has three layers and no new database or dependency:

1. Stable rules live in `AGENTS.md`, accepted ADRs, and routed documentation.
2. `memory-bank/CURRENT.md` is a short dashboard linking current task records
   and showing verified Git state, blockers, and the next action.
3. `memory-bank/tasks/<task-id>.md` stores recovery-critical state for each
   substantial active task.

A task record persists the approved goal and scope, user decisions, branch and
worktree, assigned agents, evidence, blockers, next action, and last-verified
time. A routed module `plan.md` may own detailed decomposition; the Memory Bank
links to it rather than duplicating it.

Task states are `TODO`, `DOING`, `BLOCKED`, `DONE`, and `CANCELLED`. Agent
lifecycle is separate evidence: an agent becoming idle, blocked, failed, or done
does not change task state. Only the parent marks a task `DONE` after required
evidence and the fresh-context review gate pass.

After resume, compaction, or handoff, the parent re-verifies branch, HEAD,
worktree, dirty state, and live-agent state before trusting recorded state or
continuing the next action. Stale Memory Bank or agent lifecycle claims are
reconciled or reported, never silently assumed.

### Acceptance loop

Adapt this loop to task size:

```text
user goal
  -> parent reads authority, Git, and active task state
  -> user-approved spec when behavior changes
  -> impact discovery and locked scope
  -> bounded worker implementation
  -> focused checks and independent testing when warranted
  -> fresh-context review required by AGENTS.md
  -> fix, retest, and re-review when blocked
  -> parent verifies evidence, accepts state, and reports decisions
```

## Rejected alternatives

- Parent implementation by default: consumes judgment context and couples
  implementation with acceptance.
- Permanent role agents: idle cost and stale context without demonstrated need.
- A task database or orchestration dependency: Markdown and Git cover recovery.
- A fixed automatic model router: premature without repository evidence.
- Multiple writers in one worktree: conflicts with preservation and review.
- Tool-specific operational commands in repository policy: duplicate a changing
  tool interface.

## Consequences

The parent stays available for scope, conflicts, acceptance, and user decisions;
workers get smaller fresh contexts; and substantial tasks remain recoverable
after compaction or handoff. The cost is explicit delegation and small task-state
updates, with direct parent implementation reserved for the three exceptions.
