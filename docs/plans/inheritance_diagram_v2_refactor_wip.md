# Refactor sơ đồ thừa kế V2 — WIP (Work In Progress)

> **Trạng thái:** Đang ở Phase 2 Claudex round 2 — final plan đã được Codex debate xong, **chưa được user duyệt implement**.
> Cập nhật: 28/04/2026.
> File này phục vụ resume cho agent/session kế tiếp.

### Bản ghi đầy đủ bài toán mẫu user chốt ngày 28/04/2026

#### Đề bài
X và Y là vợ chồng, có tài sản chung là 01 thửa đất.

- X chết năm 2011, Y chết năm 2015. X và Y có 03 người con chung là M, N, O.
- Cha mẹ của X là A (chết năm 1995) và B (chết năm 1996).
- Cha mẹ của Y là C (chết năm 1997) và D (chết năm 2016). C và D có 02 người con là Y và Z.
- Z chết năm 2015, có 02 người con là Z2 và Z3.

#### Lời giải chuẩn

1. Thửa đất là tài sản chung của vợ chồng X và Y nên tách trước:
   - Phần của X: `1/2` thửa đất
   - Phần của Y: `1/2` thửa đất

2. X chết năm 2011:
   - A, B đều chết trước X nên không thuộc diện hưởng di sản của X.
   - Hàng thừa kế thứ nhất của X gồm: `Y, M, N, O` (4 người).
   - Di sản của X là `1/2`, chia đều cho 4 người:
     - `1/2 ÷ 4 = 1/8`
   - Sau khi X chết:
     - `Y = 1/2 + 1/8 = 5/8`
     - `M = 1/8`
     - `N = 1/8`
     - `O = 1/8`

3. Y chết năm 2015:
   - C chết trước Y nên không hưởng.
   - D chết năm 2016, tức là chết sau Y, nên được hưởng thừa kế của Y.
   - Hàng thừa kế thứ nhất của Y gồm: `D, M, N, O` (4 người).
   - Di sản của Y là `5/8`, chia đều:
     - `5/8 ÷ 4 = 5/32`
   - Sau khi Y chết:
     - `M = 1/8 + 5/32 = 9/32`
     - `N = 9/32`
     - `O = 9/32`
     - `D = 5/32`

4. D chết năm 2016:
   - C chết trước D nên không hưởng.
   - Hai người con của D là `Y` và `Z` đều chết trước D nên áp dụng thừa kế thế vị.
   - Nếu Y và Z còn sống thì mỗi nhánh được:
     - `5/32 ÷ 2 = 5/64`
   - Nhánh Y:
     - `M, N, O` thế vị phần của Y
     - `5/64 ÷ 3 = 5/192`
     - Mỗi người `M, N, O` được thêm `5/192`
   - Nhánh Z:
     - `Z2, Z3` thế vị phần của Z
     - `5/64 ÷ 2 = 5/128`
     - Mỗi người `Z2, Z3` được `5/128`

5. Kết quả cuối cùng:
   - `M = 1/8 + 5/32 + 5/192 = 59/192`
   - `N = 59/192`
   - `O = 59/192`
   - `Z2 = 5/128`
   - `Z3 = 5/128`

#### Ý nghĩa với engine diagram
- Đây là fixture bắt buộc phải pass ở cả 3 lớp:
  - `timeline nhiều decedent`
  - `tài sản chung vợ chồng`
  - `thế vị nhiều cấp`
- Đồng thời đây cũng là case xác nhận nhánh ngoài tree:
  - `D -> Z -> Z2/Z3` không nằm trọn trong 3 tầng gốc quanh X
  - engine phải support branch ngoài tree và vẫn giữ đúng kết quả phân chia.

---

## 0. Cách resume cho agent kế tiếp

Khi quay lại task này, agent **PHẢI**:

1. Đọc toàn bộ file này (context + decisions + final plan).
2. Đọc `docs/plans/inheritance_diagram.md` (tài liệu nghiệp vụ gốc) để hiểu nguyên lý dòng chảy.
3. Hỏi user một trong 3 hành động:
   - `[y]` duyệt implement → chạy `python tools/codex_relay.py approve --run-dir runtime/codex_relay/20260428-162928-...` rồi `execute --with-review`. **LƯU Ý:** Run dir gốc đã bị xóa (gitignored), phải re-draft lại bằng task file ở mục 9 dưới đây.
   - `[g]` góp ý thêm → re-draft với feedback mới
   - `[n]` huỷ
4. Nếu user muốn re-draft hoặc bắt đầu lại Claudex → dùng task content ở Mục 9 dưới đây ghi lại làm `runtime/codex_relay_task_tmp.md` rồi chạy `python tools/codex_relay.py draft --task runtime/codex_relay_task_tmp.md`.
5. **TUYỆT ĐỐI KHÔNG** implement code trước khi có lệnh `y` từ user — đây là invariant Claudex.

---

## 1. Bối cảnh task

Sơ đồ thừa kế trong `frontend/templates/cases/form.html` + `frontend/static/ReactFlowApp.jsx` hiện tại có 3 bug nghiệp vụ + 1 thiếu sót lớn:

**Bug user phát hiện:**
1. Ô anh/chị/em chủ đất hiển thị nhưng không cho drop card vào.
2. Cha/mẹ chết trước/chết sau chủ đất không được phân biệt — cả 2 đều hiển thị label "Nút quan hệ, không tham gia chia suất" (sai luật).
3. Nút `★` gán chủ đất là dead handler — click không có hiệu ứng nghiệp vụ thật, chỉ toggle visual.

**Thiếu sót lớn:**
- Tầng 1 (CHA MẸ) đang được code coi như "nút trang trí", không tham gia chia suất.
- Theo Bộ luật Dân sự, cha/mẹ là hàng thừa kế thứ nhất ngang với vợ/chồng/con. Quyết định ai nhận = so sánh ngày mất.

---

## 2. Mục tiêu refactor

Tầng cha mẹ trở thành tầng thừa kế đầy đủ. Mỗi người chết = 1 "class" phân phối. Class lồng nhau theo logic **dòng chảy đệ quy**:

> **Nguyên lý chuẩn (do user chốt):**
> "Nước chảy vào ai → người đó chết → mở vòng lặp thừa kế mới với CÙNG quy tắc."

- Mỗi vòng lặp giống nhau về cấu trúc: 1 decedent → hàng thừa kế thứ nhất (cha/mẹ/vợ-chồng/con) → áp dụng chết trước/chết sau/thế vị.
- Số cấp đệ quy không giới hạn cứng (bài tập ví dụ có 3 cấp X→Y→D, có thể sâu hơn).

Đồng thời:
- Kích hoạt nút `★` gán chủ đất hoạt động thật (rebind topology, sync hidden input).
- Hiển thị mũi tên "nước chảy" phân biệt với mũi tên huyết thống (style + hướng).
- Hỗ trợ tài sản chung vợ chồng (mặc định 50/50).
- Hỗ trợ thế vị (representation) cho descendant chết trước decedent.

---

## 3. 4 Rule nghiệp vụ bắt buộc

### Rule 1 — Thừa kế thế vị (representation)
- Heir là **CON/CHÁU** + chết **TRƯỚC** decedent → con của heir thay thế trực tiếp với cùng phần đáng lẽ heir nhận.
- KHÔNG áp dụng cho cha/mẹ (cha/mẹ chết trước → mất quyền, không có "ông bà" thế vị trong phase này).
- KHÁC với "nước chảy" (heir chết SAU decedent → spawn class đệ quy).

### Rule 2 — Tài sản chung vợ chồng
- Nếu thửa đất là tài sản chung X+Y → tách 1/2 cho X, 1/2 cho Y trước khi chia thừa kế.
- Cần cơ chế khai báo "tài sản chung với [vợ/chồng]" + tỷ lệ (mặc định 50/50).
- Khi 1 trong 2 chết, di sản = phần gốc + phần đã nhận trước đó.

### Rule 3 — Multi-decedent timeline
- Engine xử lý theo thứ tự thời gian chết. Mỗi decedent chết → tổng tài sản hiện có của họ là di sản chia.
- Ví dụ: Y có 1/2 gốc + 1/8 nhận từ X = 5/8 khi Y chết → 5/8 này được chia.
- KHÔNG giới hạn 1 chủ đất X. Engine phải process MỌI node có `death` theo timeline.
- Same-day death: snapshot rule — không inherit chéo, warning `simultaneous_death_snapshot`.

### Rule 4 — UI spawn nhánh ngoài (cạnh tree)
- Khi sub-decedent có heir KHÔNG thuộc tree gốc (vd: mẹ vợ D có anh chị em vợ Z không có slot trong 3 tầng quanh chủ đất X) → SPAWN node ghost CẠNH tree chính (không phải tier0/1/2).
- Mũi tên từ sub-decedent (D) **hướng XUỐNG** node ghost (Z) — phân biệt với mũi tên chủ đất X **hướng LÊN** cha/mẹ X (tầng 1).
- Logic hướng mũi tên = chiều thế hệ. X → cha mẹ = lên. D → con D = xuống.
- Ghost cho phép drop card từ pool → trở thành person thực, tham gia chia.
- Nếu Z chết trước D → spawn tiếp cháu Z2/Z3 (thế vị), tiếp tục cạnh tree.

---

## 4. Bài tập ground truth (test fixture bắt buộc engine pass)

### Đề bài
X và Y là vợ chồng, có tài sản chung là 01 thửa đất.
- X chết 2011, Y chết 2015. X+Y có 3 con chung: M, N, O.
- Cha mẹ X: A (chết 1995), B (chết 1996).
- Cha mẹ Y: C (chết 1997), D (chết 2016). C+D có 2 con: Y và Z.
- Z chết 2015, có 2 con: Z2 và Z3.

### Lời giải đúng (kết quả cuối cùng)
- M = **59/192**
- N = **59/192**
- O = **59/192**
- Z2 = **5/128**
- Z3 = **5/128**

### Trace từng bước
1. **Tài sản chung X+Y** → X có 1/2, Y có 1/2.

2. **X chết 2011:** A,B đã chết trước → loại. Hàng 1 X = {Y, M, N, O} = 4 người. Mỗi người 1/2 ÷ 4 = 1/8.
   → Y có 1/2 + 1/8 = 5/8. M=N=O = 1/8.

3. **Y chết 2015:** C đã chết trước → loại. D chết SAU Y → vào hàng 1. Hàng 1 Y = {D, M, N, O} = 4 người. Mỗi người 5/8 ÷ 4 = 5/32.
   → M=N=O = 1/8 + 5/32 = 9/32. D = 5/32.

4. **D chết 2016:** C đã chết trước → loại. 2 con D = {Y, Z} đều chết TRƯỚC D → **THẾ VỊ**:
   - Phần Y (5/32 ÷ 2 = 5/64) → M, N, O thế vị, mỗi người 5/64 ÷ 3 = **5/192**.
   - Phần Z (5/64) → Z2, Z3 thế vị, mỗi người 5/64 ÷ 2 = **5/128**.

5. **Tổng kết:**
   - M = 1/8 + 5/32 + 5/192 = 24/192 + 30/192 + 5/192 = **59/192**.
   - N = O = 59/192.
   - Z2 = Z3 = 5/128.

### Ý nghĩa fixture
- Cover đệ quy 3 cấp (X → Y → D).
- Cover thế vị nhiều cấp (D có 2 con đều chết trước D, 1 trong 2 con cũng có cháu thế vị).
- Cover tài sản chung vợ chồng (1/2).
- Cover nhánh ngoài tree (Z, Z2, Z3 không thuộc tree gốc 3 tầng quanh X).
- Nguyên lý mỗi vòng lặp giống nhau — engine pass bài này thì xử lý được mọi cấp sâu hơn.

---

## 5. Decisions đã chốt với user (qua Q&A nhiều vòng)

| Câu hỏi | Quyết định |
|---|---|
| Anh chị em chủ đất có drop được? | Có. Khi cha/mẹ chết SAU chủ đất → cha/mẹ là sub-decedent → con của cha/mẹ (= anh chị em chủ đất) là heir của sub-class → drop được. |
| Cha/mẹ chết trước chủ đất → ô như thế nào? | Vẫn hiện ô, `willReceive=false`, `disabledReason="Đã mất trước chủ đất — không nhận"`, KHÔNG spawn ghost addSibling cho nhánh đó. |
| Bỏ label "không tham gia chia suất"? | Có, xóa hoàn toàn khỏi codebase. |
| 2 chủ đất là anh chị em ruột chia chung bố mẹ? | Defer phase sau. Phase này chỉ 1 chủ đất chính. |
| Class A render thế nào trong tree? | Không tách subgraph riêng. Tree giữ 3 tầng vật lý cũ — vợ A vẫn là node "mẹ X". Class chỉ là khái niệm logic ẩn. Logic hiển thị bằng mũi tên flow. |
| TH1 hàng 2 trực tiếp (anh chị em ruột X thừa kế khi hàng 1 chết hết)? | Defer phase sau. |
| Tài sản chung vợ chồng? | Phase này hỗ trợ. Toggle UI + tỷ lệ mặc định 50/50. Persist trong `__FAMILY_TREE_STATE__` runtime + warning về persistence (không lưu server). |
| Slot dynamic cho nhánh ngoài tree (Z, Z2, Z3)? | Spawn ghost CẠNH tree chính (không phải tier0/1/2). Mũi tên từ sub-decedent xuống — phân biệt với mũi tên chủ đất hướng lên cha/mẹ. |
| Multi-decedent timeline? | Có. Engine process mọi node có `death` theo thứ tự ngày chết tăng dần. |
| Same-day death? | Snapshot rule — không inherit chéo, warning `simultaneous_death_snapshot`. |
| Recursion depth cap? | `MAX_DEPTH = 12` là **technical guard mềm**, chạm guard → warning, không phải business cap. |
| Promote owner từ child/sibling thiếu metadata? | Defer phase sau. Chặn với warning, không đoán quan hệ. |
| Reuse vs duplicate khi 1 person ở tree gốc + heir của branch ngoài? | **Reuse** node ở tree gốc, cộng thêm `flowFrom`. Không tạo proxy. |

---

## 6. Defer items (backlog phase sau)

Sau khi phase này done, ghi vào `CLAUDE.md` mục "Lịch sử chức năng":
- Hàng thừa kế thứ 2 thuần (anh chị em ruột X thừa kế trực tiếp khi toàn bộ hàng 1 X chết trước X).
- 2 chủ đất là anh/chị/em ruột chia chung bố mẹ.
- Tầng ông bà thuần (chỉ active khi recursion thật sự cần — vd: D có cha/mẹ chết sau D).
- Promote owner từ child/sibling khi thiếu metadata quan hệ.
- Con riêng/con nuôi/di chúc.
- Bug medium từ reviewer cũ: import Excel chỉ hiện "Làm mới"; `commitAssign` half-state race.
- Persist `estateConfig` lên backend (hiện chỉ frontend snapshot).

---

## 7. Critical files (cần sửa)

| File | Vai trò |
|---|---|
| `frontend/static/ReactFlowApp.jsx` | Chính. Refactor `calculateInheritance` thành engine timeline đệ quy. Thêm helper deterministic. |
| `frontend/templates/cases/form.html` | Sync hidden input `case-nguoi-chet`, mở rộng `__FAMILY_TREE_STATE__`, listener `case:owner-changed`. |
| `tests/diagram_inheritance_engine.test.mjs` | **Mới**. Harness deterministic assert fixture X/Y/D/Z và các case biên. |
| `tests/fixtures/diagram_inheritance_cases.json` | **Mới**. Fixture data các case. |
| `docs/plans/inheritance_diagram.md` | Update với rule mới (canonical graph, same-day, owner-switch invariant, external-branch reuse, depth guard, estateConfig persistence). |

**KHÔNG sửa:**
- `routers/cases.py`, `routers/customers.py`, `models.py`, `tasks.py`.
- Schema DB, contract API, format submit.
- Layout vật lý 3 tầng (chỉ thêm vùng external branches dưới tree).
- `manual` share mode (chỉ refactor auto mode).

---

## 8. Reuse — đã có sẵn, không tạo mới

- `Customer.ngay_chet` (`models.py:16`) + property `con_song` (`models.py:32`)
- Field `death` đã serialize qua `to_customer_json()` (`routers/customers.py:96`) và populate vào `window.__CUSTOMER_REGISTRY__`
- `survivesAt(personDeathDate, eventDeathDate)` (`ReactFlowApp.jsx:526–530`)
- `validateAssignment` + `handleDrop` + `bridgeWorkflowUpdates` (`ReactFlowApp.jsx:215, 728, 967`)
- `appendBracketConnector` (`ReactFlowApp.jsx:882–918`) — giữ cho bloodline; thêm `appendFlowConnector` mới cho flow

---

## 9. Task content gốc (để re-draft Claudex nếu cần)

Khi cần re-draft, ghi nội dung dưới đây vào `runtime/codex_relay_task_tmp.md` rồi chạy:

```bash
python tools/codex_relay.py draft --task runtime/codex_relay_task_tmp.md
```

```
Lam gi: Refactor logic tầng cha mẹ trong sơ đồ thừa kế (cases/diagram) thành tầng thừa kế đầy đủ với class flow đệ quy theo timeline ngày chết, hỗ trợ thế vị nhiều cấp, tài sản chung vợ chồng, kích hoạt nút ★ gán chủ đất, hiển thị mũi tên nước chảy phân biệt với mũi tên huyết thống. Toàn bộ thay đổi trong frontend, không đổi schema DB hay contract API.

Sua phan nao:
- frontend/static/ReactFlowApp.jsx (chính): refactor calculateInheritance thành engine timeline với helper thuần
- frontend/templates/cases/form.html: sync hidden input case-nguoi-chet, mở rộng __FAMILY_TREE_STATE__
- tests/diagram_inheritance_engine.test.mjs (mới): harness deterministic
- tests/fixtures/diagram_inheritance_cases.json (mới): fixture data
- docs/plans/inheritance_diagram.md: update tài liệu nghiệp vụ

Pham vi:
- Chỉ frontend diagram + host + test/doc.
- KHÔNG đổi schema DB, contract API, format submit.
- Layout vật lý 3 tầng giữ nguyên; branch ngoài tree là vùng render bổ sung dưới.
- manual share mode giữ nguyên; engine mới chỉ áp auto mode.
- Defer: hàng 2 thuần, promote child/sibling thiếu metadata, ông bà thuần, 2 chủ đất anh chị em chung bố mẹ, con riêng/nuôi/di chúc, bug commitAssign half-state, bug import Excel.

Muc tieu:
1. Engine xử lý timeline nhiều decedent, không neo cứng 1 owner gốc; mỗi người có death = 1 decedent class.
2. Same-day death: snapshot rule, không inherit chéo, warning simultaneous_death_snapshot.
3. Hàng thừa kế thứ nhất chuẩn: cha/mẹ/vợ-chồng/con (theo canonical graph từ __CUSTOMER_REGISTRY__).
4. Cha/mẹ chết trước decedent: ô vẫn hiện, willReceive=false, disabledReason đúng ngữ cảnh, không spawn ghost.
5. Cha/mẹ chết sau decedent: nhận trong class hiện tại + giữ % để hiển thị + estate chia tiếp ở class sau.
6. Thế vị nhiều cấp cho descendant chết trước decedent (KHÔNG áp dụng cha/mẹ).
7. Tài sản chung vợ chồng: toggle + tỷ lệ default 50/50 + persist trong frontend snapshot + warning persistence.
8. Recursion guard: visited theo (decedentId, heirId, mode) + MAX_DEPTH=12 mềm + warning khi chạm.
9. Person reuse: 1 person.id chỉ có 1 node active toàn diagram; branch ngoài tree reuse node gốc với nhiều flowFrom.
10. ★ đổi owner: canPromoteToOwner check, source of truth là __CUSTOMER_REGISTRY__, invariant 1 owner duy nhất.
11. Flow edge riêng (vàng đậm) vs bloodline edge (xám mờ); helper appendFlowConnector mới hỗ trợ hướng lên/xuống.
12. Listener case:owner-changed sync hidden input + flip __CUSTOMER_WORKFLOW__.isOwner.

[FIXTURE BẮT BUỘC PASS]
Đề: X+Y vợ chồng tài sản chung. X chết 2011, Y chết 2015, có 3 con M/N/O. Cha mẹ X: A(1995), B(1996). Cha mẹ Y: C(1997), D(2016). C+D có 2 con Y và Z. Z chết 2015 có 2 con Z2, Z3.

Kết quả đúng:
- M = N = O = 59/192
- Z2 = Z3 = 5/128

Trace: tài sản chung → X chết 2011 chia hàng 1 X (A,B đã chết, còn Y/M/N/O) → Y chết 2015 chia hàng 1 Y (C đã chết, còn D/M/N/O) → D chết 2016 (Y,Z đều chết trước → thế vị: M/N/O thế vị Y, Z2/Z3 thế vị Z).

[NGUYÊN LÝ ĐỆ QUY CHUẨN — user chốt]
"Nước chảy vào ai → người đó chết → mở vòng lặp thừa kế mới với CÙNG quy tắc."
Số cấp không giới hạn cứng; bài fixture có 3 cấp, có thể sâu hơn.

[UI nhánh ngoài tree — user chốt]
Spawn ghost CẠNH tree chính (không phải tier0/1/2). Mũi tên từ sub-decedent hướng XUỐNG, phân biệt với mũi tên chủ đất hướng LÊN cha/mẹ.

[Code style]
- Tối giản, không over-engineer.
- Comment tiếng Việt ở các điểm phức tạp (recursion, cycle-breaker, remap matrix).
- Reuse helper sẵn có (survivesAt, validateAssignment, bridgeWorkflowUpdates).
```

---

## 10. Final Plan đã debate (round 2 Claudex — chờ user duyệt)

> Source: Codex relay round 2 (28/04/2026). Run dir gốc đã bị xóa khi gitignore — nội dung paste lại đầy đủ ở đây.

### Goal
Refactor engine sơ đồ thừa kế ở `cases/diagram` để tầng cha mẹ trở thành hàng thừa kế đầy đủ, xử lý nhiều người chết theo timeline bằng quy tắc "nước chảy", hỗ trợ thế vị nhiều cấp cho descendant, hỗ trợ tài sản chung vợ chồng, kích hoạt được luồng UI `★` đổi chủ đất, và vẽ riêng `flow-edge` cho dòng phân phối thừa kế; toàn bộ thay đổi giữ trong frontend, không đổi schema DB hay contract API.

### Final Steps

1. **Chốt invariant dữ liệu và tách bề mặt testable cho engine** trong `ReactFlowApp.jsx` và thêm harness deterministic ở `tests/diagram_inheritance_engine.test.mjs` với fixture `tests/fixtures/diagram_inheritance_cases.json`. Engine tính theo `person.id` canonical, không theo node id; node ngoài tree chỉ là proxy hiển thị. Helper thuần: `buildCanonicalPersonGraph`, `collectTimelineDecedents`, `resolveEstatePools`, `resolveFirstLineHeirs`, `resolveRepresentationChain`, `distributeEstate`, `runInheritanceCase`. Test bắt buộc cover: fixture X/Y/D/Z → 59/192, 5/128, case cha/mẹ chết trước/sau, same-day snapshot, thế vị nhiều cấp, duplicate-assignment, tài sản chung 50/50.

2. **Refactor engine chia thừa kế** trong `ReactFlowApp.jsx`. Đổi `father/mother/spouse_father/spouse_mother` → `allowsShare: true`, xóa hẳn chuỗi `"Nút quan hệ, không tham gia chia suất"`. `calculateInheritance(models, shareMode)` giữ entrypoint nhưng chỉ làm adapter; `manual` mode giữ nguyên hành vi cũ. Mỗi người có `death` là 1 decedent; timeline sort theo ngày chết tăng dần. Same-day: snapshot rule — mỗi decedent chỉ chia `baseAssetShare + receivedBeforeThisDay`, không inherit chéo trong cùng ngày, commit allocation sau khi xử lý xong cả nhóm, phát warning `simultaneous_death_snapshot`.

3. **Đặc tả rõ hàng thừa kế, thế vị, share hiển thị** trong `ReactFlowApp.jsx`. `resolveFirstLineHeirs` chỉ lấy cha/mẹ/vợ-chồng/con từ canonical graph; source of truth là `__CUSTOMER_REGISTRY__` kết hợp assignment hiện tại, không suy ngược từ vị trí render. Cha/mẹ chết trước decedent → `willReceive=false`, có `disabledReason` đúng ngữ cảnh, không spawn ghost. Descendant chết trước decedent → chạy `resolveRepresentationChain` đệ quy nhiều cấp; cha/mẹ không có thế vị phase này. Node trung gian đã chết nhưng từng nhận suất vẫn hiển thị `sharePercent/effectiveEstateShare` để truy vết, đồng thời có `flowFrom` làm điểm phát "nước chảy".

4. **Chốt guard recursion và policy duplicate/external branch** trong `ReactFlowApp.jsx`. `visited` theo khóa logic `(decedentId, heirId, mode)` và `MAX_DEPTH = 12` là guard kỹ thuật mềm; chạm guard → warning, không phải business limit 6 cấp. `validateAssignment` cấm 2 node sống cùng `person.id` trên toàn diagram. **Người đã ở tree gốc + heir của branch ngoài tree → KHÔNG tạo node thứ 2; UI reuse chính node đó và cộng thêm `flowFrom`.** Chỉ khi người đó chưa được assign mới materialize node `outsideTree`.

5. **Thiết kế riêng lớp branch ngoài tree và connector cho flow** trong `ReactFlowApp.jsx`. `onGhostExpand` và `renderExternalBranches()` render branch ngoài tree ở vùng dưới cụm 3 tầng chính, theo group decedent, cột dọc, dùng scroll container hiện có. **KHÔNG ép `appendBracketConnector` xử lý flow.** Giữ `appendBracketConnector` cho bloodline; thêm helper mới `appendFlowConnector({ fromRect, toRect, direction, variant })` cho `flow-edge`, hỗ trợ hướng lên/xuống. `drawConnectors()` chạy 2 pass riêng: bloodline xám/mờ và flow vàng đậm có arrowhead.

6. **Kích hoạt `★` đổi chủ đất bằng thuật toán rebind có invariant rõ** trong `ReactFlowApp.jsx`. Thêm `canPromoteToOwner(node)`. Phase này hỗ trợ chắc chắn cho `self/spouse/father/mother/spouse_father/spouse_mother`; `child/sibling/external` chỉ promote nếu registry đã đủ cha/mẹ/vợ-chồng/con để rebuild, ngược lại warning và không mutate. Source of truth để rebind là canonical graph từ registry, không relink theo vị trí slot. **Invariant sau commit**: đúng 1 owner, `meta.ownerId` khớp, tier cha/mẹ owner mới là slot nhận drop, node cũ demote/clear deterministically, engine tính lại ngay.

7. **Đồng bộ host form và chặn legacy path ghi đè diagram state** trong `form.html`. Mở rộng `__FAMILY_TREE_STATE__` giữ `meta.ownerId/estateConfig`, `warnings`, `shareMode`, `updatedAt`; restore trước khi mount React. Listener `case:owner-changed` cập nhật `#case-nguoi-chet` và flip `__CUSTOMER_WORKFLOW__[].isOwner`. **Listener `onFamilyTreeUpdate` idempotent + guard để legacy `recalcShares` không ghi đè share/warning vừa phát từ React diagram trong cùng tick**; host chỉ mirror, không tự tính lại.

8. **Đưa tài sản chung thành first-class frontend state có cảnh báo rõ** trong `ReactFlowApp.jsx`, `form.html`, và `docs/plans/`. Toolbar diagram thêm toggle `Tài sản chung`, chọn co-owner từ spouse hợp lệ, nhập tỷ lệ mặc định 50/50, tổng phải 100. `resolveEstatePools` inject `baseAssetShare` cho owner/co-owner trước timeline; người chết → estate = `baseAssetShare + receivedSoFar`. **Vì phase này không đổi backend/API, `estateConfig` persist như phần của frontend draft snapshot và UI hiện warning rõ rằng cấu hình này chỉ được đảm bảo khi mở lại cùng snapshot/draft frontend, tránh silent mismatch.**

9. **Cập nhật tài liệu repo đúng chuẩn** bằng update/tạo plan trong `docs/plans/` và thêm index nếu cần. Tài liệu chốt: canonical graph keyed by `person.id`, same-day snapshot rule, owner-switch invariant, external-branch reuse policy, soft depth guard 12, limitation/persistence của `estateConfig`. `CLAUDE.md` chỉ giữ backlog defer sau khi tài liệu chính cập nhật.

### Constraints
- Chỉ sửa frontend diagram/host và tài liệu: `ReactFlowApp.jsx`, `form.html`; test/doc file được phép thêm.
- Không sửa `routers/`, `models.py`, `tasks.py`; không đổi schema DB, contract API, format submit.
- Giữ layout vật lý 3 tầng chính; branch ngoài tree là vùng render bổ sung dưới tree chính.
- `manual` share mode giữ nguyên; engine mới chỉ áp auto mode.
- Same-day death luôn theo snapshot đầu ngày, auto-allocate kèm warning, không inherit chéo.
- Không 2 node active cùng `person.id`; branch ngoài tree reuse node thay vì duplicate.
- Đệ quy không dùng business cap 6 cấp; `visited` + `MAX_DEPTH=12` là guard kỹ thuật, warning khi chạm guard.
- Defer: hàng 2 thuần, promote child/sibling thiếu metadata, ông bà thuần, 2 chủ đất anh chị em, con riêng/nuôi/di chúc, bug `commitAssign` half-state, bug import Excel.

### Acceptance
- 4 ô tầng cha mẹ đều `allowsShare: true`; không còn chuỗi `"Nút quan hệ, không tham gia chia suất"`.
- **Harness deterministic pass fixture bắt buộc**: `M=59/192, N=59/192, O=59/192, Z2=5/128, Z3=5/128`.
- Deterministic test pass: cha/mẹ chết trước, cha/mẹ chết sau, same-day snapshot, representation nhiều cấp, tài sản chung, duplicate-person policy.
- Same-day death cho kết quả ổn định theo snapshot rule và phát warning, không inherit chéo.
- External branch render riêng dưới tree chính, không hard max, có scroll, `flow-edge` đúng hướng lên/xuống độc lập với `bloodline-edge`.
- `★` đổi owner ở node đủ điều kiện: chỉ còn 1 owner, owner cũ demote đúng, tier cha/mẹ owner mới nhận drop, `case:owner-changed` cập nhật hidden input và workflow.
- Người thừa kế đã có node ở tree gốc → engine/UI reuse node với nhiều `flowFrom`, không duplicate.
- Khi bật tài sản chung, `meta.estateConfig/ownerId` restore từ frontend snapshot; UI warning rõ về giới hạn persistence phase này.
- `docs/plans/` cập nhật phản ánh design mới và backlog defer.

---

## 11. Tooling fix kèm theo (đã commit cùng plan này)

`tools/codex_relay.py` đã được fix 2 bug:
1. `_read_task` mất nội dung multi-line vì regex chỉ match từng dòng đơn → thêm field `_raw_content` lưu nguyên file.
2. `_run_codex` truyền prompt qua CLI arg vượt giới hạn 8KB cmd.exe trên Windows → đổi sang stdin (`-` placeholder + `subprocess.input=prompt`).

Sau fix, Codex CLI nhận được task content đầy đủ kể cả khi task file dài (như task này có ~9KB).

---

## 12. Trạng thái hiện tại

- ✅ Phase 1 Claudex: task file đã viết đầy đủ với 4 rule + fixture
- ✅ Phase 2 Claudex round 1: planner/critic/final_plan đầu (run dir `20260428-134447-...`)
- ✅ User góp ý `g`: thêm bài tập ground truth + nguyên lý đệ quy chuẩn + UI nhánh ngoài
- ✅ Phase 2 Claudex round 2: planner/critic/final_plan refined (run dir `20260428-162928-...`)
- ⏸ **Đang chờ user duyệt `[y]` → Phase 3 implement**

Khi resume:
- Nếu user chốt `y` → re-create task file từ Mục 9, chạy `draft` lại (vì run dir đã bị xóa), rồi `approve` + `execute --with-review`
- Nếu user góp ý thêm → append note + `draft` lại
- Nếu hủy → kết thúc, có thể xóa file này
