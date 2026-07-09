# Case flow history

Archive of resolved/superseded notes that used to live in `docs/case_user_flow_spec.md`.

Current spec: `docs/specs/case_user_flow.md`.
Active issues: `docs/issues/case_flow_open_issues.md`.

## Resolved OCR modal notes

- OCR modal `x`/hide no longer auto-stages or clears OCR result/image queue.
- OCR footer uses explicit `Lưu`; closing/dismissing is not save.
- `AI OCR` appends new results and does not reset old results.
- OCR pushes data to Stage only through `Lưu`.
- OCR-to-Stage allows incomplete front/back.
- OCR-to-Stage does not block duplicate CCCD rows; user removes duplicates manually.
- Local OCR and non-person OCR results were removed/hidden from the current person-CCCD modal scope.
- Temporary OCR data/images are cleared only after Stage `Cập nhật`.

## Resolved Stage notes

- Stage button name is `Cập nhật`.
- Stage is the UI source of truth for people in the case.
- For existing cases, `Cập nhật` persists Stage snapshot to `InheritanceCase.case_state_json` through `/cases/{cid}/stage-update`.
- For new cases, `Cập nhật` updates hidden case state for later `Tạo hồ sơ`.
- Pool is derived from committed Stage minus Diagram assignments.
- Submit no longer uses draft DOM rows as authoritative if Stage has not been committed.
- Stage row delete is draft until `Cập nhật`; cascade to Pool/Diagram happens after commit.
- Duplicate CCCD/ID with different Stage row identity remains separate unless user removes it.
- Stage date display accepts/uses `dd/mm/yyyy` in UI while backend can parse legacy payloads.
- Old cases without `case_state_json` may derive Stage from participants on edit and persist later on user commit.

## Resolved Pool notes

- Pool is a computed view, not persisted as its own truth.
- Import/search/inline-create adds people to Stage draft first; Pool updates after Stage `Cập nhật`.
- Search/customer lookup must not directly set a person as in Pool.
- Drop/remove/move bridges were adjusted so assigned people do not remain visible in Pool and removed people return only if still in Stage.

## Diagram notes moved out of spec

- Existing case save uses `Lưu sơ đồ` / `/cases/{cid}/diagram-update` and should preserve Stage.
- New case uses `Tạo hồ sơ`; `Lưu sơ đồ` must not become a hidden full-submit fallback.
- Remove/move in Diagram prunes dependent branches and returns dependent people to Pool only if they still exist in Stage.
- Visual edge/arrow work is deferred to `docs/plans/diagram_visual_v2.md`.
- Detailed partial persistence risks live in `docs/issues/case_flow_open_issues.md` until resolved.

## Note

The old file was intentionally compressed because resolved implementation logs were making the active UX/business spec too noisy for agents. If full forensic details are needed, search older session artifacts or runtime notes rather than re-expanding the active spec.
