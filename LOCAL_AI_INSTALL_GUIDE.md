# Huong dan Local OCR RapidOCR-only tren Windows

Tai lieu nay da duoc chuan hoa theo huong RapidOCR-only.
He thong local OCR khong con dung module crop/phn loai rieng.

## Buoc 1: Cai Python

1. Cai Python 3.10.x (khuyen nghi 3.10.11, 64-bit).
2. Bat buoc tick `Add python.exe to PATH` khi cai.

## Buoc 2: Khoi tao moi truong

1. Chay `setup.bat` de tao `venv` va cai thu vien nen.
2. File `.env` duoc tao tu `.env.example` neu chua ton tai.

## Buoc 3: Cai Local OCR

1. Chay `run.bat`.
2. Script se tu kiem tra Local OCR va goi `install_local_ocr.bat --auto` neu thieu dependency.
3. Neu muon cai truoc bang tay, chay `install_local_ocr.bat`.
4. Neu may co NVIDIA CUDA va muon dung GPU, cai them:
   - `pip install -r requirements-gpu.txt`

## Luong xu ly hien tai

- Frontend uu tien QR truoc.
- Backend Local OCR dung Smart Crop OpenCV (soft fallback ve full image).
- Backend luon co rescue pass quet QR, khong bi chan boi `client_qr_failed`.
- `summary.local_engine` se tra ve `RapidOCR (CPU)` hoac `RapidOCR (GPU)`.

## Kiem tra nhanh sau cai dat

1. Mo `http://127.0.0.1:8000`.
2. Vao modal OCR anh va upload bo anh test.
3. Xac nhan queue chay duoc va poll trang thai tra ket qua binh thuong.
