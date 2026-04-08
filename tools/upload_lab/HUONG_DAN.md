# Upload Tool Standalone

## Chay lan dau

Double-click `run_ui.bat`.

Launcher se tu:
- tim Python 3.10+ san co
- neu chua co thi thu cai qua `winget`, neu that bai se tai installer Python tu `python.org`
- tao `.venv`
- cai dependency tu `requirements.txt`
- cai `playwright chromium`
- mo giao dien

Luu y:
- Lan dau can Internet
- Khong can Microsoft Word/Office
- Moi du lieu runtime duoc tao ngay trong thu muc tool: `output`, `runs`, `logs`, `downloads`, `upload_runs`, `registry.sqlite3`

Neu can tao bo phat hanh sach:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_standalone_release.ps1
```

## Cau hinh uploader lan dau

Tab `Upload Playwright` se tu nhac cau hinh neu:
- chua co `.env`
- thieu `ND_USERNAME` hoac `ND_PASSWORD`
- chua co `nd_storage_state.json`

Flow dung:
1. Mo tab `Upload Playwright`
2. Bam `Cau hinh uploader`
3. Dien `Base URL`, `Login URL`, `Create URL`, tai khoan, mat khau
4. Bam `Luu va dang nhap`
5. Tool se tu dang nhap va tao `nd_storage_state.json`

File `.env` duoc tao tu `.env.example` neu thieu.

## Batch scan

Tab `Batch Scan Folder`:
- browse folder tong
- nhap `modified since` neu can (`YYYY-MM-DD` hoac `DD/MM/YYYY`)
- tick `full rescan` neu muon quet lai toan bo
- bam `Chay Batch Scan`

Batch scan:
- ho tro ca `.docx` va `.doc`
- bo qua `~$*.docx` va `~$*.doc`
- tim so cong chung trong noi dung file Word
- trich xuat JSON
- ghi output vao `output/`
- ghi manifest vao `runs/`
- ghi registry vao `registry.sqlite3`

## Trich xuat 1 file

Tab `Trich Xuat 1 File`:
- chon 1 file Word (`.docx` hoac `.doc`)
- bam `Trich Xuat 1 File`

Ket qua:
- in log trong UI
- luu file `*_extracted.json` canh file goc

## Upload Playwright

Luong dung:
1. Chay batch scan truoc de tao `manifest`
2. Mo tab `Upload Playwright`
3. Chon file manifest trong `runs/`
4. Chon file Excel doi chieu hoac bam `Tai tu web`
5. Bam `Refresh Queue`
6. Bam `Start Dry-run`

Tool se:
- doc queue theo `run_id` trong manifest
- doi chieu cot A cua file Excel so cong chung
- loai cac ho so trung so da ton tai tren web
- mo tung tab Playwright va dung truoc nut `Luu`

Sau khi da tu kiem tra va bam `Luu` tren web:
- quay lai UI
- chon cac record da xong
- bam `Finalize Selected`

Neu van con record chua xu ly:
- bam `Start Dry-run` lai tren cung manifest
- tool se lay chunk tiep theo

## File cau hinh

Mau `.env.example`:

```env
ND_BASE_URL=https://congchung.namdinh.gov.vn
ND_LOGIN_URL=https://congchung.namdinh.gov.vn
ND_CREATE_URL=https://congchung.namdinh.gov.vn/ho-so-cong-chung/tao-moi-nhanh
ND_USERNAME=
ND_PASSWORD=
ND_STORAGE_STATE_PATH=nd_storage_state.json
ND_BROWSER_CHANNEL=chromium
ND_MAX_PREPARED_TABS=10
ND_POST_PREPARE_DELAY_MS=1500
```

## Output va log

- `output/<contract_no>_<hash>.json`
- `runs/<timestamp>.json`
- `registry.sqlite3`
- `logs/playwright_uploader.log`
- `upload_runs/<timestamp_runid>/`

Moi artifact dry-run thuong gom:
- `dry_run_trace.log`
- `before_save_<so_cong_chung>.png`
- `debug_<so_cong_chung>.json`

## Troubleshooting nhanh

- Thieu Python/Playwright: chay lai `run_ui.bat`
- Thieu `openpyxl`: chay lai `run_ui.bat`
- Khong upload duoc vi chua dang nhap: mo `Cau hinh uploader` va `Luu va dang nhap`
- Khong doi chieu duoc Excel: kiem tra file export va cot A
