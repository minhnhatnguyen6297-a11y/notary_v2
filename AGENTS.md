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

## Impact discovery

For non-trivial changes and every shared symbol, contract, state, or core file,
use Graphify plus focused source search to identify production callers and
affected modules before editing. Graphify is navigation evidence, not business
authority. Refresh it after meaningful code changes.

```bash
D:\graphify\.venv\Scripts\graphify.exe query "question" --graph graphify-out/graph.json
```

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
