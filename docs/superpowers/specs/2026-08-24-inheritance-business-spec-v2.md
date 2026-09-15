# Nghiệp vụ sơ đồ thừa kế — bản hoàn chỉnh vòng 2

> **Trạng thái:** DRAFT để user chỉnh tiếp. Chưa chuẩn tắc.
> **Lập ngày:** 24/08/2026. **Nội dung phản biện diễn ra:** 22/08/2026.
> **Quan hệ với tài liệu hiện có:** bản này là bản kế tiếp của
> `docs/domains/inheritance/spec.md`. Khi user duyệt, nội dung §1–§12 thay thế
> `spec.md`; §13–§14 là phụ lục phục vụ phản biện, không đưa vào `spec.md`.
> **Trạng thái code:** chưa có thay đổi code nào. Chưa chạy `verify.bat`.
>
> Bài toán kiểm thử: `docs/domains/inheritance/research/case-catalog.md`. UI/UX:
> `ux.md`. Luồng Stage/Pool/Diagram: `workflow.md`. Hợp đồng kỹ thuật:
> `technical/inheritance-engine.md`.
>
> Khi tài liệu này mâu thuẫn với code đang chạy, đó là bằng chứng phải báo, không
> phải quyền tự sửa một bên. §11 ghi rõ chỗ nào code đã khớp và chỗ nào phải sửa.
>
> **Không** ghi số điều luật trong tài liệu này. Nội dung quy định được diễn đạt
> bằng lời; việc đối chiếu điều luật cần người có chuyên môn pháp lý xác nhận
> trước khi tài liệu thành chuẩn tắc.

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
| `INV-9` | Engine không tạo người, không đoán người vào ô trống, không tự nối quan hệ còn thiếu, không tự khai ý chí thay user. |
| `INV-10` | Trường hợp ngoài năng lực engine phải trả trạng thái `unsupported` kèm mã lý do, không tính gần đúng. Nhãn hiển thị của trục này là "ngoài năng lực engine", tách khỏi danh mục nghiệp vụ "ngoài phạm vi" ở §10. |
| `INV-11` | Engine không khoá thao tác của user. Kết quả engine là thông tin để user tự xem và tự quyết. Mọi phát hiện được xử lý theo hướng **ghi vết + cảnh báo**, không **chặn**. Điều kiện chặn lưu, nếu có, do `workflow.md` quy định và phải nêu tường minh giá trị nào cho lưu. |
| `INV-12` | Mọi số hiển thị và mọi số in ra văn bản đều đọc từ kết quả engine. Không lớp nào tự tính lại. |
| `INV-13` | Engine chỉ được kết luận về **những gì có trên sơ đồ**. Engine không được kết luận về thế giới bên ngoài sơ đồ: không kết luận "người này không có con", "không còn người thừa kế nào", "tài sản thuộc về Nhà nước". Những kết luận đó là khai báo của user. |

## 2. Thuật ngữ

Tài liệu tách ba lớp mà mô hình cũ gộp làm một. Tách lớp là điều kiện để văn bản
công chứng gọi đúng tên loại việc.

| Thuật ngữ | Nghĩa | Ai quyết định |
|---|---|---|
| **Chủ đất** | Người có phần sở hữu gốc trước khi chạy thừa kế. | User bật cờ trên ô |
| **Suất theo pháp luật** | Phần một người hoặc một nhánh được hưởng trong một vòng di sản nếu chia theo pháp luật, chưa tính thoả thuận. | Engine tính |
| **Phần thực nhận** | Phần cuối cùng một người nhận sau khi áp dụng thoả thuận phân chia. | Engine tính từ suất + quyết định phân chia |
| **Quyết định phân chia** | Với mỗi người, trong mỗi vòng di sản, trên mỗi tài sản: `giữ phần` hoặc `nhường phần`. Mặc định là `giữ phần` vì pháp luật đã cho hưởng sẵn; lập luận ở §7.1. | User |
| **Người nhường phần** | Người có suất theo pháp luật lớn hơn `0` nhưng chọn `nhường phần`. | Suy ra |
| **Người từ chối nhận di sản** | Thuật ngữ pháp lý, chỉ tồn tại khi hồ sơ có văn bản từ chối riêng. | Dữ liệu pháp lý ngoài Diagram |

Quy tắc cứng về thuật ngữ:

- `nhường phần` **không** phải từ chối nhận di sản. Hai loại việc khác nhau: thoả
  thuận phân chia dồn phần cho người khác là hợp pháp và phần đó đi theo thoả
  thuận; từ chối nhận di sản phải lập văn bản riêng và phần bị từ chối chia lại
  theo pháp luật.
- Engine, giao diện và văn bản **không được** suy `Người từ chối` từ `nhường phần`.
  Chỗ dành cho `Người từ chối` để trống khi hồ sơ không có văn bản từ chối.
- **Cấm** đặt tên trường dữ liệu hay nhãn giao diện gợi ý "từ chối", "khước từ",
  "waive". Tên được chấp nhận: `giữ phần` / `nhường phần`, hoặc `keep` / `cede`.
- Chủ đất còn sống luôn giữ phần sở hữu gốc của mình. Chọn `nhường phần` trong một
  vòng di sản không lấy đi phần sở hữu gốc đó. Nếu phần sở hữu gốc chuyển cho người
  khác thì đó là tặng cho hoặc chuyển quyền — ngoài phạm vi tài liệu này, và không
  được ghi nguồn là thừa kế.
- Thoả thuận phân chia chỉ diễn ra giữa những người **có suất trong cùng một vòng
  di sản**. Dồn phần cho người không có suất là loại việc khác, xem §7.2.

## 3. Sở hữu gốc

Phạm vi bước 1 là **một tài sản** cho mỗi lần tính; xem §10.

- Phải có ít nhất một `Chủ đất`. Không có thì trả `invalid: missing_land_owner`.
- Tỷ lệ sở hữu gốc theo quy tắc **tất-cả-hoặc-không** cho mỗi tài sản:

| Trạng thái nhập | Xử lý |
|---|---|
| Không chủ đất nào có tỷ lệ | Chia đều `1/n`, kèm cảnh báo `ownership_basis_unknown`. Giao diện hiện rõ đang chia đều theo quy ước. |
| Mọi chủ đất có tỷ lệ và tổng đúng bằng `1` | Dùng đúng tỷ lệ đã nhập. |
| Điền một phần, để trống một phần | `invalid: partial_ownership_ratio` |
| Điền hết nhưng tổng khác `1` | `invalid: ownership_ratio_sum` kèm tổng thực tế |
| Có tỷ lệ bằng `0` hoặc âm | `invalid: ownership_ratio_value` |

### 3.1 Chia đều là quy ước sản phẩm, không phải kết luận pháp luật

Việc để trống tỷ lệ rồi chia đều `1/n` là **quy ước của hệ thống để có một con số
tính được**, không phải một quy tắc pháp luật tổng quát. Pháp luật phân biệt nhiều
hình thái sở hữu chung, và tỷ lệ thật đến từ giấy tờ, không từ số người đứng tên.

Hệ quả bắt buộc:

- **Cấm** viết trong tài liệu, giao diện hay văn bản rằng "không ghi tỷ lệ thì theo
  pháp luật mỗi người bằng nhau".
- Vẫn giữ chia đều làm **mặc định tính** để không chặn công việc (`INV-11`), nhưng
  phải cảnh báo rằng phép tính đang dựa trên quy ước, chưa dựa trên căn cứ.

### 3.2 Căn cứ sở hữu

Mỗi tài sản có một **căn cứ sở hữu** do user chọn:

| Căn cứ | Ghi chú |
|---|---|
| Giấy chứng nhận ghi rõ tỷ lệ | Tỷ lệ lấy từ giấy |
| Tài sản chung của vợ chồng | Có quy tắc chia riêng theo pháp luật hôn nhân, cần chuyên môn pháp lý xác nhận trước khi cài |
| Thoả thuận giữa các chủ sở hữu | Tỷ lệ lấy từ thoả thuận |
| Bản án hoặc quyết định | Tỷ lệ lấy từ bản án |
| Chưa xác định | Dùng quy ước chia đều, kèm cảnh báo |

Engine **không** suy căn cứ, không suy tỷ lệ từ quan hệ, thứ tự thẻ hay số người.
Thiếu căn cứ thì cảnh báo, không chặn.
- Mâu thuẫn giữa căn cứ đã chọn và dữ liệu đã nhập — ví dụ căn cứ "Giấy chứng
  nhận ghi rõ tỷ lệ" mà ô tỷ lệ để trống — phải cảnh báo riêng
  `ownership_basis_conflict`, cấm im lặng rơi về quy ước chia đều.

## 4. Ngày và thời điểm

### 4.1 Ba lớp, không được trộn

| Lớp | Nội dung | Ràng buộc |
|---|---|---|
| **Nhập** | Giữ đúng thứ user gõ: `2010` giữ là `2010`, `01/01/2010` giữ là `01/01/2010`. | Không bịa ngày, không thoái hoá ngày đầy đủ thành năm |
| **Tính** | So sánh thời điểm bằng comparator §4.3. Khoá sắp xếp nội bộ của dữ liệu chỉ có năm là `01/01/yyyy`. | Khoá nội bộ **không** mang nghĩa "đã biết là ngày 01/01" |
| **Hiển thị và văn bản** | In đúng thứ user đã gõ. | **Cấm** suy `01/01` thành `yyyy`; **cấm** in `yyyy` thành `01/01` |

Lớp tính cần biết một ngày là **đầy đủ** hay **chỉ có năm**, vì đó là thông tin
user đã phát biểu, không phải đánh giá chất lượng dữ liệu. Đây không phải cơ chế
"độ chính xác" để cảnh báo hay chặn.

### 4.2 Dữ liệu chỉ có năm — quyết định đã chốt của user

> Điền `yyyy` **là** phát biểu "không phân biệt được thứ tự", không phải dữ liệu
> khuyết. Nếu user phân biệt được ai chết trước thì user đã điền ngày đầy đủ.

Hệ quả bắt buộc:

- Không coi "chỉ có năm" là dữ liệu thiếu. Không cảnh báo vì lý do này. Không chặn.
- Không nơi nào trong hệ thống được hiểu ngày khác lớp tính.
- `01/01/yyyy` **chỉ** là khoá sắp xếp nội bộ, dùng cho thứ tự xử lý, ảnh chụp tài
  sản và khoá vòng di sản. Nó **không** là căn cứ để nói ai chết trước ai.

### 4.3 Comparator thời điểm chết

Năm tổ hợp, áp dụng **theo từng cặp người**:

| Dữ liệu hai bên | Kết quả |
|---|---|
| Cả hai đều là ngày đầy đủ | So đến cấp ngày. Bằng nhau là **cùng thời điểm** |
| Cả hai chỉ có năm, khác năm | So theo năm |
| Cả hai chỉ có năm, cùng năm | **Không xác định thứ tự** |
| Một bên chỉ có năm, một bên đầy đủ, khác năm | So theo năm |
| Một bên chỉ có năm, một bên đầy đủ, cùng năm | **Không xác định thứ tự** |

Hai thuật ngữ khác nhau, không được dùng lẫn:

- **Cùng thời điểm**: hai ngày đầy đủ bằng nhau.
- **Không xác định thứ tự**: dữ liệu không cho biết ai trước.

Cả hai đều cho cùng một hệ quả về quyền hưởng: **hai người không nhận di sản của
nhau**, và phần của mỗi người đi xuống hậu duệ theo thế vị.

### 4.4 Quan hệ "không xác định thứ tự" không bắc cầu

Xét A chết `2010`, B chết `01/03/2010`, C chết `01/09/2010`.

- A với B: không xác định thứ tự. A với C: không xác định thứ tự.
- B với C: B chết trước C.

Vì vậy **cấm** cài đặt bằng cách gom thành nhóm "cùng thời điểm". Phải hỏi
comparator theo từng cặp. Kết quả đúng của ví dụ trên: A không nhận từ B và C; B và
C không nhận từ A; C nhận từ B.

Thứ tự xử lý nội bộ (theo khoá §4.1) chỉ ảnh hưởng đến việc chụp tài sản đang giữ,
không ảnh hưởng đến ai nhận của ai, nên `INV-5` và `INV-6` vẫn giữ nguyên.

Vì sao **cùng khoá thì không ai nhận của ai trong nhóm**: hai người cùng khoá
chỉ có thể ở một trong ba dạng — hai ngày đầy đủ trùng nhau (cùng thời điểm);
một ngày thật đúng `01/01` trùng khoá của một dữ liệu chỉ có năm (comparator
cho "không xác định thứ tự"); hoặc cả hai chỉ có năm cùng năm (cũng không xác
định thứ tự). Cả ba đều không nhận chéo, nên không bao giờ có chuyển giao nội
nhóm và thứ tự xử lý trong nhóm vô hại với kết quả quyền hưởng.

### 4.5 So ngày chết với ngày sinh

Cùng comparator §4.3. Khi một trong hai ngày chỉ có năm thì so ở cấp năm.

Ví dụ bắt buộc đúng: sinh `15/06/2010`, chết `2010` → hợp lệ. Nếu so bằng khoá nội
bộ thì `01/01/2010 < 15/06/2010` và kiểm tra sẽ báo lỗi sai, buộc user bịa một
ngày chết mà họ không biết; trẻ mất trong năm sinh là trường hợp thật trong hồ
sơ. Đây là yêu cầu khi cài, **không phải mô tả runtime**: chưa có phép so
sinh/chết nào trong code để sửa — việc này là thêm mới (§11.3 số 3).

### 4.6 Miền giá trị ngày

- Chuẩn hoá định dạng xảy ra ở **lớp nhập**. Mọi định dạng nguồn (`dd/mm/yyyy`,
  ISO, serial Excel, số năm) được chuyển về một dạng nội bộ duy nhất tại đây, và
  dạng đó **giữ kèm** thông tin đầy đủ hay chỉ có năm.
- Engine không phải nơi đoán định dạng.
- Ngày không phân giải được là lỗi ở lớp nhập theo `workflow.md`, hiện đúng hàng dữ
  liệu sai. Nếu vẫn tới engine thì trả `invalid: invalid_death_date` kèm người
  cụ thể.
- Ô ngày chết rỗng nghĩa là còn sống. Không suy ngày chết từ tuổi, từ ngày cấp giấy
  tờ hay từ vị trí thế hệ.

## 5. Vòng di sản

Mỗi chủ đất bắt đầu với phần sở hữu gốc độc lập.

1. Xử lý các thời điểm chết theo khoá sắp xếp nội bộ tăng dần.
2. Chụp tài sản đang giữ **trước khi** tính bất kỳ vòng nào của cùng một khoá.
3. Chỉ mở vòng di sản nếu người chết thực sự có tài sản: phần sở hữu gốc, hoặc phần
   thừa kế đã thực sự nhận trước đó.
4. Hàng thừa kế thứ nhất của một vòng gồm cha, mẹ, vợ hoặc chồng, và các nhánh con.
5. Cha, mẹ, vợ/chồng chỉ là đơn vị nhận nếu comparator cho biết họ còn sống tại thời
   điểm mở vòng. Không áp dụng thế vị cho cha, mẹ, vợ/chồng.
6. Mỗi người con là **một đơn vị nhánh**, không phải một người. Chi tiết ở §6.
7. Chia đều cho các đơn vị hợp lệ, rồi áp dụng quyết định phân chia ở §7.
8. Người chết **sau** nguồn di sản nhận phần của mình bất kể quyết định phân chia,
   vì tài sản đó phải đi vào di sản thực tế của họ. Quyết định phân chia chỉ áp dụng
   cho người còn sống.
9. Phần đã thực sự nhận trở thành tài sản của người nhận và có thể mở vòng di sản
   tiếp theo tại thời điểm họ chết.

Mỗi vòng di sản có khoá định danh là cặp `(người để lại di sản, khoá thời điểm)`.

Việc một người có ngày chết **không** tự sinh toàn bộ gia đình. Hệ thống chỉ yêu cầu
những ô cần cho một vòng di sản đang mở hoặc một nhánh thế vị đang hoạt động.

## 6. Thế vị

Thế vị dùng cùng dòng phân bổ của §5 nhưng coi mỗi người con là một nhánh.

- Mỗi nhánh trước hết có phần mà người con lẽ ra được hưởng nếu còn sống.
- Con còn sống tại thời điểm mở thừa kế: phần nhánh thành tài sản của người con.
- Con chết **sau** thời điểm mở thừa kế: vẫn nhận phần nhánh; phần đó vào di sản của
  họ tại thời điểm họ chết.
- Con chết **trước**, **cùng thời điểm**, hoặc **không xác định thứ tự** so với
  người để lại di sản: phần nhánh đi qua vị trí của họ và xuống trực tiếp các con của
  họ. Nếu người cháu cũng ở một trong ba tình huống đó thì dòng tiếp tục xuống chắt
  **trong chính nhánh đó**.
- Chia đều theo từng nhánh ở **từng cấp**, không làm phẳng toàn bộ hậu duệ rồi chia
  đều.
- "Đi qua" chỉ là đường dẫn tính toán. Phần thế vị **không** từng thuộc sở hữu của
  người chết trước, không cộng vào di sản của họ, và quyết định phân chia trên ô của
  họ không giữ hoặc chặn dòng thế vị.
- Chỉ hậu duệ trong chính nhánh được nhận phần thế vị. Cha, mẹ, vợ/chồng của người
  chết trước không tham gia chia phần này.
- Khi mở nhánh thế vị, sinh ô vợ/chồng của người chết trước để thể hiện đúng cặp cha
  mẹ của các con. Ô này chỉ biểu diễn quan hệ và **không** nhận phần thế vị.
- Nếu người chết trước có phần sở hữu gốc hoặc đã thực sự nhận tài sản từ nguồn khác,
  tài sản riêng đó vẫn mở một vòng di sản độc lập. Trong vòng đó, vợ/chồng của họ là
  người thừa kế hàng thứ nhất bình thường.

### 6.1 Giới hạn độ sâu

Thế vị dừng ở **chắt**. Dưới chắt không còn là thế vị.

- Vượt giới hạn thì trả `unsupported: representation_depth_exceeded` kèm nhánh cụ
  thể.
- Cấm đệ quy không điểm dừng. Cấm âm thầm hỗ trợ sâu hơn giới hạn. Cấm âm thầm làm
  mất nhánh khi tới giới hạn.

### 6.2 Nhánh không còn đơn vị nhận — quyết định đã chốt của user

> Khi một nhánh không còn ai nhận thì các nhánh khác lấy phần của nhánh đó chia
> tiếp — coi như nhánh kia không tồn tại.

Quy tắc:

- Nhánh không còn đơn vị nhận **bị loại khỏi các đơn vị chia** của vòng đó. Phần di
  sản chia lại cho các đơn vị hợp lệ còn lại **trong cùng vòng**.
- "Không còn đơn vị nhận" gồm hai trường hợp: nhánh không còn hậu duệ để thế vị, và
  nhánh còn hậu duệ nhưng tất cả đều chọn `nhường phần`.
- Các đơn vị còn lại chia **bằng nhau**, trong đó vợ/chồng và cha/mẹ là đơn vị
  **ngang hàng** với một nhánh con.
- Nhánh bị loại **không** tạo sở hữu cho người trung gian, không chuyển cho vợ/chồng
  hoặc cha mẹ của người trung gian, và không giữ phần riêng.
- Chỉ khi **toàn bộ** vòng không còn đơn vị hợp lệ thì vòng đó giữ phần chưa có
  người nhận, xem §8.3.

Ví dụ đã được user xác nhận là **đúng ý muốn**:

> Ông X chết, còn vợ là bà V. Người con duy nhất là anh A đã chết trước ông X, để
> lại hai con C và D. Cả C và D đều chọn `nhường phần`.
> **Kết quả: bà V nhận toàn bộ.**

Ghi rõ để lần đọc sau không ai tưởng là lỗi: phần của nhánh anh A **được phép thoát
ra khỏi nhánh** và về tay đơn vị còn lại của vòng, kể cả khi đơn vị đó là vợ của
người để lại di sản. Đây là quy tắc chủ động, không phải hệ quả tình cờ.


## 7. Quyết định phân chia

### 7.1 Ý nghĩa và mặc định

Với mỗi người, trong mỗi vòng di sản, trên mỗi tài sản có đúng một quyết định:
`giữ phần` hoặc `nhường phần`.

Mặc định là `giữ phần`, và mặc định đó **không phải** hệ thống khai ý chí thay
user:

- Pháp luật trả lời sẵn: người thừa kế được hưởng suất của mình khi không có
  phát biểu ngược lại. Không ai phải "bật nhận" để được hưởng.
- Hành vi cần ý chí là `nhường phần`, thuộc thoả thuận phân chia giữa những
  người có suất trong cùng vòng. Chỉ hành vi đó do user phát biểu.
- Vì vậy không tồn tại trạng thái `chưa quyết`. Mã `receivers_undecided` bị xoá
  khỏi hệ trạng thái và khỏi case kiểm thử. Đây là đảo so với v1, xem §13 mục 1.
- Ba lớp (engine, hợp đồng lưu, bảng người tham gia) dùng **cùng một** mặc định.

Tên trường dữ liệu chỉ được là `keep` / `cede` hoặc tiếng Việt tương đương
`giữ phần` / `nhường phần`. Ánh xạ từ trường cũ `willReceive`: `willReceive=false`
tương đương `nhường phần`, `true` tương đương `giữ phần`; kế hoạch đổi tên ở
§11.3.

### 7.2 Hiệu lực của quyết định

- Quyết định chỉ có nghĩa khi suất theo pháp luật của người đó trong vòng đang
  xét lớn hơn `0`.
- `nhường phần` cho người không có suất là thao tác vô hiệu: không tạo phần nào,
  không chuyển phần cho ai. Hệ thống **cảnh báo** `cede_without_entitlement`,
  cấm im lặng. Dồn phần thật sự cho người không có suất là tặng cho hoặc chuyển
  quyền — loại việc khác, ngoài phạm vi §10.
- Người còn sống `nhường phần` ở một vòng không mất phần sở hữu gốc (§2) và
  không mất quyền hưởng ở vòng khác.
- Quy tắc chia lại áp dụng cho các đơn vị **cấp thứ nhất của vòng** (vợ/chồng,
  cha/mẹ, nhánh con), chia bằng nhau; vợ/chồng và cha/mẹ ngang hàng với một
  nhánh con. Bên trong một nhánh thế vị, chia lại theo cấp của §7.4 và phần
  không thoát khỏi nhánh, trừ khi toàn bộ nhánh bị loại theo §6.2. Việc chia lại
  không bao giờ chuyển sang vòng khác (`INV-4`).

### 7.3 Người chết và dòng thời gian

Người đã có ngày chết không tham gia thoả thuận. Ô của họ hiện quyết định ở
trạng thái chỉ đọc kèm lý do đọc được, không ẩn.

Dòng thời gian thắng mọi quyết định đã ghi:

- Chết **sau** nguồn di sản: nhận phần bất kể quyết định, vì tài sản đi vào di
  sản thật của họ (§5 điểm 8).
- Chết **trước** nguồn di sản mà từng chọn `nhường phần`: quyết định cũ vô
  nghĩa. Người đó không phải đơn vị nhận; nhánh mở thế vị bình thường như thể
  chưa từng có quyết định. Case bắt buộc: §12 số 20.

### 7.4 Nhường phần bên trong nhánh thế vị

Trong một nhánh thế vị, quyết định áp dụng theo từng cấp:

- **Một phần** đơn vị của cấp nhường: phần dồn cho các đơn vị còn `giữ phần`
  **trong chính cấp đó**, kể cả khác thế hệ. Phần không thoát ra khỏi nhánh.
- **Toàn bộ** đơn vị của nhánh đều nhường, hoặc nhánh không còn hậu duệ: nhánh
  bị loại và phần thoát lên theo quy tắc §6.2.

Ví dụ chuẩn: X chết. A là con, chết trước X. A có hai con: C còn sống nhưng
`nhường phần`; D chết trước X và để lại E còn sống.

- Suất theo pháp luật trong nhánh A: C `1/2` nhánh, E `1/2` nhánh.
- C nhường cấp mình nên phần C dồn trong nhánh; D chết trước nên E thế vị phần
  D. Kết quả: E nhận **toàn bộ** phần nhánh A.
- Giải thích **phải** tách hai lớp: phần đến từ thế vị và phần đến từ thoả
  thuận nhường. Một dòng gộp kiểu `E nhận 1/2 (X, thế vị nhánh A)` là không đủ.

## 8. Trạng thái kết quả

### 8.1 Bốn trạng thái trên một trục

Tên trục là mã máy. Nhãn hiển thị do giao diện đặt và **không được** dùng chữ
"ngoài phạm vi" cho trục này, để tách khỏi danh mục nghiệp vụ cùng tên ở §10.

| Trạng thái | Nghĩa với user | Ví dụ mã lý do |
|---|---|---|
| `invalid` | Dữ liệu vào sai hoặc mâu thuẫn, chưa tính được gì. | `missing_land_owner`, `partial_ownership_ratio`, `ownership_ratio_sum`, `ownership_ratio_value`, `invalid_death_date`, `duplicate_person`, `dangling_parent`, `self_parent`, `self_spouse`, `spouse_conflict`, `too_many_parents`, `ancestry_cycle` |
| `unsupported` | Dữ liệu hợp lệ nhưng bài toán ngoài năng lực engine. Nhãn hiển thị: "ngoài năng lực engine". | `second_order_required`, `representation_depth_exceeded`, `multiple_spouse_chain`, `parent_capacity_exceeded`, `date_bound_not_representable` |
| `incomplete` | Tính được nhưng còn phần chưa có người nhận, cần user bổ sung. | `all_receivers_declined` |
| `complete` | Đã chia hết theo đúng quy tắc, mọi vòng bảo toàn. Warnings không ngăn `complete`. | — |

Thứ tự ưu tiên khi nhiều điều kiện cùng đúng:

```text
invalid > unsupported > incomplete > complete
```

### 8.2 Quy tắc cứng

- `complete` chỉ khi không có lỗi, mọi vòng bảo toàn theo `INV-4`, và không còn
  phần chưa có người nhận.
- **Cấm dùng chung một mã** cho hai nguyên nhân khác nhau. Cặp tối thiểu phải
  tách: không còn ai hàng thứ nhất là `unsupported: second_order_required`;
  có người hàng thứ nhất nhưng tất cả `nhường phần` là
  `incomplete: all_receivers_declined`.
- `invalid: too_many_parents` và `unsupported: parent_capacity_exceeded` **chưa
  phân biệt được bằng dữ liệu hiện có**. Kiểm tra thật là
  `len(node["parentSlotIds"]) > 2` (`services/inheritance_engine.py:161`), và cả
  hai nguyên nhân — payload hỏng, và quan hệ cha/mẹ thứ ba **có thật** (cha mẹ đẻ
  cùng cha mẹ nuôi) — cho **cùng một hình dạng payload**. Muốn tách phải có
  thuộc tính loại quan hệ trên liên kết cha/mẹ; đó là điều kiện tiên quyết thứ ba
  ở §11.1. Cho tới khi có thuộc tính đó, hệ thống **chỉ** được trả
  `invalid: too_many_parents`; mã `parent_capacity_exceeded` (§8.1, §10, §13 mục
  4) là mã **chờ điều kiện tiên quyết**, không được cài trước.
- Nhãn hiển thị của `unsupported` phải khác hẳn kết quả đã tính, để không ai
  đọc thành "đã chia xong".
- Mọi trạng thái khác `complete` giữ nguyên dữ liệu user đã nhập. Engine không
  xoá, không dọn, không tự sửa quan hệ (`INV-9`, `INV-11`).

### 8.3 Vòng không còn đơn vị nhận

Chỉ khi **toàn bộ** các đơn vị của vòng bị loại thì vòng giữ phần chưa có người
nhận: ghi fraction vào `unresolvedEstates` kèm lý do, trả `incomplete`, và
không dồn phần đó sang vòng hay chủ đất khác (`INV-4`). Còn ít nhất một đơn vị
hợp lệ thì phải chia lại đến hết trong cùng vòng.

### 8.4 Cảnh báo

Cảnh báo không chặn (`INV-11`), hiện từng dòng trong một vùng chung:

| Mã | Khi nào |
|---|---|
| `ownership_basis_unknown` | Không ai nhập tỷ lệ, đang chia đều theo quy ước (§3). |
| `ownership_basis_conflict` | Căn cứ chọn mâu thuẫn dữ liệu nhập (§3.2). |
| `cede_without_entitlement` | `nhường phần` trên người không có suất (§7.2). |

## 9. Kết quả giải thích và giá trị đưa vào văn bản

### 9.1 Hai lớp trong kết quả

Kết quả engine giữ **cả hai** lớp, không chỉ tổng cuối:

| Lớp | Nội dung | Dùng để |
|---|---|---|
| Suất theo pháp luật | Ai được xét trong vòng nào, suất từng người/nhánh | Chứng minh cơ sở pháp luật |
| Phần thực nhận | Sau khi áp dụng quyết định phân chia | Con số ghi vào văn bản |

Không có lớp thứ nhất thì không chứng minh được phần vượt lên của một người đến
từ thoả thuận, và văn bản sẽ gọi sai tên loại việc.

### 9.2 `Xem cách tính`

Mỗi người nhận một dòng, phân số chính xác, nguồn trong ngoặc:

```text
Người A nhận: 17/40 = 3/10 (X) + 1/10 (Y) + 1/40 (Z)
Người B nhận: 1/2 = 1/4 (X) + 1/4 (Y, thừa kế)
Người C nhận: 1/6 = 1/6 (X, thế vị nhánh Y)
```

Khi cần dòng cơ sở thứ tự, chỉ được dùng **nguyên văn dữ liệu user nhập** và
kết luận của comparator §4.3:

```text
A với B không xác định thứ tự (A chỉ có năm 2010)
B chết trước C (01/03/2010 trước 01/09/2010)
C và D cùng thời điểm (đều mất 05/07/2011)
```

Cấm in khoá sắp xếp nội bộ: không câu giải thích nào chứa `01/01/yyyy` do hệ
thống suy ra. Thế vị ghi nguồn di sản thật và nhánh đi qua, không ghi người
chết trước như thể họ là nguồn. Phần từ thoả thuận ghi rõ là thoả thuận. Giao
diện chỉ đọc kết quả engine (`INV-12`).

### 9.3 Giá trị pháp lý trong văn bản

- Con số pháp lý trong văn bản là **phân số**. Phần trăm chỉ đi kèm, không đứng
  một mình.
- Nguồn duy nhất là phân số cuối của engine. **Cấm** lấy phần trăm làm tròn rồi
  in như con số pháp lý: ba người mỗi người `1/3` cho tổng tròn `99.99`.
- Ngày in đúng thứ user đã nhập (§4.1): cấm in một ngày `01/01` thật thành chỉ
  có năm, cấm in dữ liệu chỉ có năm thành `01/01`.

## 10. Ngoài phạm vi

Đây là danh mục **nghiệp vụ** ngoài năng lực engine, khác trục trạng thái §8.
Trong phạm vi: thừa kế theo pháp luật hàng thứ nhất, thế vị con/cháu/chắt,
nhiều chủ đất, nhiều vòng nối tiếp, quyết định phân chia `giữ phần`/
`nhường phần`, tỷ lệ sở hữu gốc nhập được, một tài sản.

Ngoài phạm vi, trả `unsupported` kèm mã lý do, **không** tính gần đúng:

| Việc | Mã | Ghi chú |
|---|---|---|
| Hàng thừa kế thứ hai và thứ ba | `second_order_required` | Thường gặp; nhãn hiển thị riêng, không gọi là thiếu dữ liệu |
| Di chúc | `wills_not_supported` | Chưa có đầu vào |
| Từ chối nhận di sản theo văn bản | `legal_refusal_not_supported` | Chưa có đầu vào; cấm suy từ `nhường phần` |
| Truất quyền hưởng, bị tước quyền | `disinheritance_not_supported` | Chưa có đầu vào |
| Thai nhi đã thành thai trước thời điểm mở | `fetus_not_supported` | Chưa có đầu vào |
| Tặng cho, chuyển quyền | `gift_transfer_out_of_scope` | Loại việc khác |
| Chuyển cho người ngoài Diagram | `external_transferee_out_of_scope` | Loại việc khác |
| Nhiều tài sản trong một hồ sơ | `multi_asset_out_of_scope` | Cần scope riêng |
| Hôn nhân đã chấm dứt trước ngày chết | `marriage_ended_before_death` | Cần thuộc tính hiệu lực theo thời điểm |
| Tái hôn: nhiều đời vợ/chồng trong cùng sơ đồ | `multiple_spouse_chain` | Mô hình một `spouseSlotId` không biểu diễn được; gặp thật ở hồ sơ đất |
| Con nuôi song song với cha mẹ đẻ | `parent_capacity_exceeded` | Đảo so với v1, xem §13 mục 4. Mã **chờ điều kiện tiên quyết thứ ba** (§11.1, §8.2); chưa có thuộc tính loại quan hệ thì chỉ trả `invalid: too_many_parents` |
| Ngày chỉ biết "trước/sau mốc" | `date_bound_not_representable` | Comparator §4.3 không có cách nhập dạng này |
| Quan hệ chưa được xác nhận | `unconfirmed_relation` | Cần trạng thái xác nhận |

## 11. Đối chiếu code hiện tại

### 11.1 Điều kiện tiên quyết schema — ba chỗ thiếu

Toàn bộ §4 đứng trên giả định hệ thống biết một ngày là đầy đủ hay chỉ có năm.
Hiện tại **không nơi nào lưu thông tin đó**:

| Bằng chứng | Nội dung |
|---|---|
| `models.py:15-16` | `ngay_sinh`, `ngay_chet` là cột `Date`; không có cờ độ phân giải. |
| `services/inheritance_engine.py:44-45` | `"2010"` bị ép thành `date(2010, 1, 1)` ngay lúc parse; cờ mất tại đây. |
| `services/inheritance_engine.py:38-39` | Engine nhận thẳng đối tượng `date` từ DB; không phân biệt nổi nguồn. |
| `routers/customers.py:98-100` | Suy lại bằng thủ thuật `day == 1 and month == 1` khi hiển thị. |
| `frontend/templates/cases/form.html:4717,:4720` | Cùng thủ thuật trong payload sinh/chết cho frontend. |
| `services/word_engine.py:104-111` | Cùng thủ thuật khi in Word. |

Hệ quả đã thấy: ngày `01/01` **thật** bị in thành năm trong văn bản công chứng;
đọc–ghi một vòng làm ngày đầy đủ thoái hoá thành năm.

Yêu cầu: thêm chỗ lưu độ phân giải — cột cờ `'day' | 'year'`, hoặc lưu nguyên
văn chuỗi user gõ. Đây là **thay đổi schema**, điều kiện tiên quyết của §4.
Sửa comparator mà không sửa chỗ lưu thì §4 vẫn chỉ là mong muốn.

Thứ hai — dữ liệu theo từng tài sản. §3 và §7 gắn tỷ lệ sở hữu gốc, căn cứ sở
hữu và quyết định phân chia vào **từng tài sản**, nhưng nơi lưu không chứa chúng:
`InheritanceCaseProperty` (`models.py:114-126`) chỉ là bảng nối
`case_id`–`property_id`–`is_primary`, không có cột tỷ lệ/căn cứ/quyết định.
Chưa có chỗ lưu thì §3.2 và §7 không cài được.

Thứ ba — loại quan hệ trên liên kết cha/mẹ. §8.2 và mã
`unsupported: parent_capacity_exceeded` đòi phân biệt payload hỏng với hồ sơ hợp
lệ cần cha/mẹ thứ ba có thật. Kiểm tra hiện tại chỉ đếm hình dạng
(`services/inheritance_engine.py:161` `len(node["parentSlotIds"]) > 2`), và hai
nguyên nhân cho cùng một hình dạng, nên không luồng nào phân biệt được. Yêu cầu:
thuộc tính loại quan hệ (`đẻ` / `nuôi`) trên **liên kết** cha/mẹ trong hợp đồng
Diagram và nơi lưu. Chưa có thuộc tính đó thì `parent_capacity_exceeded` không
cài được, và §8.2 buộc chỉ trả `too_many_parents`.

Mâu thuẫn runtime kèm phải báo: `word_engine.py:31` đặt `MAX_WORD_ASSETS = 5`
(dùng tại `:811`, `:936`) — runtime đã hỗ trợ đa tài sản trong khi §10 xếp ngoài
phạm vi. Theo quy tắc hồ sơ, đây là bằng chứng chờ user quyết — thu hẹp runtime
về một tài sản, hoặc mở rộng §10 — không bên nào tự khai một bên.

### 11.2 Code đã khớp tài liệu này

| Nội dung | Bằng chứng |
|---|---|
| Tính bằng `Fraction`, không float trong đường tính | `services/inheritance_engine.py` toàn bộ đường tính; **chỉ trong engine** — lớp lưu vi phạm, xem 11.3 số 14 |
| Kết quả độc lập thứ tự node | `sorted()` tại `:322`, `:333`, `:338`, `:409` |
| Mỗi vòng phân bổ hết phần của mình vào holdings | `credit()` tại `:344-350`; đây là phân bổ, chưa phải kiểm tra bảo toàn riêng từng vòng — xem 11.3 số 9 |
| Chụp holdings trước khi tính vòng cùng khoá | `:370-375` |
| Không mở vòng giá trị `0` | `:371-375` |
| Thế vị chia theo từng nhánh, không làm phẳng | `:308-350` |
| Bảo toàn tổng hồ sơ | `:397-400` |

Ghi chú: dòng "quy ước năm khớp code" của v1 §11.1 **hết hiệu**. Comparator
mới (§4.3–4.5) là yêu cầu sửa, không phải mô tả code đang chạy.

### 11.3 Code phải sửa

Thứ tự theo rủi ro pháp lý:

| # | Việc | Bằng chứng | Điều khoản |
|---|---|---|---|
| 1 | Schema lưu độ phân giải ngày; bỏ cả ba thủ thuật `day==1 and month==1` | §11.1 | 4.1, 9.2, 9.3 |
| 2 | Comparator theo cặp; hai thuật ngữ "cùng thời điểm"/"không xác định thứ tự"; bỏ nhóm gộp cùng khoá khi xét quyền | `death_comparison` `inheritance_engine.py:293-301`; `accepts` `:303-306` | 4.3, 4.4 |
| 3 | Thêm quy tắc so sinh/chết theo cấp năm ở lớp nhập/validation — việc **thêm mới**, không phải sửa | chưa có địa chỉ: đã soát `inheritance_engine.py` và `form.html`, không tìm thấy phép so sinh/chết nào | 4.5 |
| 4 | Thêm trạng thái `unsupported`; tách `no_valid_heir` thành `second_order_required` / `all_receivers_declined`; xoá mọi đường `receivers_undecided` | `:72`, `:384-391` | 8 |
| 5 | Đổi tên `willReceive` → `keep`/`cede`; một mặc định duy nhất; bỏ bốn chỗ lệch: `inheritance_engine.py:120` (True), `routers/cases.py:217` (legacy accept), `:279` (False), `:528` (`is True`) | §7.1 | 7.1 |
| 6 | Nhập tỷ lệ sở hữu gốc + căn cứ; cảnh báo `ownership_basis_unknown`, `ownership_basis_conflict`; xoá clause "không đều là unsupported" | `:276` | 3 |
| 7 | Cảnh báo `cede_without_entitlement` thay vì bỏ qua im lặng | `:330-342` | 7.2 |
| 8 | Điểm dừng thế vị ở chắt | `:308-328` | 6.1 |
| 9 | Bảo toàn hồi quy **từng vòng**, không chỉ tổng hồ sơ | `:397-405` | `INV-4` |
| 10 | Chuẩn hoá ngày về lớp nhập; engine không đoán ISO | `:46-51` | 4.6 |
| 11 | QĐ-A: bỏ cả hai chỗ chặn lưu; cho lưu hồ sơ ở mọi trạng thái, trạng thái ghi rõ trong `engineResult` | `routers/cases.py:573-585` raise trên `{invalid, incomplete, unsupported}`; `frontend/templates/cases/form.html:6517-6521` chặn theo chuỗi `'complete'` | `INV-11`; quyết định đã chốt của user |
| 12 | Word: người nhường phần vẫn là **bên của thoả thuận**; danh sách "Chúng tôi gồm" lấy từ suất pháp luật, không lọc theo nhận/nhường | `word_engine.py:475` lọc `will_receive`; `:771` chặn khi rỗng; `:778` in thiếu bên | 2, 9.1 |
| 13 | Word cho xem/xuất được hồ sơ `incomplete`, trạng thái hiện rõ | `word_engine.py:820-821` từ chối khi không còn người nhận | 8.3 |
| 14 | Projection lưu `ty_le` float và `co_nhan_tai_san` rồi `tong_ty_le` cộng lại từ đó — vi phạm `INV-2`/`INV-12` ở lớp lưu; phải lưu/tính từ kết quả exact | `routers/cases.py:527-528`; `models.py:105-111` | `INV-2`, `INV-12` |
| 15 | Đa tài sản: mâu thuẫn spec/runtime cần user quyết — thu hẹp runtime hay mở §10; đi cùng điều kiện tiên quyết schema thứ hai (§11.1) | `word_engine.py:31` (`MAX_WORD_ASSETS = 5`, dùng `:811`, `:936`) | 10 |
| 16 | Thuộc tính loại quan hệ (`đẻ`/`nuôi`) trên liên kết cha/mẹ — điều kiện tiên quyết thứ ba; **chưa làm thì không cài** `parent_capacity_exceeded` | `services/inheritance_engine.py:161` chỉ đếm `len(parentSlotIds) > 2`, không biết nguyên nhân | 8.2, 10, §11.1 |

Việc 1 đi trước vì chặn toàn bộ §4. Việc 11 đi trước việc 4: thêm `unsupported`
mà chưa bỏ chặn thì mọi hồ sơ hàng thừa kế thứ hai chuyển từ lưu được thành
không lưu được. Việc 4 mở đường enum cho 5–8. Việc 2, 3, 10 thuộc cụm ngày, làm
sau khi 1 xong. Việc 16 chặn mã `parent_capacity_exceeded`: chưa xong 16 thì
không được cài mã đó ở bất kỳ luồng nào.

### 11.4 Tài liệu phải đồng bộ sau khi duyệt

Liệt kê để sửa máy móc khi bản này thành chuẩn tắc; chưa sửa trước.

| Tài liệu | Chỗ chống với bản này | Điều khoản |
|---|---|---|
| `workflow.md:126-133` | Công thức "Người không nhận = Diagram − Chủ đất − Người nhận" sai theo mô hình suất/thực nhận; đồng thời phải ghi QĐ-A: bỏ điều kiện chặn lưu, lưu được mọi trạng thái (hiện không tài liệu nào giữ quyết định này) | 2, 7, 11.3 số 11 |
| `ux.md:13-17` | Hai nút `Chủ đất`/`Nhận` → `Chủ đất` + cặp quyết định `giữ phần`/`nhường phần`; thiếu chỉ-read cho người chết | 7.1, 7.3 |
| `ux.md:37-39` | Ví dụ `Xem cách tính` cần dòng cơ sở mới §9.2; dòng 38 dùng `(A tặng cho)` trong khi tặng cho ngoài phạm vi §10 | 9.2, 10 |
| `research/case-catalog.md` | O2 hết hiệu lực (tỷ lệ không đều nhập được); R1/R2/R3 viết lại theo giữ/nhường; xoá case "chưa quyết"; thêm case §12 | 12 |
| `technical/inheritance-engine.md:133,:159` | Clause "tỷ lệ không đều là unsupported" xoá; §4.1 viết lại theo comparator; đổi tên field | 3, 7.1 |
| `research/validation-matrix.md` | PASS ghi trên workspace chưa commit; chạy lại sau khi xong §11.3 | — |
| `word_templates/placeholder_mapping.md:29,:31` | Quy tắc "Ngày `01/01/yyyy` hiển thị `yyyy`" là nguồn quy ước in sai ngày; §11.1 dừng ở `word_engine.py`, chưa tới gốc | 4.1, 9.3 |
| Tests: 16 dòng chứa trạng thái `"complete"` rải bốn file (`test_inheritance_engine.py` 11 dòng, `test_diagram_payload_parser.py:3065,:3084,:3112`, `test_inheritance_research_catalog.py:78`, `test_word_engine.py:107`) — số đo bằng đếm dòng chứa chuỗi, chưa phân loại từng dòng có phải `assert` | Vỡ khi làm 11.3 số 4 và số 5; cập nhật theo từng thay đổi enum/mặc định | 8, 7.1 |

## 12. Case kiểm thử bắt buộc

Bổ sung vào `research/case-catalog.md`. Mỗi dòng một câu user hiểu.

**Ngày và thời điểm**

1. Hai người chỉ có năm `2010` → không xác định thứ tự, không nhận chéo, không cảnh báo.
2. A `2010` và B `15/06/2010` → không xác định thứ tự, không nhận chéo; dòng giải thích chỉ được dùng nguyên văn nhập (`A chỉ có năm 2010`), không in khoá nội bộ.
3. Bộ ba A `2010`, B `01/03/2010`, C `01/09/2010` → A không nhận từ B và C; B và C không nhận từ A; C nhận từ B (§4.4).
4. Ngày `01/01/2010` thật → hiển thị và in Word là `01/01/2010`, không phải `2010`.
5. Dữ liệu chỉ có năm `2010` → hiển thị và in Word là `2010`, không phải `01/01/2010`.
6. Đọc rồi ghi lại hồ sơ có `01/01/2010` thật → không thoái hoá thành năm.
7. Sinh `15/06/2010`, chết `2010` → hợp lệ, không báo lỗi.
8. Chết trước ngày sinh ở cấp năm (sinh `2011`, chết `2010`) → lỗi dữ liệu ở lớp nhập; quy tắc phải **thêm mới**, xem §11.3 số 3.

**Sở hữu gốc**

9. Ba chủ đất, không ai có tỷ lệ → mỗi người `1/3` + cảnh báo `ownership_basis_unknown`.
10. Hai chủ đất `7/10` và `3/10` → dùng đúng tỷ lệ, không trả "ngoài năng lực".
11. Căn cứ "Giấy chứng nhận ghi rõ tỷ lệ" nhưng để trống tỷ lệ → cảnh báo `ownership_basis_conflict`, vẫn tính theo quy ước.
12. Điền tỷ lệ một người, để trống người kia → `invalid: partial_ownership_ratio`.
13. Tỷ lệ điền hết nhưng tổng `9/10` → `invalid: ownership_ratio_sum` kèm tổng thực tế.
14. Không có chủ đất → `invalid: missing_land_owner`.

**Quyết định phân chia**

15. Hai con còn sống, một `nhường phần` → người kia nhận cả phần; tách rõ suất pháp luật `1/2` và phần thực nhận `1`.
16. Mọi người để mặc định `giữ phần` → `complete`; không tồn tại trạng thái "chưa quyết".
17. Mọi người hàng thứ nhất đều `nhường phần` → `incomplete: all_receivers_declined`.
18. `nhường phần` cho người không có suất → không tạo phần, cảnh báo `cede_without_entitlement`.
19. Chủ đất còn sống `nhường phần` → vẫn giữ phần sở hữu gốc.
20. Người `nhường phần` rồi chết **trước** nguồn → quyết định bỏ qua; nhánh mở thế vị bình thường (§7.3).
21. Nhường một phần trong nhánh thế vị (ví dụ §7.4) → E nhận toàn bộ nhánh; breakdown tách thế vị và thoả thuận.
22. Người chết sau nguồn → nhận bất kể quyết định (§5 điểm 8).

**Thế vị và trạng thái**

23. X → A → B → C chết hết, D là con C còn sống → `unsupported: representation_depth_exceeded`.
24. Nhánh chết trước không hậu duệ → loại khỏi mẫu số; nhánh còn lại nhận toàn bộ; không tạo sở hữu cho người trung gian.
25. Ông X chết, vợ V còn sống, con duy nhất A chết trước để lại C và D, cả hai `nhường phần` → V nhận toàn bộ (§6.2).
26. Không còn ai hàng thứ nhất → `unsupported: second_order_required`, nhãn khác hẳn kết quả đã chia.
27. Hai vợ chồng cùng chết năm `2010`, không có con → cả hai vòng `second_order_required`, không âm thầm mất tài sản.
28. Vòng không có người nhận trong khi chủ đất khác còn sống → không dồn cho chủ đất đó (`INV-4`).
29. Đổi thứ tự mảng node của cùng hồ sơ → kết quả y hệt (`INV-5`).
30. Một người nhận từ hai vòng → tổng đúng, hai nguồn giữ nguyên.

**Văn bản**

31. Ba người mỗi người `1/3` → in phân số `1/3`, không in `33.33` làm số pháp lý duy nhất.
32. Hồ sơ không có văn bản từ chối → chỗ `Người từ chối` để trống, không suy từ `nhường phần`.
33. Lưu, tải lại và xuất Word dùng cùng một phân số cuối.
34. Engine trả `incomplete` hoặc `unsupported` (ví dụ hàng thừa kế thứ hai) → vẫn lưu được hồ sơ; trạng thái ghi rõ, không bị chặn (QĐ-A).
35. Người nhường phần vẫn đứng trong danh sách "Chúng tôi gồm" vì họ là bên của thoả thuận.
36. Hồ sơ `incomplete` vẫn xem/xuất được để làm việc tiếp, nhãn trạng thái hiện rõ.
37. `tong_ty_le` đọc từ kết quả exact của engine, không cộng từ phần trăm float đã lưu.
38. Một người khai ba liên kết cha/mẹ → `invalid: too_many_parents`; **không** trả `parent_capacity_exceeded` cho tới khi có thuộc tính loại quan hệ (§8.2, §11.3 số 16).

## 13. Quyết định đảo so với v1 — chờ xác nhận

Các mục dưới đây **đảo quyết định** so với `spec.md` v1 hoặc thay phán định
vòng trước. Không mục nào đã được duyệt; duyệt bản này là duyệt cả bảng.

| # | Vấn đề | v1 nói | Bản này nói | Vì sao |
|---|---|---|---|---|
| 1 | Mặc định quyết định phân chia | Ba trạng thái, mặc định `chưa quyết`, mã `receivers_undecided` | Mặc định `giữ phần`, xoá `chưa quyết` | Mặc định là của pháp luật (thừa kế mặc nhiên), không phải ý chí hệ thống khai thay; hành vi cần ý chí là `nhường phần`. Đồng thời gỡ nghẽn `workflow.md:125` và bốn đường code lưu không khớp nhau. Chi tiết §7.1 |
| 2 | Lệch độ chính xác cùng năm | Chỉ-có-năm tính `01/01` nên "A chết trước B", kèm dòng giải thích in `01/01` | Comparator theo cặp: không xác định thứ tự; cấm in khoá nội bộ | Không bịa thứ tự không có. Hai người vẫn không nhận chéo nên kết quả quyền hưởng không đổi, chỉ bỏ kết luận giả |
| 3 | Tỷ lệ sở hữu gốc không đều | `unsupported: unequal_base_ownership_source` | Nhập được nếu tổng `= 1`, kèm căn cứ sở hữu và cảnh báo | Giấy tờ thật có tỷ lệ; trả "ngoài năng lực" là từ chối hồ sơ thật |
| 4 | Con nuôi song song cha mẹ đẻ | Không đưa vào danh sách ngoài phạm vi | Đưa vào, mã `parent_capacity_exceeded`, chờ điều kiện tiên quyết thứ ba §11.1 | Mô hình tối đa hai cha/mẹ không đủ chứa cha mẹ đẻ + cha mẹ nuôi; trả sai rõ ràng tốt hơn giả vờ hỗ trợ. Chưa có thuộc tính loại quan hệ thì hai nguyên nhân trùng hình dạng payload nên chỉ trả `too_many_parents` (§8.2) |
| 5 | Lưu hồ sơ khi engine chưa `complete` | Không tài liệu nào giữ quyết định: v1 đẩy sang `workflow.md`, `workflow.md` lại không quy định; hai chỗ chặn vẫn chạy | Bỏ cả hai chỗ chặn (server + client); lưu được ở mọi trạng thái | QĐ-A đã chốt của user bị rơi khỏi vòng 2; nếu không bỏ chặn, làm 11.3 số 4 sẽ sinh hồi quy hàng thừa kế thứ hai |

## 14. Phụ lục phản biện vòng 2

Phụ lục phục vụ phản biện, không đưa vào `spec.md`.

| Phát hiện | Xử lý |
|---|---|
| File dở dang ở `<!-- NEXT -->` | Tai nạn ghi file; đã viết nốt §7–§14 |
| Mặc định `giữ phần` mâu thuẫn v1 §7.2 | Đảo có chủ đích; lập luận pháp lý ở §7.1; bảng đảo ở §13 mục 1; xoá `receivers_undecided` |
| Tỷ lệ không đều: trôi bốn chỗ (`technical/inheritance-engine.md:133,:159`; `spec.md:289`; `research/case-catalog.md:187-194`) | Xác minh; hai tài liệu còn lệch mã nhau từ trước v2 (`unequal_base_ownership_source` vs `unequal_base_ownership`); đồng bộ theo §11.4 |
| Viết "Bốn nhánh" nhưng bảng 5 dòng | Sửa thành "Năm tổ hợp" |
| `INV-10` trùng chữ "ngoài phạm vi" với §10 | Trục đặt tên `unsupported`, nhãn "ngoài năng lực engine"; §10 là danh mục nghiệp vụ |
| Ánh xạ tên trường `willReceive` | §7.1; kế hoạch đổi tên §11.3 số 5 |
| Căn cứ sở hữu mâu thuẫn dữ liệu tỷ lệ | Cảnh báo riêng `ownership_basis_conflict` (§3.2, case 11) |
| "Cùng khoá ⇒ không nhận chéo" mới là khẳng định chưa chứng minh | Chứng minh kèm case bộ ba (case 3); cả trường hợp khoá thật `01/01` trúng người chỉ có năm |
| Nhường phần rồi chết trước nguồn; nhường một phần trong nhánh thế vị | §7.3, §7.4; case 20, 21 |
| Tái hôn, con nuôi song song, "chết sau mốc X" | §10 kèm mã riêng |
| Schema không chứa độ phân giải ngày | §11.1 — điều kiện tiên quyết, là thay đổi schema |
| Vòng phản biện 2: QĐ-A mất, hai chỗ chặn còn nguyên ngoài spec | 11.3 số 11; case 34; §13 mục 5; cảnh báo hồi quy hàng thừa kế thứ hai |
| Word thiếu bên thoả thuận, chặn xuất khi incomplete, float là giá trị lưu, đa tài sản runtime 5 | 11.3 số 12–15; schema tài sản đưa vào §11.1 |
| §7.2 chống §7.4 | Giới hạn chia lại ngoài nhánh cho cấp thứ nhất |
| `too_many_parents` chồng `parent_capacity_exceeded` | Vòng 3: hai nguyên nhân trùng hình dạng payload (`inheritance_engine.py:161`), không phân biệt được bằng dữ liệu hiện có. §8.2 buộc chỉ trả `too_many_parents`; thuộc tính loại quan hệ cha/mẹ thành điều kiện tiên quyết thứ ba §11.1 |
| Đếm test lệch: tài liệu ghi 15 | Đếm lại 16 dòng chứa `"complete"` (11/3/1/1 theo bốn file); §11.4 ghi kèm cách đo |
| §11.2 dòng `Fraction` đọc rộng hơn sự thật | Thu về phạm vi engine, trỏ chéo 11.3 số 14 |
| Case 2 chống §9.2 | Sửa thành "chỉ dùng nguyên văn nhập, không in khoá nội bộ" |
| So sinh/chết: không có code để sửa | 11.3 số 3 chuyển thành việc thêm; §4.5 viết lại theo yêu cầu cài |
| Lệch dòng comparator; `credit()` cấp bằng chứng sai | Sửa `:293-306`; tách phân bổ khỏi bảo toàn trong §11.2 |
