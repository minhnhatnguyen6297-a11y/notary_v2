# Diagram flow

Task ID: `diagram-flow`
State: `TODO`
Updated: 2026-08-17
Last verified: 2026-08-17 against the named dirty Diagram source worktree.

## Goal and approved scope

On a future clean Diagram branch, continue the OCR modal -> Stage -> Pool ->
Diagram flow and the Diagram/Word work in progress.

Stage remains the people source of truth. OCR modal close does not save or
auto-stage. Pool and Diagram must not mutate Stage people.

## User decisions and non-goals

- All OCR modal to Stage to Pool to Diagram work belongs on a future clean
  Diagram branch.
- Diagram/Word WIP stays separate from main reconstruction.
- Create the clean Diagram branch from rebuilt/pushed main, then selectively
  transplant protected sources after scope and review.
- Keep the current dirty source worktree untouched; remote containment gates
  cleanup of that old source, not clean-branch reconstruction.
- This record documents the approved branch scope; it does not expand it.

## Git state

- Branch: future clean Diagram branch; current source is
  `codex/ocr-stage-pool-diagram-v1`
- Worktree: `D:\notary_v2-worktrees\ocr-stage-pool-diagram`
- Baseline/checkpoint: source HEAD `42c88b3`; current worktree is dirty. Rebuilt
  and pushed main is the clean-branch prerequisite.
- Protected primary source: `D:\notary_v2`, branch
  `codex/inheritance-diagram-v2`, HEAD `7b982d2`.
- Clean protected commits to reconcile selectively: `4451ffe` (inheritance
  engine), `40f636c` (Diagram refactor), and `c727173` (Word rebuild). These
  commits are absent from `42c88b3`.
- Protected patch backups exist at
  `D:\notary_v2-handoffs\ocr-stage-pool-diagram\stage-flow.patch` and
  `D:\notary_v2-handoffs\ocr-stage-pool-diagram\stage-flow-applied.patch`;
  both have SHA256
  `8C83AA57F9018064E22B9FA6CCBA3A0BE9170703EA2376EC2909DCC81853DD6D`.
  They are evidence for selective reconciliation only, not verbatim application.

## Agents

| Agent label | Role | Last observed lifecycle | Assignment |
| --- | --- | --- | --- |
| none | unassigned | none verified | Wait for a clean-branch task and explicit acceptance scope. |

## Evidence

- The source worktree contains uncommitted Diagram/form/case changes and
  local-OCR removals.
- Protected primary HEAD `7b982d2` contains clean inheritance/Diagram/Word
  commits `4451ffe`, `40f636c`, and `c727173`; those commits are absent from the
  `42c88b3` source and must be reconciled with the protected dirty patch.
- Routed behavior is documented by the inheritance workflow and provisional
  case-workspace contract.
- Word behavior is routed through the inheritance Word export and document-
  generation documentation; it remains WIP for this reconstruction.

## Blockers

- Rebuilt and pushed main is required before clean-branch reconstruction.
- Protected clean commits and the dirty patch require selective reconciliation.
- Diagram/Word acceptance and spec questions remain unresolved.
- The dirty source is protected evidence, not a reconstruction blocker; remote
  containment gates only its later cleanup.

## Next exact action

Finish/review/push rebuilt main, create the authorized clean Diagram branch from
it, selectively reconcile the protected `7b982d2` commits with the dirty patch,
then lock the OCR-to-Diagram and Word scope and acceptance evidence before
editing.

## References

- [`AGENTS.md`](../../AGENTS.md)
- [Inheritance route](../../docs/domains/inheritance/README.md)
- [Inheritance workflow](../../docs/domains/inheritance/workflow.md)
- [Inheritance active plan](../../docs/domains/inheritance/plan.md)
- [Word export flow](../../docs/domains/inheritance/word-export.md)
- [Case workspace route](../../docs/platform/case-workspace/README.md)
- [Document generation route](../../docs/platform/document-generation/README.md)
