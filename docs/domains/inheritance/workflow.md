# Case user flow spec - Hồ sơ thừa kế

This file is the current UX/business spec for the case screen. It describes one unified flow for the `Hồ sơ thừa kế` model.

Read this before changing:
- `frontend/templates/cases/form.html`
- person CCCD OCR modal
- Stage / Pool / Diagram interaction
- preview/export behavior that depends on case state
- Word export UX and flow: `word-export.md`

Resolved bug notes are historical. Active issues live in `plan.md`.

## 1. Core principles

- Each button has one clear responsibility.
- A button may save/delete/clear/reset data only when this spec explicitly says so.
- Modal `x` means hide/minimize only.
- Do not invent hidden merge/sync behavior when the source of truth is unclear.
- If the requested change affects business behavior, identify the affected rule before editing.
- If a rule is ambiguous, ask the user before changing logic.

## 2. Data zones

- Image queue: selected OCR images before/around OCR.
- OCR modal: temporary OCR result plus source images.
- Stage: UI source of truth for people in the case.
- Pool: computed view of Stage people not assigned in Diagram.
- Diagram: relationship, assignment, engine, and render state.
- DB: persisted case/customer/stage/diagram state.

## 3. Person CCCD OCR modal

Input:
- User selects one or more CCCD images and clicks `AI OCR`.

Expected output:
- OCR result appears in the OCR modal.
- Source images remain available in the OCR modal.
- Each person row has `Xem ảnh`.
- If one row came from front + back images, `Xem ảnh` must show both.
- OCR result is not pushed to Stage until user clicks `Lưu`.

`Lưu` in OCR modal:
- Pushes OCR rows to Stage.
- Keeps OCR temporary result/images until Stage `Cập nhật` succeeds.
- Allows incomplete front/back.
- Repeated `Lưu` of the same OCR card creates another Stage row; no hidden merge/update.

Modal `x`:
- Hides/minimizes only.
- Does not save, clear image queue, clear OCR result, reset, flush, or auto-stage.

Running `AI OCR` again:
- Adds new OCR results above old results.
- Does not delete old OCR results.
- Does not auto-merge duplicate CCCD rows.

## 4. Stage

Stage is the UI source of truth for people in a case.

Stage receives people from:
- OCR person modal
- Excel/import
- search/inline create
- future input sources

Minimum visible person fields:
- `ho_ten`
- `ngay_sinh`
- `ngay_chet`
- `so_giay_to`
- `ngay_cap`
- `dia_chi`

Rules:
- Stage rows are editable.
- Only the remove button at the end of a Stage row may delete that row.
- Deleting a Stage row is draft UI until user clicks `Cập nhật`.
- Other buttons must not clear/remove Stage rows.
- Duplicate CCCD/ID rows are user-managed unless a task explicitly changes this rule.

`Cập nhật`:
- Takes current Stage rows as committed source of truth.
- Syncs Pool/Diagram from committed Stage.
- Persists Stage for an existing case.
- For a new case, updates hidden case state for later submit.
- Clears temporary OCR modal data/images only after successful commit.

## 5. Pool

Pool is a computed/intermediate view, not a source of truth.

Rules:
- Pool = committed Stage people minus people currently assigned in Diagram.
- Dropping a Pool card into Diagram removes it from Pool display only.
- Removing a Diagram card returns it to Pool only if that person still exists in Stage.
- Pool/Diagram actions must not delete Stage people.

## 6. Diagram

Diagram stores:
- person assignments to nodes/slots
- relationships
- branch state
- asset-owner assignments
- receiver assignments for the current asset
- engine output
- render metadata

Rules:
- Diagram must reference people that exist in Stage.
- Diagram save must not alter Stage person fields.
- Removing/moving cards in Diagram must not delete people from Stage.
- If Stage deletes a person and user clicks `Cập nhật`, Diagram must cascade/prune references to that person.
- Diagram inheritance/business rules live in `spec.md`.
- Diagram UI/UX and edge rules live in `ux.md`.
- Word export UX/flow lives in `word-export.md`.

### Asset decision rule

- Diagram only lets the user mark who is an original landowner and who receives the current asset.
- The two card buttons are `Chủ đất` and `Nhận`; there is no `★` or `Từ chối` button.
- A person node must not have a separate unset/refusal decision.
- The non-receiver list is derived as:

```text
Người không nhận = Tất cả người trên Diagram - Chủ đất - Người nhận
```

- `Người không nhận` is a product label, not legal refusal of inheritance.
- `Người từ chối` may only come from separately confirmed legal data; Diagram does not infer it from `Nhận`.
- Existing refusal fields may be read only for legacy migration; they are not a source of truth after the new rule is implemented.
- Stage remains the source of truth for person data. Marking a landowner or receiver changes Diagram state only.
- Receiver selection is scoped to the current asset. Multi-asset assignment will reuse the same rule separately for each asset.

## 7. Delete / clear permissions

Allowed:
- Stage row delete button: removes that draft Stage row.
- Stage `Cập nhật`: may clear temporary OCR modal data/images after committing Stage.
- Diagram card `x`: removes assignment from Diagram and returns the person to Pool if still present in Stage.

Not allowed:
- OCR modal `x` deleting or saving anything.
- `AI OCR` clearing old OCR results.
- Pool/Diagram operations deleting Stage people.
- Diagram save modifying Stage people.

## 8. Agent checklist

Before editing this flow, answer:

- Which zone is touched: OCR modal, Stage, Pool, Diagram, DB, preview/export?
- Which button/action is the user input?
- What exact data may this action create/update/delete?
- Is Stage still the UI source of truth?
- If deleting/moving in Diagram, should the person return to Pool or disappear because Stage no longer contains them?
- If touching inheritance engine, did you read `spec.md`?
- If touching Diagram UI/UX or connectors, did you read `ux.md`?

If unclear, stop and ask user before changing business logic.
