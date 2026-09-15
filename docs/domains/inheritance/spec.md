# Nghiệp vụ sơ đồ thừa kế

> **Trạng thái:** DRAFT chờ user đọc và duyệt lần cuối.
> **Cập nhật:** 22/08/2026.
> **Vai trò:** đề xuất draft, chưa chuẩn tắc cho đến khi user phê duyệt rõ ràng.
>
> Bài toán kiểm thử nằm tại `research/case-catalog.md`; UI/UX nằm tại `ux.md`;
> luồng Stage/Pool/Diagram nằm tại `workflow.md`; hợp đồng kỹ thuật nằm tại
> `technical/inheritance-engine.md`.
>
> Khi tài liệu này mâu thuẫn với code đang chạy, đó là bằng chứng phải báo, không
> phải quyền tự sửa một bên. Mục 11 ghi rõ chỗ nào code đã khớp và chỗ nào phải sửa.
>
> Các số điều luật cụ thể **không** được ghi trong tài liệu này. Nội dung quy định
> được diễn đạt bằng lời; việc đối chiếu điều luật cần người có chuyên môn pháp lý
> xác nhận trước khi tài liệu thành chuẩn tắc.

## 1. Nguyên tắc bất biến

| Mã | Bất biến |
|---|---|
| `INV-1` | Engine tính bằng phân số chính xác. Không dùng số thực trong bất kỳ phép tính nào. |
| `INV-2` | Phần trăm chỉ là định dạng hiển thị. Giá trị pháp lý luôn là phân số. |
| `INV-3` | Quan hệ gia đình chỉ lấy từ dữ liệu quan hệ tường minh, không suy từ vị trí thẻ, nhãn vai trò, thế hệ, nhóm gia đình hay thẻ đầu tiên. |
| `INV-4` | Mỗi vòng di sản phải bảo toàn riêng: `tổng phần đã chia + phần chưa có người nhận = giá trị vòng đó`. Bảo toàn toàn hồ sơ là kết quả tổng hợp, không phải điều kiện thay thế. |
| `INV-5` | Kết quả không phụ thuộc thứ tự phần tử trong dữ liệu vào. Đổi thứ tự node phải cho kết quả y hệt. |
| `INV-6` | Cùng dữ liệu vào và cùng phiên bản engine cho cùng kết quả. |
| `INV-7` | Một người nhận từ nhiều nguồn thì các phần được cộng dồn. Không nguồn nào ghi đè nguồn khác. |
| `INV-8` | Không mở vòng di sản giá trị `0`. |
| `INV-9` | Engine không tạo người, không đoán người vào ô trống, không tự nối quan hệ còn thiếu. |
| `INV-10` | Trường hợp ngoài năng lực engine phải trả trạng thái `unsupported` kèm mã lý do, không tính gần đúng. |
| `INV-11` | Engine không khoá thao tác của user. Kết quả engine là thông tin để user tự xem và tự quyết; điều kiện chặn lưu do `workflow.md` quy định, không do tài liệu này. |
| `INV-12` | Mọi số hiển thị và mọi số in ra văn bản đều đọc từ kết quả engine. Không lớp nào tự tính lại. |

## 2. Thuật ngữ

Tài liệu tách ba lớp khác nhau mà mô hình cũ gộp làm một. Tách lớp là điều kiện để
văn bản công chứng gọi đúng tên loại việc.

| Thuật ngữ | Nghĩa | Ai quyết định |
|---|---|---|
| **Chủ đất** | Người có phần sở hữu gốc trước khi chạy thừa kế. | User bật cờ trên ô |
| **Suất theo pháp luật** | Phần một người/nhánh được hưởng trong một vòng di sản nếu chia theo pháp luật, chưa tính thoả thuận. | Engine tính |
| **Phần thực nhận** | Phần cuối cùng một người nhận sau khi áp dụng thoả thuận phân chia. | Engine tính từ suất + cờ `Nhận` |
| **Nhận** | Cờ trên ô, thể hiện ý chí của người còn sống trong **thoả thuận phân chia di sản**. | User bật/tắt |
| **Người nhường phần** | Người có suất theo pháp luật lớn hơn `0` nhưng tắt `Nhận`. Phần của họ được chia lại cho những người còn nhận trong cùng vòng. | Suy ra |
| **Người chưa quyết** | Người có suất lớn hơn `0` mà ô chưa có quyết định `Nhận`. | Suy ra |
| **Người từ chối nhận di sản** | Thuật ngữ pháp lý, chỉ tồn tại khi hồ sơ có văn bản từ chối riêng. | Dữ liệu pháp lý ngoài Diagram |

Quy tắc cứng về thuật ngữ:

- `Nhận=false` **không** phải từ chối nhận di sản. Hai loại việc khác nhau: thoả thuận
  phân chia dồn phần cho người khác là hợp pháp và phần đó đi theo thoả thuận; từ chối
  nhận di sản phải lập văn bản riêng và phần bị từ chối chia lại theo pháp luật.
- Engine, giao diện và văn bản **không được** suy `Người từ chối` từ `Nhận=false`.
  Chỗ dành cho `Người từ chối` để trống khi hồ sơ không có văn bản từ chối.
- Chủ đất còn sống luôn giữ phần sở hữu gốc của mình. Tắt `Nhận` không lấy đi phần đó.
  Nếu phần sở hữu gốc chuyển cho người khác thì đó là tặng cho/chuyển quyền — ngoài
  phạm vi tài liệu này, và không được ghi nguồn là thừa kế.
- Thoả thuận phân chia chỉ diễn ra giữa những người **có suất trong cùng một vòng di sản**.
  Dồn phần cho người không có suất là loại việc khác, xem mục 7.

## 3. Sở hữu gốc

- Phạm vi hiện tại là **một tài sản** cho mỗi lần tính. Nhiều tài sản là việc riêng,
  xem mục 10.
- Phải có ít nhất một `Chủ đất`. Không có thì trả `invalid: missing_land_owner`.
- Tỷ lệ sở hữu gốc theo quy tắc **tất-cả-hoặc-không** cho mỗi tài sản:

| Trạng thái nhập | Xử lý |
|---|---|
| Không chủ đất nào có tỷ lệ | Chia đều `1/n`. Giao diện hiện rõ đang chia đều. |
| Mọi chủ đất có tỷ lệ và tổng đúng bằng `1` | Dùng đúng tỷ lệ đã nhập. |
| Điền một phần, để trống một phần | `invalid: partial_ownership_ratio` |
| Điền hết nhưng tổng khác `1` | `invalid: ownership_ratio_sum` kèm tổng thực tế |
| Có tỷ lệ bằng `0` hoặc âm | `invalid: ownership_ratio_value` |

- Nguồn của tỷ lệ không đều là giấy chứng nhận quyền sử dụng đất. Engine không suy
  tỷ lệ từ quan hệ, thứ tự thẻ hay số người.
- Không bắt user xác nhận thêm khi để trống. Để trống **là** phát biểu "chia đều", vì
  sở hữu chung không ghi rõ phần thì phần bằng nhau.

## 4. Ngày và thời điểm

### 4.1 Ba lớp, không được trộn

| Lớp | Nội dung | Ràng buộc |
|---|---|---|
| **Nhập** | Giữ đúng thứ user gõ: `2010` giữ là `2010`, `01/01/2010` giữ là `01/01/2010`. | Không bịa ngày, không thoái hoá ngày đầy đủ thành năm |
| **Tính** | Chỉ có năm thì tính như `01/01/yyyy`. | Quy ước cố định, xem 4.2 |
| **Hiển thị và văn bản** | In đúng thứ user đã gõ. | **Cấm** suy `01/01` thành `yyyy` |

Lớp tính **không có** khái niệm độ chính xác ngày. Engine luôn thấy một ngày duy nhất.
Việc ghi lại user đã gõ gì thuộc lớp nhập và không đổi một phép tính nào.

### 4.2 Quy ước năm — quyết định đã chốt của user

> Chỉ có năm thì cố định thành `01/01/yyyy`. Hai người cùng chết năm 2010 được coi là
> chết cùng thời điểm `01/01/2010`. Nếu user phân biệt được ai chết trước thì user đã
> điền ngày đầy đủ, chứ không điền `yyyy` chung chung. Điền `yyyy` **là** phát biểu
> "không phân biệt thứ tự", không phải dữ liệu khuyết.

Hệ quả bắt buộc:

- Không thêm khái niệm độ chính xác vào lớp tính.
- Không coi "chỉ có năm" là dữ liệu thiếu, không cảnh báo, không chặn.
- Không nơi nào trong hệ thống được hiểu ngày khác lớp tính.
- Chết cùng thời điểm thì hai người không thừa kế của nhau; phần của mỗi người đi
  xuống hậu duệ theo thế vị.

### 4.3 So sánh thời điểm

- Chỉ so đến cấp ngày. Không giờ, không phút. Không tách giờ để tìm ai chết trước
  trong cùng một ngày.
- Cùng ngày sau chuẩn hoá là **cùng thời điểm**: dùng ảnh chụp tài sản đầu ngày, và
  những người chết cùng ngày không nhận chéo di sản của nhau.
- Ngoại lệ ưu tiên duy nhất: nhánh thế vị của con, cháu, chắt vẫn mở theo mục 6.
- Ô ngày chết rỗng nghĩa là còn sống. Không suy ngày chết từ tuổi, từ ngày cấp giấy
  tờ hay từ vị trí thế hệ.

### 4.4 Lệch độ chính xác trong cùng một năm

A chết `2010`, B chết `15/06/2010`. Sau chuẩn hoá là `01/01/2010` và `15/06/2010`, hai
ngày khác nhau, nên A chết trước B và B nhận từ A.

Đây là **hệ quả được chấp nhận** của quy ước 4.2, không phải lỗi. Nhưng nó không được
im lặng:

- `Xem cách tính` phải hiện một dòng nêu cơ sở, dạng
  `A chết trước B (A chỉ có năm 2010 → tính là 01/01/2010)`.
- Kết quả không đổi vì lý do này. Dòng giải thích chỉ để công chứng viên thấy cơ sở và
  tự quyết có bổ sung ngày hay không.

### 4.5 So ngày chết với ngày sinh

Khi một trong hai ngày chỉ có năm thì **so ở cấp năm**, không so ngày đã chuẩn hoá.

Ví dụ bắt buộc đúng: sinh `15/06/2010`, chết `2010`. So cấp năm cho `2010 = 2010`,
hợp lệ. Nếu so ngày đã chuẩn hoá thì `01/01/2010 < 15/06/2010` và hệ thống báo lỗi
sai, buộc user bịa một ngày chết mà họ không biết. Trẻ mất trong năm sinh là trường
hợp thật trong hồ sơ thừa kế.

Chỉ khi cả hai ngày đều đầy đủ thì mới so đến cấp ngày.

### 4.6 Miền giá trị ngày

- Chuẩn hoá xảy ra ở **lớp nhập**. Mọi định dạng nguồn (`dd/mm/yyyy`, ISO, serial
  Excel, số năm) được chuyển về một dạng nội bộ duy nhất tại đây.
- Engine chỉ nhận dạng nội bộ đó cộng dạng chỉ có năm. Engine không phải nơi đoán
  định dạng.
- Ngày không phân giải được là lỗi ở lớp nhập theo `workflow.md`, hiện đúng hàng dữ
  liệu sai. Nếu vẫn tới engine thì trả `invalid: invalid_death_date` kèm người cụ thể.

## 5. Vòng di sản

Mỗi chủ đất bắt đầu với phần sở hữu gốc độc lập.

1. Gom người chết theo ngày, xử lý các ngày tăng dần.
2. Chụp tài sản đang giữ **đầu ngày**, trước khi tính bất kỳ người chết nào trong ngày đó.
3. Chỉ mở vòng di sản nếu người chết thực sự có tài sản: phần sở hữu gốc, hoặc phần
   thừa kế đã thực sự nhận ở ngày trước.
4. Hàng thừa kế thứ nhất của một vòng gồm cha, mẹ, vợ hoặc chồng và các nhánh con.
5. Cha, mẹ, vợ/chồng chỉ là đơn vị nhận nếu còn sống tại ngày mở vòng. Không áp dụng
   thế vị cho cha, mẹ, vợ/chồng.
6. Mỗi người con là **một đơn vị nhánh**, không phải một người. Chi tiết ở mục 6.
7. Chia đều cho các đơn vị hợp lệ, rồi áp dụng thoả thuận phân chia ở mục 7.
8. Người chết **sau** nguồn di sản nhận phần của mình bất kể cờ `Nhận`, vì tài sản đó
   phải đi vào di sản thực tế của họ. Cờ `Nhận` chỉ áp dụng cho người còn sống.
9. Phần đã thực sự nhận trở thành tài sản của người nhận và có thể mở vòng di sản tiếp
   theo tại ngày họ chết.

Việc một người có ngày chết **không** tự sinh toàn bộ gia đình. Hệ thống chỉ yêu cầu
những ô cần cho một vòng di sản đang mở hoặc một nhánh thế vị đang hoạt động.

## 6. Thế vị

Thế vị dùng cùng dòng phân bổ của mục 5 nhưng coi mỗi người con là một nhánh.

- Mỗi nhánh trước hết có phần mà người con lẽ ra được hưởng nếu còn sống.
- Con còn sống tại ngày mở thừa kế: phần nhánh thành tài sản của người con.
- Con chết **sau** ngày mở thừa kế: vẫn nhận phần nhánh; phần đó vào di sản của họ ở
  ngày họ chết.
- Con chết **trước hoặc cùng thời điểm**: phần nhánh đi qua vị trí của họ và xuống
  trực tiếp các con của họ. Nếu người cháu cũng chết trước hoặc cùng thời điểm thì
  dòng tiếp tục xuống chắt **trong chính nhánh đó**.
- Chia đều theo từng nhánh ở **từng cấp**, không làm phẳng toàn bộ hậu duệ rồi chia đều.
- "Đi qua" chỉ là đường dẫn tính toán. Phần thế vị **không** từng thuộc sở hữu của
  người chết trước, không cộng vào di sản của họ, và cờ `Nhận` trên ô của họ không giữ
  hoặc chặn dòng thế vị.
- Chỉ hậu duệ trong chính nhánh được nhận phần thế vị. Cha, mẹ, vợ/chồng của người
  chết trước không tham gia chia phần này.
- Khi mở nhánh thế vị, sinh ô vợ/chồng của người chết trước để thể hiện đúng cặp cha
  mẹ của các con. Ô này chỉ biểu diễn quan hệ và **không** nhận phần thế vị.
- Nếu người chết trước có phần sở hữu gốc hoặc đã thực sự nhận tài sản từ nguồn khác,
  tài sản riêng đó vẫn mở một vòng di sản độc lập. Trong vòng đó, vợ/chồng của họ là
  người thừa kế hàng thứ nhất bình thường.

### 6.1 Giới hạn độ sâu

Thế vị dừng ở **chắt**. Dưới chắt không còn là thế vị.

- Vượt giới hạn thì trả `unsupported: representation_depth_exceeded` kèm nhánh cụ thể.
- Cấm đệ quy không điểm dừng. Cấm âm thầm hỗ trợ sâu hơn giới hạn.
- Cấm âm thầm làm mất nhánh khi tới giới hạn.

### 6.2 Nhánh không còn người thế vị

- Con chết trước/cùng thời điểm mà không còn con, cháu, chắt để thế vị: nhánh đó kết
  thúc và **bị loại khỏi các đơn vị chia**. Phần di sản chia lại cho các đơn vị hợp lệ
  còn lại trong cùng vòng.
- Ví dụ: X có hai nhánh B và C; B chết cùng thời điểm và không có hậu duệ; C nhận toàn
  bộ phần di sản của X.
- Nhánh bị loại **không** tạo sở hữu cho người trung gian, không chuyển cho vợ/chồng
  hoặc cha mẹ của người trung gian, và không giữ phần riêng.
- Đây là quy ước tính toán để tài sản không bị mất, không phải kết luận rằng người
  trung gian đã từng sở hữu phần đó.
- Chỉ khi **toàn bộ** vòng không còn đơn vị hợp lệ thì vòng đó giữ phần chưa chia và
  trả trạng thái theo mục 8.

## 7. Thoả thuận phân chia và cờ `Nhận`

### 7.1 Ý nghĩa

Cờ `Nhận` là ý chí của **người còn sống** trong một thoả thuận phân chia di sản. Đây là
loại việc công chứng hợp pháp: các đồng thừa kế thoả thuận dồn phần cho một hoặc một số
người. Nó khác từ chối nhận di sản, và khác tặng cho.

Vì vậy:

- Người đã có ngày chết **không** tham gia thoả thuận. Ô của họ hiện cờ `Nhận` ở trạng
  thái chỉ đọc, kèm lý do đọc được, ví dụ "người đã chết không tham gia thoả thuận phân
  chia". Không ẩn cờ, vì ẩn làm user tưởng thẻ bị lỗi.
- Quyền hưởng của người đã chết do dòng thời gian quyết định, theo mục 5 điểm 8.

### 7.2 Mặc định

Không có mặc định ngầm. Ô chưa có quyết định là **`chưa quyết`**, khác cả `Nhận=true`
và `Nhận=false`.

- Tự mặc định `true` là hệ thống khai một ý chí không ai phát biểu — trái `INV-9`.
- Tự mặc định `false` cũng là suy đoán, và làm mọi ô mới trông như đã nhường phần.
- `chưa quyết` phải phân biệt được với `đã quyết không nhận` trong kết quả, xem mục 8.

Ba lớp (engine, hợp đồng lưu, bảng người tham gia) phải dùng **cùng một** mặc định.

### 7.3 Phạm vi có hiệu lực

Cờ `Nhận` chỉ có nghĩa khi suất theo pháp luật của người đó trong vòng đang xét lớn
hơn `0`.

- Bật `Nhận` cho người không có suất thì **không tạo ra phần nào**, và hệ thống phải
  **cảnh báo** `receive_without_entitlement` để user biết thao tác đó không có hiệu lực.
  Cấm im lặng.
- Dồn phần cho người không có suất là tặng cho hoặc chuyển quyền, không phải thừa kế.
  Ngoài phạm vi tài liệu này.

### 7.4 Chia lại khi có người nhường phần

- Người còn sống tắt `Nhận` bị loại khỏi đơn vị nhận của vòng đó; mẫu số tính lại giữa
  các đơn vị hợp lệ còn lại **trong cùng vòng**.
- Phần sở hữu gốc của chủ đất còn sống **không** bị loại bởi `Nhận=false`.
- Việc chia lại chỉ xảy ra trong cùng một vòng di sản. Không bao giờ chuyển phần chưa
  có người nhận của vòng này sang một vòng khác chỉ để tổng bằng `1` — đây là hệ quả
  trực tiếp của `INV-4`.

### 7.5 Nhường phần bên trong nhánh thế vị

Người nhường phần ở một cấp làm phần đó dồn xuống các đơn vị hợp lệ còn lại trong
**cùng nhánh**, kể cả khi họ ở thế hệ khác.

Ví dụ chuẩn: X chết. A là con, chết trước X. A có hai con: C còn sống nhưng tắt `Nhận`,
D chết trước X và để lại E còn sống.

- Suất theo pháp luật trong nhánh A: C `1/2` nhánh, E `1/2` nhánh.
- Phần thực nhận: E nhận **toàn bộ** phần nhánh A, vì C nhường phần.
- Kết quả giải thích **phải** cho thấy hai lớp này. Một dòng gộp kiểu
  `E nhận 1/2 (X, thế vị nhánh A)` là không đủ, vì nó che mất việc phần vượt lên là do
  C thoả thuận nhường, không phải do pháp luật.

## 8. Trạng thái kết quả

Bốn trạng thái, nghĩa khác nhau đối với user: tôi nhập sai, tôi cần quyết thêm, tôi
thiếu dữ liệu, hay máy không làm được việc này.

| Trạng thái | Nghĩa với user | Ví dụ mã lý do |
|---|---|---|
| `invalid` | Dữ liệu vào sai hoặc mâu thuẫn, chưa tính được gì. | `missing_land_owner`, `partial_ownership_ratio`, `ownership_ratio_sum`, `ownership_ratio_value`, `invalid_death_date`, `duplicate_person`, `dangling_parent`, `self_parent`, `self_spouse`, `spouse_conflict`, `too_many_parents`, `ancestry_cycle` |
| `incomplete` | Tính được nhưng còn phần chưa có người nhận vì cần user quyết hoặc bổ sung. | `all_receivers_declined`, `receivers_undecided` |
| `unsupported` | Dữ liệu hợp lệ nhưng bài toán ngoài năng lực engine. | `second_order_required`, `representation_depth_exceeded`, `unequal_base_ownership_source` |
| `complete` | Đã chia hết theo đúng quy tắc, mọi vòng bảo toàn. | — |

Thứ tự ưu tiên khi nhiều điều kiện cùng đúng:

```text
invalid > unsupported > incomplete > complete
```

Quy tắc cứng:

- `complete` chỉ khi không có lỗi, mọi vòng bảo toàn theo `INV-4`, và không còn phần
  chưa có người nhận.
- **Cấm dùng chung một mã** cho hai nguyên nhân khác nhau. Cụ thể, ba trường hợp sau
  phải tách:

| Tình huống | Mã | Vì sao khác nhau |
|---|---|---|
| Không còn ai ở hàng thứ nhất | `unsupported: second_order_required` | Là kết luận nghiệp vụ: phần này thuộc hàng thừa kế sau. User nhập thêm cũng không giải quyết được. |
| Có người ở hàng thứ nhất nhưng tất cả tắt `Nhận` | `incomplete: all_receivers_declined` | Là thoả thuận phân chia chưa chỉ ra ai nhận. |
| Có người ở hàng thứ nhất nhưng chưa ai quyết | `incomplete: receivers_undecided` | User chưa thao tác, khác với đã quyết không nhận. |

- Nhãn hiển thị của `unsupported` phải khác hẳn kết quả đã tính, để không ai đọc thành
  "đã chia xong". Đặc biệt: trường hợp người chết không còn vợ/chồng, cha/mẹ và con là
  trường hợp **thường gặp**, và quy ước 4.2 làm nó xuất hiện nhiều hơn (hai vợ chồng
  cùng chết trong một năm mà không có con thì cả hai vòng đều rơi vào đây).
- Mọi trạng thái khác `complete` vẫn giữ nguyên dữ liệu user đã nhập. Engine không xoá,
  không dọn, không tự sửa quan hệ, theo `INV-11`.

## 9. Kết quả giải thích và giá trị đưa vào văn bản

### 9.1 Hai lớp trong kết quả

Kết quả engine phải giữ **cả hai** lớp, không chỉ tổng cuối:

| Lớp | Nội dung | Dùng để |
|---|---|---|
| Suất theo pháp luật | Ai được xét trong vòng nào, suất của từng người/nhánh | Chứng minh cơ sở pháp luật |
| Phần thực nhận | Sau khi áp dụng thoả thuận phân chia | Con số ghi vào văn bản |

Không có lớp thứ nhất thì không thể chứng minh được phần vượt lên của một người đến từ
thoả thuận, và văn bản sinh ra sẽ gọi sai tên loại việc.

### 9.2 `Xem cách tính`

Mỗi người nhận có một dòng, dùng phân số chính xác, ghi nguồn trong ngoặc:

```text
Người A nhận: 17/40 = 3/10 (X) + 1/10 (Y) + 1/40 (Z)
Người B nhận: 1/2 = 1/4 (X) + 1/4 (Y, thừa kế)
Người C nhận: 1/6 = 1/6 (X, thế vị nhánh Y)
```

Khi có thoả thuận phân chia hoặc lệch độ chính xác ngày, thêm dòng cơ sở:

```text
Người E nhận: 1/4 = 1/8 (X, thế vị nhánh A) + 1/8 (C nhường phần, thoả thuận phân chia)
Cơ sở thứ tự: A chết trước B (A chỉ có năm 2010 → tính là 01/01/2010)
```

- Thế vị ghi nguồn di sản thật và nhánh đi qua, không ghi người chết trước như thể họ
  là nguồn di sản.
- Phần đến từ thoả thuận phải ghi rõ là thoả thuận, không ghi gộp vào thừa kế.
- Không hiển thị JSON, tên trường kỹ thuật hay chi tiết từng vòng theo mặc định.
- Giao diện chỉ đọc kết quả engine, không tự tính lại (`INV-12`).

### 9.3 Giá trị pháp lý trong văn bản

- Con số pháp lý trong văn bản là **phân số**. Phần trăm chỉ được đi kèm, không được
  đứng một mình.
- Nguồn duy nhất là phần cuối dạng phân số của engine. **Cấm** lấy phần trăm đã làm
  tròn rồi in ra như con số pháp lý.
- Lý do: ba người mỗi người `1/3` thì phần trăm làm tròn hai chữ số cho `33.33` ba lần,
  tổng `99.99`. Trong văn bản khai nhận hoặc phân chia di sản, con số này không cộng đủ.
- Ngày trong văn bản in đúng thứ user đã nhập, theo 4.1. Cấm in một ngày `01/01` thật
  thành chỉ có năm, và cấm in một dữ liệu chỉ có năm thành `01/01`.

## 10. Ngoài phạm vi

Trong phạm vi: thừa kế theo pháp luật hàng thứ nhất, thế vị theo chiều con/cháu/chắt,
nhiều chủ đất, nhiều vòng di sản nối tiếp, thoả thuận phân chia qua cờ `Nhận`, một tài sản.

Ngoài phạm vi, phải trả `unsupported` kèm mã lý do, **không** tính gần đúng:

| Việc | Ghi chú |
|---|---|
| Hàng thừa kế thứ hai và thứ ba | Thường gặp; xem cảnh báo ở mục 8 |
| Di chúc | Chưa có đầu vào |
| Từ chối nhận di sản theo văn bản | Chưa có đầu vào; cấm suy từ `Nhận` |
| Truất quyền hưởng, người bị tước quyền hưởng | Chưa có đầu vào |
| Thai nhi đã thành thai trước thời điểm mở thừa kế | Chưa có đầu vào |
| Tặng cho, chuyển quyền | Loại việc khác |
| Chuyển cho người ngoài Diagram | Loại việc khác |
| Nhiều tài sản trong một hồ sơ | Cần scope riêng |
| Hôn nhân đã chấm dứt trước ngày chết | Cần thuộc tính hiệu lực theo thời điểm |
| Quan hệ chưa được xác nhận | Cần trạng thái xác nhận |

**Không** đưa vào danh sách ngoài phạm vi: con nuôi hợp pháp và cha mẹ nuôi. Quá phổ
biến trong hồ sơ công chứng để trả `unsupported`. Về dữ liệu, đây là một thuộc tính trên
quan hệ cha/mẹ–con, không phải một mô hình khác. Giới hạn tối đa hai cha/mẹ hiện tại
không đủ cho người có cả cha mẹ đẻ và cha mẹ nuôi; xem mục 11.

Tài liệu này **không** quy định điều kiện chặn lưu, popup, cascade hay quyền xoá dữ
liệu. Những việc đó thuộc `workflow.md` và spec luồng dữ liệu.

## 11. Đối chiếu code hiện tại

Ghi lại để lần review sau kiểm được, và để không ai sửa thứ đã đúng.

### 11.1 Code đã khớp tài liệu này

| Nội dung | Bằng chứng |
|---|---|
| Chỉ có năm thì tính `01/01/yyyy` | `services/inheritance_engine.py:44-45` |
| Ảnh chụp tài sản đầu ngày cho nhóm người chết cùng ngày | `services/inheritance_engine.py:370-375` |
| Chết cùng thời điểm không nhận chéo | `services/inheritance_engine.py:293-306` |
| Nhánh con chết cùng thời điểm vẫn mở thế vị | `services/inheritance_engine.py:313-328` |
| Người chết sau nguồn di sản nhận bất kể cờ `Nhận` | `services/inheritance_engine.py:303-306` |
| Cờ `Nhận` của người đã chết bị bỏ qua khi tính | `services/inheritance_engine.py:303-306` |
| Thế vị chia theo từng nhánh, không làm phẳng | `services/inheritance_engine.py:308-350` |
| Không mở vòng di sản giá trị `0` | `services/inheritance_engine.py:371-375` |
| Kết quả độc lập thứ tự node | `sorted()` tại `:322`, `:333`, `:338`, `:409` |
| Mỗi vòng chia hết phần của mình | `credit()` tại `:344-350` |
| Đã có test cho quy ước năm | `tests/test_inheritance_engine.py:181`, `:192` |

Quy ước 4.2 vì vậy là **ghi tài liệu cho khớp code**, không phải sửa engine.

### 11.2 Code phải sửa

| # | Vấn đề | Bằng chứng | Điều khoản |
|---|---|---|---|
| 1 | Mọi ngày `01/01` bị thu về chỉ còn năm khi hiển thị và khi in Word. Ngày `01/01` thật bị in sai trong văn bản công chứng; user không phân biệt được ngày thật với ngày chuẩn hoá; đọc–ghi một vòng làm ngày đầy đủ thoái hoá thành năm. | `routers/customers.py:98-100`, `services/word_engine.py:104-111` | 4.1, 9.3 |
| 2 | Văn bản in phần trăm đã làm tròn dạng số thực, không phải phân số. Ba người `1/3` cho tổng `99.99`. | `routers/cases.py:522-527`, `services/word_engine.py:249-256`, `:449` | `INV-2`, 9.3 |
| 3 | Mặc định cờ `Nhận` khác nhau ở bốn chỗ: `True`, theo quyết định legacy, `False`, và `is True`. | `services/inheritance_engine.py:120`, `routers/cases.py:217`, `:279`, `:528` | 7.2 |
| 4 | Không có trạng thái `unsupported`. Mọi lời hứa "trả chưa hỗ trợ" hiện không thể thực thi. | `services/inheritance_engine.py:72`, `:429` | 8 |
| 5 | Không còn ai ở hàng thứ nhất và tất cả tắt `Nhận` dùng chung mã `no_valid_heir`. | `services/inheritance_engine.py:384-391` | 8 |
| 6 | Đệ quy thế vị không có điểm dừng ở chắt. | `services/inheritance_engine.py:308-328` | 6.1 |
| 7 | Không có đầu vào tỷ lệ sở hữu gốc; `1/n` là đường duy nhất. | `services/inheritance_engine.py:276` | 3 |
| 8 | Bật `Nhận` cho người không có suất bị bỏ qua im lặng, không cảnh báo. | `services/inheritance_engine.py:330-342` | 7.3 |
| 9 | Bảo toàn chỉ kiểm ở mức tổng toàn hồ sơ. Hiện chưa có lỗi lộ ra vì `credit()` chia hết, nhưng không có gì canh hồi quy. | `services/inheritance_engine.py:397-405` | `INV-4` |
| 10 | Giới hạn tối đa hai cha/mẹ chặn trường hợp có cả cha mẹ đẻ và cha mẹ nuôi. | `services/inheritance_engine.py:161-164` | 10 |
| 11 | So ngày chết với ngày sinh chưa có quy tắc cấp năm; luật kiểm hiện tại báo lỗi sai với trường hợp sinh và chết cùng năm. | `docs/superpowers/specs/2026-08-18-stage-sot-sync-model.md:226` | 4.5 |
| 12 | Engine còn tự đoán định dạng ngày ISO, trong khi chuẩn hoá phải ở lớp nhập. | `services/inheritance_engine.py:46-51` | 4.6 |

Thứ tự đề nghị: `1` trước tiên vì đây là chỗ duy nhất đang in sai dữ liệu ra văn bản
công chứng. Rồi `4` và `5` vì enum trạng thái mở đường cho `6`, `7`, `8`. `2` độc lập,
làm song song được. `9` là canh hồi quy, không gấp.

### 11.3 Tài liệu khác phải sửa sau khi bạn duyệt

Chỉ liệt kê, **không** tự sửa, vì đây là các tài liệu có thẩm quyền riêng.

| Tài liệu | Chỗ chống với bản này | Điều khoản |
|---|---|---|
| `workflow.md:126-133` | Công thức `Người không nhận = người trên Diagram − Chủ đất − Người nhận`. Công thức này trừ nhóm `Chủ đất` nên bỏ sót chủ đất còn sống tắt `Nhận` ở một vòng di sản khác, và không phân biệt `chưa quyết` với `đã quyết không nhận`. | 2, 7.2 |
| `ux.md:13-17` | Chỉ mô tả hai trạng thái của cờ `Nhận`; chưa có `chưa quyết` và chưa có trạng thái chỉ đọc cho người đã chết. | 7.1, 7.2 |
| `ux.md:37-39` | Ví dụ `Xem cách tính` chưa có dòng cơ sở thứ tự ngày và chưa tách phần đến từ thoả thuận. | 4.4, 9.2 |
| `research/case-catalog.md:199-243` | Case R1/R2/R3 viết theo mô hình `Người không nhận`; cần viết lại theo suất pháp luật và phần thực nhận. | 7, 9.1 |
| `research/validation-matrix.md` | Ghi PASS cho một workspace chưa commit; các mục liên quan tới `no_valid_heir`, độ sâu thế vị và phần trăm phải chạy lại sau khi sửa 11.2. | 8, 9.3 |
| `technical/inheritance-engine.md` | Đã thêm con trỏ tới 11.2 ở đầu file; nội dung chi tiết chỉ sửa sau khi bạn duyệt bản này. | 11.2 |
| `word_templates/placeholder_mapping.md:29-31` | Ghi quy tắc `01/01/yyyy` hiển thị thành `yyyy` — đúng chỗ này là nguồn của lỗi in sai ngày. | 4.1, 9.3 |

## 12. Case kiểm thử bắt buộc

Bổ sung vào `research/case-catalog.md`. Mỗi dòng diễn đạt được bằng một câu user hiểu.

**Ngày và thời điểm**

1. Hai người chỉ có năm `2010` → cùng thời điểm `01/01/2010`, không nhận chéo, không cảnh báo.
2. A `2010` và B `15/06/2010` → A trước B, B nhận từ A, và có dòng cơ sở thứ tự (4.4).
3. Ngày `01/01/2010` thật → hiển thị và in Word là `01/01/2010`, không phải `2010`.
4. Dữ liệu chỉ có năm `2010` → hiển thị và in Word là `2010`, không phải `01/01/2010`.
5. Đọc rồi ghi lại một hồ sơ có ngày `01/01/2010` thật → ngày không thoái hoá thành năm.
6. Sinh `15/06/2010`, chết `2010` → hợp lệ, không báo lỗi ngày chết trước ngày sinh.

**Sở hữu gốc**

7. Ba chủ đất, không ai có tỷ lệ → mỗi người `1/3`, giao diện hiện rõ đang chia đều.
8. Hai chủ đất `7/10` và `3/10` → dùng đúng tỷ lệ.
9. Điền tỷ lệ cho một người, để trống người kia → `invalid: partial_ownership_ratio`.
10. Tỷ lệ điền hết nhưng tổng `9/10` → `invalid: ownership_ratio_sum`.
11. Không có chủ đất → `invalid: missing_land_owner`.

**Thoả thuận phân chia**

12. Hai con còn sống, một người tắt `Nhận` → người kia nhận cả phần, và kết quả tách rõ
    suất theo pháp luật `1/2` với phần thực nhận `1`.
13. Ô chưa quyết → `incomplete: receivers_undecided`, khác với case 14.
14. Mọi người hàng thứ nhất đều tắt `Nhận` → `incomplete: all_receivers_declined`.
15. Bật `Nhận` cho người không có suất → không tạo phần nào, có cảnh báo
    `receive_without_entitlement`.
16. Chủ đất còn sống tắt `Nhận` → vẫn giữ phần sở hữu gốc.
17. Người còn sống tắt `Nhận`, sau đó có ngày chết → cờ chuyển sang chỉ đọc, kết quả
    tính theo dòng thời gian, không theo cờ.
18. Nhánh thế vị có người nhường phần (ví dụ 7.5) → E nhận toàn bộ phần nhánh, và kết
    quả ghi rõ `1/8` từ pháp luật cộng `1/8` từ thoả thuận.

**Thế vị và trạng thái**

19. X → A → B → C chết hết, D là con C còn sống → `unsupported: representation_depth_exceeded`.
20. Nhánh chết cùng thời điểm không có hậu duệ → loại khỏi mẫu số; nhánh còn lại nhận
    toàn bộ; không tạo sở hữu cho người trung gian.
21. Người chết không còn vợ/chồng, cha/mẹ, con → `unsupported: second_order_required`,
    nhãn khác hẳn kết quả đã chia.
22. Hai vợ chồng cùng chết năm `2010`, không có con → cả hai vòng đều
    `unsupported: second_order_required`, không âm thầm làm mất tài sản.
23. Vòng di sản không có người nhận trong khi một chủ đất khác còn sống → **không** dồn
    phần đó cho chủ đất còn sống (`INV-4`).
24. Đổi thứ tự mảng node của cùng một hồ sơ → kết quả y hệt (`INV-5`).
25. Một người nhận từ hai vòng → tổng đúng, hai số hạng giữ nguyên hai nguồn.

**Văn bản**

26. Ba người mỗi người `1/3` → văn bản in phân số `1/3`, không in `33.33` như con số
    pháp lý duy nhất.
27. Hồ sơ không có văn bản từ chối → chỗ `Người từ chối` để trống, không suy từ `Nhận`.
28. Lưu, tải lại và xuất Word dùng cùng một phân số cuối.

## 13. Quyết định đã chọn thay bạn, chờ bạn xác nhận

Bốn chỗ trước đây còn để ngỏ. Tôi đã chọn để tài liệu đọc được liền mạch. Bạn đọc và
đảo nếu không đồng ý; mỗi mục ghi rõ chỗ sửa.

| # | Vấn đề | Đã chọn | Vì sao | Sửa ở |
|---|---|---|---|---|
| 1 | Lệch độ chính xác trong cùng một năm | Giữ nguyên thứ tự A trước B, thêm dòng cơ sở đọc được | Không đổi code, không đổi quyết định 4.2 của bạn, nhưng công chứng viên thấy được cơ sở | 4.4 |
| 2 | Mặc định cờ `Nhận` | `chưa quyết`, không phải `true` hay `false` | Là phương án duy nhất không khai một ý chí không ai phát biểu | 7.2 |
| 3 | Hàng thừa kế thứ hai | Giữ ngoài phạm vi, nhưng bắt buộc `unsupported: second_order_required` với nhãn riêng | Trường hợp thường gặp; gọi nó là "thiếu dữ liệu" sẽ khiến user nhập thêm vô ích | 8, 10 |
| 4 | Ô `Nhận` của người đã chết | Chỉ đọc kèm lý do, không ẩn | Ẩn làm user tưởng thẻ lỗi; hiện mờ kèm lý do thì tự giải thích | 7.1 |

Ngoài ra, tài liệu này khẳng định lại quyết định của bạn ở 4.2 mà **không** kèm điều
kiện nào: không thêm khái niệm độ chính xác vào lớp tính, không coi dữ liệu chỉ có năm
là thiếu, không cảnh báo, không chặn. Điều khoản mới duy nhất quanh nó là **cấm lớp hiển
thị và lớp văn bản làm ngược lại phép chuẩn hoá** — việc này không đổi phép tính nào, và
nó chữa lỗi in sai ngày trong văn bản công chứng ở mục 11.2 số `1`.
