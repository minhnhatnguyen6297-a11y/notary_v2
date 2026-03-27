# Cẩm nang Kích hoạt Local OCR (YOLO + RapidOCR) trên Windows

Nếu bạn muốn chạy mô-đun AI hạng nặng (OCR Offline) trực tiếp trên máy Windows để đạt được **100% chức năng** của Repo này, bạn buộc phải "dọn dẹp" lại môi trường máy tính để tránh lỗi DLL của thư viện C++ (PyTorch/OpenCV/YOLO) và giữ đường OCR text engine ở mức nhẹ hơn với RapidOCR.

Dưới đây là 3 bước chuẩn chỉnh nhất dành cho người mới:

---

### Bước 1: Dọn dẹp tàn dư cũ (Python 3.13)
Phiên bản Python 3.13 hiện tại của bạn là nguyên nhân chính gây ra lỗi `c10.dll` vì các thư viện AI chưa hỗ trợ kịp.
1. Mở **Control Panel** -> **Uninstall a program**.
2. Tìm chữ `Python 3.13` (kể cả bản Launcher) và ấn **Uninstall** toàn bộ.
3. Quay lại thư mục code dự án của bạn (thư mục chứa `run.bat`), tìm thư mục **`venv`** và **XÓA THẲNG TAY** thư mục đó (Shift + Delete). *Lý do: thư mục này đang chứa các thư viện tải bằng lỗi 3.13 cũ, giữ lại sẽ gây lỗi.*

### Bước 2: Cài đặt Python "Quốc dân" 3.10
Python 3.10 là phiên bản hoàn hảo nhất, mọi file `wheel` (.whl) của AI đều gắn liền với nó, giúp máy không bao giờ phải tự build C++.
1. Nhấp vào link tải **Python 3.10.11 (64-bit)**: [Windows installer (64-bit)](https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe)
2. Mở file `.exe` vừa tải. **[CỰC KỲ QUAN TRỌNG]**: Ở màn hình cài đặt đầu tiên, bạn bắt buộc phải tích chọn ô **`Add python.exe to PATH`** ở góc dưới cùng bên trái.
3. Nhấp `Install Now` và đợi hoàn thiện.

### Bước 3: Tiêm "Thuốc trợ lực" C++ (Runtime DLL)
Để Windows không bao giờ than phiền về các file `.dll` vắng mặt khi kích hoạt PyTorch hoặc OpenCV.
1. Nhấp vào link tải từ Microsoft: [VC_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe)
2. Cài đặt file vừa tải vào máy (rất nhanh, chỉ 5 giây).
3. (Khuyến nghị) Khởi động lại máy tính 1 lần để Windows nạp DLL nền.

---

### Bước 4: Khởi chạy 100% Sức mạnh App
Sau khi máy bạn đã "thay máu" hoàn tất, hãy quay lại thư mục Code (`notary_v2`):

1. Bấm đúp **`setup.bat`** (Nó sẽ tạo ra 1 thư mục `venv` hoàn toàn mới bằng lõi Python 3.10 và cài các thư viện Web).
2. Bấm đúp **`run.bat`** để mở Server. Ngay lần chạy đầu, script sẽ **tự kiểm tra và tự cài Local OCR** nếu máy còn thiếu bộ **YOLO + RapidOCR**.
3. Script cài sẽ tự ghim lại **`numpy<2`** để tránh cảnh báo/xung đột giữa Torch và NumPy 2.x trên Windows.
4. Chỉ khi bạn muốn cài trước bằng tay hoặc debug riêng, mới cần chạy **`install_local_ocr.bat`**.

Bây giờ bạn có thể thử ném một tấm CCCD vào Web, bấm nút **`[ Local OCR (Miễn phí) ]`** và tận hưởng "con quái thú" AI chạy 100% Offline trên RAM máy trạm của bạn.
