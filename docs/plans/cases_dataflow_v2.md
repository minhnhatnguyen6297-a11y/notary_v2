# Cases dataflow V2 — Single SSoT refactor

> **Trạng thái:** APPROVED, sẵn sàng commit 1.
> **Tier:** MAJOR
> **Cập nhật:** 18/05/2026

---

## 1. Mục tiêu

Loại bỏ "11-layer state" trong cases module. Thay bằng **1 single source of truth**:

```js
window.__CASE_STATE__ = {
  caseId: number | null,
  stage: [/* full person records, append-only trừ khi user xóa */],
  diagram: {
    assignments: { [slotId]: personId },
    engineState: { /* nodes/edges metadata cho React render */ }
  }
}

// Pool = COMPUTED, không lưu
getPool() = stage.filter(p => !Object.values(diagram.assignments).includes(p.id))
```

**Invariant:** `|stage| = |pool| + |diagram.assignedPersons|` luôn đúng tự động.

---

## 2. Bối cảnh — root cause bug LẶP LẠI

User báo 3 bug:
1. **Remove khỏi diagram không quay lại pool** — `derivePoolVisibility()` đòi `inPool=true && !inTree && !inDiagram`. Legacy hidden tree set `inTree=true` cho participant nhưng React `removeWithWorkflow` chỉ clear `inDiagram` không clear `inTree`. → flag stuck.
2. **"Lưu hồ sơ" với pool còn card → pool biến mất** — Submit chỉ gửi `diagram_payload` + `engine_state_json`. DB không lưu pool/stage. Reload → `loadStagingFromStorage()` set `inPool:false` cho mọi row. → pool unassigned mất vĩnh viễn.
3. **Stage cards biến mất sau save** — Stage DOM bị `display:none` khi 0 visible. localStorage `ocr_staging_*` không hydrate đúng vì workflow flag đã lệch.

**Root cause sâu:** Code dùng **flag-based exclusion** (4 boolean: `inStaging`, `inPool`, `inTree`, `inDiagram` ngầm coi mutually exclusive) thay vì **list-based**. Mỗi action mutate 4-6 chỗ → race + reset blindly. DB không persist Stage/Pool → reload mất.

---

## 3. Decisions đã chốt với user

| # | Quyết định |
|---|---|
| 1 | **1 PR atomic, nhiều commit checkpoint.** Không tách 2 bước hybrid (vừa case_state_json vừa workflow flags chạy production). PR bàn giao là 1 merge atomic chứa toàn bộ; commit lịch sử bên trong PR có thể nhiều (mỗi commit có checkpoint test riêng) để dễ review/bisect. |
| 2 | **Cột mới `case_state_json` trong InheritanceCase.** KHÔNG reuse `engine_state_json` (cột cũ giữ cho diagram engine + legacy fallback). |
| 3 | **Xóa `derivePoolVisibility`, `__CUSTOMER_WORKFLOW__`, `__POOL_DATA_MAP__`.** Pool computed từ stage − diagram. |
| 4 | **Giữ `__CUSTOMER_REGISTRY__`** chỉ làm cache lookup danh bạ (read-only). Không quyết định person nào thuộc case. |
| 5 | **Legacy migration bắt buộc.** `GET /cases/{id}/edit` nếu `case_state_json IS NULL` → derive `{stage, diagram}` từ `engine_state_json` + `participants`. Không write DB ở GET. POST đầu tiên lưu cột mới (lazy migrate). |
| 6 | **Quick-update update __CASE_STATE__.stage ngay sau success** → re-render Stage/Pool/Diagram labels. |
| 7 | **Invariant test** kiểm `diagramIds ⊆ stageIds` và `pool = stage - diagram`. Chạy sau mỗi action (dev mode). Node test riêng. |
| 8 | **Estimate không cam kết theo số dòng.** Plan có checkpoint test rõ ràng sau mỗi commit. Mục tiêu xóa nhiều hơn thêm, không vá flag. |
| 9 | **InheritanceParticipant table giữ + derive trong POST.** Không drop phase này. `case_state_json` là SSoT nhưng POST vẫn sinh lại participant rows để tương thích Word export/preview legacy. |
| 10 | **Stage record fields (10 fields):** `id, ho_ten, gioi_tinh, ngay_sinh, ngay_chet, so_giay_to, ngay_cap, noi_cap, dia_chi, place_of_origin`. Nếu frontend code dùng tên `issue_date/issue_place`, helper `normalizeStagePerson()` phải map 2 chiều với `ngay_cap/noi_cap`. |
| 11 | **Engine output (allocations/breakdowns/warnings):** LƯU snapshot trong `case_state_json.diagram.engineState` (audit + Word export at submit time). KHI mở edit, React/engine recompute từ stage + assignments; nếu khác snapshot cũ → update khi user save tiếp. |
| 12 | **`frontend/static/diagram_state.js`:** giữ nếu React còn cần store tạm (commit ref). Chỉ xóa khi `grep -r "diagram_state" frontend/ tests/` không còn usage sau commit 5. Quyết định cuối ở commit 7. |

---

## 4. Schema thay đổi

### 4.1 DB schema
```python
# models.py — InheritanceCase
class InheritanceCase(Base):
    # ... fields cũ giữ nguyên ...
    engine_state_json = Column(Text, nullable=True)  # GIỮ — legacy, fallback derive
    case_state_json = Column(Text, nullable=True)    # MỚI — SSoT V2
```

```python
# database.py — migration
def migrate_inheritance_cases_v2():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    _ensure_table_columns(cur, "inheritance_cases", {
        "case_state_json": "TEXT",
    })
    con.commit()
    con.close()
```

### 4.2 `case_state_json` JSON shape
```json
{
  "version": 2,
  "caseId": 123,
  "updatedAt": "2026-05-12T10:30:00Z",
  "stage": [
    {
      "id": 80,
      "ho_ten": "Nguyễn Văn X",
      "gioi_tinh": "Nam",
      "ngay_sinh": "1950-01-01",
      "ngay_chet": "2011-05-15",
      "so_giay_to": "012345678",
      "ngay_cap": "2020-06-15",
      "noi_cap": "Cục Cảnh sát QLHC về TTXH",
      "dia_chi": "Số 1, Trần Phú, Ba Đình, Hà Nội",
      "place_of_origin": "Nam Định"
    },
    ...
  ],
  "diagram": {
    "assignments": {
      "slot_owner": 80,
      "slot_spouse": 81,
      "slot_father": null
    },
    "engineState": {
      "nodes": [...],
      "edges": [...],
      "allocations": {...}
    }
  }
}
```

**Stage record fields (10 fields chốt):**
- `id, ho_ten, gioi_tinh, ngay_sinh, ngay_chet, so_giay_to, ngay_cap, noi_cap, dia_chi, place_of_origin`
- Helper `normalizeStagePerson(input)` map 2 chiều:
  - `issue_date ↔ ngay_cap`
  - `issue_place ↔ noi_cap`
  - Đảm bảo cả frontend code legacy + Customer model serialize tương thích.
- Khi cần full record (vd tất cả custom fields) → lookup `__CUSTOMER_REGISTRY__`.

### 4.3 Hidden inputs form
```html
<!-- XÓA: diagram_payload, engine_state_json hidden riêng -->
<input type="hidden" name="case_state_json" id="case-state-json" value="">
<input type="hidden" name="nguoi_chet_id" value="{{...}}">
<input type="hidden" name="tai_san_id" value="{{...}}">
```

---

## 5. API contract changes

### 5.1 `GET /cases/{id}/edit` (read)
```python
@router.get("/{cid}/edit")
def edit_case(cid: int, request: Request, db: Session = Depends(get_db)):
    case = db.query(InheritanceCase).get(cid)
    if case.case_state_json:
        case_state = json.loads(case.case_state_json)
    else:
        # Lazy migrate — derive từ legacy
        case_state = derive_from_legacy(case, db)
        # KHÔNG write DB ở GET. POST đầu tiên sẽ save.
    return templates.TemplateResponse("cases/form.html", {
        "request": request,
        "case_state_json": json.dumps(case_state, ensure_ascii=False),
        # ... existing context ...
    })
```

### 5.2 `POST /cases/{id}/edit` (write)
```python
@router.post("/{cid}/edit")
def update_case(
    cid: int,
    case_state_json: str = Form(...),
    nguoi_chet_id: Optional[int] = Form(None),
    tai_san_id: Optional[int] = Form(None),
    # ... other form fields ...
):
    try:
        payload = parse_case_state(case_state_json)
    except CaseStateValidationError as e:
        # Render lại form với errors echo
        return templates.TemplateResponse("cases/form.html", {
            "case_state_json": case_state_json,  # echo lại để React restore
            "validation_errors": e.errors,
            # ...
        })
    
    case = db.query(InheritanceCase).get(cid)
    case.case_state_json = case_state_json  # raw JSON, đã validate
    case.nguoi_chet_id = nguoi_chet_id
    case.tai_san_id = tai_san_id
    
    # Derive InheritanceParticipant rows từ diagram cho Word export legacy compat
    _replace_participants_from_state(db, cid, payload)
    
    db.commit()
    return RedirectResponse(...)
```

### 5.3 Helper `derive_from_legacy`
```python
def derive_from_legacy(case: InheritanceCase, db: Session) -> dict:
    """Hồ sơ cũ → derive {stage, diagram} từ engine_state_json + participants."""
    participants = db.query(InheritanceParticipant).filter_by(ho_so_id=case.id).all()
    stage = []
    for p in participants:
        customer = db.query(Customer).get(p.customer_id)
        if not customer:
            continue
        stage.append({
            "id": customer.id,
            "ho_ten": customer.ho_ten,
            "gioi_tinh": customer.gioi_tinh,
            "ngay_sinh": customer.ngay_sinh.isoformat() if customer.ngay_sinh else None,
            "ngay_chet": customer.ngay_chet.isoformat() if customer.ngay_chet else None,
            "so_giay_to": customer.so_giay_to,
            "ngay_cap": customer.ngay_cap.isoformat() if customer.ngay_cap else None,
            "noi_cap": customer.noi_cap,
            "dia_chi": customer.dia_chi,
            "place_of_origin": customer.place_of_origin,
        })
    
    engine_state = json.loads(case.engine_state_json) if case.engine_state_json else {}
    # Best effort: dùng engine_state nodes làm diagram.assignments
    diagram = {
        "assignments": _build_assignments_from_nodes(engine_state.get("nodes", [])),
        "engineState": engine_state,
    }
    
    return {
        "version": 2,
        "caseId": case.id,
        "stage": stage,
        "diagram": diagram,
        "updatedAt": case.updated_at.isoformat() if case.updated_at else None,
    }
```

### 5.4 Validation
```python
class CaseStateValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors

def parse_case_state(raw: str) -> dict:
    """Parse + validate. Reject duplicate stage IDs, invalid customer refs."""
    payload = json.loads(raw)
    errors = []
    
    if payload.get("version") != 2:
        errors.append("Unsupported version")
    
    stage = payload.get("stage", [])
    stage_ids = set()
    for s in stage:
        if not s.get("id"):
            errors.append(f"Stage item thiếu id")
            continue
        if s["id"] in stage_ids:
            errors.append(f"Duplicate stage id: {s['id']}")
        stage_ids.add(s["id"])
    
    diagram = payload.get("diagram", {})
    assignments = diagram.get("assignments", {})
    for slot_id, person_id in assignments.items():
        if person_id is not None and person_id not in stage_ids:
            errors.append(f"Diagram slot {slot_id} reference personId không có trong stage: {person_id}")
    
    if errors:
        raise CaseStateValidationError(errors)
    return payload
```

---

## 6. Frontend architecture

### 6.1 `frontend/static/case_state.js` (MỚI)
```js
// Single source of truth
window.__CASE_STATE__ = {
  caseId: null,
  stage: [],
  diagram: { assignments: {}, engineState: { nodes: [], edges: [] } },
};

const subscribers = new Set();

function notify() {
  // Dev-mode invariant check. Browser-safe: process không tồn tại trong browser.
  if (window.__CASE_STATE_DEV__ === true) {
    assertCaseStateInvariant();
  }
  subscribers.forEach(cb => cb(window.__CASE_STATE__));
}

// === Actions ===
function addToStage(person) {
  const exists = window.__CASE_STATE__.stage.find(p => p.id === person.id);
  if (exists) {
    Object.assign(exists, person);  // update
  } else {
    window.__CASE_STATE__.stage.push(person);
  }
  persist();
  notify();
}

function removeFromStage(personId) {
  // Cảnh báo nếu person đang trong diagram
  const assignedSlots = Object.entries(window.__CASE_STATE__.diagram.assignments)
    .filter(([, id]) => id === personId)
    .map(([slot]) => slot);
  if (assignedSlots.length) {
    if (!confirm(`Người này đang trong sơ đồ ở ô ${assignedSlots.join(', ')}. Xóa luôn?`)) return;
    assignedSlots.forEach(slot => delete window.__CASE_STATE__.diagram.assignments[slot]);
  }
  window.__CASE_STATE__.stage = window.__CASE_STATE__.stage.filter(p => p.id !== personId);
  persist();
  notify();
}

function assignToSlot(personId, slotId) {
  window.__CASE_STATE__.diagram.assignments[slotId] = personId;
  notify();
}

function unassignSlot(slotId) {
  delete window.__CASE_STATE__.diagram.assignments[slotId];
  notify();
}

// === Computed ===
function getPool() {
  const assigned = new Set(Object.values(window.__CASE_STATE__.diagram.assignments).filter(Boolean));
  return window.__CASE_STATE__.stage.filter(p => !assigned.has(p.id));
}

function getStaged() { return window.__CASE_STATE__.stage; }
function getDiagramAssignments() { return window.__CASE_STATE__.diagram.assignments; }

// === Persistence ===
function persist() {
  const caseId = window.__CASE_STATE__.caseId ?? 'new';
  localStorage.setItem(`case_state_${caseId}`, JSON.stringify(window.__CASE_STATE__));
}

function hydrate(serverState) {
  window.__CASE_STATE__ = serverState;
  notify();
}

// === Invariant ===
function assertCaseStateInvariant() {
  const stageIds = new Set(window.__CASE_STATE__.stage.map(p => p.id));
  const assigned = Object.values(window.__CASE_STATE__.diagram.assignments).filter(Boolean);
  for (const personId of assigned) {
    if (!stageIds.has(personId)) {
      console.error(`INVARIANT VIOLATION: diagram references personId ${personId} not in stage`);
    }
  }
}

// === Subscribe ===
function subscribe(cb) {
  subscribers.add(cb);
  cb(window.__CASE_STATE__);  // replay current
  return () => subscribers.delete(cb);
}

window.__CASE_STATE_API__ = {
  addToStage, removeFromStage,
  assignToSlot, unassignSlot,
  getPool, getStaged, getDiagramAssignments,
  hydrate, subscribe,
};
```

### 6.2 `form.html` mutations

**XÓA toàn bộ:**
- `window.__CUSTOMER_WORKFLOW__` declaration + tất cả mutations
- `window.__POOL_DATA_MAP__`
- `window.__FAMILY_TREE_STATE__`
- `derivePoolVisibility()` function
- `setCustomerWorkflowState()` function
- `commitCustomerToPool()` function
- `updateCustomerWorkflow()` function
- Event listener `onFamilyTreeUpdate` phần reset workflow
- `loadStagingFromStorage()` phần set `inPool:false`

**Thay bằng:**
- Render pool/stage/diagram đăng ký qua `window.__CASE_STATE_API__.subscribe()`
- Mutation đi qua actions
- OCR/Excel/inline-create → `addToStage(person)`
- Drag pool → diagram drop → `assignToSlot(personId, slotId)` (via React callback)
- Remove diagram → `unassignSlot(slotId)` (via React callback)
- Quick-update success → `addToStage(updatedPerson)` (idempotent update)
- Submit handler → serialize `window.__CASE_STATE__` vào hidden `case_state_json`, native submit

### 6.3 `ReactFlowApp.jsx`
- Bỏ `__DIAGRAM_API__` complex (`getCommittedState`, `subscribe`, `setSaving`, `busyCount`)
- Diagram state = `window.__CASE_STATE__.diagram`
- Drop callback: `props.onAssign(personId, slotId)` → form gọi `__CASE_STATE_API__.assignToSlot`
- Remove callback: `props.onUnassign(slotId)` → form gọi `__CASE_STATE_API__.unassignSlot`
- Engine compute từ assignments + stage → output `nodes`/`edges` để render
- Engine output có thể được sync vào `__CASE_STATE__.diagram.engineState` qua callback `props.onEngineUpdate(engineState)`

---

## 7. Implementation — chia commit nhỏ (bàn giao 1 PR)

### Commit 1 — Backend schema + migration (~150 dòng)
- `models.py`: add cột `case_state_json TEXT NULL`
- `database.py`: thêm `migrate_inheritance_cases_v2()`, gọi trong startup
- `main.py`: gọi migration (nếu chưa được include trong existing migration)
- Test: `python -m py_compile models.py database.py`, `python -m uvicorn main:app --port 8000` không crash
- **Checkpoint:** mở SQLite DB, verify cột mới tồn tại + null cho mọi row cũ

### Commit 2 — Backend parser + derive_from_legacy + GET (~250 dòng)
- `routers/cases.py`:
  - `parse_case_state(raw)` + `CaseStateValidationError`
  - `derive_from_legacy(case, db)`
  - `_build_assignments_from_nodes(nodes)`
  - Sửa `GET /{cid}/edit`: dùng `derive_from_legacy` nếu null
- `tests/test_case_state_parser.py`:
  - Valid payload
  - Duplicate stage id → error
  - Invalid assignment ref → error
  - `derive_from_legacy` với hồ sơ cũ minh họa
- **Checkpoint:** chạy pytest, mở 1 hồ sơ cũ ở `/cases/{id}/edit`, xem source HTML có `case_state_json` đầy đủ stage list

### Commit 3 — Frontend case_state.js + invariant test (~200 dòng)
- `frontend/static/case_state.js` (mới): toàn bộ API
- `tests/case_state.test.mjs`: test getPool, addToStage, assignToSlot, removeFromStage cảnh báo, invariant detection
- **Checkpoint:** `node --test tests/case_state.test.mjs` pass

### Commit 4 — Frontend hydrate + render stage/pool (~400 dòng, gồm XÓA nhiều)
- `form.html`:
  - Thêm `<script src="/static/case_state.js">` trước inline JS
  - Bootstrap: `__CASE_STATE_API__.hydrate(JSON.parse('{{ case_state_json | safe }}'))`
  - XÓA `__CUSTOMER_WORKFLOW__`, `__POOL_DATA_MAP__`, `derivePoolVisibility`, `setCustomerWorkflowState`, `commitCustomerToPool`, `updateCustomerWorkflow`
  - Render stage area từ `__CASE_STATE_API__.subscribe(render)`
  - Render pool area từ `__CASE_STATE_API__.getPool()`
  - OCR/import/inline-create handlers → `addToStage()`
- **Checkpoint:** mở `/cases/create`, thêm 3 người qua inline-create → stage hiện 3, pool hiện 3 (computed)

### Commit 5 — React integration (~200 dòng)
- `ReactFlowApp.jsx`:
  - Bỏ `__DIAGRAM_API__` (giữ tối thiểu nếu cần)
  - Props: `onAssign(personId, slotId)`, `onUnassign(slotId)`, `assignments` từ state
  - Engine compute từ assignments
- `form.html`: mount React với callbacks gọi `__CASE_STATE_API__`
- **Checkpoint:** drag person từ pool → diagram, pool tự update; remove diagram → person về pool

### Commit 6 — Save handler + atomic submit (~150 dòng)
- `form.html` submit handler:
  - Snapshot `window.__CASE_STATE__`
  - Set hidden `case_state_json` = JSON.stringify
  - Native form submit (không fetch)
  - KHÔNG clear stage/localStorage trước submit
- `routers/cases.py` `POST /{cid}/edit`:
  - Nhận `case_state_json`
  - Parse + validate
  - Lưu raw vào cột mới
  - Derive `InheritanceParticipant` rows cho Word export legacy
  - Validation fail → render template với `validation_errors` + echo `case_state_json`
- `cases/form.html` template: thêm `<div id="validation-errors">{{ errors }}</div>`
- **Checkpoint:**
  - 3 case bug user báo: drop z1 → save → reload, z1 còn nguyên
  - Save với pool có cards → pool còn nguyên sau reload
  - Stage cards không biến mất

### Commit 7 — Cleanup + verify (~50 dòng)
- Xóa `frontend/static/diagram_state.js` nếu không còn ai dùng
- Xóa hidden `diagram_payload`, `engine_state_json` form input nếu không backward compat needed
- Verify: `.\verify.bat`
- Run manual checklist 5 case
- Update `AGENTS.md` history mục `cases > diagram data flow`

---

## 8. Checkpoint test (sau mỗi commit)

| Commit | Test |
|---|---|
| 1 | `py_compile`, uvicorn start không crash, SQLite có cột mới |
| 2 | `pytest tests/test_case_state_parser.py`, GET edit trả HTML có case_state_json |
| 3 | `node --test tests/case_state.test.mjs` pass |
| 4 | Inline-create 3 người → stage 3, pool 3 (computed); thêm 1 → 4/4 |
| 5 | Drag → pool 3/diagram 1; remove → pool 4/diagram 0 |
| 6 | Drop z1 → save → reload → z1 còn (3 bug case) |
| 7 | `.\verify.bat` PASS; manual 5 case pass |

**Nếu checkpoint fail:** dừng, không tiếp commit sau, fix tại chỗ.

---

## 9. Risk + rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| `derive_from_legacy` bug → hồ sơ cũ mở sai | Test với 3+ hồ sơ thật trước merge | Backup DB trước migrate, revert commit |
| Xóa workflow logic missed reference → OCR/Excel import vỡ | Manual test OCR import + Excel import sau commit 4 | Revert commit 4, fix tại chỗ |
| React bridge bỏ DIAGRAM_API → diagram không render | Test commit 5 immediate | Revert commit 5 |
| Submit format đổi → backend old code reject | Commit 6 yêu cầu commit 2 (parser) merged trước | Backend parser deploy trước frontend |
| 1 PR atomic merge → deploy fail → cả PR rollback | Test trên staging trước production | `git revert <merge-commit>` |

---

## 10. Migration tool (defer phase sau)

Hồ sơ cũ trong DB sẽ lazy migrate khi user save lần đầu (commit 2 derive_from_legacy + commit 6 save mới). Không cần batch migration script ngay.

Nếu cần batch sau (vd để clean old `engine_state_json`):
```bash
python tools/migrate_cases_to_v2.py --dry-run
python tools/migrate_cases_to_v2.py --commit
```
Tool này KHÔNG trong scope phase này. Backlog.

---

## 11. Defer (sau phase này)

- Fetch async + JSON error contract
- Banner restore localStorage draft mới hơn DB
- Versioned localStorage migration đầy đủ
- Engine refactor đa-`*` (đồng chủ sở hữu)
- Renderer bug gom sibling cùng nhóm (Z bị vẽ cạnh X thay vì Y)
- UI label động ("Con của Z")
- Live preview parser align với V2
- Batch migration tool v1 → v2
- Cleanup orphan customer (tạo qua inline-create nhưng case không save)
- Bỏ hoàn toàn `engine_state_json` cột cũ (sau khi 100% hồ sơ migrated)

---

## 12. Post-task report template

Sau khi implement xong, agent print:

```text
BAO CAO HOAN THANH:
- File da sua: <list>
- File da them: <list>
- File da xoa: <list>
- Ham/symbol da xoa: __CUSTOMER_WORKFLOW__, __POOL_DATA_MAP__, derivePoolVisibility, setCustomerWorkflowState, commitCustomerToPool, updateCustomerWorkflow, onFamilyTreeUpdate (phần reset)
- Ham/symbol moi them: __CASE_STATE__, __CASE_STATE_API__, parse_case_state, derive_from_legacy, CaseStateValidationError
- verify: .\verify.bat <PASS/FAIL>
- Scope match list ban dau: <YES/NO + giải thích nếu cần SCOPE BREAK>
- Ghi chu rui ro/test con lai: <list bug pattern còn nghi ngờ, test chưa cover>
```

---

## 13. Câu hỏi đã đóng

- ✅ Cột mới hay reuse? → Cột mới `case_state_json`
- ✅ Tách 2 bước hay 1 PR atomic? → 1 PR atomic, nhiều commit checkpoint
- ✅ Migration ở GET hay batch tool? → Lazy migrate ở GET (derive_from_legacy)
- ✅ Quick-update flow? → Success callback update `__CASE_STATE__.stage[i]`
- ✅ Registry có giữ? → Có, làm cache lookup danh bạ
- ✅ Estimate dòng? → Không cam kết, mục tiêu xóa nhiều hơn thêm
- ✅ Invariant test? → Yes, `node --test` cho pure helpers
- ✅ `InheritanceParticipant` table? → GIỮ + derive trong POST cho Word export compat
- ✅ Stage record fields? → 10 fields (`id, ho_ten, gioi_tinh, ngay_sinh, ngay_chet, so_giay_to, ngay_cap, noi_cap, dia_chi, place_of_origin`) + helper map `issue_date/issue_place` ↔ `ngay_cap/noi_cap`
- ✅ Engine output? → LƯU snapshot trong `case_state_json.diagram.engineState` (audit + Word export), recompute khi mở edit
- ✅ `diagram_state.js`? → Giữ nếu commit 5 vẫn ref. Xóa ở commit 7 chỉ khi grep không còn usage.
- ✅ Dev-mode check trong browser? → `window.__CASE_STATE_DEV__ === true` (không dùng `process.env`)
