# Catalog bài toán nghiệp vụ thừa kế

> **Trạng thái:** DRAFT chờ user duyệt.
> **Cập nhật:** 22/07/2026.
> **Nguồn rule:** `../spec.md`.
>
> File này chỉ chứa ví dụ và kết quả mong đợi. Khi ví dụ mâu thuẫn với tài liệu
> nghiệp vụ, phải dừng và sửa mâu thuẫn trước khi sửa code.

---

## 4. Research set

Research provenance and machine-readable records are maintained in
`case-provenance.md` and
`tests/fixtures/inheritance_research_cases.json`.

- Only `accepted` records may be used as exact engine oracles.
- `ambiguous`, `source_error`, `out_of_scope`, and `duplicate_source` records
  are review evidence, not expected results.
- If a source conflicts with the approved business rule, classify the mismatch;
  do not change code or rules to force a match.

## 1. Ký hiệu

- `owner`: người được đánh dấu `Chủ đất`.
- `receive`: người được đánh dấu `Nhận`.
- `base`: phần sở hữu gốc.
- `vested`: phần đã thực sự nhận từ vòng di sản trước.
- `estate`: `base + vested` tại thời điểm người đó chết.
- Năm chết không có ngày được chuẩn hóa thành `01/01/yyyy`.

---

## 2. Fixture X/Y/D/Z

### Đề bài

- X và Y là vợ chồng, cùng là chủ đất; mỗi người có `1/2`.
- X chết năm 2011, Y chết năm 2015; có ba con M, N, O.
- Cha mẹ X: A chết 1995, B chết 1996.
- Cha mẹ Y: C chết 1997, D chết 2016.
- C và D có hai con Y và Z.
- Z chết năm 2015, có hai con Z2 và Z3.

### Trace chuẩn

1. X chết: `estate(X) = 1/2`. Hàng thứ nhất còn Y, M, N, O; mỗi người nhận
   `1/8`. Sau vòng này Y có `1/2 + 1/8 = 5/8`.
2. Y chết: `estate(Y) = 5/8`. Hàng thứ nhất còn D, M, N, O; mỗi người nhận
   `5/32`.
3. D chết: `estate(D) = 5/32`. Hai con Y và Z đều chết trước D. Nhánh Y do
   M, N, O thế vị; nhánh Z do Z2, Z3 thế vị.

### Kết quả

- `M = N = O = 59/192`.
- `Z2 = Z3 = 5/128`.
- Tổng bằng `1`.

Fixture này kiểm tra nhiều vòng di sản và hai nhánh thế vị song song một cấp.
Nó không phải fixture thế vị nhiều cấp.

---

## 3. Ma trận thay đổi trạng thái Y

Giả định X là chủ đất, Y là con X và Z là con Y.

### Case Y1 — Y còn sống

- Y không phải chủ đất và chưa chết.
- X chết trước Y.

Kỳ vọng:

- Y thuộc hàng thứ nhất và nhận từ X.
- Z không tham gia vòng X và không cần node để tính vòng X.
- Không mở vòng di sản Y khi Y còn sống.

### Case Y2 — Y chết trước X, không có tài sản

- Y không phải chủ đất.
- Y chết trước X.
- Z còn sống.

Kỳ vọng:

- Y không nhận tài sản từ X.
- Không có `estateEvent(Y)`.
- Z nhận trực tiếp phần thế vị của nhánh Y.
- Có thể hiển thị Y làm mắt xích huyết thống.
- Không yêu cầu cha/mẹ hoặc vợ/chồng Y cho vòng của X.

### Case Y3 — Y chết sau X

- Y không phải chủ đất.
- Y còn sống tại ngày X chết và nhận một phần từ X.
- Y chết ở ngày sau đó.

Kỳ vọng:

- Vòng X ghi phần của Y vào `vested(Y)`.
- Khi Y chết, mở `estateEvent(Y)` với phần đã nhận từ X.
- Khi đó mới yêu cầu cha/mẹ, vợ/chồng và con của Y để tính vòng Y.
- Z nhận trong vòng Y với tư cách con, không phải thế vị cho Y.

### Case Y4 — Y chết trước X nhưng là chủ đất

- X và Y cùng là chủ đất.
- Y chết trước X.
- Z còn sống.

Kỳ vọng:

- Mở vòng di sản Y từ `base(Y)`.
- Trong vòng X, Y vẫn không nhận; Z có thể thế vị nhánh Y.
- Hai dòng tài sản độc lập phải được cộng vào người nhận cuối, không ghi đè.

---

## 4. Thế vị nhiều cấp thật

### Đề bài

- X là chủ đất và chết.
- A là con X, chết trước X.
- B là con A, cũng chết trước X.
- C là con B và còn sống.

Kỳ vọng:

- Không có `estateEvent(A)` hoặc `estateEvent(B)` nếu A và B không có tài sản
  riêng hoặc phần đã nhận trước đó.
- C nhận trực tiếp phần mà A lẽ ra được hưởng trong vòng X.
- Không sinh cha/mẹ hoặc vợ/chồng A/B để chia phần thế vị.

---

## 5. Cùng ngày và năm chết

### Case D1 — cùng ngày đầy đủ

- A và B có quyền thừa kế của nhau.
- Cả hai có cùng ngày chết theo dữ liệu.

Kỳ vọng:

- Áp dụng `same_day_snapshot`.
- A và B không nhận chéo trong ngày đó.
- Không phát cảnh báo UI.

### Case D2 — cùng năm, không có ngày

- A chết `2015`, B chết `2015`.

Kỳ vọng:

- Cả hai được chuẩn hóa thành `01/01/2015`.
- Áp dụng `same_day_snapshot`.
- User chịu trách nhiệm nhập ngày đầy đủ nếu cần kết quả khác.

### Case D3 — khác năm

- A chết `2015`, B chết `2016`.

Kỳ vọng:

- A được xử lý trước B.
- Phần B nhận từ A được cộng vào estate của B trước vòng B.

---

## 6. Nhiều chủ đất

### Case O1 — năm chủ đất

- Có năm người bật `Chủ đất`.
- Không có dữ liệu tỷ lệ riêng.

Kỳ vọng:

- Mỗi người có `base = 1/5`.
- Chủ còn sống giữ phần gốc.
- Chủ đã chết mở vòng di sản riêng từ `1/5`.

### Case O2 — tỷ lệ không đều

- Giấy tờ ghi tỷ lệ sở hữu không bằng nhau.
- Hệ thống chưa có đầu vào tỷ lệ.

Kỳ vọng:

- Trả `unsupported: unequal_base_ownership`.
- Không âm thầm chia đều và coi đó là kết quả chính xác của hồ sơ.

---

## 7. Người nhận, người không nhận và người từ chối

### Case R1 — người không nhận

- A và B cùng thuộc hàng hợp lệ; A không bật `Nhận`, B bật `Nhận`.
- Không có dữ liệu từ chối hợp lệ.

Kỳ vọng:

- A thuộc danh sách `Người không nhận`.
- A không được xuất dưới nhãn `Người từ chối`.
- `entitlementTrace` vẫn cho thấy A và B là hai người được xét.
- `distributionTrace` loại A và tính lại mẫu số; B nhận toàn bộ phần của vòng.

### Case R1b — không còn người nhận hợp lệ

- A và B cùng thuộc hàng hợp lệ nhưng đều không bật `Nhận`.

Kỳ vọng:

- Không tự chuyển sang hàng thừa kế tiếp theo.
- Không tự chọn một người khác trên Diagram.
- Trả trạng thái cần user xử lý trước khi chốt kết quả.

### Case R2 — chủ đất không bật Nhận

- A có `base = 1/2` và không bật `Nhận`.

Kỳ vọng:

- A vẫn giữ `base = 1/2` trong lớp sở hữu.
- Engine không coi A đã từ chối tài sản của chính mình.
- Nếu phần này chuyển cho người khác, kết quả phải ghi nguồn là tặng cho/chuyển
  quyền từ A, không ghi nguồn là thừa kế.
- `Xem cách tính` tách rõ phần thừa kế và phần A chuyển quyền.

### Case R3 — từ chối theo nghĩa pháp lý

- A có quyền hưởng và hồ sơ có dữ liệu xác nhận việc từ chối.

Kỳ vọng:

- Chỉ dữ liệu xác nhận riêng mới được gọi là `Người từ chối`.
- Nút `Nhận` không được dùng thay cho dữ liệu xác nhận đó.
- Khi chưa có đầu vào từ chối trong sản phẩm, engine không tự suy ra kết quả này.

---

## 8. Acceptance chung

- Không có vòng di sản giá trị `0`.
- Người chết trước trong nhánh thế vị không nhận rồi truyền lại.
- Tổng tài sản sau mọi vòng bằng `1`.
- Một người nhận từ nhiều nguồn có kết quả được cộng dồn.
- `Xem cách tính` trình bày được toàn bộ trace trên bằng các dòng ngắn.
- Save/reload cùng input phải cho cùng kết quả và cùng phiên bản engine.
