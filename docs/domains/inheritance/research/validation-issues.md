# Inheritance Engine V2 classified issues

Audit date: 2026-07-23. No accepted research oracle or in-scope matrix item has an unclassified
mismatch.

## Remaining items

### Previously recorded verification (uncommitted snapshot)

Full `verify.bat`, the target engine/parser/Word/research suite, and the Node UI suite were recorded as passing for an uncommitted workspace snapshot. This is not evidence for clean HEAD.

### OUT_OF_SCOPE - uploaded custom Word content

The built-in Word export is verified against V2. A user-uploaded legacy template can still contain
hard-coded legal/gift prose in its own document body. The engine cannot safely rewrite arbitrary
template prose; template-content migration remains a separate Word-template task.

### MIGRATION_COMPAT - read-only legacy input

`inheritanceDecision` and legacy `engineState.nodes` remain read-only migration inputs. They are
converted to `willReceive`/canonical nodes and are not written back. Legacy `edges`, `allocations`,
`warnings`, and `trace` are dropped during normalization; a V2 save persists only authoritative
`engineInput` and backend `engineResult`.

### TEST_RISK - browser automation coverage

The representative flow was executed with Chrome DevTools, including calculation details,
diagram save, reload and built-in Word download. There is no repository Playwright/Cypress suite,
so cross-browser and multi-tab behavior remain manual regression areas rather than inheritance
logic gaps.

## Classification summary

- `CODE_BUG`: all discovered in-scope bugs fixed and regression-tested.
- `SPEC_CONFLICT`: none remaining for accepted cases.
- `SPEC_GAP`: none required to decide accepted cases.
- `SOURCE_ERROR`: two catalog records retained as non-oracles.
- `OUT_OF_SCOPE`: eight source cases plus arbitrary uploaded template prose.
