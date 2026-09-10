# AGENTS.md - notary_v2

Project authority, routing, stop conditions, and review gates only. Graphify
describes code structure; routed specs define behavior.

## Authority

- Preserve user changes and external state. Do not modify, revert, commit, or
  publish unrelated work.
- Change behavior only inside the task explicitly authorized by the user.
- Business rules, API/data contracts, DB schema, OCR flow, and shared behavior
  require explicit scope covering every affected module.
- A task/spec/contract/runtime conflict is evidence to report, not permission
  to change any side. Stop and ask which source wins.
- Completion claims require fresh verification evidence.

## Task boundary

Before editing, establish:

```text
GOAL:
AUTHORIZED BEHAVIOR:
EXPECTED MODULES/FILES:
KNOWN SHARED BOUNDARIES:
ACCEPTANCE EVIDENCE:
SCOPE: LOCKED
```

If another module, shared core, contract, or business rule becomes necessary,
stop with `SCOPE BREAK REQUEST` naming the dependency, affected behavior, and
why work cannot safely continue. Only the user may expand scope. Never rewrite
a plan or brief to legitimize work already performed.

## Sources of truth

`AGENTS.md` -> accepted architecture ADR -> approved domain spec -> platform
contract -> technical/UX docs -> active plan -> research/history.

Use `docs/README.md` only when the task area is unclear. Otherwise route here:

| Task area | Read first |
| --- | --- |
| Inheritance rules and case UX | `docs/domains/inheritance/README.md` |
| Cloud AI OCR and document intake | `docs/platform/document-intake/README.md` |
| Local OCR | `docs/platform/document-intake/README.md`; separate scope required |
| Shared Stage/Pool capability | `docs/platform/case-workspace/README.md` |
| Word generation | `docs/platform/document-generation/README.md` |
| Fast text audit | `docs/platform/fast-text-audit/README.md` |
| Architecture decisions | `docs/architecture/README.md` |

New or changed business behavior requires an approved spec. Missing, draft,
ambiguous, or runtime-conflicting coverage blocks implementation until the user
decides. Only the user approves business specs.

For cross-machine continuation or interrupted work, read
`memory-bank/CURRENT.md` first, verify it against Git, then follow only its
relevant links. Memory Bank is operational context and cannot override the
sources above or fresh evidence.

## Cross-product context (read only when needed)

`D:\systemdocs` — parent docs for the notary product family
(`notary_v2`, `upload_lab`, `notaryoffice`). Not needed for normal tasks.

Read it only when the task touches: product boundaries, shared entity keys
(CCCD / GCN serial / parcel / notarization number), or a cross-product
integration. Then read only the file you need:
`PROJECTS.md` (what the other repos are), `contracts/entities.md` (key
normalization), `OPEN_DECISIONS.md` (do not decide these alone).

MUST read before choosing a new technology (a different OCR provider, ORM,
queue, or UI framework) or making an architecture decision: `TECH_STACK.md`.
The three repos will merge onto one shared database; diverging now means
rewriting later.

It does not override this file. On conflict, this repo wins for internal
behavior; report the conflict instead of silently following either side.

## Tool routing and impact discovery

Tool selection:
- Known file, symbol, or exact text: use targeted search/read or available LSP tools. For local, well-located edits, do not query graph or index data.
- Cross-file relationships or unclear ownership: query the existing Graphify graph when available:
  `D:\graphify\.venv\Scripts\graphify.exe query "<question>" --graph graphify-out/graph.json`
- Start graph queries narrowly (depth 1–2); expand only when evidence is insufficient. Graphify is navigation evidence, not business authority. Read current source before editing or making behavioral claims.
- Large logs/data: use context-mode when available (`ctx_execute`, `ctx_batch_execute`) to filter or aggregate before returning output; preserve exit status and a route to the full data.
- Already-small tool results, including bounded graph results: consume directly.
- Use `ctx_search` only for previously indexed content (`ctx_index`).
- Missing, stale, or inconclusive graph: inspect current source directly; refresh only when needed. Do not rebuild the full graph for routine edits.
- After code changes, run checks appropriate to the affected behavior and project requirements.

## Review gate

Review every completed task/slice before dependent work or commit. Use an
independent reviewer with fresh context; the implementer must not approve its
own work. Review the original request, normative spec, base-to-head diff,
affected production callers, and actual test output—not the implementer's
summary.

```text
SCOPE: PASS/FAIL — missing, extra, or misunderstood behavior
SPEC: PASS/FAIL — implementation matches normative behavior
SHARED IMPACT: PASS/FAIL — affected consumers and contracts checked
TEST EVIDENCE: SUFFICIENT/INSUFFICIENT — focused checks per affected module;
  full-suite status reported separately
VERDICT: APPROVE/BLOCK
```

Unapproved behavior, unresolved shared impact, or spec/runtime conflict blocks
the next task and commit even when tests pass.

## Completion

Prefer the smallest behavior-preserving change and existing code. Run focused
regressions, then `.\verify.bat` for non-trivial code unless out of scope.
Never describe focused checks as a full-suite pass. Report:

```text
CHANGED FILES:
SCOPE VERDICT:
SHARED BEHAVIOR: YES/NO; AFFECTED MODULES:
FOCUSED VERIFICATION:
FULL-SUITE STATUS:
REMAINING RISK:
```

Detailed business invariants belong in routed normative specs, not here.

## Agent skills

### Issue tracker

GitHub Issues / local specs in `docs/superpowers/specs/`. See `docs/agents/issue-tracker.md`.

### Domain docs

Modular domain specs and ADRs in `docs/architecture/decisions/`. See `docs/agents/domain.md`.

## Hybrid engineering workflow

This repository combines Matt Pocock Skills (product discovery & specification) with Superpowers (engineering execution discipline).

### 1. Discovery & Specification (Matt Pocock)

For a new feature, substantial refactoring, or unclear domain requirements:
1. **Trigger**: Use Matt Pocock `grill-with-docs` (or `grilling` + `domain-modeling`).
2. **Conflict Override**: Superpowers `brainstorming` is INACTIVE during this phase. Do not invoke `brainstorming` while a Matt discovery session is active.
3. **Prototype / Spike**: Matt `prototype` is explicitly permitted to explore UX, state models, or architectural feasibility. Prototype code is throwaway and MUST be deleted before spec approval and production implementation.
4. **Output**: Finish discovery with Matt `to-spec` (saving to `docs/superpowers/specs/<feature>.md` or issue tracker).
5. **Approval Checkpoint**: An explicitly user-approved `to-spec` document satisfies Superpowers' requirement for an approved design/spec.
6. **Context Refresh**: Once approved and saved, prefer starting a fresh session or running `handoff` for implementation to keep the execution context window clean.

### 2. Macro Decomposition (Optional)

- For large features spanning multiple independent parts, use Matt `to-tickets` after `to-spec` to divide the spec into vertical tracer-bullet slices.
- Each ticket enters the Superpowers implementation workflow independently.

### 3. Implementation Discipline (Superpowers)

Once an approved spec exists:
1. **No Re-brainstorming**: Do not re-brainstorm or alter approved business behavior without explicit user approval.
2. **Plan**: Use Superpowers `writing-plans` to generate fine-grained TDD steps, exact file paths, commands, and verification criteria (saved in `docs/superpowers/plans/<feature>.md`).
3. **Execute**: Use `subagent-driven-development` (or `executing-plans`).
4. **Worktree Isolation**: Use `using-git-worktrees` where isolation is needed; fall back to a dedicated branch if file-locking occurs on Windows.
5. **Quality Gates**: Follow strict `test-driven-development`, `systematic-debugging` (for bug fixes), and `verification-before-completion` (fresh verification evidence required).
6. **Review**: Subagents requesting or conducting code reviews must evaluate work against both the approved spec and the Review Gate defined in this `AGENTS.md`.
7. **Branch Finish**: Use `finishing-a-development-branch` when all tasks and tests are verified.

### 4. Bug Fixing Fast-Path

- Bugs bypass the discovery phase and route directly to Superpowers `systematic-debugging` -> failing regression test -> root cause fix -> `verification-before-completion`.

### 5. Concurrency & Subagent Guardrails

- `dispatching-parallel-agents` is DISABLED by default unless explicitly requested.
- Maximum 2 concurrent subagents.
- Single writer per worktree/branch.
- Repository/user instructions in this `AGENTS.md` strictly take precedence over all skill systems.
