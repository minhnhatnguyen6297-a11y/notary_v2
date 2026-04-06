# Agent Handoff - Nam Dinh Upload Flow

## Muc tieu nghiep vu

Day la luong moi, tach rieng khoi app chinh. Muc tieu la xu ly cac ho so cu:

1. Quet folder tong chua ho so hop dong `.docx`.
2. Tim dung file hop dong bang so cong chung trong noi dung Word.
3. Trich xuat du lieu thanh JSON.
4. Doc JSON extracted de mo web So Tu phap Nam Dinh.
5. Tu dien form theo che do dry-run: bot dung truoc nut `Luu`, nguoi dung tu kiem tra va bam `Luu`.
6. Sau khi luu tay xong, nguoi dung quay lai UI va `Finalize Selected` de danh dau `uploaded_success`.

Khong ghep luong nay vao FastAPI app hien tai. Toan bo tool nam trong thu muc `UPLOAD/`.

## Quy tac nghiep vu da chot

### 1. Batch scan

- Script quet folder tong, co the browse bang UI hoac nhan `--folder`.
- Quet toi da `max depth = 3`.
- Chi xu ly `.docx`.
- Bo qua `~$*.docx`.
- Bo `.doc`, `.xls`, `.xlsx` va ghi registry/manifest la unsupported.
- Nhan dien file hop dong bang cach doc noi dung Word va tim pattern so cong chung:
  - `\\d+/2026/CCGD`
- Keyword `HĐ`, `HD`, `hop dong`, `hợp đồng` chi la dau hieu phu, khong du de auto-upload.
- Chong trung theo `registry.sqlite3`.
- Ho so da `uploaded_success` thi batch scan sau se skip neu trung `contract_no`.
- File `extract_failed` hoac `upload_failed` van duoc retry, ke ca cu hon `--modified-since`.

### 2. Upload Playwright

- Nguon queue la `manifest` do nguoi dung chon.
- Queue resolve bang:
  - doc `run_id` tu manifest
  - query `UPLOAD/registry.sqlite3`
  - chi lay cac status: `extracted`, `upload_failed`, `prepared_dry_run`, `prepared_partial`
  - loai `uploaded_success`
- Dry-run theo kieu tab deck:
  - mo tung ho so tren tab moi
  - dien form
  - upload file
  - verify lai field quan trong
  - chup screenshot
  - dung truoc nut `Luu`
- Khong auto click `Luu` trong MVP.
- Nguoi dung tu sua tay neu can va bam `Luu`.
- Sau do nguoi dung tick record da xong va bam `Finalize Selected`.
- `prepared_dry_run` va `prepared_partial` neu chua finalize thi phai duoc chuan bi lai o lan chay sau.
- `MAX_PREPARED_TABS = 10` mac dinh.
- Luong dung chunk:
  - chuan bi toi da 10 ho so
  - nguoi dung ra soat, luu, finalize, dong tab cu
  - bam `Start Dry-run` lai tren cung manifest de bot lay chunk ke tiep

### 3. Browser/auth

- MVP dung Playwright Chromium visible + `storage_state`.
- Khong bat buoc Chrome profile rieng.
- Ho tro `ND_BROWSER_CHANNEL=chrome` neu site that can.
- Neu `storage_state` het han, bot auto login lai bang `.env`.

### 4. Verify sau khi dien

Bat buoc doc lai toi thieu:

- `ten_hop_dong`
- `so_cong_chung`
- `nhom_hop_dong`
- `loai_tai_san`
- marker upload file thanh cong

Neu lech, thieu, hoac upload file khong xac nhan duoc thi danh dau `prepared_partial`.

## Cac file chinh da co

- `UPLOAD/extract_contract.py`
  - trich xuat 1 file `.docx`
  - co them `scan_docx_for_contract_no(path)`
- `UPLOAD/batch_scan.py`
  - batch scan folder
  - ghi `output/`, `runs/`, `registry.sqlite3`
  - bo sung helper registry cho uploader
- `UPLOAD/playwright_uploader.py`
  - queue resolution tu manifest -> registry
  - session Playwright
  - auto login + storage state
  - prepare tab dry-run
  - finalize record
- `UPLOAD/uploader_selectors.py`
  - selector va thu tu fill form
  - hien van la best-effort, can calibrate tren site that
- `UPLOAD/ui_runner.py`
  - UI gom 3 tab:
    - `Batch Scan Folder`
    - `Trich Xuat 1 File`
    - `Upload Playwright`
- `UPLOAD/HUONG_DAN.md`
  - huong dan su dung
- `UPLOAD/.env.example`
  - mau bien moi truong
- `tests/test_upload_batch_scan.py`
- `tests/test_playwright_uploader.py`

## Trang thai ky thuat hien tai

- Batch scan da chay duoc tren du lieu that.
- Queue uploader da doc duoc manifest that va thay dung 7 ho so pending.
- Unit test pass:
  - `tests.test_upload_batch_scan`
  - `tests.test_playwright_uploader`
- Playwright package da co trong `venv`.
- Chromium cho Playwright da cai xong.

## Cach chay

### UI

```powershell
cd d:\notary_v2\UPLOAD
..\venv\Scripts\python.exe ui_runner.py
```

### Batch scan bang terminal

```powershell
cd d:\notary_v2
venv\Scripts\python.exe UPLOAD\batch_scan.py --folder "D:\HoSo"
```

### Upload dry-run

1. Mo UI.
2. Vao tab `Upload Playwright`.
3. Chon manifest trong `UPLOAD/runs/`.
4. Bam `Refresh Queue`.
5. Bam `Start Dry-run`.
6. Bot mo toi da 10 tab, dien xong va dung truoc `Luu`.
7. Nguoi dung quay lai tung tab, kiem tra, sua tay neu can, bam `Luu`.
8. Tro lai UI, tick record da xong, bam `Finalize Selected`.
9. Neu con queue, bam `Start Dry-run` lai tren cung manifest.

## Bien moi truong can dung

Tao file `UPLOAD/.env` dua tren `.env.example`:

- `ND_BASE_URL`
- `ND_LOGIN_URL`
- `ND_CREATE_URL`
- `ND_USERNAME`
- `ND_PASSWORD`
- `ND_STORAGE_STATE_PATH`
- `ND_BROWSER_CHANNEL`
- `ND_MAX_PREPARED_TABS`
- `ND_POST_PREPARE_DELAY_MS`

Mac dinh quan trong:

- `ND_BROWSER_CHANNEL=chromium`
- `ND_MAX_PREPARED_TABS=10`
- `ND_POST_PREPARE_DELAY_MS=1500`

## Dieu chua khoa cung 100%

Phan con thieu lon nhat la calibrate selector tren site that. Hien tai `UPLOAD/uploader_selectors.py` chu yeu dua vao:

- label text
- input gan label
- fallback cho dropdown/editor

Can mot phien test that de:

1. Inspect DOM form tao moi nhanh.
2. Ghi selector on dinh cho:
   - login
   - ten hop dong
   - ngay cong chung
   - so cong chung
   - tinh trang
   - nhom hop dong
   - loai tai san
   - cong chung vien
   - thu ky
   - 3 editor
   - upload file
3. Xac dinh marker thanh cong cua upload file.
4. Chay thu 1-2 ho so that o dry-run.

## Luu y van hanh

- Day la nghiep vu phap ly, nen giu che do dry-run la mac dinh.
- Khong nen nang cap thanh auto save neu chua qua giai doan verify selector.
- SQLite la nguon su that cua status; khong doi sang JSON registry.
- Queue uploader khong duoc quet backlog toan bo `output/`, ma phai di tu manifest duoc chon.

