# Spec: Mô hình đồng bộ Stage (SOT) → Pool → Diagram

Ngày: 2026-08-18
Trạng thái: **ĐỀ XUẤT — chờ user duyệt**. Chưa normative. Không được implement trước khi user duyệt.
Module: Hồ sơ thừa kế (case workspace)
Nguồn liên quan: `docs/domains/inheritance/workflow.md` (SOT hành vi hiện tại),
`docs/domains/inheritance/ux.md` (DRAFT), `docs/domains/inheritance/plan.md` (DIAGRAM-R1/R2),
`docs/platform/case-workspace/contract.md` (provisional)

Nguyên tắc user đã chốt cho spec này:
1. Chọn phương án **đơn giản nhất, ít lỗi, ổn định**.
2. Khi có nhiều thứ trùng lặp hoặc dễ mâu thuẫn → **đẩy quyết định cho user đang thao tác**, không tự suy đoán.

---

## Problem Statement

Người dùng nhập dữ liệu người vào hồ sơ thừa kế từ nhiều nguồn (Excel, nhập thủ công, OCR CCCD),
rồi gán họ vào sơ đồ thừa kế. Stage được chọn làm bản gốc (source of truth) cho dữ liệu người.

Khi thao tác đơn giản (sửa Stage → bấm `Cập nhật`) thì chạy đúng. Khi thao tác phức tạp —
sửa ở Stage rồi xoá thẻ người đó trên sơ đồ — vùng Stage hỏng theo hai kiểu:

1. **Mất dữ liệu**: người vừa sửa biến mất khỏi Stage.
2. **Đỏ toàn bộ**: mọi hàng Stage bị tô viền đỏ, không lưu được gì.

Người dùng không biết vì sao, không tái hiện được ổn định, và không tin được rằng dữ liệu
mình vừa nhập có còn hay không. Với hồ sơ công chứng, mất dữ liệu người là lỗi nghiêm trọng.

### Nguyên nhân đã xác định bằng code

| # | Nguyên nhân | Bằng chứng |
|---|---|---|
| C1 | Hai endpoint lưu, mỗi endpoint tin DB cho nửa còn lại. `stage-update` lấy stage mới + **diagram cũ trong DB**; `diagram-update` lấy diagram mới + **stage cũ trong DB**. | `cases.py:1478`, `cases.py:1462` |
| C2 | Validation bắt mọi reference của diagram phải nằm trong stage. Xoá người ở Stage + diagram cũ trong DB còn trỏ người đó → **từ chối cả lần lưu** (400). | `cases.py:1403`, `:1413`, `:567-571` |
| C3 | Client **đã** prune node ngoài stage trước khi gửi, nhưng server **ném đi** bản đã prune và dùng bản DB cũ. Công sức prune vô nghĩa. | `form.html:6402-6407` vs `cases.py:1462` |
| C4 | Client mutate state cục bộ (đánh dấu deleted, xoá hàng Pool khỏi DOM) **trước** khi gọi server, và **không có rollback** khi server từ chối. | `form.html:4825-4834` trước `:4844` |
| C5 | `persistCommittedStageSnapshot` được gọi **vô điều kiện**, trước khi kiểm `failedCount === 0` → Stage bị chốt ở trạng thái thiếu người. | `form.html:11862` vs `:11866` |
| C6 | Hàng Stage không có `dataset.cid` bị **lọc im lặng** khỏi snapshot. Hàng lưu người thất bại → không có mã → mất không báo. | `form.html:4780`, `:4735-4736` |
| C7 | Cờ `__allowClearStaging` mở chốt bảo vệ `inStaging` — chốt là quy ước mềm, không phải ranh giới kiến trúc. | `form.html:5390-5396`, `:4832` |
| C8 | Xoá 1 node lan truyền tới hết nhánh con (vòng lặp `while changed`), user không được báo trước. | `ReactFlowApp.jsx:290-302` |

### Xung đột spec ↔ runtime (user đã phân xử)

`workflow.md` §6 yêu cầu: xoá người ở Stage + bấm `Cập nhật` thì **Diagram phải cascade prune**
reference tới người đó. Runtime làm ngược: giữ diagram cũ và **từ chối** lần lưu.

**Phân xử của user (Q9a): spec đúng, runtime sai.** Stage là bản gốc; bản gốc phải xoá được người.
Cascade prune là hệ quả bắt buộc.

---

## Solution

Một mô hình đồng bộ có **một bản gốc duy nhất**, **một cổng commit**, và **lan truyền một chiều**.

Bốn trụ:

1. **Một bản gốc (single store).** Dữ liệu người (tên, ngày sinh, ngày chết, CCCD, ngày cấp,
   nơi cấp, địa chỉ) chỉ tồn tại ở **một** nơi. Pool là **giá trị tính ra**, không lưu.
   Diagram chỉ giữ **mã người** + dữ liệu riêng của Diagram (quan hệ, slot, Chủ đất, Nhận).

2. **Một cổng commit.** Sửa Stage là bản nháp. Chỉ `Cập nhật` mới chốt.
   Còn nháp chưa chốt mà thao tác nơi khác → **popup buộc chọn**: commit phần vừa sửa, hoặc huỷ thay đổi.

3. **Tất-cả-hoặc-không.** Một lần commit chỉ có hai kết quả: mọi hàng hợp lệ và lưu thành công,
   hoặc không lưu gì và bản nháp còn nguyên. Không commit một phần.

4. **Lan truyền một chiều, có xác nhận.** Stage → Pool → Diagram → Engine → Participants.
   Không có đường ngược. Khi lan truyền gây mất gán trên sơ đồ, **hỏi user trước** kèm danh sách
   chính xác ai bị ảnh hưởng.

---

## User Stories

### Nhập dữ liệu vào Stage

1. Là công chứng viên, tôi muốn nhập người từ OCR CCCD, để không phải gõ lại thông tin từ ảnh giấy tờ.
2. Là công chứng viên, tôi muốn nhập người từ Excel, để đưa nhanh danh sách nhiều người vào hồ sơ.
3. Là công chứng viên, tôi muốn nhập người bằng tay, để xử lý trường hợp không có ảnh hay file.
4. Là công chứng viên, tôi muốn tìm và chọn người đã có trong kho khách hàng, để không tạo trùng bản ghi.
5. Là công chứng viên, tôi muốn mọi nguồn nhập cho ra **cùng một dạng hàng Stage**, để không phải nhớ nguồn nào thiếu trường gì.
6. Là công chứng viên, tôi muốn thấy rõ hàng nào chưa đủ dữ liệu để lưu, để sửa trước khi chốt.
7. Là công chứng viên, tôi muốn OCR ra kết quả sai thì sửa được ngay trên hàng Stage, để không phải OCR lại.
8. Là công chứng viên, tôi muốn OCR hai lần cùng một người thì hệ thống **không tự gộp**, để tôi tự quyết giữ hàng nào.
9. Là công chứng viên, tôi muốn hàng Stage chưa lưu được vào kho khách hàng phải **báo lỗi rõ**, để không bị mất người mà không biết.

### Sửa dữ liệu ở Stage

10. Là công chứng viên, tôi muốn sửa tên/ngày sinh/CCCD của một người ở Stage, để sửa sai sót OCR.
11. Là công chứng viên, tôi muốn phần đang sửa dở **không bị mất** khi tôi bấm sang vùng khác, để không phải gõ lại.
12. Là công chứng viên, tôi muốn khi sửa Stage xong và bấm `Cập nhật` thì **mọi nơi hiển thị người đó đều đổi theo**, để không thấy dữ liệu cũ trên thẻ sơ đồ.
13. Là công chứng viên, tôi muốn sửa CCCD của một người **không làm đứt** liên kết của họ với thẻ trên sơ đồ, để không phải gán lại.
14. Là công chứng viên, tôi muốn sửa ngày chết của một người và hiểu rằng điều đó **làm thay đổi vòng thừa kế**, để không bị bất ngờ khi sơ đồ đổi hình.
15. Là công chứng viên, khi tôi đang sửa Stage dở mà bấm sang sơ đồ, tôi muốn hệ thống **hỏi tôi commit hay huỷ**, để tôi tự quyết chứ không bị hệ thống chọn hộ.

### Xoá người ở Stage

16. Là công chứng viên, tôi muốn xoá một người khỏi Stage bằng nút xoá cuối hàng, để loại người nhập sai.
17. Là công chứng viên, tôi muốn xoá người ở Stage **thành công được** dù họ đang được gán trên sơ đồ, để không bị kẹt.
18. Là công chứng viên, khi xoá một người làm gãy nhánh sơ đồ (A→B→C, xoá B thì C mất chỗ), tôi muốn thấy **danh sách chính xác ai sẽ bị bỏ gán** trước khi xác nhận.
19. Là công chứng viên, tôi muốn người bị bỏ gán khỏi sơ đồ **vẫn còn trong Stage** và quay về Pool, để gán lại được mà không nhập lại.
20. Là công chứng viên, tôi muốn huỷ hộp xác nhận thì **không có gì thay đổi**, để thử nghiệm an toàn.

### Pool

21. Là công chứng viên, tôi muốn Pool tự có thêm người khi tôi commit người mới ở Stage, để kéo vào sơ đồ ngay.
22. Là công chứng viên, tôi muốn Pool tự nhận lại người khi tôi xoá thẻ họ trên sơ đồ, để gán lại chỗ khác.
23. Là công chứng viên, tôi muốn Pool nhận lại **cả nhánh** người khi tôi xoá một node làm gãy nhánh, để không mất ai.
24. Là công chứng viên, tôi muốn Pool **không bao giờ** hiện người đã bị xoá khỏi Stage, để không gán người không còn tồn tại.
25. Là công chứng viên, tôi muốn thao tác trên Pool **không bao giờ xoá hay sửa** dữ liệu người ở Stage, để Stage là chỗ tin được.
26. Là công chứng viên, tôi muốn Pool hiện đúng tên/ngày sinh mới nhất sau khi tôi sửa Stage, để đối chiếu.

### Diagram

27. Là công chứng viên, tôi muốn kéo người từ Pool vào slot trên sơ đồ, để dựng quan hệ thừa kế.
28. Là công chứng viên, tôi muốn bỏ gán một thẻ khỏi sơ đồ, để sắp lại vị trí.
29. Là công chứng viên, tôi muốn phân biệt rõ **bỏ gán** (người về Pool, Stage giữ nguyên) với **xoá người** (chỉ làm ở Stage), để không xoá nhầm.
30. Là công chứng viên, tôi muốn đánh dấu Chủ đất và Nhận trên thẻ, để engine tính được tỷ lệ.
31. Là công chứng viên, tôi muốn lưu sơ đồ **không sửa** dữ liệu người ở Stage, để hai vùng không đè nhau.
32. Là công chứng viên, tôi muốn thẻ sơ đồ hiện dữ liệu người **lấy từ bản gốc**, để không bao giờ thấy dữ liệu cũ.
33. Là công chứng viên, tôi muốn sơ đồ tham chiếu người không còn trong Stage thì được **tự dọn** khi commit, để không bị chặn lưu.
34. Là công chứng viên, tôi muốn biết khi engine chưa tính được kết quả (thiếu dữ liệu, chưa hỗ trợ), để không tưởng là đã xong.

### Lưu và lỗi

35. Là công chứng viên, tôi muốn khi có hàng lỗi thì **không lưu gì cả** và bản nháp còn nguyên, để không bị chốt nửa vời.
36. Là công chứng viên, tôi muốn chỉ **hàng sai** bị tô đỏ kèm lý do, để biết sửa ở đâu.
37. Là công chứng viên, tôi muốn hệ thống báo lỗi **không được xoá hay sửa** dữ liệu tôi đang nhập, để lỗi không kèm mất mát.
38. Là công chứng viên, tôi muốn lưu thất bại thì màn hình **trở về đúng trạng thái trước khi bấm**, để thử lại được.
39. Là công chứng viên, tôi muốn biết có người khác vừa sửa hồ sơ này trước tôi, để không đè mất việc của họ.

---

## Implementation Decisions

### D1 — Danh tính người (Q1)

Khoá liên kết Stage ↔ Pool ↔ Diagram là **mã khách hàng trong DB** (`customers.id`). Giữ nguyên,
đã đúng và đã ổn định: sửa tên hay CCCD **không** làm đứt liên kết.

CCD (`so_giay_to`) là **dữ liệu**, không phải khoá: sửa được, có thể trùng, có thể rỗng.
Vị trí hàng / index **không bao giờ** được dùng làm khoá.

### D2 — Hai lần lưu, và xử lý dứt điểm hàng chưa có mã (Q1)

Hiện có **hai lần ghi khác nhau**, phải nói rõ trong spec vì đây là gốc của việc mất người:

| Lần | Ghi gì | Ghi vào | Kích hoạt |
|---|---|---|---|
| L1 | Từng người | bảng `customers` (kho dùng chung toàn hệ thống) | nút lưu người |
| L2 | Danh sách Stage của hồ sơ | `case_state_json.stage` | ngay sau L1, cùng một hành động |

OCR `Lưu` **không** ghi DB — chỉ đẩy hàng vào Stage dưới dạng nháp. Mã chỉ sinh ở L1.

**Quyết định:** L1 và L2 là **một hành động nguyên tử đối với user**. Một lần bấm `Cập nhật`:

1. Kiểm hợp lệ **toàn bộ** hàng ở client trước, chưa gọi mạng.
2. Có hàng lỗi → **dừng, không gọi mạng**, tô đỏ đúng hàng lỗi, giữ nguyên nháp.
3. Mọi hàng hợp lệ → L1 cho mọi hàng.
4. Bất kỳ hàng nào L1 thất bại → **dừng, không chạy L2**, báo đúng hàng đó, giữ nguyên nháp.
5. Mọi hàng L1 xong → L2.
6. L2 thất bại → **rollback hiển thị** về trạng thái trước khi bấm.

**Bỏ hẳn việc lọc im lặng hàng không có mã.** Hàng không có mã sau L1 là **lỗi phải báo**,
không phải hàng để bỏ qua. Đây là sửa trực tiếp C6.

### D3 — Một bản gốc (Q2a, Q14a)

Dữ liệu người tồn tại ở **đúng một** nơi trong trang. Cụ thể:

- **Bản gốc**: một map `people` khoá theo mã người, chứa toàn bộ trường người.
- **Pool**: **selector tính ra**, không có state riêng: `pool = stage_ids − assigned_ids`.
  Không lưu, không có DOM là nguồn.
- **Diagram**: node chỉ giữ `personId` + dữ liệu riêng của Diagram (`parentSlotId`, `relationType`,
  `sourceId`, `isLandOwner`, `willReceive`, `sharePercent`, metadata layout).
  **Không** giữ bản sao tên/ngày sinh/CCCD.
- Thẻ sơ đồ render bằng cách **tra bản gốc theo `personId`** tại thời điểm vẽ.

Hệ quả: bỏ được cơ chế bắn tin nhắn đồng bộ bản sao (`caseParticipantRecordUpdated`) — không còn
bản sao nào để đồng bộ. Đây là cách duy nhất để "Stage là bản gốc" thành sự thật kỹ thuật.

**Ghi chú phạm vi:** D3 chạm vào state của phần sơ đồ (React) → **ticket riêng**, không nằm trong
lát sửa lỗi đầu tiên. Xem *Out of Scope*.

### D4 — Chuẩn hoá input từ mọi nguồn (yêu cầu chi tiết của user)

Mọi nguồn đi qua **một hàm chuẩn hoá duy nhất** trước khi thành hàng Stage. Không nguồn nào được
đi đường riêng.

Bốn nguồn hiện có: **OCR CCCD**, **Excel/import**, **nhập thủ công**, **tìm–chọn từ kho khách hàng**.

Hợp đồng chuẩn hoá:

| Trường | Bắt buộc | Chuẩn hoá |
|---|---|---|
| `ho_ten` | **Có** | cắt khoảng trắng đầu/cuối, gộp khoảng trắng lặp, giữ nguyên hoa/thường user nhập |
| `gioi_tinh` | Không | về tập giá trị đóng; không suy đoán từ tên |
| `ngay_sinh` | Không | về một định dạng ngày nội bộ duy nhất; chấp nhận chỉ có năm |
| `ngay_chet` | Không | như `ngay_sinh`; rỗng = còn sống |
| `so_giay_to` | Không | cắt khoảng trắng; **không** ép định dạng; **không** tự sửa số |
| `ngay_cap` | Không | như `ngay_sinh` |
| `noi_cap` | Không | cắt khoảng trắng |
| `dia_chi` | Không | cắt khoảng trắng, gộp khoảng trắng lặp |
| `place_of_origin` | Không | cắt khoảng trắng |

Quy tắc cứng:

- Chuẩn hoá **chỉ làm sạch hình thức**, không suy đoán nội dung, không tự điền, không tự sửa số giấy tờ.
- Thiếu trường không bắt buộc → để rỗng, **không** chặn nhập, **không** chặn commit.
- **Không tự gộp trùng.** Trùng CCCD do user tự xử lý (giữ đúng `workflow.md` §4).
  Hệ thống chỉ được **cảnh báo**, không được gộp hay xoá.
- Nguồn nhập được ghi lại để truy vết, nhưng **không** ảnh hưởng hành vi đồng bộ về sau.

### D5 — Định nghĩa "hàng lỗi" (Q12)

Hiện chỉ có **một** phép kiểm ở client: thiếu `ho_ten`. Spec định nghĩa lại rõ ràng.

Một hàng Stage là **lỗi** khi và chỉ khi:

| Mã | Điều kiện | Lý do hiện cho user |
|---|---|---|
| E1 | `ho_ten` rỗng sau chuẩn hoá | "Thiếu họ tên" |
| E2 | Ngày không phân giải được (`ngay_sinh`/`ngay_chet`/`ngay_cap`) | "Ngày không hợp lệ" |
| E3 | `ngay_chet` sớm hơn `ngay_sinh` | "Ngày chết trước ngày sinh" |
| E4 | L1 thất bại cho hàng đó | thông điệp server trả về |

Quy tắc cứng cho validation:

- Tính **thuần theo từng hàng**. **Không** phụ thuộc trạng thái Pool/Diagram/engine.
- **Không bao giờ** mutate: validation chỉ đọc và trả kết quả, không xoá, không sửa, không dọn.
- Chỉ tô đỏ **đúng hàng sai**, kèm lý do đọc được.
- Trùng CCCD **không** phải lỗi — chỉ cảnh báo (D4).
- Toàn bộ hàng đỏ chỉ được xảy ra khi **thực sự** mọi hàng sai, không phải vì một lần lưu bị từ chối.

### D6 — Tất-cả-hoặc-không (Q12)

Một lần `Cập nhật` có đúng hai kết quả:

- **Thành công**: mọi hàng hợp lệ, L1 xong, L2 xong. Stage được chốt. Nháp OCR tạm được dọn.
- **Thất bại**: **không ghi gì**. Bản nháp còn nguyên từng ký tự. Hàng lỗi được tô đỏ kèm lý do.

Sửa trực tiếp C5: bỏ việc gọi commit vô điều kiện rồi mới kiểm `failedCount`.

### D7 — Server đồng ý trước, màn hình đổi sau (Q11a)

Thứ tự bắt buộc cho **mọi** thao tác phá huỷ (xoá người, cascade bỏ gán):

1. Chụp trạng thái hiện tại (để rollback).
2. Gửi server.
3. Server đồng ý → mới cập nhật bản gốc + vẽ lại.
4. Server từ chối → **rollback về ảnh chụp**, báo lỗi, không mất gì.

Sửa trực tiếp C4. Xoá người là hành động phá huỷ — không optimistic.

### D8 — Cổng commit-hoặc-huỷ (Q3, Q5)

Stage có **hai trạng thái**: *đã chốt* và *đang sửa dở*.

Khi Stage **đang sửa dở** mà user thao tác ở nơi khác (kéo thả sơ đồ, bỏ gán thẻ, đổi Chủ đất/Nhận,
lưu hồ sơ, đổi tài sản), hệ thống **chặn thao tác đó** và hiện popup buộc chọn:

- **Cập nhật phần vừa sửa** → chạy D6; thành công thì cho thao tác tiếp; thất bại thì ở lại Stage.
- **Huỷ thay đổi** → bỏ nháp, Stage về bản đã chốt, cho thao tác tiếp.

Không có lựa chọn thứ ba. Không tự chọn hộ. Đúng nguyên tắc "đẩy quyết định cho user".

Hệ quả bắt buộc: thao tác ở Diagram **không được** vẽ lại Stage từ dữ liệu đã lưu — vì tại thời điểm
đó Stage chắc chắn không còn nháp. Nếu phải vẽ lại thì vẽ từ bản gốc trong trang.

### D9 — Cascade prune một chiều, có xác nhận (Q9a, Q10, Q15a)

**Phân biệt hai hành động** — user story 29:

| Hành động | Làm ở đâu | Người đó ở Stage | Người đó ở Pool |
|---|---|---|---|
| **Bỏ gán** | Diagram | còn nguyên | quay về Pool |
| **Xoá người** | chỉ Stage, nút cuối hàng | bị xoá | mất khỏi Pool |

**Lan truyền chỉ đi một chiều: Stage → Diagram.** Không bao giờ có đường Diagram → Stage.

Khi commit một Stage đã xoá người, server **tự dọn** mọi reference tới người đó trong Diagram
(sửa C1/C2/C3 và thực thi `workflow.md` §6). Không còn từ chối lần lưu vì lý do này.

**Lan truyền tới hết nhánh (A→B→C).** Xoá B làm C mất chỗ neo. Quy tắc:

- C bị **bỏ gán** khỏi Diagram, **vẫn còn** trong Stage, **quay về Pool**.
- Lan truyền chạy tới hết: cháu, chắt của nhánh cũng bị bỏ gán và về Pool.
- Node cấu trúc không mang người thì bị dọn; node không được xoá thì **giữ node, bỏ người** khỏi nó.

**Bắt buộc xác nhận trước.** Trước khi commit một Stage có xoá người mà việc đó gây bỏ gán,
hiện hộp xác nhận nêu **chính xác**:

- ai bị xoá khỏi Stage,
- ai bị bỏ gán khỏi sơ đồ và **quay về Pool** (danh sách đầy đủ theo nhánh),
- node cấu trúc nào bị dọn.

User xác nhận → chạy D7. User huỷ → **không gì thay đổi**, kể cả nháp.

Dữ liệu cho hộp thoại **đã có sẵn** trong code hiện tại (hàm thu thập người bị ảnh hưởng theo nhánh).

### D10 — Phạm vi ghi và phát hiện đè (Q7a)

- Lưu Diagram **chỉ ghi phần Diagram**. Lưu Stage **chỉ ghi phần Stage**.
  Không endpoint nào được ghi cả khối trạng thái hồ sơ.
- Mỗi hồ sơ có một **số phiên bản**. Client gửi kèm phiên bản mình đang giữ.
  Lệch → server **từ chối** và báo "hồ sơ vừa được sửa, tải lại rồi thử lại".
  Sửa cơ chế "ai lưu sau thắng" (user story 39).
- **Bỏ** cách lấy nửa dữ liệu từ DB: mỗi endpoint làm việc với dữ liệu client gửi cho phần mình,
  và với phần còn lại thì **đọc để kiểm tra**, không **thay thế**.

### D11 — Bỏ cửa sau (Q13)

Chốt bảo vệ hiện có: hễ ai định gỡ cờ `inStaging` thì bị ép trả lại. Cờ `__allowClearStaging`
mở chốt đó. Vấn đề: chốt là **quy ước mềm** — code nào truyền cờ cũng mở được — và hiện nó được
dùng **trước khi** server đồng ý.

**Quyết định:** bỏ cờ. Người bị gỡ khỏi Stage **chỉ** qua một đường duy nhất:
nút xoá cuối hàng Stage → xác nhận cascade (D9) → server đồng ý (D7) → cập nhật bản gốc.

Không đường nào khác. Không cờ vượt rào. Đây là ranh giới kiến trúc, không phải quy ước.

### D12 — Đồ thị lan truyền đầy đủ (yêu cầu chi tiết của user)

Liệt kê **mọi cấp phụ thuộc**, không dừng ở cấp một.

#### Sửa dữ liệu người ở Stage rồi commit

```text
L0  Sửa trường của người P ở Stage (nháp)
 └─ L1  Bản gốc: bản ghi người P
     ├─ L2a bảng customers (kho dùng chung — ảnh hưởng MỌI hồ sơ khác dùng P)
     ├─ L2b case_state_json.stage của hồ sơ này
     ├─ L3a Hiển thị Pool của P (tính ra, không lưu)
     ├─ L3b Thẻ sơ đồ của P: tên, ngày sinh/chết (tra bản gốc → tự đúng theo D3)
     └─ L4  Nếu trường sửa là ngày sinh / ngày chết:
         └─ L5  engineInput đổi
             └─ L6  Engine tính lại
                 ├─ L7a Vòng di sản mở/đóng khác đi → **tập slot yêu cầu đổi**
                 │   └─ L8  Node/slot xuất hiện hoặc thành không hợp lệ
                 │       └─ L9  Có thể phát sinh bỏ gán → **cần xác nhận (D9)**
                 ├─ L7b Tỷ lệ nhận của từng người đổi
                 ├─ L7c Di sản chưa có người nhận đổi
                 └─ L7d Trạng thái engine đổi (hợp lệ / thiếu / chưa hỗ trợ)
                     └─ L10 Bảng người tham gia được dựng lại
                         ├─ L11a Xuất Word (đọc người tham gia + kết quả engine)
                         ├─ L11b Xem trước hồ sơ
                         └─ L11c Hiển thị ở danh sách hồ sơ
```

**Cảnh báo cho user:** sửa `ngay_chet` **không** phải sửa hiển thị. Nó đổi vòng thừa kế,
đổi tập slot, và có thể làm gãy phần sơ đồ đã dựng. Theo `ux.md`, node đã có dữ liệu
**không được tự biến mất** — phải báo để user xử lý. Kết hợp D9: phải hiện xác nhận.

**Cảnh báo phạm vi:** `customers` là kho **dùng chung**. Sửa người ở hồ sơ này ảnh hưởng
hồ sơ khác đang dùng cùng người. Spec này **không** giải quyết vấn đề đó (xem *Out of Scope*),
nhưng phải nêu vì nó là phụ thuộc thật.

#### Xoá người ở Stage rồi commit

```text
L0  Xoá hàng người P ở Stage (nháp) → bấm Cập nhật
 └─ L1  Tính trước ảnh hưởng (chưa ghi gì)
     ├─ L2  P bị gỡ khỏi danh sách Stage
     ├─ L3  Node của P trong Diagram bị dọn
     └─ L4  **Lan truyền tới hết nhánh**: mọi node neo vào node của P
         └─ L5  Người ở các node đó bị **bỏ gán** (KHÔNG bị xoá khỏi Stage)
             └─ L6  Họ **quay về Pool**
 └─ L7  **Hộp xác nhận** liệt kê L2 + L5 + node cấu trúc bị dọn   ← user quyết
     ├─ Huỷ → không gì thay đổi
     └─ Đồng ý:
         └─ L8  Gửi server (D7)
             ├─ L9  Server dọn reference ngoài Stage
             ├─ L10 Engine tính lại → tỷ lệ, di sản chưa nhận, trạng thái
             ├─ L11 Người tham gia dựng lại
             └─ L12 Xuất Word / xem trước / danh sách đổi theo
         └─ L13 Server từ chối → rollback toàn bộ, nháp còn nguyên
```

#### Thao tác ở Pool

Pool **không có state riêng** (D3). Mọi thay đổi Pool là **hệ quả tính ra**. Ba nguồn:

| Nguồn | Pool đổi thế nào | Stage có đổi? |
|---|---|---|
| Commit Stage thêm người mới | người mới **vào** Pool (chưa gán) | — (nguyên nhân) |
| Commit Stage xoá người | người đó **ra khỏi** Pool | — (nguyên nhân) |
| Kéo người từ Pool vào slot | người đó **ra khỏi** Pool (chỉ ẩn khỏi Pool) | **Không** |
| Bỏ gán một thẻ ở Diagram | người đó **vào lại** Pool | **Không** |
| Xoá node làm gãy nhánh | **cả nhánh** người vào lại Pool | **Không** |
| Sửa dữ liệu người ở Stage | hiển thị Pool đổi theo | — (nguyên nhân) |

Bất biến: **không thao tác Pool nào được xoá hay sửa người ở Stage** (Q4, user story 25).
Người chỉ vào lại Pool nếu **vẫn còn** trong Stage.

#### Thao tác ở Diagram

| Thao tác | Đổi gì | Engine tính lại? | Stage có đổi? |
|---|---|---|---|
| Kéo người vào slot | gán `personId` vào node; ra khỏi Pool | Có | **Không** |
| Bỏ gán một thẻ | bỏ `personId`; về Pool | Có | **Không** |
| Xoá node có nhánh con | lan truyền tới hết; cả nhánh về Pool | Có | **Không** |
| Bật/tắt Chủ đất | cờ trên node | Có | **Không** |
| Bật/tắt Nhận | cờ trên node | Có | **Không** |
| Sửa quan hệ / thêm slot | cấu trúc node | Có | **Không** |
| Lưu sơ đồ | chỉ phần Diagram (D10) | Có | **Không** (user story 31) |

Sau **mọi** thao tác Diagram, chuỗi lan truyền: engine tính lại → tỷ lệ + di sản chưa nhận +
trạng thái → người tham gia dựng lại → xuất Word / xem trước / danh sách.

**Không** thao tác Diagram nào được ghi vào dữ liệu người ở Stage.

### D13 — Vẫn giữ nguyên (không đổi trong spec này)

- Stage nhận người từ 4 nguồn; OCR `Lưu` không tự ghi DB.
- Modal `x` chỉ thu nhỏ, không lưu/xoá gì (`workflow.md` §3).
- Trùng CCCD do user tự xử lý, hệ thống không tự gộp.
- Chỉ nút xoá cuối hàng Stage được xoá hàng.
- Quy tắc Chủ đất / Nhận và cách suy ra "người không nhận" (`workflow.md` §6).

---

## Testing Decisions

### Thế nào là test tốt ở đây

Test **hành vi quan sát được** ở mức seam cao nhất, không test chi tiết cài đặt.
Không assert tên hàm nội bộ, không assert hình dạng DOM trung gian.
Mỗi test phải diễn đạt được bằng một câu tiếng Việt mà user hiểu.

### Seam

Ưu tiên seam **đã có**, càng ít seam càng tốt:

| Seam | Đã có? | Test gì |
|---|---|---|
| Hàm chuẩn hoá + kiểm hợp lệ payload trạng thái hồ sơ (thuần, không DB) | **Có** — đã có bộ test | D5, D9 cascade, D10 phạm vi ghi |
| Endpoint lưu Stage / lưu Diagram (có DB) | **Có** | D2, D6, D7, D10 |
| Hàm thu thập người bị ảnh hưởng theo nhánh (thuần) | **Có** | D9 lan truyền A→B→C |
| Hàm chuẩn hoá input từ mọi nguồn | **Cần thêm** — đề xuất tách thành hàm thuần | D4 |

Đề xuất **một** seam mới duy nhất: tách chuẩn hoá input thành hàm thuần để test được cả 4 nguồn
mà không cần dựng UI.

### Bất biến phải có test canh

Mỗi dòng là một test hồi quy:

1. Xoá người ở Stage đang được gán trên sơ đồ → commit **thành công**, server tự dọn reference. *(chặn C1/C2/C3)*
2. Server từ chối lần lưu → mọi hàng Stage **còn nguyên**, không hàng nào mất. *(chặn C4)*
3. Một hàng lỗi → **không hàng nào** được chốt, nháp còn nguyên. *(chặn C5)*
4. Hàng lưu người thất bại → **báo lỗi rõ**, không bị lọc im lặng. *(chặn C6)*
5. Không đường nào từ Pool/Diagram xoá được người ở Stage — kiểm từng đường: bỏ gán, lan truyền, tải lại, lưu sơ đồ. *(Q4, chặn C7)*
6. A→B→C: xoá B → C **bỏ gán** khỏi sơ đồ, **vẫn còn** ở Stage, **về Pool**. *(D9)*
7. Huỷ hộp xác nhận cascade → **không byte nào** đổi, kể cả nháp. *(D9)*
8. Lưu sơ đồ **không** sửa được trường người của Stage. *(D10)*
9. Lưu Stage **không** làm mất dữ liệu riêng của Diagram còn hợp lệ. *(D10)*
10. Phiên bản lệch → từ chối, không đè. *(D10)*
11. Bốn nguồn nhập cùng một người → ra **cùng một dạng** hàng Stage. *(D4)*
12. Chuẩn hoá **không** tự sửa số giấy tờ, **không** tự điền trường thiếu. *(D4)*
13. Trùng CCCD → **cảnh báo**, không gộp, không xoá. *(D4)*
14. Sửa ngày chết → engine tính lại, slot đổi, **có** xác nhận nếu gây bỏ gán. *(D12)*
15. Validation **không** mutate: chạy kiểm nhiều lần, dữ liệu không đổi. *(D5)*
16. Đang sửa Stage dở + thao tác sơ đồ → **popup buộc chọn**, không tự chọn hộ. *(D8)*
17. Chọn "huỷ thay đổi" ở popup → Stage về bản đã chốt, thao tác kia chạy tiếp. *(D8)*
18. Chọn "cập nhật" ở popup, commit lỗi → ở lại Stage, thao tác kia **không** chạy. *(D8)*

### Prior art

Bộ test hiện có cho chuẩn hoá/kiểm tra payload trạng thái hồ sơ là mẫu tốt: thuần, không DB,
dựng payload rồi assert lỗi hoặc kết quả. Dùng đúng kiểu đó cho D5/D9/D10.
Test có DB đi theo mẫu test endpoint hiện có.

---

## Out of Scope

Những việc **không** làm trong spec này, cần scope riêng:

1. **Chuyển sang một-bản-gốc trong phần sơ đồ (D3 / Q14a).** Là refactor state React.
   Spec này chốt **hướng**; việc thực thi tách ticket riêng.
2. **Gộp hai endpoint thành một (Q10c).** Sạch hơn nhưng chạm `DIAGRAM-R1` đang dở.
3. **Dọn chồng lấn lưu trữ legacy** (`engine_state_json`, `diagram_payload`, bảng người tham gia).
   Đang theo dõi ở `DIAGRAM-R1/R2`.
4. **Chia sẻ người giữa nhiều hồ sơ.** `customers` là kho dùng chung; sửa người ở một hồ sơ
   ảnh hưởng hồ sơ khác. Vấn đề thật, **chưa** giải trong spec này.
5. **Đường kết nối / mũi tên trên sơ đồ.** `DIAGRAM-3`/`DIAGRAM-R3` đã hoãn, cần tiêu chí nghiệm thu riêng.
6. **Quy tắc nghiệp vụ thừa kế** (cách chia, thế vị, từ chối). Ở `spec.md`, vẫn là DRAFT.
7. **Luồng OCR và ba file OCR đang sửa dở chưa được duyệt** (theo `memory-bank/CURRENT.md`).
   Spec này **không** chạm.
8. **Tách Stage/Pool thành capability dùng chung.** `contract.md` nói rõ: hoãn tới khi có
   domain thứ hai xác nhận.
9. **Nhiều tài sản.** Người nhận đang tính theo tài sản hiện tại; mở rộng là việc riêng.

---

## Further Notes

### Cần user duyệt trước khi implement

Theo `AGENTS.md`, chỉ user duyệt spec nghiệp vụ. Spec này **chưa** normative.

Ba điểm cần duyệt rõ:

1. **D9 sửa hành vi quan sát được**: xoá người ở Stage từ "bị từ chối lưu" thành
   "hỏi xác nhận rồi dọn sơ đồ". Đúng `workflow.md` §6, khác runtime hiện tại.
2. **D8 thêm popup mới** chưa có trong `workflow.md`. Cần thêm vào `workflow.md` sau khi duyệt.
3. **D10 thêm số phiên bản** — đổi hợp đồng API.

### Đề xuất ADR

Quyết định **D3 + D10** (một bản gốc, ghi có phạm vi, phát hiện đè) đủ ba tiêu chí ADR:
khó đảo, người đọc sau sẽ thắc mắc vì sao, và là kết quả đánh đổi thật.

Đề xuất viết một ADR ngắn trong `docs/architecture/decisions/` **sau khi** user duyệt spec.

### Thứ tự lát thực thi (đề xuất, chờ duyệt)

| Lát | Nội dung | Vì sao trước |
|---|---|---|
| S1 | Test hồi quy tái hiện đúng hai triệu chứng (1–5 ở trên) | Có bằng chứng lỗi trước khi sửa |
| S2 | D2 + D5 + D6: kiểm trước, tất-cả-hoặc-không, báo lỗi rõ | Chặn mất dữ liệu, đổi ít |
| S3 | D7 + D11: server đồng ý trước, bỏ cửa sau | Chặn mất dữ liệu do rollback thiếu |
| S4 | D9: cascade một chiều + xác nhận | Cần S2/S3 xong mới an toàn |
| S5 | D8: popup commit-hoặc-huỷ | Cần cổng commit đã đáng tin |
| S6 | D10: phạm vi ghi + phiên bản | Đổi hợp đồng API |
| S7 | D4: một hàm chuẩn hoá + seam test | Độc lập, làm song song được |
| — | D3 (một bản gốc ở sơ đồ) | **Ticket riêng**, ngoài phạm vi |

Mỗi lát qua review gate của `AGENTS.md` trước khi sang lát sau.

### Chưa xác minh được

User báo "đỏ viền các hàng" nhưng chưa tái hiện ổn định. Tôi tìm được cơ chế tô viền đỏ
là inline style đặt **theo từng hàng**, và điều kiện duy nhất ở client là thiếu họ tên.
Giả thuyết khớp nhất: cả lần lưu bị từ chối (C1/C2) làm mọi hàng cùng fail.
**Chưa chứng minh được bằng đường code cụ thể.** Test S1 phải tái hiện được trước khi
tuyên bố đã sửa.
