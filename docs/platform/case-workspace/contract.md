# Case workspace contract

Status: provisional, non-normative
Source of truth: `../../domains/inheritance/workflow.md`

- Stage owns committed people for the current case.
- Pool is derived from committed Stage minus Diagram assignments.
- Pool and Diagram must not mutate Stage person data.
- Shared extraction is deferred until a second domain confirms the same contract.
