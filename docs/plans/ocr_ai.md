# Plan: OCR AI (Cloud)

**Trang thai:** active  
**Cap nhat:** 2026-04-13  
**Files lien quan:** `routers/ocr_ai.py`, `frontend/templates/cases/form.html`  
**API endpoint:** `POST /api/ocr/analyze`, `GET /api/ocr/config`

---

## Muc tieu

OCR AI la pipeline cloud uu tien latency de deploy nhanh. Day khong phai pipeline nghien cuu front/back nhu local.

Batch input co the gom:
- nhieu anh cung luc
- thu tu lon xon
- nhieu CCCD khac nhau
- anh khong phai CCCD

Ket qua tra ve phai dung contract JSON hien tai, nhung AI path khong duoc keo theo triage/fallback cua local.

---

## Nguyen tac da chot

- AI va Local tach thanh 2 module doc lap:
  - `routers/ocr_ai.py`
  - `routers/ocr_local.py`
- Khong shared helper QR/parser giua AI va Local.
- Route AI giu nguyen de khong vo UI:
  - `POST /api/ocr/analyze`
  - `GET /api/ocr/config`
- Cloud AI mac dinh `no fallback`.
- QR trong AI chi scan 1 lan o server, `raw_only`, bang `zxingcpp`.
- Neu `QR=false` thi chuyen AI ngay.
- Khong dung `upscale`, `threshold`, `cv2 QRCodeDetector` trong AI path.
- Khong xoay anh de suy side trong AI path.
- Khong auto-ghep front/back o backend AI. Moi anh/person duoc tra rieng; pairing neu can de lop sau xu ly.
- Frontend AI path khong scan QR client-side truoc khi goi server.

---

## Flow hien tai

```text
[AI button]
  -> frontend gui toan bo files len /api/ocr/analyze
  -> routers/ocr_ai.py doc tung file
  -> try_decode_qr(raw image)
     -> QR hit: parse_cccd_qr() -> append person {source_type=QR, paired=false}
     -> QR miss: preprocess nhe -> queue Qwen/AI
  -> call_vision_images()
  -> normalize JSON
  -> append AI docs
  -> mark persons unpaired
  -> tra response
```

---

## Logging

`routers/ocr_ai.py` co logger rieng `ocr_ai`.

Log bat buoc:
- request-level:
  - `event=ocr_ai_done`
  - `model`
  - `total_images`
  - `qr_hits`
  - `ai_runs`
  - `total_ms`
  - `qr_ms`
  - `prepare_ms`
  - `qwen_ms`
  - `pair_ms`
- per AI call:
  - `event=qwen_call` khi model la Qwen
  - `filename`
  - `model`
  - `latency_ms`
  - `status=ok|error`

---

## QR policy

Decision record tu benchmark 2026-04-13:
- `raw_only` la mode mac dinh cho AI.
- `cv2` khong cuu them hit tren bo test da do.
- `upscale/threshold` co tradeoff latency khong tot cho fast deploy.

Rule:
- Khong them fallback chi vi "co the tot hon".
- Chi them fallback moi neu co benchmark moi cho thay:
  - recall tang dang ke
  - va latency van chap nhan duoc o batch thuc te

---

## Frontend policy cho AI button

Trong `frontend/templates/cases/form.html`:
- AI button chi goi server route.
- Khong dung `tryQRScan()` / `parseQRToPerson()` cho AI path.
- UI phai ton trong `source_type` backend:
  - `QR`
  - `AI`
- Khong dua vao heuristic `_source=cccd+back` de suy ket qua AI.

Client QR worker (`frontend/static/ocr_qr_worker.js`) hien tai thuoc local/telemetry path, khong phai source of truth cho AI path.

---

## Response notes

Response shape giu nguyen:
- `persons`
- `properties`
- `marriages`
- `raw_results`
- `errors`
- `summary`

Luu y:
- `paired_persons` tren AI path hien tai mac dinh `0`.
- Moi person tu AI path duoc tra rieng theo file; khong merge front/back o backend.

---

## Khi debug

Bug AI OCR mo theo thu tu:
1. `docs/plans/ocr_ai.md`
2. `routers/ocr_ai.py`
3. `.env`
4. `frontend/templates/cases/form.html`

Khong debug AI bang cach doc `ocr_local.py` tru khi dang dieu tra mot side effect ro rang.
