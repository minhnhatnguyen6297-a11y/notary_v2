# Inheritance Engine V2 — Technical contract

Status: current
Verification evidence: `../research/`

If this contract conflicts with business rules, `../spec.md` wins.
UI/UX is governed by `../ux.md`; verification scenarios and evidence live in
`../research/case-catalog.md`, `../research/validation-matrix.md`, and
`../research/validation-issues.md`.

## 1. Mục tiêu và nguyên nhân phải refactor

Mục tiêu cuối là một engine thừa kế duy nhất, xác định đúng quan hệ gia đình, chia chính xác bằng
phân số, giải thích được từng nguồn và lưu/reload/xuất Word cùng một kết quả.

Các lỗi gốc đã được audit và user duyệt:

- Engine hiện tại làm phẳng toàn bộ hậu duệ trong nhánh thế vị rồi chia đều, nên sai khi nhánh có
  nhiều tầng hoặc số hậu duệ không đều.
- React tự sinh node bằng heuristic `có ngày chết`, làm sinh bố mẹ/vợ chồng sai và thiếu con cần
  cho nhánh thế vị.
- Quan hệ cha mẹ/con bị suy từ owner, spouse hoặc node đầu tiên; người có thể bị gắn nhầm nhánh.
- Di sản không có người nhận hợp lệ bị đưa về `0`, làm tổng tài sản biến mất.
- Người còn sống tắt `Nhận` nhưng có sở hữu gốc đang bị engine tự chia như tặng cho dù user chưa
  chọn người nhận hoặc tỷ lệ chuyển quyền.
- Frontend, backend, `InheritanceParticipant`, Word và legacy tree đang giữ nhiều projection khác
  nhau; UI có thể đúng nhưng save/reload/Word sai.
- Hệ thống đang suy mọi người không nhận là `Người từ chối`, tạo nội dung pháp lý không có dữ liệu
  chứng minh.
- `form.html` vẫn chạy engine legacy `recalcShares()` dù tree legacy đã ẩn.

## 2. Quyết định kiến trúc bắt buộc

### 2.1 Một engine nghiệp vụ duy nhất ở backend

- Thêm `services/inheritance_engine.py` dùng `fractions.Fraction` của Python.
- Backend dùng cùng hàm engine cho API calculate, create, edit, update-diagram và Word snapshot.
- React không tự tính phần thừa kế. React chỉ tạo input quan hệ, gọi API và render output.
- Sau khi React chuyển xong, xóa `frontend/static/inheritance_engine.js`; không giữ hai engine.
- Không thêm engine Python thứ hai, adapter tính gần đúng hoặc fallback chia tỷ lệ trong template.

Lý do: kết quả pháp lý không được tin trực tiếp từ browser; save phải được backend tính lại bằng
đúng engine đã dùng để kiểm thử.

### 2.2 Source of truth khi lưu

`case_state_json` là nguồn commit chính cho Stage và Diagram. Không đổi schema DB.

```json
{
  "version": 2,
  "caseId": 123,
  "updatedAt": "2026-07-22T10:00:00Z",
  "stage": [],
  "diagram": {
    "engineInput": { "version": 2, "nodes": [] },
    "engineResult": {
      "engineVersion": 2,
      "status": "complete",
      "allocations": {},
      "breakdowns": [],
      "requiredSlots": [],
      "warnings": [],
      "errors": [],
      "unresolvedEstates": [],
      "conservation": { "allocated": "1", "unresolved": "0", "total": "1" }
    }
  }
}
```

- `engineInput` là dữ liệu có thẩm quyền để tái tính.
- `engineResult` là snapshot do backend tạo tại lần save, dùng cho audit/Word; không phải input cho
  lần tính sau.
- `engine_state_json` chỉ dùng làm nguồn đọc legacy nếu hồ sơ chưa có Diagram V2 trong
  `case_state_json`. Không ghi đè cột này trong save V2; không xóa cột hoặc đổi schema ở phase này.
- `InheritanceParticipant` là projection tương thích legacy. Backend sinh lại projection từ
  `engineResult`, nhưng Word V2 không dùng bảng này làm source of truth cho tỷ lệ.
- Nếu request có cả V2 và legacy, V2 thắng. Payload V2 invalid phải báo lỗi, không fallback legacy.

## 3. Contract đầu vào engine

Backend nhận danh sách node quan hệ; dữ liệu cá nhân như ngày sinh/ngày chết được tải lại từ Customer
theo `personId`, không tin bản sao trong browser.

```json
{
  "version": 2,
  "nodes": [
    {
      "id": "slot_owner",
      "personId": "42",
      "relationType": "person",
      "roleLabel": "Chủ đất",
      "parentSlotIds": [],
      "spouseSlotId": "slot_spouse",
      "isLandOwner": true,
      "willReceive": false,
      "hidden": false,
      "deleted": false
    }
  ]
}
```

Quy ước field:

| Field | Rule |
|---|---|
| `id` | ID của slot/node trong tree, duy nhất; không phải Customer ID. |
| `personId` | `Customer.id`; `null` với slot trống. |
| `relationType` | Chỉ phục vụ UI/validation; engine lấy huyết thống từ các ID quan hệ rõ ràng. |
| `roleLabel` | Nhãn hiển thị, không quyết định quyền thừa kế. |
| `parentSlotIds` | 0-2 slot cha/mẹ. Không fallback về owner hoặc parent đầu tiên. |
| `spouseSlotId` | Slot vợ/chồng; backend chuẩn hóa quan hệ hai chiều. |
| `isLandOwner` | Trạng thái nút `Chủ đất`; có thể có nhiều người. |
| `willReceive` | Trạng thái nút `Nhận`; chỉ điều khiển người còn sống ở kết quả cuối. |
| `hidden/deleted` | Node bị ẩn/xóa không phải active node. |

Active node là node có `personId` và không `hidden/deleted`. Một `personId` không được xuất hiện ở
hai active node. Slot trống được giữ để UI nhận drop nhưng không đưa vào graph người.

Validation bắt buộc:

- `id` duy nhất, `personId` tồn tại trong Stage và DB.
- Mỗi active `personId` chỉ có một node.
- Mọi `parentSlotIds` và `spouseSlotId` phải trỏ đến node tồn tại.
- Tối đa hai cha/mẹ; không self-parent, self-spouse, chu kỳ huyết thống hoặc quan hệ vợ/chồng lệch.
- Không suy quan hệ từ vị trí card, `roleLabel`, generation, `familyGroupId`, `sourceId` hoặc node đầu.
- Có ít nhất một `Chủ đất`; các chủ đất được chia sở hữu gốc đều `1/n`.
- Tỷ lệ sở hữu gốc không đều là `unsupported`, không tự tính gần đúng.

Loader hồ sơ cũ được phép đọc `parentSlotId`, `parentPersonId`, `spouseOf`, `familyGroupId` để migrate
trong bộ nhớ. Save V2 chỉ ghi contract chuẩn trên. Quan hệ legacy mơ hồ phải báo user đặt lại nhánh,
không tự gắn.

## 4. Thuật toán nghiệp vụ bắt buộc

### 4.1 Chuẩn hóa thời gian

- Parse `dd/mm/yyyy`, ISO date hiện hữu và `yyyy`.
- Chỉ có năm `yyyy` được chuẩn hóa thành `01/01/yyyy`.
- Chỉ so sánh đến ngày; không dùng giờ/phút.
- Các người chết có cùng ngày sau chuẩn hóa được coi là cùng thời điểm; xử lý từ cùng
  `same_day_snapshot` và không nhận chéo di sản.
- Không phân biệt giờ/phút hoặc suy người chết trước trong cùng ngày.
- Ưu tiên xử lý thế vị của nhánh con trước quy tắc không nhận chéo. Nếu nhánh không còn hậu duệ,
  nhánh đó bị loại khỏi mẫu số; quota được chia lại cho các đơn vị hợp lệ còn lại. Đây là cách
  engine đạt mục tiêu phân phối hết tài sản, không phải kết luận rằng anchor đã sở hữu quota.
  Đây là quy ước tính toán của hệ thống, không trình bày như nguyên văn pháp luật.

### 4.2 Khởi tạo tài sản

- Có `n` chủ đất thì mỗi người có `1/n` sở hữu gốc.
- Chủ đất còn sống luôn giữ phần sở hữu gốc, kể cả tắt `Nhận`.
- Tắt `Nhận` không được tự biến thành tặng cho/chuyển quyền.
- Tặng cho, chuyển quyền và tỷ lệ sở hữu gốc không đều ngoài scope; trả `unsupported` nếu input yêu
  cầu hành vi này.

### 4.3 Vòng di sản

1. Gom người chết theo ngày và xử lý các ngày tăng dần.
2. Chụp holdings đầu ngày trước khi tính bất kỳ người chết nào trong cùng ngày.
3. Chỉ mở estate nếu người chết có sở hữu gốc hoặc đã thực sự nhận tài sản từ ngày trước.
4. Hàng thứ nhất của estate gồm cha, mẹ, vợ/chồng và các nhánh con.
5. Cha/mẹ/vợ/chồng chỉ là đơn vị nhận nếu còn sống tại ngày mở estate. Người chết cùng thời điểm
   không nhận chéo; không áp dụng thế vị cho cha/mẹ hoặc vợ/chồng.
6. Mỗi người con là một đơn vị nhánh. Nhánh còn sống nhận trực tiếp; nhánh chết trước/cùng thời điểm
   được ưu tiên mở thế vị đệ quy. Nếu nhánh không có hậu duệ hợp lệ, loại nhánh đó khỏi danh sách
   đơn vị chia trước khi tính mẫu số.
7. Chia estate đều cho các đơn vị hợp lệ còn lại, ghi holdings cho người thực nhận và chỉ holdings
   của người thực nhận mới tạo vòng di sản ở ngày chết sau. Ví dụ B không có hậu duệ, C là nhánh
   hợp lệ duy nhất thì C nhận 100% phần estate đó.
8. Người chết sau nguồn estate được nhận ở vòng trước bất kể nút `Nhận`, vì tài sản đó phải đi vào
   estate thực tế của họ. Nút `Nhận` chỉ áp dụng người còn sống ở kết quả cuối.

### 4.4 Thế vị theo từng nhánh, không làm phẳng

Viết helper tương đương `allocate_descendant_branch(branch_person_id, source_date, share, path)`:

- Người nhánh còn sống tại ngày nguồn: nhận phần nhánh nếu là người nhận cuối hợp lệ.
- Người nhánh chết sau ngày nguồn: nhận phần nhánh; holdings của họ được xử lý ở ngày chết sau.
- Người nhánh chết trước hoặc cùng thời điểm: không sở hữu phần nhánh; nếu có con/cháu/chắt hợp lệ
  thì chia phần đó đều cho từng nhánh con rồi gọi đệ quy. Nếu không có hậu duệ, trả nhánh đó là
  `ineligible_branch` để loại khỏi mẫu số của estate cha; không tạo ownership cho anchor.
- Chỉ hậu duệ trong chính nhánh nhận thế vị. Cha/mẹ, vợ/chồng và người ngoài dòng con cháu của
  anchor không nhận phần này.
- Vợ/chồng anchor vẫn là đồng phụ huynh trong graph và được UI hiển thị, nhưng bị loại khỏi phép chia
  phần thế vị.
- Nếu anchor có tài sản độc lập từ nguồn khác, estate độc lập của họ vẫn chia theo hàng thứ nhất và
  vợ/chồng có thể nhận ở estate đó.
- `path` lưu các anchor đã đi qua để output giải thích `thế vị nhánh Y`, kể cả nhiều tầng.

Không được trả một mảng phẳng toàn bộ hậu duệ rồi chia đều.

### 4.5 `Người không nhận`

- Với người còn sống ở kết quả cuối, `willReceive=false` loại họ khỏi đơn vị nhận theo quy ước sản
  phẩm và mẫu số được tính lại giữa người/nhánh hợp lệ còn lại.
- Người đó không được gọi là `Người từ chối`.
- Sở hữu gốc của chủ đất còn sống không bị loại bởi `willReceive=false`.
- Nếu loại tất cả đơn vị nhận của một estate thì trả `unresolvedEstates` với reason `no_valid_heir`;
  không làm mất phần đó hoặc báo kết quả complete. Nếu còn ít nhất một đơn vị hợp lệ thì phải
  chia lại để không còn unresolved quota.

### 4.6 Bảo toàn tài sản

- Engine theo dõi `allocated + unresolved = 1` bằng Fraction.
- `status=complete` chỉ khi `unresolved=0`, không có error và tổng final holdings bằng `1`.
- Nhánh thế vị không còn hậu duệ không tạo unresolved quota nếu estate còn đơn vị hợp lệ khác;
  nhánh đó chỉ bị loại khỏi mẫu số. Chỉ estate không còn bất kỳ đơn vị hợp lệ nào mới giữ fraction
  trong `unresolvedEstates` và trả `status=incomplete`.
- Create/edit không commit hồ sơ diagram như kết quả hoàn tất nếu engine invalid/incomplete. Form
  phải giữ nguyên Stage/Diagram và hiển thị từng lỗi một dòng.

## 5. Contract output và giải thích kết quả

```json
{
  "engineVersion": 2,
  "status": "complete",
  "allocations": {
    "42": {
      "baseShare": "1/5",
      "inheritedShare": "3/20",
      "distributedShare": "0",
      "finalShare": "7/20",
      "displayPercent": "35.00"
    }
  },
  "breakdowns": [
    {
      "personId": "42",
      "total": "7/20",
      "terms": [
        { "kind": "base", "fraction": "1/5" },
        {
          "kind": "representation",
          "fraction": "3/20",
          "sourcePersonId": "10",
          "viaBranchPersonIds": ["21"]
        }
      ]
    }
  ],
  "requiredSlots": [],
  "warnings": [],
  "errors": [],
  "unresolvedEstates": [],
  "conservation": { "allocated": "1", "unresolved": "0", "total": "1" }
}
```

`requiredSlots` là output UI, không tham gia tính tỷ lệ:

| Reason | Slot cần hiển thị |
|---|---|
| `active_estate` | Hai cha/mẹ, một vợ/chồng và ít nhất một slot con của người có estate. |
| `representation_branch` | Một vợ/chồng và ít nhất một slot con của anchor chết trước/cùng ngày. |

Mỗi requirement có `anchorSlotId`, `reason`, `slotTypes` và `minimumEmptyChildSlots`. Engine không
tự tạo Customer hoặc đoán người vào slot.

`breakdowns` là nguồn duy nhất của `Xem cách tính`. UI format một dòng/người:

```text
Người A nhận: 17/40 = 3/10 (X) + 1/10 (Y) + 1/40 (Z)
Người C nhận: 1/6 = 1/6 (X, thế vị nhánh Y)
```

Không tạo term `gift/transfer` khi chưa có input nghiệp vụ riêng. Sửa ví dụ tặng cho đang nằm trong
tài liệu cũ để không gợi ý một tính năng ngoài scope.

## 6. Backend implementation

### 6.1 File mới

`services/inheritance_engine.py` chứa code thuần, không import FastAPI/SQLAlchemy:

- Dataclass/TypedDict tối thiểu cho normalized person, node và result nếu thực sự giúp type safety.
- Hàm public duy nhất đề xuất: `run_inheritance_case(engine_input, people_by_id)`.
- Helper nội bộ: parse date, build/validate graph, process estate, allocate descendant branch,
  serialize Fraction và conservation check.
- Không dùng float trong tính toán.

`tests/test_inheritance_engine.py` kiểm thử engine thuần bằng pytest, không cần DB cho test toán.

### 6.2 `routers/cases.py`

- Thêm `POST /cases/diagram/calculate` nhận JSON engine input, tải Customer theo `personId`, chạy
  engine và trả JSON result; endpoint không mutate DB.
- Dùng cùng parser/engine trong create, edit và update-diagram.
- Khi save: parse Stage + engineInput, chờ/kiểm Customer tồn tại, chạy engine, reject invalid hoặc
  incomplete, ghi engineResult do backend tạo vào `case_state_json`, replace participant projection,
  update case/property và commit một lần.
- Validation phải xảy ra trước delete/replace participant. Exception phải rollback toàn transaction.
- Không lấy `allocations`, `trace`, `warnings` do browser gửi làm kết quả có thẩm quyền.
- `ty_le` projection lấy từ `finalShare`/`displayPercent`, không hardcode `0.0`.
- Legacy `diagram_payload`, `engine_state_json`, `participant_*` chỉ được dùng khi request hoàn toàn
  không có V2; không fallback khi V2 có mặt nhưng invalid.
- Loader ưu tiên `case_state_json.diagram.engineInput`. Nếu thiếu, migrate lenient từ
  `engine_state_json`; quan hệ mơ hồ trả warning cần user đặt lại.
- Giữ API legacy optional trong một chu kỳ để hồ sơ cũ mở được; frontend V2 ngừng gửi các field đó.

### 6.3 Persistence invariant

- `diagram.engineInput.nodes[].personId` phải thuộc `case_state_json.stage`.
- `diagram.engineResult` luôn được tạo lại từ đúng input trong cùng transaction save.
- Participant projection không được quyết định người nào ở Stage/Pool/Diagram.
- Save lỗi không clear Stage/localStorage, không xóa participant cũ và không ghi một phần case.

## 7. Frontend implementation

### 7.1 `ReactFlowApp.jsx`

- `buildEngineInput()` chỉ xuất contract V2; không xuất `flowFrom`, share output hoặc quan hệ suy
  đoán.
- Thay `runDiagramEngine()` bằng effect gọi `/cases/diagram/calculate`.
- Dùng sequence number hoặc `AbortController`; response cũ không được ghi đè response mới.
- Tăng busy counter trước request và giảm trong `finally`; save bị khóa khi busy count lớn hơn `0`.
- Giữ kết quả gần nhất trong `DiagramStateStore`; publish snapshot chỉ khi response khớp input mới
  nhất.
- `resolveSubRelations()` không tính share và không dùng heuristic ngày chết. Hàm chỉ ghép node đã
  persist với slot trống được derive từ `requiredSlots`.
- Không tự xóa node đã có người khi requirement biến mất. Đánh dấu quan hệ không còn hợp lệ và yêu
  cầu user xử lý.
- Hydrate legacy không fallback về owner/father/mother đầu tiên. Thiếu parent rõ ràng phải giữ node
  ở trạng thái ambiguous và báo lỗi.
- `Nhận` tương tác với người còn sống. Card người đã chết hiển thị control disabled/read-only vì
  entitlement của họ do timeline quyết định.
- Nút `Chủ đất` hoạt động với nhiều người; không dùng dấu `*`.
- Bỏ label `Đã nhận/chảy qua`; người thế vị không được trình bày như từng sở hữu phần nhánh.
- Thêm panel thu gọn `Xem cách tính`, đọc trực tiếp `engineResult.breakdowns`.

### 7.2 `diagram_state.js`

- Tái sử dụng store hiện hữu; không tạo `case_state.js` hoặc store thứ hai trong task này.
- Snapshot thêm calculation status/result nếu cần, nhưng không chứa engine toán riêng.
- `getCommittedState()` phải trả input mới nhất và result backend tương ứng; không ghép input mới
  với result cũ.

### 7.3 `diagram_edges.js`

- Chỉ dựng kinship edges từ `parentSlotIds` và `spouseSlotId`.
- Cặp cha/mẹ cùng trỏ xuống con; Z phải nối đúng C/D nếu input ghi C/D.
- Không build/render flow edge tài sản.
- Quan hệ thiếu/mơ hồ không tự nối về A/B hoặc owner.

### 7.4 `form.html`

- Chỉ submit canonical `case_state_json` V2 từ `__DIAGRAM_API__`.
- Không gửi `diagram_payload`/`engine_state_json` từ frontend V2.
- Trước save: không tự flush/commit Stage draft; chỉ chờ quick-update đã bắt đầu và calculation mới
  nhất, rồi block nếu engine invalid/incomplete. Nút Stage `Cập nhật` vẫn là commit trigger duy nhất.
- Save native/fetch hiện hữu phải giữ nguyên Stage khi validation/server/network fail.
- Cảnh báo/lỗi hiển thị trong một vùng chung, mỗi lỗi một dòng; không dùng popup chồng nhau.
- Gỡ script `inheritance_engine.js` sau khi React đã chuyển sang backend.

## 8. Word, detail và thuật ngữ pháp lý

### 8.1 Rule bắt buộc

- `Người không nhận` là trạng thái sản phẩm từ Diagram.
- `Người từ chối nhận di sản` chỉ tồn tại khi có dữ liệu pháp lý xác nhận riêng.
- Hiện chưa có input Diagram cho việc từ chối hợp lệ; các placeholder `Người từ chối` phải để
  trống, không suy từ `willReceive=false`.
- Không được tạo câu “đã từ chối theo Văn bản...” nếu hồ sơ không có dữ liệu văn bản từ chối.

## 9. Test matrix bắt buộc

### Engine thuần

1. Fixture X/Y/D/Z: `M=N=O=59/192`, `Z2=Z3=5/128`.
2. Thế vị lệch tầng: B sống `1/2`; nhánh A cho C `1/4`; nhánh D cho E/F mỗi `1/8`.
3. Y bỏ `Chủ đất`, chết trước X: không mở estate riêng cho Y; nhánh con của Y vẫn thế vị phần từ X.
4. Vợ/chồng Y không nhận phần thế vị nhưng là đồng phụ huynh; nếu Y có estate độc lập thì spouse
   tham gia hàng thứ nhất của estate Y.
5. Người nhận từ nhiều nguồn: tổng đúng và breakdown giữ từng nguồn, không ghi đè.
6. Người chết sau nguồn nhận tài sản rồi mở estate sau.
7. Cùng ngày không nhận chéo, dùng snapshot, không warning.
8. `yyyy` thành `01/01/yyyy`; full date giữ nguyên.
9. Năm người `Chủ đất` mỗi người base `1/5`.
10. Chủ đất sống tắt `Nhận` vẫn giữ base share.
11. Người sống không nhận bị loại theo quy ước sản phẩm; mẫu số/nhánh được tính lại.
12. Con chết trước/cùng thời điểm không có hậu duệ: loại nhánh đó khỏi mẫu số; nếu C là nhánh hợp
    lệ duy nhất thì C nhận 100% estate, không tạo ownership cho anchor.
13. Không còn người nhận hợp lệ trả incomplete, `allocated + unresolved = 1`.
14. Dangling parent, duplicate person, cycle, self-spouse và hơn hai parent trả invalid.
15. Z có `parentSlotIds=[C,D]` không được engine tự gắn về A/B.

### Backend/persistence

15. Calculate không mutate DB và không nhận output giả từ client.
16. Save chạy lại engine; client sửa allocations không thay đổi kết quả backend.
17. Invalid/incomplete không delete participant hoặc mutate case một phần.
18. Save/reload giữ `Chủ đất`, `Nhận`, quan hệ và cùng tỷ lệ.
19. Hồ sơ legacy load được; quan hệ mơ hồ hiện warning thay vì tự nối.
20. `InheritanceParticipant.ty_le` không còn hardcode `0.0`.

### UI/Word

21. Response calculate cũ không ghi đè response mới.
22. Save bị khóa trong khi quick-update/calculation pending.
23. Slot bố mẹ chỉ sinh cho active estate; branch thế vị sinh spouse + child, không sinh bố mẹ anchor.
24. Populated node không tự biến mất sau recalculation.
25. `Xem cách tính` một dòng/người, hiện nguồn và nhánh thế vị.
26. Canvas chỉ có kinship edge; không có asset flow edge.
27. Word, detail và fallback route không suy `Người từ chối`.
28. Save/reload/export Word dùng cùng final fraction và display percent.

## 10. Verification commands

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_inheritance_engine.py -q
.\venv\Scripts\python.exe -m pytest tests/test_diagram_payload_parser.py tests/test_inheritance_research_catalog.py tests/test_word_engine.py -q
node --test --test-reporter=dot tests\*.test.mjs
.\verify.bat
D:\graphify\.venv\Scripts\graphify.exe update .
```

Chạy thêm `rg` để chứng minh final state không còn active usage:

```powershell
rg -n "recalcShares|buildFlowEdges|flowFrom|Đã nhận/chảy qua|Tặng phần sở hữu" frontend routers services tests
rg -n "Người từ chối|Từ chối nhận" frontend routers services tests docs
```

Kết quả `Người từ chối` còn lại chỉ được phép là placeholder/nhánh dữ liệu pháp lý có nguồn xác
nhận, không phải phép suy từ `Nhận=false`.
