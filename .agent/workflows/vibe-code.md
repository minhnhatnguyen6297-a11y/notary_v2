---
description: Kỷ luật viết code và comment (Vibe Code Guidelines)
---

# KỶ LUẬT VIẾT CODE: GHI CHÚ "LINH HỒN" CỦA CODE (VIBE CODE)

Khi AI thực hiện viết code mới, refactor code cũ, hoặc hỗ trợ người dùng xây dựng tính năng, LUÔN LUÔN phải tự động tuân thủ các quy tắc sau mà không cần người dùng nhắc lại:

1. **Vượt ra khỏi logic khô khan**: Đừng chỉ comment những thứ hiển nhiên (như `// Lặp qua danh sách user`). Hãy giải thích lý do tồn tại của khối code đó.
2. **Comment "linh hồn" (Vibe Code)**: Tại các hàm, component, class, hay các đoạn logic quan trọng, PHẢI thêm comment giải thích "linh hồn", "ý định" hoặc "mục tiêu trải nghiệm người dùng/nghiệp vụ".
3. **Ngôn ngữ mạch lạc**: Comment phải giúp người đọc sau này (hoặc AI ở ngữ cảnh khác) khi nhìn vào liền "vibe" (cảm nhận) được ý đồ thiết kế ban đầu. Luôn đề cập đến lợi ích của End-User hoặc ràng buộc nghiệp vụ.
4. **Viết bằng Tiếng Việt**: Viết comment giải thích bằng tiếng Việt trừ khi dự án có quy định khắt khe khác.

## Các ví dụ chuẩn xác:

*Ví dụ Mảng UI/UX:*
```javascript
// Nút này phải được làm nổi bật và phản hồi nhạy ngay tức khắc, 
// vì đây là hành động call-to-action chính giúp tăng tỉ lệ chuyển đổi người dùng.
<Button variant="primary" onClick={handleCheckout}>Mua Ngay</Button>
```

*Ví dụ Mảng System/Deployment:*
```bash
# Người dùng cuối (end-user/admin) thường không rành kỹ thuật,
# script này cung cấp trải nghiệm 1-click để khởi chạy toàn bộ hệ thống từ A-Z bỏ qua setup rườm rà.
start_all_services() { ... }
```

*Ví dụ Mảng Backend/AI/Logic:*
```python
# Mẹo: Dùng 3 hình vuông ở góc QR code làm điểm neo định vị.
# Xoay ảnh liên tục kiểm tra cho đến khi đúng chiều để đảm bảo 
# camera người dùng dù cầm nghiêng hay ngược tay vẫn đều quét thành công ngay lập tức.
def align_qr_code(image):
    # ... logic OpenCV
```

> **Lưu ý dành cho AI Agent:** Hãy gọi luồng này là "Vibe Code Guidelines". Bắt đầu từ lúc đọc được file này, hãy tự thầm áp dụng triết lý này vào công việc.
