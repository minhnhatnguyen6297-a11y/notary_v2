# Nguyên tắc thừa kế — Tài liệu nghiệp vụ cho Sơ đồ

> **Mục đích**: Đây là tài liệu gốc định nghĩa logic nghiệp vụ cho sơ đồ thừa kế.
> Mọi thay đổi logic sơ đồ phải đối chiếu với file này trước.
> Cập nhật: 15/04/2026.

---

## Cập nhật thiết kế 29/04/2026 — engine state và tree tối giản

- Nút `★` trên thẻ người là **đồng chủ sở hữu tài sản ban đầu**, không phải một "người chết" duy nhất. Nếu có `n` người được tích `★`, phase hiện tại chia đều phần sở hữu gốc `1/n`.
- Nút `Nhận` chỉ áp dụng cho **phần di sản chảy vào** một người. Người đã là chủ sở hữu gốc không thể dùng `Nhận` để từ chối tài sản của chính họ.
- `%` hiển thị trên thẻ là output của engine, không được tính rải rác ở card hoặc legacy DOM tree. Engine tính bằng phân số, UI chỉ format phần trăm cuối cùng.
- Source of truth khi lưu hồ sơ là `InheritanceCase.engine_state_json`. `case-nguoi-chet` chỉ còn là field legacy để giữ tương thích form/router cũ.
- Sơ đồ ưu tiên tree tối giản: user hiểu bằng vị trí node, label quan hệ, nút `★`, nút `Nhận`, và mũi tên. Không thiết kế panel "nhánh phụ/external branch" tách khỏi tree chính.
- Thế vị phase này chỉ đi xuống con/cháu/chắt trong vòng thừa kế đang xét; không sinh bố mẹ/vợ chồng của người chết trước để xử lý thế vị.

---

## I. Nguyên tắc nền tảng

### 1. Xác định chủ sử dụng tài sản

Bước đầu tiên — và quan trọng nhất — là xác định ai là chủ sử dụng đất:

| Tình huống | Cách xử lý |
|---|---|
| Tài sản chung của vợ chồng | Mỗi người sở hữu **1/2**, mỗi nửa chạy dòng chảy riêng |
| Tài sản riêng của chồng | Chỉ 1 bình nước — dòng chảy từ chồng |
| Tài sản riêng của vợ | Chỉ 1 bình nước — dòng chảy từ vợ |
| Nhiều chủ đồng sở hữu (ngoài vợ chồng) | Mỗi chủ có 1 bình riêng tương ứng phần sở hữu |

> **Lưu ý thực tế**: Trong hồ sơ công chứng, trường hợp phổ biến nhất là tài sản chung vợ chồng, tức là 2 bình nước song song. Sơ đồ hiện tại giải quyết 1 bình (1 chủ đất) là bài toán cơ sở.

---

### 2. Nguyên lý Dòng Chảy

Đây là hình mẫu tư duy trung tâm của toàn bộ sơ đồ.

```
Mỗi chủ đất = 1 bình nước (= phần tài sản họ sở hữu)

Khi chủ đất chết → bình vỡ → nước chảy xuống hàng thừa kế thứ 1

Mỗi người nhận nước → hình thành 1 bình nhỏ mới

Khi người đó chết (sau khi đã nhận nước) → bình của họ vỡ tiếp
→ nước chảy tiếp theo quy tắc thừa kế của người đó

Quá trình lặp lại (đệ quy) cho đến khi:
  - Không còn ai chết, hoặc
  - Nước đã chảy hết đến những người còn sống
```

**Nguyên tắc cốt lõi của dòng chảy:**
- Nước **chỉ chảy xuống** khi người đó chết.
- Nước **không chảy ngược** về quá khứ — người đã chết trước chủ đất **không nhận được nước** (ngoại lệ: xem Thế Vị bên dưới).
- Người còn sống giữ nước — không chảy tiếp.

---

### 3. Hàng thừa kế

Nước chỉ chảy đến **hàng tiếp theo** khi hàng hiện tại không còn ai nhận.

#### Hàng thừa kế thứ 1
Cha đẻ, mẹ đẻ, vợ/chồng, con đẻ / con nuôi của người có bình nước.

> Tất cả người còn sống ở hàng 1 nhận **phần bằng nhau**.

#### Hàng thừa kế thứ 2
*(Chỉ áp dụng khi hàng 1 không còn ai nhận)*

Theo pháp luật: ông nội, bà nội, ông ngoại, bà ngoại, anh ruột, chị ruột, em ruột; cháu ruột (con của anh/chị/em).

> **Trong sơ đồ hiện tại**: Hàng 2 chỉ thể hiện anh/chị/em. Sẽ mở rộng nếu nghiệp vụ yêu cầu.

#### Hàng thừa kế thứ 3+
*(Chỉ áp dụng khi cả hàng 1 và 2 không còn ai)*

Không thể hiện trong sơ đồ ở giai đoạn này.

---

## II. Thừa kế thế vị — Trường hợp ngoại lệ

### Khái niệm

> Thế vị là trường hợp **ngoại lệ mang tính nhân văn**: Con đẻ chết trước chủ đất, đáng ra nước không thể chảy vào người đã mất. Nhưng pháp luật quy định **cháu (con của người con đó) được nhận thay** phần mà người con lẽ ra được hưởng.

### Điều kiện áp dụng

| Điều kiện | Kết quả |
|---|---|
| Con chết **trước** chủ đất | Thế vị — cháu nhận thay |
| Con chết **cùng thời điểm** với chủ đất | Coi như chết trước → Thế vị |
| Con chết **sau** chủ đất | Không phải thế vị — con đã nhận nước, bình của con vỡ tiếp theo dòng chảy thông thường |

### Ví dụ minh họa

```
Chủ đất (chết)
├── Cha ruột (còn sống)       → nhận 1/3
├── Vợ (còn sống)             → nhận 1/3
└── Con A (chết trước chủ đất) → [THẾ VỊ]
    ├── Cháu A1               → nhận 1/6  (= 1/3 ÷ 2)
    └── Cháu A2               → nhận 1/6

Nếu Con A còn sống:
├── Cha ruột  → 1/3
├── Vợ        → 1/3
└── Con A     → 1/3
```

### Giới hạn của thế vị

- Thế vị **chỉ đi theo chiều xuống**: con → cháu → chắt (nếu cháu cũng chết trước chủ đất).
- **Không áp dụng thế vị** cho vợ/chồng của người con đã chết — họ không phải hàng thừa kế của chủ đất.
- Thế vị **chỉ áp dụng cho con đẻ/con nuôi**, không áp dụng cho cha/mẹ chết trước chủ đất.

---

## III. Các quan hệ trong sơ đồ và vai trò

| Node | Hàng | Nhận di sản? | Ghi chú |
|---|---|---|---|
| Cha ruột | Hàng 1 | Có (nếu còn sống) | |
| Mẹ ruột | Hàng 1 | Có (nếu còn sống) | |
| Vợ/Chồng | Hàng 1 | Có (nếu còn sống, chưa ly hôn) | |
| Con ruột | Hàng 1 | Có (nếu còn sống) | Nếu chết trước → thế vị |
| Cháu (con của con) | Thế vị | Có (khi con chết trước) | Nhận thay phần của cha/mẹ |
| Anh/Chị/Em | Hàng 2 | Chỉ khi hàng 1 trống | |
| Cha/Mẹ vợ-chồng | — | **Không** | Chỉ thể hiện quan hệ gia đình |
| Con dâu/Rể (branchSpouse) | — | **Cần chốt** (xem mục IV) | |

---

## IV. Điểm chưa chốt — Cần xác nhận

### 4.1 Con dâu / Rể (`branchSpouse`)

Hiện tại sơ đồ có node này. Cần xác định:

- **Trường hợp A**: Con chết **sau** chủ đất → Con đã nhận nước, bình của con vỡ → nước chảy theo thừa kế của con → vợ/chồng của con (con dâu/rể) **có thể nhận** từ bình của con đó.
- **Trường hợp B**: Con chết **trước** chủ đất → thế vị → con dâu/rể **không nhận** từ chủ đất.

> **Câu hỏi**: `branchSpouse` trong sơ đồ áp dụng cho trường hợp nào? Hay cả hai?
# Căn cứ vào thời điểm chết của con, nếu con chết sau chủ đất thì mở khóa 1 ô cạnh ô con, có dấu nối để thể hiện là dâu/rể, nếu con chết trước thì không mở

### 4.2 Từ chối nhận thừa kế

Pháp luật cho phép người thừa kế từ chối. Hệ thống có cần hỗ trợ logic này không?
# Tạm thời không hỗ trợ, mặc định không tick "nhận di sản" thì là từ chối
### 4.3 Tài sản chung vợ chồng (2 bình song song)

Khi tài sản là chung vợ chồng, có 2 dòng chảy độc lập:
- **Bình của chồng** (1/2 tài sản) → dòng chảy theo người chết trước
- **Bình của vợ** (1/2 tài sản) → dòng chảy khi người còn lại chết

> Sơ đồ hiện tại xử lý 1 bình. Logic 2 bình cần thiết kế riêng nếu nghiệp vụ yêu cầu.
# Thiết kế luôn, rất nhiều trường hợp vợ chồng đều đã chết

### 4.4 Con nuôi

Pháp luật đặt con nuôi ngang bằng con đẻ. Sơ đồ có cần phân biệt không?
# Không, hiển thị chung là con
---

## V. Quy tắc tính phần trăm (logic hiện tại)

```
1. Xác định tập người nhận (willReceive = true, còn sống, không có lý do bị loại)
2. Nhóm theo "đơn vị thừa kế":
   - Mỗi người hàng 1 (cha, mẹ, vợ/chồng, con còn sống) = 1 đơn vị
   - Nhóm cháu thế vị của 1 người con = 1 đơn vị (chia đều trong nhóm)
3. Chia 100% đều cho các đơn vị
4. Trong mỗi đơn vị nhiều người: chia đều tiếp
```
# duyệt logic này

**Ví dụ:**
```
Hàng 1 có: Vợ + Con A (sống) + [Nhóm thế vị của Con B gồm Cháu B1, B2]
→ 3 đơn vị → mỗi đơn vị 33.33%
→ Vợ: 33.33%
→ Con A: 33.33%
→ Cháu B1: 16.67%, Cháu B2: 16.67%
```
---

## VI. Điều kiện sinh/ẩn node trong sơ đồ

| Node | Điều kiện hiển thị |
# Tạo 1 chức năng để thể hiện chủ tài sản. Ví dụ nhiều người ở hàng 1 (có trường hợp là anh chị em, do bố mẹ chết sau) thì phải có 1 cách phân biệt ai là chủ đất => Gợi ý, tạo 1 ô tích chủ đất để thể hiện chủ đất ban đầu.
|---|---|
| Cha ruột, Mẹ ruột, Vợ/Chồng | Luôn hiển thị (có thể trống) 
|# Luôn hiển thị 2 ô cho cha mẹ, 1 ô cho vợ/chồng, nếu không điền gì thì
| Con | Luôn có ít nhất 1 slot trống; tự sinh thêm khi tất cả đã có người |
| Anh/Chị/Em | Hiển thị node ghost khi cha/mẹ đã gán (hoặc luôn hiển thị — cần chốt) |
| Tầng 4 (Cháu) | Chỉ hiện khi có ít nhất 1 con chết trước chủ đất |
| Cháu của Con X | Chỉ hiện khi Con X có người và đã gán ngày mất trước chủ đất |
# Tầng 4 hiện ô cháu khi ô con có người chết, tức là hiện ô cháu bất kể con X chết trước hay chết sau. Chỉ khác nhau là con X chết trước X thì vợ/chồng X không được hưởng, con X chết sau X thì vợ/chồng X được hưởng
| Con dâu/Rể | Phụ thuộc vào kết quả chốt mục IV.1 |

---

## VII. Sơ đồ luồng tổng quát

```
[Chủ đất chết]
      |
      v
[Xác định hàng 1]
      |
  Có người còn sống?
  /              \
Có               Không
  |                 |
Chia đều      [Xét hàng 2]
hàng 1            |
  |           Có anh/chị/em sống?
  |           /              \
  |          Có               Không
  |          |                  |
  |       Chia đều          Hàng 3+
  |       hàng 2            (ngoài scope)
  |
Xét từng người hàng 1:
  - Còn sống → giữ phần
  - Chết sau chủ đất → bình vỡ tiếp (đệ quy)
  - Chết TRƯỚC chủ đất → thế vị (cháu nhận thay nếu có)
```
