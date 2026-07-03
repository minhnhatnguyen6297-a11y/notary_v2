# Pool/Diagram Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dong cac issue con mo cua Phase 3 Pool va Phase 4 Diagram de flow Stage -> Pool -> Diagram khong tu xoa/nhan doi/move sai du lieu, dong thoi lam ro rule truoc khi code.

**Architecture:** Stage van la source of truth UI duy nhat. Pool la projection tu committed Stage tru diagram assignments. Diagram chi luu trang thai pool/diagram va khong duoc ghi de Stage.

**Tech Stack:** FastAPI + Jinja2 + Vanilla JS trong `frontend/templates/cases/form.html`, React trong `frontend/static/ReactFlowApp.jsx`, Node static tests, Python unittest cho router/state parser.

---

## Current Open Items

- `POOL-2`: Resolved 2026-06-22. Import/them nguoi chi tao Stage draft; pool refresh sau `Cap nhat`.
- `POOL-3`: Resolved 2026-06-22 cho data-flow hien tai. Assign/move/remove da co guard tranh displaced stale va swap occupied target.
- `POOL-R2`: Resolved by decision 2026-06-19: duplicate cung so giay to nhung khac row id la 2 dong doc lap; khong tu gop/xoa.
- `DIAGRAM-2`: Resolved 2026-06-22 cho data-flow non-visual: drop/move vao node da co nguoi bi block; khong replace, khong swap.
- `DIAGRAM-3`: Deferred 2026-06-19: visual diagram/edge/arrow se tach thanh task lon rieng.
- `DIAGRAM-R3`: Deferred theo task visual diagram rieng.
- `DIAGRAM-R4`: Resolved 2026-06-22. Tach `Tao ho so` va `Luu so do`; case moi chua co id khong fallback full submit bang nut luu so do.

## Files

- Modify: `docs/case_user_flow_spec.md` - update resolved/open status sau tung task.
- Modify: `frontend/templates/cases/form.html` - Stage commit, pool projection, import/add-person refresh, diagram save boundary.
- Modify: `frontend/static/ReactFlowApp.jsx` - diagram assignment/move/remove rule.
- Modify: `tests/cases_ui_dataflow_static.test.mjs` - static regression cho frontend contract.
- Modify: `tests/test_diagram_payload_parser.py` - backend state/parser regression neu can boundary DB/API.

## Decision Gates Before Coding

- [x] **Gate A: Occupied diagram node rule**

Decision 2026-06-19: `block` drop vao node da co nguoi. User phai xoa node dich truoc neu muon thay nguoi.

Reason: Dung tinh than spec "mot nut mot viec", tranh hanh vi an nhu swap/replace lam user khong biet vi sao the bi chuyen.

Rejected:
- `replace`: nguoi cu o node dich bi tra ve pool, nguoi moi vao node dich.
- `swap`: giu legacy, hai nguoi doi node cho nhau. Khong khuyen nghi vi an nhieu side-effect.

- [x] **Gate B: Connector visual style**

Decision 2026-06-19: defer visual diagram/connector/arrow thanh mot task lon rieng de user mo ta chi tiet sau.

- Current implementation plan khong sua connector visual, tru khi can test de bao ve behavior data-flow.

- [x] **Gate C: New case without id**

Decision 2026-06-19: tach han `Tao ho so` va `Luu so do`. Khi chua co case id, `Luu so do` disabled hoac hien thong bao can tao ho so truoc.

- [x] **Gate D: Duplicate document identity**

Decision 2026-06-19: duplicate cung CCCD/so giay to nhung khac Stage row id van la 2 row doc lap. He thong khong tu gop, khong tu xoa; user tu xoa dong thua bang nut xoa cuoi dong Stage.

## Task 1: Close POOL-2 With Committed Stage Refresh

**Files:**
- Modify: `frontend/templates/cases/form.html`
- Modify: `tests/cases_ui_dataflow_static.test.mjs`
- Modify: `docs/case_user_flow_spec.md`

- [x] **Step 1: Add failing static tests**

Test intent:
- Import Excel/them nguoi khong duoc day thang vao pool bang workflow flag.
- Pool chi refresh tu `loadPool()` sau `saveParticipantDraftRows()` commit thanh cong.
- `loadPool()` van tinh tu `getCommittedStageSnapshot()` tru diagram assignments.

Run:
```powershell
node --test tests/cases_ui_dataflow_static.test.mjs
```

Expected: FAIL vi test moi chua duoc code dap ung hoac chua co guard.

- [x] **Step 2: Normalize import/add-person entrypoints**

Implementation rule:
- Moi nguon them nguoi chi duoc upsert registry va tao/sua row Stage draft.
- Khong set `inPool: true` truoc khi bam `Cap nhat`.
- Sau `Cap nhat` thanh cong moi goi `loadPool()`.

- [x] **Step 3: Update spec status**

Update `POOL-2` thanh resolved neu import Excel/them nguoi deu theo contract tren.

- [x] **Step 4: Verify**

Run:
```powershell
node --test tests/cases_ui_dataflow_static.test.mjs
.\verify.bat
```

Expected: PASS.

## Task 2: Close POOL-3 Assign/Displace Race

**Files:**
- Modify: `frontend/static/ReactFlowApp.jsx`
- Modify: `tests/cases_ui_dataflow_static.test.mjs`
- Modify: `docs/case_user_flow_spec.md`

- [x] **Step 1: Add failing tests for atomic move/remove**

Test intent:
- Assign tu pool vao diagram khong tao duplicate person active.
- Remove node tra target + dependent branch ve pool.
- Move node chi giu moved person trong diagram, dependent branch ve pool.
- Displaced/blocked behavior phai theo Gate A.

- [x] **Step 2: Make assignment result deterministic**

Implementation rule:
- Recheck validation inside `commitLogicalNodes`.
- Compute affected/displaced people from same logical transition, not from stale preview if possible.
- Bridge workflow only after knowing final transition.
- Khong tra moved person ve pool khi move thanh cong.

- [x] **Step 3: Verify**

Run:
```powershell
node --test tests/cases_ui_dataflow_static.test.mjs
.\verify.bat
```

Expected: PASS.

## Task 3: Implement Gate A Occupied Node Rule

**Files:**
- Modify: `frontend/static/ReactFlowApp.jsx`
- Modify: `tests/cases_ui_dataflow_static.test.mjs`
- Modify: `docs/case_user_flow_spec.md`

- [x] **Step 1: Add failing test for chosen rule**

If `block` is chosen:
- Drop vao node co nguoi returns validation error.
- Source node khong bi clear.
- Target node khong bi replace.
- Pool khong nhan lai moved person.

- [x] **Step 2: Implement rule in one validation path**

Implementation rule:
- `validateAssignment()` la gate duy nhat cho drop from pool va move within diagram.
- UI toast/message noi ro ly do bi chan.

- [x] **Step 3: Verify**

Run:
```powershell
node --test tests/cases_ui_dataflow_static.test.mjs
.\verify.bat
```

Expected: PASS.

## Task 4: Defer DIAGRAM-3 Connector/Arrow Geometry

**Files:**
- Modify: `docs/case_user_flow_spec.md`

- [x] **Step 1: Update spec only**

Mark `DIAGRAM-3` va `DIAGRAM-R3` la deferred sang task visual diagram rieng. Khong sua connector code trong plan nay.

## Task 5: Resolve DIAGRAM-R4 New Case Boundary

**Files:**
- Modify: `frontend/templates/cases/form.html`
- Modify: `routers/cases.py` only if backend create flow needs explicit route/result change.
- Modify: `tests/cases_ui_dataflow_static.test.mjs`
- Modify: `tests/test_diagram_payload_parser.py` only if backend boundary changes.
- Modify: `docs/case_user_flow_spec.md`

- [x] **Step 1: Add failing boundary test**

Test intent:
- Existing case: `Luu so do` posts `/cases/${caseId}/diagram-update`.
- New case without id: behavior follows Gate C.
- Diagram save must not silently submit full form unless Gate C chooses temporary fallback.

- [x] **Step 2: Implement selected boundary**

If split is chosen:
- Disable or block `Luu so do` until case exists.
- Keep/create separate `Tao ho so` action for initial create.
- After create, user edits existing case and can use `Luu so do`.

- [x] **Step 3: Verify**

Run:
```powershell
node --test tests/cases_ui_dataflow_static.test.mjs
.\venv\Scripts\python.exe -m unittest tests.test_diagram_payload_parser
.\verify.bat
```

Expected: PASS.

## Task 6: Final Spec Sync And Handoff

**Files:**
- Modify: `docs/case_user_flow_spec.md`

- [x] **Step 1: Mark resolved/remaining issues**

Update each item:
- `POOL-2`
- `POOL-3`
- `POOL-R2`
- `DIAGRAM-2`
- `DIAGRAM-3`
- `DIAGRAM-R3`
- `DIAGRAM-R4`

- [x] **Step 2: Final verify**

Run:
```powershell
node --test tests/cases_ui_dataflow_static.test.mjs
.\venv\Scripts\python.exe -m unittest tests.test_diagram_payload_parser
.\verify.bat
```

Expected: PASS.

- [ ] **Step 3: Post-task report**

Report must include:
- File da sua/them/xoa.
- Ham/symbol moi/xoa.
- Verify output.
- Scope match.
- Risk/test con lai.

## Execution Notes

- Tier khi code: `MAJOR`, vi cham cross-module UI state, diagram behavior, va co the cham router/test.
- Truoc khi sua code phai in scope lock theo `AGENTS.md`.
- Khong sua `AGENTS.md` hoac `.understand-anything/` neu khong phai scope duoc user chot.
- Khong them helper/module moi neu chi can sua trong file hien co.
- Neu phat sinh rule nghiep vu mo ho, dung va hoi user thay vi tu quyet.
