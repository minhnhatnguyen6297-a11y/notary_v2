# Nghiệp vụ sơ đồ thừa kế

> **Trạng thái:** DRAFT chờ user duyệt.
> **Cập nhật:** 22/07/2026.
> **Vai trò:** nguồn chuẩn duy nhất cho nghiệp vụ tính thừa kế của Diagram.
>
> Bài toán kiểm thử nằm tại `research/case-catalog.md`; UI/UX nằm tại
> `ux.md`; luồng Stage/Pool/Diagram nằm tại
> `workflow.md`.

## 1. Nguyên tắc và phạm vi

- Engine tính bằng phân số; phần trăm chỉ là định dạng hiển thị.
- Quan hệ gia đình phải lấy từ dữ liệu, không suy ra từ vị trí card hoặc tên slot.
- Card chỉ có hai quyết định của user: `Chủ đất` và `Nhận`; không có nút `Từ chối`.
- Có thể có nhiều `Chủ đất`. Khi chưa có tỷ lệ riêng, phần sở hữu gốc được chia đều
  `1/n`. Tỷ lệ sở hữu không đều hiện là trường hợp `chưa hỗ trợ`.
- Một người có thể nhận từ nhiều nguồn. Kết quả cuối bằng phần sở hữu gốc cộng các
  phần nhận hợp lệ; không nguồn nào được ghi đè nguồn khác.
- Một người chết chỉ mở vòng di sản khi có tài sản thực tế để lại: phần sở hữu gốc
  hoặc phần thừa kế đã thực sự nhận trước khi chết.
- Tổng tài sản cuối phải được phân phối hết và bằng `1` khi còn ít nhất một người/nhánh hợp lệ.
  Không giữ quota ở một nhánh không có người nhận và không gọi kết quả chưa chia hết là
  `complete`.
- Cùng dữ liệu đầu vào và cùng phiên bản engine phải cho cùng kết quả.
- Trường hợp ngoài phạm vi phải trả `chưa hỗ trợ`, không tự suy đoán hoặc tính gần đúng.

Phạm vi hiện tại gồm thừa kế theo pháp luật ở hàng thứ nhất, thế vị theo chiều
con/cháu/chắt, nhiều chủ đất và nhiều vòng di sản nối tiếp. Chưa mặc định hỗ trợ di
chúc, truất quyền hưởng, hàng thừa kế thứ hai/thứ ba đầy đủ, quan hệ chưa được xác
nhận, tỷ lệ sở hữu gốc không đều hoặc chuyển cho người ngoài Diagram.

## 2. Thuật ngữ và quyết định của user

- **Chủ đất:** người có phần sở hữu gốc trước khi chạy thừa kế. Một card có thể vừa
  bật `Chủ đất`, vừa bật `Nhận`.
- **Người nhận:** người được user bật `Nhận` để nhận kết quả cuối. Nút này không tạo
  quan hệ gia đình hoặc tư cách thừa kế.
- **Người không nhận:** thuật ngữ sản phẩm, được suy ra bằng `người trên Diagram -
  Chủ đất - Người nhận`. Engine loại họ khỏi kết quả phân bổ cuối và tính lại mẫu số
  giữa các người/nhánh hợp lệ còn nhận.
- **Người từ chối nhận di sản:** thuật ngữ pháp lý, chỉ dùng khi hồ sơ có dữ liệu từ
  chối hợp lệ. Không được suy ra từ nút `Nhận`, không đồng nghĩa với `Người không
  nhận`, và hiện không có nút nhập riêng trên Diagram.

Phần sở hữu gốc của chủ đất còn sống luôn thuộc người đó. Nếu họ không bật `Nhận`,
việc chuyển phần sở hữu này cho người khác là tặng cho/chuyển quyền, không phải thừa
kế hoặc từ chối di sản.

## 3. Dòng tài sản và thừa kế thế vị

Mỗi chủ đất bắt đầu với phần sở hữu gốc độc lập. Khi một người chết và có tài sản,
engine mở một vòng di sản cho người đó:

1. Di sản bằng phần sở hữu gốc cộng phần thừa kế người đó đã thực sự nhận trước đó.
2. Hàng thừa kế thứ nhất gồm cha, mẹ, vợ hoặc chồng và các con.
3. Những người cùng hàng được hưởng bằng nhau; sau đó áp dụng lựa chọn `Nhận` để tạo
   kết quả phân bổ cuối theo quy ước sản phẩm ở mục 2.
4. Phần nhận được trở thành tài sản của người nhận và có thể tạo vòng di sản tiếp
   theo nếu người đó chết sau nguồn di sản.

Thế vị dùng cùng dòng phân bổ trên nhưng coi mỗi người con là một nhánh:

- Mỗi nhánh con trước hết có phần mà người con lẽ ra được hưởng nếu còn sống.
- Nếu người con còn sống tại ngày mở thừa kế, phần nhánh trở thành tài sản họ nhận.
- Nếu người con chết trước hoặc cùng ngày, phần nhánh đi qua vị trí của họ và xuống
  trực tiếp các con của họ. Nếu một người cháu cũng chết trước hoặc cùng ngày thì
  dòng tiếp tục xuống chắt trong chính nhánh đó.
- Với cùng ngày sau chuẩn hóa, hệ thống coi là cùng thời điểm và ưu tiên mở nhánh thế vị trước.
  Không tách giờ chết để tìm người chết trước trong cùng ngày.
- Nếu người con chết trước/cùng thời điểm nhưng không còn con, cháu hoặc chắt hợp lệ để thế vị,
  nhánh con đó kết thúc và bị loại khỏi các đơn vị chia. Phần di sản được chia lại cho các
  người/nhánh hợp lệ còn lại trong cùng vòng. Ví dụ X có hai nhánh B và C, B chết cùng thời điểm
  không có hậu duệ, thì C nhận toàn bộ phần di sản của X.
- Nhánh bị loại không tạo ownership cho người trung gian, không chuyển cho vợ/chồng hoặc cha mẹ
  của người trung gian và không giữ quota riêng. Chỉ khi toàn bộ vòng không còn đơn vị hợp lệ thì
  engine trả `chưa hỗ trợ`/`no_valid_heir` thay vì tự làm mất tài sản.
- “Đi qua” chỉ là đường dẫn tính toán, không có nghĩa phần thế vị từng thuộc sở hữu
  của người đã chết trước. Phần này không được cộng vào di sản của họ và nút `Nhận`
  trên card của họ không được giữ hoặc chặn dòng thế vị.
- Chỉ con, cháu, chắt trong nhánh được nhận phần thế vị. Cha/mẹ, vợ/chồng hoặc người
  ngoài dòng con cháu của người chết trước không tham gia chia phần này.
- Khi mở nhánh thế vị, sinh slot vợ/chồng của người chết trước để thể hiện đúng cặp
  cha mẹ của các con, nhưng slot này chỉ biểu diễn quan hệ và không nhận phần thế vị.
- Nếu người chết trước có sở hữu gốc hoặc đã thực sự nhận tài sản từ nguồn khác,
  tài sản riêng đó vẫn tạo một vòng di sản độc lập theo quy tắc chung.

Như vậy, việc một người có ngày chết không tự sinh toàn bộ gia đình. Engine chỉ yêu
cầu hàng thừa kế của một vòng di sản thực sự hoặc cặp vợ/chồng và các con cần để
đọc, tiếp tục một nhánh thế vị.

## 4. Quy ước ngày chết

- Hệ thống so sánh đến cấp ngày, không xử lý giờ/phút.
- Ngày đầy đủ `dd/mm/yyyy` được dùng nguyên giá trị.
- Chỉ có năm `yyyy` được chuẩn hóa thành `01/01/yyyy`.
- Hai người có cùng ngày sau chuẩn hóa được coi là chết cùng thời điểm và dùng
  `same_day_snapshot`: không nhận chéo di sản của nhau trong cùng ngày. Ngoại lệ ưu tiên là
  nhánh thế vị của con, cháu, chắt theo quy tắc ở mục 3. Nếu nhánh không còn hậu duệ, nhánh đó
  bị loại khỏi mẫu số và phần di sản được chia lại cho nhánh hợp lệ.

Đây là quy ước hệ thống và không phát cảnh báo. User phải tự cân nhắc việc nhập ngày
đầy đủ nếu thứ tự chết thực tế làm thay đổi kết quả.

## 5. Kết quả giải thích

`Xem cách tính` chỉ cần hiển thị một dòng cho mỗi người nhận, dùng phân số chính xác
và ghi nguồn trong ngoặc:

```text
Người A nhận: 17/40 = 3/10 (X) + 1/10 (Y) + 1/40 (Z)
Người B nhận: 1/2 = 1/4 (X) + 1/4 (Y, thừa kế)
Người C nhận: 1/6 = 1/6 (X, thế vị nhánh Y)
```

Mỗi số hạng phải lấy từ cùng kết quả của engine, không để UI tự tính lại. Nguồn tặng
cho/chuyển quyền phải ghi rõ để không bị hiểu là thừa kế. Các tình huống và số liệu
kiểm thử cụ thể chỉ nằm trong `research/case-catalog.md`, không phải rule mới.

Khi thay đổi engine, phải đối chiếu quy định hiện hành về thời điểm mở thừa kế, người
thừa kế, chết cùng thời điểm, từ chối nhận di sản, hàng thừa kế và thế vị. Các quy
ước `1/n`, `01/01/yyyy`, `same_day_snapshot` và `Người không nhận` là quy ước sản
phẩm, không được trình bày như nguyên văn pháp luật.
