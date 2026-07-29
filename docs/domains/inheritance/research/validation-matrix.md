# Inheritance Engine V2 validation matrix

Verified 2026-07-23. The business-rule source remains
`../spec.md`; this document records implementation evidence only.

## Research evidence

- Catalog: `tests/fixtures/inheritance_research_cases.json`.
- Provenance: 23 anonymized records, one explicit duplicate, 22 independent scenarios from 8
  public source groups.
- Oracle policy: 8 accepted exact-fraction cases; 15 records are explicitly classified
  `ambiguous`, `source_error`, `out_of_scope`, or `duplicate_source` and never become expected
  engine output.
- Automated result: every accepted oracle is exact, conserves one, and matches the backend
  engine (`tests/test_inheritance_research_catalog.py`).

## Required matrix

| # | Requirement | Evidence | Result |
|---:|---|---|---|
| 1 | X/Y/D/Z exact fixture | `test_fixture_x_y_d_z_matches_exact_expected_fractions` | PASS |
| 2 | Representation splits per branch and generation | `test_representation_splits_by_branch_at_each_generation_not_flat_descendants` | PASS |
| 3 | Non-owner child predeceases source; descendants represent | `test_non_owner_child_dead_before_source_has_no_estate_but_descendant_represents` | PASS |
| 4 | Representation spouse excluded unless anchor has an independent estate | `test_spouse_of_representation_anchor_only_receives_from_anchor_independent_estate` | PASS |
| 5 | One person receives from multiple sources with separate terms | `test_person_receiving_from_multiple_estates_keeps_each_source_in_breakdown` | PASS |
| 6 | Later death receives first, then opens a later estate | `test_person_dead_after_source_receives_then_opens_later_estate` | PASS |
| 7 | Same-day estates do not cross-inherit | `test_same_day_spouses_do_not_receive_cross_estates` | PASS |
| 8 | Year-only date uses 01/01; full date is preserved | `test_year_only_dates_normalize_to_same_day_snapshot`; `test_full_death_date_is_preserved_while_year_only_uses_first_of_january` | PASS |
| 9 | Five landowners each retain 1/5 base | `test_five_living_land_owners_each_keep_one_fifth` | PASS |
| 10 | Living landowner with `Nhận=false` retains base | `test_living_land_owner_keeps_base_when_receive_is_off` | PASS |
| 11 | Living nonreceiver is removed without representation | `test_living_nonreceiver_is_removed_without_opening_representation` | PASS |
| 12 | Dead child branch without descendants is removed from denominator | `test_dead_child_branch_without_descendants_is_removed_from_denominator` | PASS |
| 13 | No valid receiver returns incomplete and conserves one | `test_estate_without_any_valid_receiver_is_incomplete_and_conserved` | PASS |
| 14 | Invalid graph shapes are rejected | Parameterized `test_invalid_graphs_are_rejected`; strict boolean test | PASS |
| 15 | Explicit parents never fall back to owner branch | `test_explicit_parents_do_not_fallback_unrelated_person_to_land_owner_branch`; `diagram_edges.test.mjs` | PASS |
| 16 | Calculate/save ignore client-authored output | `test_calculate_diagram_uses_database_people_without_committing`; `test_v2_case_state_recomputes_result_and_projects_backend_percentage` | PASS |
| 17 | Invalid/failing save is atomic | Incomplete V2 rejection plus create/edit rollback tests in `AtomicPersistenceTests` | PASS |
| 18 | Save/reload preserves flags, relations and fractions | Chrome `/cases/3/edit`: owner x plus m/n/o, reload returned exact `1/3` each | PASS |
| 19 | Legacy ambiguous relation warns instead of guessing | Static test `legacy cases require explicit V2 relation rebuild...` | PASS |
| 20 | Participant share comes from backend exact result | `test_v2_participant_projection_uses_exact_engine_share_instead_of_hardcoded_value` | PASS |
| 21 | Stale calculate response cannot overwrite newer state | Static test verifies sequence id, abort controller and busy counter | PASS |
| 22 | Save waits for active customer update/calculation | Static tests verify 10-second active-update wait, double-submit guard and complete calculation gate; it does not auto-commit Stage drafts | PASS |
| 23 | Required slots follow estate/representation reason | Engine required-slot assertions plus static `resolveSubRelations` contract tests | PASS |
| 24 | Populated generated relation survives recalculation | Static regression `populated generated relations survive recalculation...` | PASS |
| 25 | Calculation details use backend breakdowns | Engine multi-source terms; Chrome displayed `1/3 = 1/3 (x)` for m/n/o | PASS |
| 26 | Canvas renders kinship only, no asset-flow edge | `diagram_edges.test.mjs`; static no-`buildFlowEdges` assertion | PASS |
| 27 | Word/detail do not infer legal refusal | `test_word_engine.py`; `cases_word_export_static.test.mjs` | PASS |
| 28 | Save/reload/Word use the same result | Chrome save/reload exact `1/3`; built-in Word endpoint HTTP 200 DOCX; Word tests read V2 engine result | PASS |

## Runtime evidence

Chrome DevTools, `/cases/3/edit`, after legacy-tree cleanup and save/reload:

```json
{
  "stageRows": 13,
  "poolRows": 9,
  "engineStatus": "complete",
  "exactShares": {"568": "0", "570": "1/3", "571": "1/3", "572": "1/3"},
  "legacyTreePresent": false,
  "legacySortableCallsPresent": false
}
```

The built-in Word export returned status 200, DOCX content type, ZIP header `PK` and 24,493
bytes. The persisted Diagram object contained only `engineInput` and `engineResult`; the
calculation panel showed one backend-derived line for each receiver.
