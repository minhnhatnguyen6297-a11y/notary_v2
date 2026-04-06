# Trích xuất Hợp đồng và Batch Scan Folder

## Cài đặt

```bash
pip install python-docx playwright python-dotenv
playwright install chromium
```

## 1. Trích xuất một file `.docx`

```bash
python extract_contract.py "D:\hoso\hop_dong.docx"
```

Kết quả:
- In JSON ra màn hình
- Tự lưu file `*_extracted.json` cùng thư mục với file gốc

## 2. Batch scan cả folder tổng

Script `batch_scan.py` sẽ:
- Cho chọn folder tổng bằng hộp thoại Windows, hoặc nhận `--folder`
- Quét đệ quy tối đa 3 tầng
- Chỉ xét `.docx`, bỏ qua `~$*.docx`
- Tìm file hợp đồng bằng số công chứng dạng `123/2026/CCGD` trong nội dung Word
- Gọi `extract_contract.py` để trích xuất JSON
- Ghi output vào `UPLOAD/output/`
- Ghi manifest từng lần chạy vào `UPLOAD/runs/`
- Ghi registry SQLite vào `UPLOAD/registry.sqlite3`
- Ô `modified since` nhận cả `YYYY-MM-DD` và `DD/MM/YYYY`

### Cách dùng

```bash
# Mở hộp thoại chọn folder
python batch_scan.py

# Chỉ định folder trực tiếp
python batch_scan.py --folder "D:\HoSo"

# Chỉ quét file sửa từ ngày 2026-04-01 trở đi
python batch_scan.py --folder "D:\HoSo" --modified-since 2026-04-01

# Quét lại toàn bộ, bỏ qua mốc ngày
python batch_scan.py --folder "D:\HoSo" --full-rescan
```

## 3. Giao diện UI đơn giản

Neu khong muon go lenh, co the mo UI bang 1 trong 2 cach:

```bash
python ui_runner.py
```

hoac double-click:

```text
UPLOAD/run_ui.bat
```

UI hien tai co 2 man hinh:
- `Batch Scan Folder`: browse folder tong, nhap `modified since` neu can, tick `full rescan`, roi bam `Chay Batch Scan`
- `Trich Xuat 1 File`: browse 1 file `.docx`, roi bam `Trich Xuat 1 File`
- `Upload Playwright`: chon manifest, refresh queue, `Start Dry-run`, `Stop`, `Finalize Selected`

UI se hien log ngay trong cua so va thong bao duong dan output khi chay xong.

## 4. Upload Playwright dry-run

Luong su dung:
- Chay `Batch Scan Folder` truoc de tao `manifest` va `output`
- Mo tab `Upload Playwright`
- Browse file manifest trong `UPLOAD/runs/`
- Bam `Refresh Queue`
- Bam `Start Dry-run`

Bot se:
- doc dung batch tu `manifest` duoc chon
- query `registry.sqlite3` theo `run_id`
- mo toi da `ND_MAX_PREPARED_TABS` tab
- tu dien form va upload file
- dung truoc nut `Luu`

Sau khi nguoi dung da tu ra soat, sua va bam `Luu` xong:
- quay lai UI
- chon cac record da luu thanh cong
- bam `Finalize Selected`

Neu batch con ho so chua xu ly:
- dong cac tab cu neu da xong
- bam `Start Dry-run` lai tren cung manifest
- bot se tu bo qua record `uploaded_success` va lay chunk tiep theo

## 5. Cau hinh uploader

Tao file `.env` trong `UPLOAD/` dua theo mau `.env.example`:

```env
ND_BASE_URL=https://congchung.namdinh.gov.vn
ND_LOGIN_URL=https://congchung.namdinh.gov.vn
ND_CREATE_URL=https://congchung.namdinh.gov.vn/ho-so-cong-chung/tao-moi-nhanh
ND_USERNAME=
ND_PASSWORD=
ND_STORAGE_STATE_PATH=UPLOAD/nd_storage_state.json
ND_BROWSER_CHANNEL=chromium
ND_MAX_PREPARED_TABS=10
ND_POST_PREPARE_DELAY_MS=1500
```

## Quy tắc nhận diện file hợp đồng

- Bắt buộc phải tìm thấy số công chứng trong nội dung `.docx`
- Pattern hiện tại đang khóa năm: `\d+/2026/CCGD`
- Các keyword `HĐ`, `HD`, `hop dong`, `hợp đồng` chỉ là tín hiệu phụ, không đủ để auto flow nếu không có số công chứng

## Output batch scan

- `UPLOAD/output/<contract_no>_<hash>.json`
- `UPLOAD/runs/<timestamp>.json`
- `UPLOAD/registry.sqlite3`
- `UPLOAD/upload_runs/<timestamp_runid>/`

Ví dụ:

```text
UPLOAD/
├── batch_scan.py
├── extract_contract.py
├── output/
│   └── 428_2026_CCGD_ab12cd34.json
├── runs/
│   └── 2026-04-06_143022.json
├── upload_runs/
│   └── 20260406T170000_run1234/
└── registry.sqlite3
```

## Lưu ý

- Chỉ hỗ trợ `.docx`
- File đã `upload_failed` hoặc `extract_failed` vẫn được retry, kể cả khi cũ hơn `--modified-since`
- Nếu một `contract_no` đã có trạng thái `uploaded_success` trong registry thì batch scan sẽ skip các file mới cùng số đó
- Muốn đổi tên công chứng viên, thư ký mặc định thì sửa trong `extract_contract.py`
- Upload Playwright hien la `dry-run`: bot khong tu bam `Luu`
- Queue uploader chi lay record tu `manifest` duoc chon, khong quet ca backlog cu
