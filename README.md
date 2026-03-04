Phần mềm Quản lý Hồ sơ Công chứng

Cài đặt lần đầu (chỉ làm 1 lần)
Bước 1 — Cài Python
Vào trang: https://www.python.org/downloads
Tải về và cài. Khi cài nhớ tích vào ô Add Python to PATH trước khi nhấn Install.
Bước 2 — Giải nén phần mềm
Giải nén file zip vào thư mục bất kỳ, ví dụ C:\CongChung
Bước 3 — Mở CMD trong thư mục đó
Mở thư mục C:\CongChung bằng File Explorer
→ Click vào thanh địa chỉ trên cùng
→ Gõ cmd rồi nhấn Enter
Bước 4 — Cài thư viện (chỉ làm 1 lần)
Trong cửa sổ CMD vừa mở, gõ lệnh sau rồi nhấn Enter:
pip install -r requirements.txt
Chờ đến khi xong (khoảng 1-2 phút).

Dùng hàng ngày
Khởi động
Mở CMD trong thư mục phần mềm (làm như Bước 3 ở trên), rồi gõ:
uvicorn main:app --reload
Khi thấy dòng chữ Uvicorn running on http://127.0.0.1:8000 → mở Chrome và vào:
http://127.0.0.1:8000
Tắt phần mềm
Quay lại cửa sổ CMD → nhấn Ctrl + C

⚠️ Cửa sổ CMD phải luôn mở trong lúc dùng phần mềm. Đừng đóng nó.


Quy trình làm hồ sơ thừa kế
1. Nhập người (menu Danh sách người)
→ Thêm từng người từ CCCD hoặc giấy khai tử
→ Người đã chết thì điền thêm Ngày chết
2. Nhập tài sản (menu Tài sản / Sổ đỏ)
→ Nhập thông tin từ sổ đỏ / GCN quyền sử dụng đất
3. Tạo hồ sơ (menu Hồ sơ thừa kế)
→ Chọn người chết + tài sản + loại văn bản
→ Thêm người thừa kế, nhập tỷ lệ % từng người
4. Xuất Word
→ Nhấn Khoá hồ sơ → nhấn Xuất Word → file .docx tải về máy

Import hàng loạt từ Excel
Vào Danh sách người → nhấn Tải file mẫu → điền dữ liệu vào file → nhấn Import Excel

Sao lưu dữ liệu
Toàn bộ dữ liệu lưu trong file notary.db trong thư mục phần mềm.
Copy file này sang USB hoặc Google Drive để sao lưu.

Lỗi thường gặp
LỗiCách sửapython not foundCài lại Python, nhớ tích Add Python to PATHuvicorn not foundChạy lại pip install -r requirements.txtTrang web trắng / không mở đượcKiểm tra CMD còn đang chạy khôngCổng 8000 đang bậnThêm --port 8001 vào lệnh chạy, rồi vào http://127.0.0.1:8001
