# Plan: OCR AI (Cloud)

**Trạng thái:** active  
**Cập nhật:** 2026-04-07  
**Files liên quan:** `routers/ocr.py`  
**API endpoint:** `POST /api/ocr/analyze`

---

## Tinh thần / Mục tiêu

OCR AI là con đường **nhanh và đơn giản** — gửi ảnh lên AI vision model (OpenAI GPT-4o / Gemini), nhận về JSON có cấu trúc. Không xử lý logic nghiệp vụ phức tạp. Không phân biệt mặt trước/sau, CCCD cũ/mới. Chỉ hỏi AI "đây là loại giấy tờ gì, đọc ra dữ liệu gì" rồi trả về.

Dùng khi: văn phòng có API key và muốn độ chính xác cao hơn OCR local, hoặc khi ảnh chất lượng kém mà local OCR thất bại.

---

## Quyết định thiết kế quan trọng

- **QR-first trước khi gọi AI**: Thử decode QR bằng zxingcpp + OpenCV trước. Nếu QR thành công → dùng luôn, không tốn tiền gọi API. Đây là fast path tiết kiệm chi phí.
- **Không làm heuristic front/back trong Cloud OCR**: Tất cả logic phân loại mặt trước/sau, CCCD cũ/mới đã được chuyển sang Local OCR pipeline. Cloud OCR cố tình giữ đơn giản.
- **Multi-model support**: Hỗ trợ OpenAI và Gemini qua cùng một interface. Phân biệt bằng `"gemini" in model.lower()`. Model cấu hình qua env `OCR_MODEL`.
- **Gemini model alias**: `gemini-2.0-flash` tự động redirect sang `gemini-2.5-flash` (model cũ deprecated).
- **Concurrency = 4**: Gửi tối đa 4 ảnh lên AI cùng lúc (`AI_CONCURRENCY = 4`). Dùng asyncio Semaphore.
- **Resize ảnh trước khi gửi AI**: Max 1000px cạnh dài, JPEG quality 82, + UnsharpMask nhẹ. Mục đích: giảm token/cost, tăng tốc, đủ dùng cho text recognition.
- **QR decode nhiều variant**: Thử raw PIL, upscale 2x, CLAHE+sharpen+adaptive threshold. Lý do: QR trên CCCD hay bị mờ khi chụp.

---

## Flow chính

```
[Upload ảnh] 
    → Thử QR decode (zxingcpp + cv2 QRCodeDetector)
        ✓ QR decode OK → parse_cccd_qr() → trả về person với source_type="QR"
        ✗ QR fail → resize ảnh → gửi AI vision API
    → AI trả về JSON array [{"doc_type": ..., "data": {...}}]
    → Normalize data (clean text, normalize date DD/MM/YYYY, strip non-digit từ ID)
    → Phân loại vào persons / properties / marriages
    → Trả về response tổng hợp
```

---

## Response schema

```json
{
  "persons": [...],
  "properties": [...],
  "marriages": [...],
  "raw_results": [...],
  "errors": [...],
  "summary": {
    "total_images": 3,
    "qr_hits": 1,
    "ai_runs": 2,
    "model": "gpt-4o-mini",
    "persons": 2,
    "properties": 0,
    "marriages": 0,
    "unknowns": 0
  }
}
```

`source_type` trong mỗi person/result: `"QR"` hoặc `"AI"`.

---

## Doc types hỗ trợ

| doc_type | Loại giấy tờ | Schema data |
|---|---|---|
| `person` | CCCD / CMND | ho_ten, so_giay_to, ngay_sinh, gioi_tinh, dia_chi, ngay_cap, ngay_het_han |
| `marriage_cert` | Giấy đăng ký kết hôn | chong_*, vo_*, ngay_dang_ky, noi_dang_ky |
| `land_cert` | Sổ đỏ / Sổ hồng | so_serial, so_thua_dat, so_to_ban_do, dia_chi_dat, loai_dat, ngay_cap, co_quan_cap |
| `unknown` | Không nhận dạng được | {} |

---

## System prompt cho AI

Prompt cố định trong `SYSTEM_PROMPT` constant — chỉ yêu cầu AI extract JSON array, không classify front/back. Rules trong prompt:
- Không phân loại mặt CCCD.
- Không infer field không nhìn thấy trong ảnh.
- Date format: DD/MM/YYYY.
- ID chỉ chứa digits.
- Nếu nhiều giấy tờ trong 1 ảnh → nhiều object.

**Không được tùy tiện thay đổi SYSTEM_PROMPT** mà không test regression.

---

## Parse QR CCCD (`parse_cccd_qr`)

Hàm phức tạp nhất trong file, dùng nhiều heuristic:
- Split bằng `|`, `\r\n`, `;`.
- Detect 12 số liên tiếp → đó là số CCCD.
- Detect tên: 2-6 từ, không có số, không là từ khóa hành chính.
- Detect ngày: nhiều format (DD/MM/YYYY, DDMMYYYY, YYYYMMDD, 16 số = 2 ngày liền).
- Detect địa chỉ: ≥10 ký tự, có dấu phẩy hoặc từ khóa địa danh.
- Heuristic năm để phân biệt ngày sinh / ngày cấp / ngày hết hạn.

---

## Những thứ đã thử và thất bại / Không làm

- **Không dùng bilateral filter** trong preprocess (thêm latency, không cải thiện QR decode).
- **Không phân loại front/back trong Cloud OCR** — đã thử, phức tạp hóa không cần thiết. Local OCR làm điều này tốt hơn.
- **Không retry khi AI lỗi** — lỗi được wrap thành Exception và trả về trong `errors[]`. Retry logic để ở tầng frontend nếu cần.

---

## Env variables

| Var | Default | Ý nghĩa |
|---|---|---|
| `OCR_MODEL` | `gpt-4o-mini` | Model AI sử dụng |
| `OPENAI_API_KEY` | - | API key OpenAI |
| `GEMINI_API_KEY` | - | API key Google Gemini |
