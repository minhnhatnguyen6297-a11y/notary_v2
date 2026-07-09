# fast_text_audit - Kế hoạch triển khai

Cập nhật: 04/07/2026

## Mục tiêu

Pipeline OCR nhanh, độc lập để soát chính tả và sai chuỗi trong hồ sơ thừa kế.

- Không tham gia flow OCR CCCD của web app.
- Không dùng Celery, DB job, pairing, hay logic thừa kế phức tạp.
- Giao diện v1 là CLI terminal.
- Tối ưu cho tốc độ: OCR page-level, cache theo hash, không queue.
- So theo field/cụm, không so toàn văn tự do.
- Bỏ hẳn trang và đoạn Lờ chứng.

## Quyết định đã chốt

| # | Quyết định |
|---|---|
| 1 | CLI là giao diện duy nhất ở v1. Không web UI, không desktop app. |
| 2 | Pipeline tách biệt: `services/fast_audit/` và `tools/run_fast_audit.py`. |
| 3 | Không sửa `routers/ocr_ai.py` hay `routers/ocr_local.py` cho v1. |
| 4 | OCR qua HTTP API (`qwen`/`openai`); không fallback local OCR nặng. |
| 5 | Tin vào thứ tự scan thực tế; grouping rule-based, không AI. |
| 6 | Cache page ảnh và OCR text theo `sha256(page_bytes)`. |
| 7 | Bỏ qua toàn bộ trang/đoạn Lờ chứng trong Word lẫn OCR. |

## Cấu trúc module

```
services/fast_audit/
  __init__.py
  models.py          # dataclasses
  scan_loader.py     # quét folder
  pdf_splitter.py    # render PDF / copy ảnh
  ocr_runner.py      # gọi OCR API + cache
  doc_grouper.py     # nhóm page thành span
  word_parser.py     # parse .docx
  compare_engine.py  # so Word với OCR
  report_writer.py   # xuất md/json
  cache_store.py     # file cache
  rules.py           # regex, anchors, helpers

tools/
  run_fast_audit.py  # CLI

tests/
  test_fast_audit_scan_loader.py
  test_fast_audit_word_parser.py
  test_fast_audit_compare_engine.py
  test_fast_audit_integration.py
```

## Cách chạy

```bash
python tools/run_fast_audit.py --folder "<hoso>"
```

Cấu hình `.env`:

```env
FAST_AUDIT_OCR_PROVIDER=qwen
FAST_AUDIT_OCR_BASE_URL=https://dashscope-intl.aliyuncs.com
FAST_AUDIT_OCR_API_KEY=...
FAST_AUDIT_OCR_MODEL=qwen-vl-ocr-2025-11-20
FAST_AUDIT_OCR_CONCURRENCY=6
FAST_AUDIT_OCR_TIMEOUT=60
```

## Output

Mặc định ghi vào `<folder>\_audit_out/`:

- `run_meta.json`
- `ocr_pages.json`
- `documents.json`
- `word_extract.json`
- `report.json`
- `report.md`

Cache ghi vào `<folder>\_audit_cache/`:

- `page_images/<hash>.jpg`
- `ocr_text/<hash>.json`
- `file_hashes.json`

## Chiến lược so sánh

| Loại field | Chiến lược |
|---|---|
| CCCD, ngày tháng, số văn bản, số thửa/tờ, diện tích | Exact / normalized exact |
| Họ tên, địa danh, cụm quan hệ | RapidFuzzy partial ratio, ngưỡng 88-90 |
| Template residue | Regex placeholder, tên file vs declarant |

## Giả định

- OCR API trả text thuần ổn định cho scan tiếng Việt.
- User chạy trên máy có quyền đọc ổ mạng và ghi thư mục output.
- Word chính là `.docx`.
- Thứ tự scan nhìn chung đúng.
- V1 không xử lý logic pháp luật, chỉ audit text.

## Hướng phát triển sau

- Web UI mỏng bọc CLI.
- Desktop app shell gọi CLI.
- OCR vùng nếu page-level không đủ.
- LLM fallback sau khi đã đo được tốc độ/lợi ích rõ ràng.

## Kiem thu

- `pytest tests/test_fast_audit_*.py`
- `.\\verify.bat`
