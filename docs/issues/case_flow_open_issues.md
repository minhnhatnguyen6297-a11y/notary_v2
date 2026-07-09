# Case flow open issues

Only active/unresolved case-flow issues belong here. Resolved history belongs in `docs/changelog/case_flow_history.md`.

## Diagram

Status: `partial`.

- `DIAGRAM-3`: deferred. Edge/arrow visual behavior is a separate task. Before editing connectors, define acceptance with fixture or screenshot and read `docs/plans/diagram_visual_v2.md`.
- `DIAGRAM-R1`: partial. Diagram save/persistence still has legacy overlap between `case_state_json.diagram.*`, `engine_state_json`, `diagram_payload`, and participants. Current rule: save must prefer the newest `case_state_json.diagram.engineState`, prune stale/out-of-stage references, preserve valid edge metadata, and avoid stale hidden-field overwrite.
- `DIAGRAM-R2`: partial. Dependent branch pruning, duplicate active person nodes, ghost nodes, orphan structural slots, and preserved node metadata remain technical-risk areas. Current rule: backend save/reload must prune invalid nodes/edges and preserve valid metadata needed for reload/save stability.
- `DIAGRAM-R3`: deferred. Visual connector/edge task needs explicit acceptance test before implementation.

## Add new issues

For each active issue, include:

```text
- ID:
- Status: active | partial | deferred | blocked
- Current rule:
- Risk:
- Verification needed:
```
