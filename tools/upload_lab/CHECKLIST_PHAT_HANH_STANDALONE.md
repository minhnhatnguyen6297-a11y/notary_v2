# Checklist phat hanh standalone

## Ship trong goi phat hanh

- `batch_scan.py`
- `bootstrap_ui.py`
- `build_standalone_release.ps1`
- `extract_contract.py`
- `install_python_windows.ps1`
- `playwright_uploader.py`
- `requirements.txt`
- `run_ui.bat`
- `ui_runner.py`
- `uploader_selectors.py`
- `HUONG_DAN.md`
- `.env.example`
- `__init__.py`

## Khong ship

- `.env`
- `nd_storage_state.json`
- `.venv/`
- `registry.sqlite3`
- `logs/`
- `output/`
- `runs/`
- `downloads/`
- `upload_runs/`
- `__pycache__/`
- file debug, screenshot, manifest cu, du lieu thuc te

## Kiem tra truoc khi zip

- co the chay `build_standalone_release.ps1` de tao thu muc `_release/upload_lab` sach
- `run_ui.bat` mo duoc bootstrap
- `.env.example` dung `ND_STORAGE_STATE_PATH=nd_storage_state.json`
- `requirements.txt` khong con `pywin32`
- UI khong con nut `.doc -> .docx`
- tab upload co nut `Cau hinh uploader`
- `HUONG_DAN.md` da cap nhat cho flow standalone

## Acceptance nhanh

- May co Python san: `run_ui.bat` mo UI thanh cong
- May khong co Python: launcher co duong fallback cai Python
- Batch scan doc duoc `.docx` va `.doc`
- Upload tab cau hinh lan dau, dang nhap tao duoc `nd_storage_state.json`
- Dry-run van doi chieu Excel va loc duplicate truoc khi upload
