# Plan: Diagram Visual V2 (Sơ đồ thừa kế)

**Trang thai:** PLANNED (26/06/2026)
**Cap nhat:** 2026-06-26
**Files lien quan:** `frontend/static/ReactFlowApp.jsx`, `frontend/static/diagram_edges.js`, `frontend/templates/cases/form.html`
**Tier:** MAJOR

---

## Muc tieu

Thiet ke lai visual cua so do thua ke:
- thay bezier curves lon xon bang **orthogonal org-chart connectors** (goc vuong, T-junction).
- tach bet 2 luong: huyet thong (visible) + tai san (hidden).
- inline pending spouse (non-blocking) + 3 rules chat.
- auto-layout can doi, khong tu bien vi tri.
- card toi gian, bo label "Cha ruot/Me ruot/Chu dat".

## Van de hien tai

1. `buildSoftCurve()` ve bezier curves → nhieu connection se cheo nhau.
2. `flowPaths` (cam) + `kinshipPaths` (xam dashed) cung render → roi.
3. Spouse chi la slot co dinh `id="spouse"` canh `owner`, khong co UI ket noi dong.
4. User khong phan biet duoc "quan he" vs "dong tien".
5. Card fixed `CARD_WIDTH=140` + `flexWrap:wrap` → lon xon khi nhieu nguoi.

## Nguyen tac da chot

### 2 luong
- **Luong 1 (huyet thong) — VISIBLE, orthogonal style:**
  - Cha─Me: duong ngang lien (solid) + icon ♡ giua.
  - Cha/Me → con: T-junction — duong doc xuong tu giua cap cha me → nhanh ngang → doc xuong moi con.
  - Anh/chi/em: cung nhanh ngang tu cung cha me.
  - Spouse cua con (dau/re): ngang canh con, cung style ♡.
  - Con the vi: nhanh xuong tu node cha da mat.
  - Mui ten mac dinh huong xuong (khong ve mui ten tren duong noi).
- **Luong 2 (tai san) — HIDDEN:**
  - Xoa hoan toan `flowPaths` khoi SVG render.
  - `diagram_edges.js` van giu `buildFlowEdges()` → engine dung noi bo.
  - Share % van hien text tren card.
  - ★ toggle giu nguyen de danh dau chu dat ban dau.
  - Backend tu tinh huong chay: hang 2 ↑ bo me + ↓ con.

### Spouse pairing — cach A (inline pending)
- Drop de card co nguoi → tao node `kind: "pendingSpouse"`, `parentSlotId: anchorId`.
- Card pending: glow vang + banner "Chen vo/chong?" + [Yes][No].
- Yes → materialize thanh spouse node (`relationType: "spouse"`, `spouseOf: anchorId`).
- No → xoa pending, tra person ve pool.
- Pending khong draggable, khong vao engine, khong persist.
- **Khong co popup modal** — inline pending tren card, user van thao tac cac node khac.
- Khi drop 2 the → ghi **1 node moi** (pending) ben canh anchor, khong thay the anchor.

### 3 Rules chat
- **Rule 1:** Xoa nhanh → pending trong nhanh tra pool (tu dong qua cascade `parentSlotId` + `removeWithWorkflow`). Pending ngoai nhanh giu nguyen. 0 dong code them.
- **Rule 2:** Drop C len anchor A dang pending B → block, phai × B truoc. ~10 dong trong `handleDrop`. Khong alert popup — card pending da glow vang, user nhin thay ngay.
- **Rule 3:** Pending → khoa save/engine/export + **banner warning** "⚠ N the cho xac nhan vo/chong" (~30 dong, wire `cases/form.html`).
  - Lop sap xep diagram (keo tha, them con, xoa node) van cho phep khi pending.
  - Lop workflow (luu, chay engine, export, commit stage) bi khoa.

### Auto-layout can doi
- **Khong free positioning** — pure auto-layout, user khong keo doi vi tri node (chi keo tha de gan person).
- Moi tang: dem so "unit" (1 person = 1 unit, 1 spouse pair = 1 unit rong hon).
- Dynamic card width theo `availableWidth / unitCount` voi min/max bound.
- Max card = current size, **tang font size**, **bo label** "Cha ruot, Me ruot, Chu dat" (so do da the hien quan he).
- Card chi chua: Ten, Ngay sinh–mat, nut ×, nut ★, o %.
- Min card ~30% nho hon max, khong bien dang field.
- Khoang cach deu, can giua tung tang.
- Spouse pair = 1 unit rong (2 card + connector).
- Overflow → **horizontal scroll** (1 hang, khong wrap).

### Layout pool/diagram
- Giam width pool, tang width diagram trong `cases/form.html`.

## Phan Phase thuc hien

### Phase 1 — Orthogonal connectors (core visual)
- Thay `buildSoftCurve` → `buildOrthogonalPath`: vertical drop → horizontal branch → vertical to children.
- T-junction deterministic nho auto-layout.
- Spouse pair: duong ngang lien + ♡.
- Giu `nodeRefs` + `getRelativeBox` + `ResizeObserver`.
- File: `ReactFlowApp.jsx`

### Phase 2 — An Luong tai san
- Xoa `flowPaths.map(...)` khoi SVG render.
- Giu `buildFlowEdges` trong `diagram_edges.js` (engine noi bo).
- Share % van hien text tren card.
- File: `ReactFlowApp.jsx`

### Phase 3 — Auto-layout can doi
- Layout calc: dem unit/tang, dynamic card width (min ~30% nho hon max, max = current).
- Spouse pair = 1 unit rong.
- Gap deu, can giua.
- Overflow → horizontal scroll (1 hang, khong wrap).
- Khong free positioning.
- File: `ReactFlowApp.jsx`

### Phase 4 — Card toi gian
- Bo label "Cha ruot, Me ruot, Chu dat, Vo/Chong" (so do the hien san).
- Tang font size (ten, ngay sinh/mat).
- Card chi chua: Ten, Ngay sinh–mat, ×, ★, o %.
- Min card khong bien dang field.
- File: `ReactFlowApp.jsx`

### Phase 5 — Inline pending spouse
- Drop de card co nguoi → node `kind: "pendingSpouse"`, `parentSlotId: anchorId`.
- Card pending: glow vang + banner "Chen vo/chong?" + [Yes][No].
- Yes → materialize spouse (`relationType: "spouse"`, `spouseOf: anchorId`).
- No → xoa pending, tra person ve pool.
- Pending khong draggable, khong vao engine (`buildEngineInput` filter `kind === "person"`), khong persist (`buildParticipantsPayload` filter `kind === "person"`).
- File: `ReactFlowApp.jsx`

### Phase 6 — 3 Rules chat + warning banner
- Rule 1: tu dong qua cascade (0 dong).
- Rule 2: block drop tren pending anchor (~10 dong `handleDrop`).
- Rule 3: khoa workflow khi pending + banner warning (~30 dong, wire `cases/form.html`).
  - `__DIAGRAM_API__.pendingCount()` expose so luong pending.
  - `cases/form.html` lang nghe `onFamilyTreeUpdate` → render banner + disable nut Save/Export.
- File: `ReactFlowApp.jsx`, `cases/form.html`

### Phase 7 — Spouse dynamic data model
- `spouseOf: nodeId` len node spouse dong (khong chi fixed owner→spouse).
- `buildKinshipEdges` nhan spouse pair dong → children junction.
- Backward compat: node `spouse` cu → migrate `spouseOf: "owner"`.
- File: `ReactFlowApp.jsx`, `diagram_edges.js`

### Phase 8 — Layout pool/diagram ratio
- Giam width pool, tang width diagram trong `cases/form.html`.
- File: `cases/form.html`

## Files du kien

| File | Phase |
|------|-------|
| `frontend/static/ReactFlowApp.jsx` | 1,2,3,4,5,6,7 |
| `frontend/static/diagram_edges.js` | 7 |
| `frontend/templates/cases/form.html` | 6, 8 |
| `docs/plans/diagram_visual_v2.md` | doc |

## OUT-OF-SCOPE (phase rieng)

- **Refuse checkbox**: con song + tu choi nhan → exclude khoi flow, van hien so do + Word.
  - Can plan rieng `diagram_refuse_feature.md` vi dung `inheritance_engine.js`, `buildEngineInput`, Word export.
  - Yeu cau: tick vao → nguoi do con song nhung tu choi nhan, coi nhu khong co trong dong chay, nhung van hien trong so do va van ban Word.

## Rui ro

- `drawConnectors` do bounding box → phai giu khi doi path builder.
- Spouse dynamic → backward compat voi engine state da luu.
- Rule 3 wire ngoai ReactFlowApp → dam bao event fire.
- Auto-layout dynamic width → connector phai ve lai dung sau resize.

## Thu tu implement de xuat

1 → 2 → 4 → 3 → 7 → 5 → 6 → 8

(Ly do: Phase 4 card toi gian truoc de Phase 3 auto-layout co card size cu the; Phase 7 data model truoc Phase 5 pending de pending materialize vao model dung.)
