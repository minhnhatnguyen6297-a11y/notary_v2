# Feature specification: <business feature name>

> **Status:** DRAFT
> **Owner/approver:** User
> **Input:** <user's original idea or request>
> **Parent source:** <routed domain spec/platform contract, or `none`>
> **Created:** <YYYY-MM-DD>
> **Updated:** <YYYY-MM-DD>

This document defines **what** the system must do and **why**. Keep implementation details such as files, functions, database tables, libraries, and coding steps out of this spec.

## 1. Goal

- Current problem: <observable business problem>
- Expected outcome: <business result>
- User/actor: <who receives the value>

## 2. Scope

### In scope

- <included behavior>

### Out of scope

- <explicitly excluded behavior>

## 3. Terms and rule authority

Use one rule type:

- `LEGAL`: externally sourced legal rule; cite the source and effective date.
- `PRODUCT`: user-approved product convention; do not present it as law.
- `OBSERVED`: current code/UI behavior; not automatically the desired rule.
- `UNRESOLVED`: unclear or conflicting content that blocks approval.

| ID | Term or rule | Precise meaning | Type | Source/decision |
| --- | --- | --- | --- | --- |
| R-001 | <term or rule> | <one unambiguous meaning> | <LEGAL/PRODUCT/OBSERVED/UNRESOLVED> | <citation, user decision, or path> |

## 4. User scenarios and acceptance

### US-001: <scenario name> (Priority: P1)

<Describe the business journey in plain language. It must be independently testable.>

1. **Given** <initial business state>, **When** <action/event>, **Then** <required outcome>.
2. **Given** <edge or error state>, **When** <action/event>, **Then** <required safe outcome>.

## 5. Functional requirements

- **FR-001:** The system MUST <observable behavior>.
- **FR-002:** The system MUST NOT <forbidden behavior>.
- **FR-003:** [NEEDS CLARIFICATION: <one precise unresolved question>]

Every `FR-*` must be covered by at least one acceptance scenario.

## 6. Business data and source of truth

| Data | Meaning | Source of truth | Required | Validation/business rule |
| --- | --- | --- | --- | --- |
| <data> | <meaning> | <authoritative location> | <yes/no> | <rule> |

## 7. Edge cases and failure behavior

- Missing data: <expected behavior>
- Conflicting data: <expected behavior>
- Unsupported case: <explicit stop/error behavior; never guess>
- Behavior that must never occur: <data loss, silent mutation, false legal conclusion, etc.>

## 8. Measurable success criteria

- **SC-001:** <technology-independent, verifiable outcome>.
- **SC-002:** <evidence the user can inspect or a test can prove>.

## 9. Assumptions and dependencies

- <assumption or dependency, with owner/source>

## 10. Unresolved questions

- [NEEDS CLARIFICATION: <question>]

Replace this section with `None` before approval. Do not hide an unresolved decision in assumptions.

## Approval

- Status: `DRAFT`
- Approved by: <user only>
- Approved on: <YYYY-MM-DD>
- Approval note: <scope or conditions stated by the user>

## Agent self-check before requesting approval

- [ ] The routed authoritative documents were read and linked.
- [ ] Legal rules, product conventions, and observed behavior are not mixed.
- [ ] Terms have one precise meaning in this context.
- [ ] Each requirement is observable and has an acceptance scenario.
- [ ] Important edge, error, and forbidden cases are explicit.
- [ ] Scope and out-of-scope are explicit.
- [ ] No implementation plan or coding detail appears in the spec.
- [ ] No `[NEEDS CLARIFICATION]` marker remains.
- [ ] The agent has summarized the spec in plain business language for user review.
- [ ] The user explicitly approved the spec before its status changed to `APPROVED`.
