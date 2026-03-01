# CHAT HANDOFF - 2026-03-01

Tài liệu này dùng để tiếp tục công việc trên máy khác khi không thấy lại lịch sử chat.

## Repo
- URL: https://github.com/minhnhatnguyen6297-a11y/notary_v2.git
- Branch: main
- Trạng thái đã force push từ máy hiện tại lên `origin/main` tại commit: `33db2c3`

## Các thay đổi/chủ đề đã làm gần đây
- Chỉnh luồng tạo hồ sơ thừa kế theo hướng nhập nhanh trực tiếp trên form.
- UI kéo-thả phân vai trò trong cây quan hệ.
- Cải tiến hiển thị lỗi tiếng Việt, tránh văng sang trang JSON lỗi.
- Bổ sung/chỉnh phần form tài sản (thứ tự trường và bảng loại đất - diện tích - thời hạn).
- Sửa nhiều lỗi backend ở `routers/cases.py` liên quan create/edit participant.

## Lỗi đã gặp trong log (tham khảo)
- `NameError: name 'case' is not defined` trong create.
- `AttributeError: type object 'InheritanceParticipant' has no attribute 'case_id'` trong edit.
- `NameError: name 'request' is not defined` ở nhánh exception của edit.
- Một số lần `422 Unprocessable Entity` do payload/list field không đúng kiểu.

## Chạy dự án trên máy mới
```powershell
git clone https://github.com/minhnhatnguyen6297-a11y/notary_v2.git
cd notary_v2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

## Quy trình làm việc ngắn gọn
- Bắt đầu ngày làm việc: `git pull`
- Kết thúc: `git add .` -> `git commit -m "..."` -> `git push`

## Ghi chú quan trọng
- Nếu VS Code không thấy terminal server log, có thể bạn đang chạy app ở cửa sổ CMD riêng.
- Log lỗi phải xem ở đúng cửa sổ đã chạy lệnh `uvicorn`.
