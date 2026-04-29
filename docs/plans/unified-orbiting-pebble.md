# DEBATE — Vòng 3: chốt 7/8, đào sâu E6 (persist đa-`*`)

## Quyết định đã chốt vòng 1+2+3

| # | Chốt |
|---|---|
| A1 | Defer slot ông bà cố định. |
| A2 | Engine không cap; UI là giới hạn riêng. |
| A3 | Label động cho node thế vị/con phát sinh ("Con của Z"). Hàng 1 giữ label slot cũ. |
| A4 | Rule chung: sibling/child chết trước có con → spawn node thế vị tự động. |
| B1 | Visited + MAX_DEPTH technical. Warning khi chạm. |
| B2 | Card hiển thị % cuối cùng còn giữ cho người sống. Người chết style muted, hiển thị "đã nhận/chảy qua" để trace. Engine giữ breakdown. |
| B3 | Thế vị chỉ cho descendant (con/cháu/chắt). |
| B4 | Fraction class BigInt tự viết nhỏ. |
| B5 | Warning trace `same_day_treated_as_predeceased_for_representation` trong breakdown. |
| B6 | Disable Nhận khi tích `*` và không có inflow. Có inflow → enable, label rõ. |
| B7 | Manual share mode disable / loại khỏi source of truth. |
| C1 | Mũi tên cong/ngang vợ chồng cùng tầng OK. |
| C2 | Flow theo decedent → heir (có thể đi lên). |
| C3 | Không auto-tích `*` hồ sơ mới. Restore Owner cũ → migrate `*`. |
| C4 | `case-nguoi-chet` giữ contract cũ làm hidden legacy. Source mới = tree state. |
| C5 | Heuristic restore: Owner cũ → tích `*`, willReceive giữ data cũ. |
| D1 | Check `package.json` trước khi viết test JS. Có thể helper Node thuần. |
| D2 | Seed script defer. Fixture deterministic test ưu tiên. |
| **E1** | **Giữ slot cũ hàng 1 + spawn động cho thế vị/con phát sinh.** Không free-form picker phase này. |
| **E2** | **Engine refuse compute đầy đủ khi heir thiếu node trong tree.** Báo thiếu dữ liệu/quan hệ. |
| **E3** | **Code phân biệt 2 lớp logic, UI phase đầu chỉ vẽ flow.** Bloodline ngầm qua vị trí tầng + label. |
| **E4** | **Sửa lại:** Điều 652 BLDS chỉ nói thế vị con/cháu/chắt của người để lại di sản. Cháu (con anh chị em) thế vị anh chị em **KHÔNG phải rule mặc định Điều 652**. Plan phase này không support thế vị qua sibling — KHÔNG sai BLDS, chỉ là chưa làm hàng 2 đầy đủ. |
| **E5** | **Hide checkbox Nhận** khi không tích `*` và không có inflow. |
| **E7** | Relationship data lưu trong `__FAMILY_TREE_STATE__` localStorage = source of truth FE. Persist BE defer phase sau. |
| **E8** | 1 person.id = 1 node active max. Confirm. |
| **PHASE** | Sub-phase 1 (engine pure) + Sub-phase 2 (UI tích hợp tối thiểu) trong PR này. Sub-phase 3 (label động/persist BE) sang PR sau. |

---

## Chỉ còn E6 — đào sâu

### Vấn đề
- Engine mới hỗ trợ đa-`*` (vd 5 đồng chủ sở hữu).
- Submit hồ sơ → DB chỉ lưu 1 `case-nguoi-chet` + participants với `vai_tro/hang_thua_ke/share`.
- Nếu user dùng đa-`*` rồi submit → state đa-`*` MẤT khi reload/đổi máy.
- Reload → migrate fallback 1-owner → kết quả engine KHÁC lúc submit.

### Hệ quả nghiệp vụ thật
1. **Hồ sơ in ra (Word template) hôm nay** dùng % engine A. Tuần sau mở lại → % engine B. **Sai dữ liệu công chứng.**
2. **Multi-device:** notary làm trên máy desktop, tablet → mỗi máy 1 state khác.
3. **Audit trail:** không có history "engine version A đã tính ra X% tại thời điểm Y".

### Các option chi tiết

#### (a) Block submit khi state khác mặc định 1-owner
- Engine chạy nội bộ cho user thử nghiệm
- Submit chỉ cho phép khi đúng 1 người tích `*` (giống owner cũ)
- Đa-`*` → UI báo "Tính năng đa chủ đang preview, chưa lưu được. Hãy tích chỉ 1 chủ trước khi submit."
- **Pros:** không đụng BE, không silent loss
- **Cons:** user không thấy giá trị tính năng đa-`*` thực sự

#### (b) Persist localStorage theo case ID + warning rõ
- `__FAMILY_TREE_STATE__` = SOT FE. Lưu cả tree state + assetOwnerIds + willReceive
- Khi mở case → restore từ localStorage trước, nếu không có thì migrate từ DB
- Submit hồ sơ → vẫn lưu DB cách cũ (1 owner), localStorage giữ engine state
- UI cảnh báo trên toolbar diagram: "⚠ Cấu hình đa chủ chỉ lưu tại trình duyệt này. Đổi máy/xóa cache → mất."
- **Pros:** không đụng BE, dùng được ngay
- **Cons:** không multi-device, không audit trail. Risk: user nhầm tưởng đã lưu

#### (c) Mở rộng schema 1 cột TEXT — `inheritance_cases.engine_state_json`
- 1 migration nhỏ: `ALTER TABLE inheritance_cases ADD COLUMN engine_state_json TEXT`
- Submit serialize toàn bộ tree state JSON vào cột này
- Restore deserialize ngược
- Participants table giữ nguyên (legacy compat cho hiển thị/word template cũ)
- Engine output (% mỗi người) cũng có thể lưu thêm `participants.engine_share_percent` (cột mới)
- **Pros:** persist thật, audit trail, multi-device, không phá schema cũ
- **Cons:** migration + 1 endpoint update + restore logic. Vi phạm scope "không đổi BE" đã chốt

#### (d) Chỉ engine + UI preview, KHÔNG cho submit hồ sơ phase này
- Phase này = research/preview tính năng
- Submit hồ sơ vẫn dùng UI cũ (chưa có engine mới)
- 2 chế độ song song: "Sơ đồ cũ (submit được)" + "Engine mới (preview, không submit)"
- **Pros:** không đụng BE, không risk submit sai
- **Cons:** UX confusing — 2 chế độ. Engine mới không production-ready

#### (e) Defer toàn bộ persist sang sub-phase 3 — phase này chỉ làm engine + render
- Engine + UI render % chạy trên FE memory
- KHÔNG persist đâu hết (kể cả localStorage)
- Reload page → reset hết, user nhập lại
- Submit cũ vẫn hoạt động (1 owner fallback)
- Sub-phase 3 sẽ giải quyết persist (chọn b hoặc c sau)
- **Pros:** scope sạch nhất, không cam kết persist gì
- **Cons:** UX kém — user nhập lâu xong reload mất

### So sánh nhanh

| Option | Đụng BE | Reload OK | Multi-device | Submit đa-`*` | Risk |
|---|---|---|---|---|---|
| (a) Block submit | Không | N/A | N/A | Block | Thấp — UX hạn chế |
| (b) localStorage + warn | Không | OK cùng máy | KHÔNG | Submit fallback 1-owner | Trung — user nhầm |
| (c) Schema TEXT | CÓ (1 col) | OK | OK | Lưu đầy đủ | Thấp — phá scope |
| (d) Preview-only | Không | N/A | N/A | Block | Thấp — UX 2 chế độ |
| (e) FE memory only | Không | MẤT | KHÔNG | Submit fallback | Cao — user mất data |

---

## Đề xuất của tôi để bạn chọn

**Khuyến nghị mạnh: (b) localStorage + warning rõ.**

Lý do:
1. **Không phá scope BE** đã chốt (giữ promise với phase này).
2. **UX dùng được ngay**: notary có thể test/preview engine, dùng cho hồ sơ nội bộ.
3. **Warning rõ**: user biết giới hạn, không nhầm tưởng đã lưu vĩnh viễn.
4. **Submit fallback an toàn**: hồ sơ DB vẫn dùng 1-owner cũ, không sai dữ liệu công chứng đã in.
5. **Migration path rõ**: sub-phase 3 sẽ implement (c) schema TEXT, lúc đó migrate localStorage → DB.

**Cấu trúc lưu localStorage:**
```js
window.__FAMILY_TREE_STATE__ = {
  caseId: "...",
  positions: { [nodeId]: {x, y} },
  assetOwnerIds: ["personId1", "personId2", ...],
  willReceive: { [personId]: bool },
  spawnedNodes: { [nodeId]: { personId, parentId, role } },  // node thế vị động
  schemaVersion: 1,
  updatedAt: "ISO date"
}
```

Lưu localStorage key: `family_tree_state_${caseId}`.

**UI warning:** banner màu vàng top diagram khi `assetOwnerIds.length > 1`:
> ⚠ Đa chủ sở hữu đang ở chế độ preview. Cấu hình này chỉ lưu tại trình duyệt này. Để lưu vĩnh viễn vào DB, cần phase tiếp theo. Submit hồ sơ hiện tại sẽ fallback về 1 chủ.

---

## Câu hỏi chốt cuối cùng

Bạn chọn option nào cho E6?
- (a) Block submit
- **(b) localStorage + warning** ← khuyến nghị
- (c) Schema TEXT (đụng BE)
- (d) Preview-only 2 chế độ
- (e) FE memory only — không persist gì

Hoặc combo: (b) phase này + commit (c) như sub-phase 3 ngay?

Sau khi chốt E6 → tôi viết task file Codex (hoặc đi thẳng implement sub-phase 1) → confirm với bạn → bắt đầu code.
