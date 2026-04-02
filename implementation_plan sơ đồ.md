# Kế hoạch Tái cấu trúc Sơ đồ Thừa kế Mở rộng Tăng dần

Kế hoạch này chuyển các thống nhất kiến trúc và góp ý nghiệp vụ mới nhất thành các đầu việc kỹ thuật cụ thể để xây dựng sơ đồ thừa kế dạng "đồ thị mở rộng vô hạn": mở rộng theo thế hệ, có chú thích thông minh, tính tỷ lệ an toàn và vẫn vận hành ổn định trong môi trường mạng nội bộ.

## Các quyết định đã chốt

> [!IMPORTANT]
> - `Nhãn % tỷ lệ` mặc định là **tự tính, chỉ đọc** để luôn bảo toàn tổng `100%`.
> - Bổ sung nút `Chỉnh sửa thủ công`. Khi người dùng bật chế độ này, hệ thống **khóa tự cân bằng toàn cục** cho đến khi người dùng bấm `Đặt lại`.
> - `dagre` sẽ được **phục vụ nội bộ từ local**, không dùng CDN cho tính năng sơ đồ.
> - `Anh/Chị/Em` của người chết được xếp cùng tầng thế hệ với `Owner`.
> - Thứ tự triển khai ưu tiên: **Giai đoạn 1 = tự sắp xếp bằng Dagre**, sau đó mới mở rộng đệ quy và nghiệp vụ sâu.

## Hiện trạng codebase đã xác minh

- `templates/cases/form.html` đã có sẵn dữ liệu kéo thả từ pool với các trường `id`, `name`, `doc`, `gender`, `death`, `birth`.
- `existingParticipants` cũng đã có `gender`, `death`, `share`, `receive`, nên không cần đổi schema DB chỉ để bắt đầu đợt refactor này.
- `static/ReactFlowApp.jsx` hiện vẫn đồng bộ qua `window.__CURRENT_TREE_PAYLOAD__`.
- `templates/cases/form.html` hiện đọc preview từ `window.__CURRENT_TREE_PAYLOAD__ || []`.
- Tên field thực tế trong template là `death` và `birth`, không phải `deathDate` và `birthday`.

## Phạm vi thay đổi

### [THÊM] `static/vendor/dagre.min.js`
- Thêm bản `dagre` local vào repo để tránh phụ thuộc CDN trong môi trường văn phòng công chứng hoặc mạng nội bộ.
- Tập tin này sẽ được nạp trực tiếp từ `/static/vendor/dagre.min.js`.

### [SỬA] `templates/cases/form.html`
- Nạp `dagre` từ local thay vì CDN.
- Giữ cơ chế `window.handleNativeDragStart`, nhưng chuẩn hóa contract payload để React Flow luôn nhận được:
  - `id`
  - `name`
  - `doc`
  - `gender`
  - `birth`
  - `death`
- Thay logic đọc `window.__CURRENT_TREE_PAYLOAD__` bằng lắng nghe `window.addEventListener('onFamilyTreeUpdate', ...)`.
- Cập nhật phần `live-preview` để dùng đúng dữ liệu phát ra từ React Flow:
  - `participant_id`
  - `participant_role`
  - `participant_share`
  - `participant_receive`
- Giữ fallback an toàn nếu event chưa bắn hoặc cây đang rỗng.

### [SỬA] `static/ReactFlowApp.jsx`
- Thêm lớp chuẩn hóa dữ liệu đầu vào, ví dụ `normalizePersonPayload(rawPerson)`, để hấp thụ contract hiện tại từ Jinja nhưng cho phép code nội bộ dùng logic nhất quán.
- Thay quản lý tọa độ thủ công bằng `dagre` mỗi khi cấu trúc đồ thị thay đổi.
- Thay `window.__CURRENT_TREE_PAYLOAD__ = assigned` bằng:
  - `window.dispatchEvent(new CustomEvent('onFamilyTreeUpdate', { detail }))`
- Mở rộng mô hình node để chứa đủ trạng thái nghiệp vụ:
  - `willReceive`
  - `sharePercent`
  - `shareMode`
  - `disabledReason`
  - `relationType`
  - `isGhost`
  - `isExpanded`
  - `deathComparison`
- Nâng cấp `RoleSlotNode`:
  - Người đã chết hiển thị xám màu và giảm độ đậm.
  - Có `willReceive` để bật/tắt quyền nhận.
  - Có `.share-badge` chỉ đọc trong chế độ tự động.
  - Có nút `Chỉnh sửa thủ công` và `Đặt lại`.
  - Có vùng `Insight` hiển thị chú thích nghiệp vụ.

## Các logic bắt buộc cần bổ sung trong `ReactFlowApp.jsx`

### 1. `resolveSubRelations(person, context)`
- Hàm đệ quy chịu trách nhiệm mở rộng các nhánh phát sinh khi một người đã chết.
- Không tự động sinh ra hàng loạt node thật ngay lập tức.
- Thay vào đó, sinh ra **ghost nodes / ghost slots** để sơ đồ gọn và chỉ mở khi người dùng cần.
- Ví dụ:
  - `[+] Thêm Anh/Chị/Em`
  - `[+] Thêm Con thế vị`
  - `[+] Thêm Vợ/Chồng của người này`

### 2. `compareDeathDates(ownerDeathDate, personDeathDate)`
- Hàm nghiệp vụ để phân loại đúng thuật ngữ:
  - `predeceased`: chết trước chủ đất, ưu tiên nhánh **thế vị**
  - `postdeceased`: chết sau chủ đất, ưu tiên nhánh **thừa kế chuyển tiếp**
  - `simultaneous`: chết cùng thời điểm hoặc không đủ căn cứ phân định, cần cảnh báo kiểm tra hồ sơ
  - `unknown`: thiếu dữ liệu ngày chết, chỉ hiển thị insight trung tính
- Kết quả hàm này sẽ điều khiển:
  - tiêu đề chú thích
  - nhãn nghiệp vụ trên node
  - loại ghost slot được mở ra

### 3. `calculateInheritance(nodes, shareMode)`
- Trong `auto mode`, chỉ chia cho danh sách `eligibleReceivers`.
- `eligibleReceivers` phải được tính từ những người:
  - có `willReceive = true`
  - không bị `disabled`
  - không bị loại bởi rule nghiệp vụ hiện hành
- Thuật toán `Remainder-to-Last` phải áp dụng cho **người cuối cùng còn hiệu lực**, không phải phần tử cuối trong mảng gốc.
- Trong `manual mode`:
  - giữ nguyên các giá trị người dùng nhập
  - kiểm tra tổng phải bằng `100%`
  - hiển thị cảnh báo nếu lệch tổng
  - chỉ quay về chế độ tự động khi người dùng bấm `Đặt lại`

## Kiến trúc giao tiếp mới

### Cấu trúc payload event đề xuất
```js
{
  participants: [
    {
      id,
      role,
      name,
      doc,
      gender,
      birth,
      death,
      willReceive,
      sharePercent,
      disabledReason,
      relationType,
      deathComparison
    }
  ],
  shareMode: 'auto' | 'manual',
  warnings: [],
  updatedAt: 'ISO_TIMESTAMP'
}
```

### Nguyên tắc
- `form.html` chỉ là nơi tiêu thụ state của sơ đồ.
- `ReactFlowApp.jsx` là nguồn dữ liệu chuẩn cho payload cây.
- Không dùng side effect kiểu ghi đè biến global rồi polling lại.

## Tự sắp xếp bằng Dagre

### Giai đoạn 1
- Tạo helper `buildLayoutedGraph(nodes, edges)`.
- Mỗi lần thêm node, mở ghost slot, xóa node hoặc đổi topology thì chạy lại layout.
- Giữ một số điểm neo trực quan:
  - `Owner` là tâm cụm chính
  - `Cha/Mẹ` ở tầng trên
  - `Vợ/Chồng` ngang hàng với `Owner`
  - `Con` ở tầng dưới
  - `Anh/Chị/Em` ngang tầng với `Owner`

### Mục tiêu
- Không còn đè node khi cây lớn.
- Có thể debug logic đệ quy trong trạng thái hình học ổn định.

## Quy tắc chú thích thông minh

- Nếu hàng thừa kế thứ nhất trống hoặc bị loại hết, hiển thị insight chuyển sang hàng kế tiếp.
- Nếu có chênh lệch tuổi hoặc quan hệ giới tính bất thường, giữ các cảnh báo đang có và map chúng sang UI mới.
- Nếu `compareDeathDates(...)` trả về:
  - `predeceased`: hiện insight theo hướng `thế vị`
  - `postdeceased`: hiện insight theo hướng `thừa kế chuyển tiếp`
  - `simultaneous`: hiện insight cần rà soát chứng tử hoặc thời điểm mở thừa kế

## Rủi ro và kiểm soát

- Rủi ro lớn nhất là layout chưa ổn định, dẫn tới khó debug nghiệp vụ đệ quy.
- Rủi ro thứ hai là lệch tên field giữa Jinja và React Flow.
- Rủi ro thứ ba là preview hoặc form submit vẫn đọc payload cũ.

### Biện pháp
- Triển khai Dagre trước.
- Chuẩn hóa qua `normalizePersonPayload`.
- Chỉ đổi cơ chế sync sau khi event payload mới đã phát đúng dữ liệu.

## Kế hoạch kiểm thử

### Kiểm thử thủ công
1. Mở hồ sơ có nhiều participant, xác nhận pool kéo thả vẫn mang đủ `gender`, `birth`, `death`.
2. Kéo một người còn sống vào `Owner`, xác nhận không mở nhánh chết.
3. Kéo một người đã chết vào `Cha/Mẹ`, xác nhận sơ đồ chỉ sinh ghost slot, không tạo tràn node thật.
4. Bấm ghost slot `[+] Thêm Anh/Chị/Em`, xác nhận node mới xuất hiện đúng tầng với `Owner`.
5. Kiểm tra `compareDeathDates` với 3 trường hợp:
   - chết trước chủ đất
   - chết sau chủ đất
   - chết cùng lúc hoặc không đủ dữ liệu
6. Bật hoặc tắt `willReceive` trên 3 người, trong đó người thứ 3 bị disabled, xác nhận số dư được dồn cho **người cuối cùng còn hiệu lực**.
7. Bật `Chỉnh sửa thủ công`, nhập tỷ lệ riêng, xác nhận tự cân bằng bị khóa cho tới khi `Đặt lại`.
8. Kiểm tra `live-preview` lấy đúng `participant_share` và `participant_receive` từ event payload mới.
9. Ngắt internet hoặc mô phỏng môi trường không truy cập ra ngoài được, xác nhận sơ đồ vẫn chạy vì `dagre` là local.

## Kết luận triển khai

Kế hoạch này đã sẵn sàng để chuyển sang viết code. Trình tự khuyến nghị:

1. Đưa `dagre` local vào dự án và kích hoạt tự sắp xếp ổn định.
2. Đổi cơ chế đồng bộ sang `CustomEvent`.
3. Chuẩn hóa payload và bộ máy tính tỷ lệ.
4. Thêm `ghost nodes`, `compareDeathDates` và `resolveSubRelations`.
