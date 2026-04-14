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
- AI goi native OCR `text_recognition`, backend parse text + MRZ + side + pair theo ID 12 so.
- Frontend AI path khong scan QR client-side truoc khi goi server.
- Muc tieu uu tien la dung nghiep vu cuoi cung.
- Neu gap ca sai ma khong ro rule nghiep vu, phai log ro case sai va hoi lai user truoc khi quyet dinh logic.

---

## Flow hien tai

```text
[AI button]
  -> frontend gui toan bo files len /api/ocr/analyze
  -> routers/ocr_ai.py doc tung file
  -> chay song song theo tung anh:
     - QR server raw_only (zxingcpp)
     - Qwen native OCR task (text_recognition)
  -> neu QR hit: uu tien QR, bo ket qua AI cua anh do
  -> neu QR miss: backend parse text lines, parse MRZ, detect side
  -> backend pair deterministic front/back theo so giay to 12 so
  -> tra response
```

---

## Logging

`routers/ocr_ai.py` co logger rieng `ocr_ai`.

Log bat buoc:
- request-level:
  - `event=ocr_ai_done`
  - `model`
  - `images`
  - `qr_hits`
  - `ai_started`
  - `ai_selected`
  - `ai_discarded_by_qr`
  - `total_ms`
  - `ocr_native_ms`
  - `backend_parse_ms`
  - `pair_ms`
- per AI call:
  - `event=qwen_call`
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
- `paired_persons` duoc tinh sau khi backend pair theo ID 12 so.
- `summary` co them telemetry native path: `ocr_native_ms`, `backend_parse_ms`,
  `ai_started`, `ai_selected`, `ai_discarded_by_qr`.

---

## Khi debug

Bug AI OCR mo theo thu tu:
1. `docs/plans/ocr_ai.md`
2. `routers/ocr_ai.py`
3. `.env`
4. `frontend/templates/cases/form.html`

Khong debug AI bang cach doc `ocr_local.py` tru khi dang dieu tra mot side effect ro rang.

---

## Vong lap kiem thu khi fix AI OCR

Thu tu debug bat buoc:

1. Chot bo anh cua phien dang debug
- Uu tien dung bo anh vua gay sai trong phien lam viec hien tai.
- Ghi ro ky vong dung tren moi anh: QR hit/miss, loai giay to, JSON field can co.

2. Test truoc o tang router/ham
- Chay truc tiep tren `routers/ocr_ai.py` hoac script benchmark/phu tro de lay output that cua AI path.
- Chua chay UI o buoc nay.

3. Doi chieu voi ket qua ky vong
- So `expected` voi `router output`.
- Neu sai, khoanh stage sai:
  - QR raw_only
  - preprocess
  - Qwen/model output
  - normalize JSON
  - response shaping
 - Neu thay sai co the do rule nghiep vu, ghi ro ca sai va dung lai de hoi user neu chua du can cu.

4. Fix dung tang gay sai
- Khong nhay sang fix UI neu router output chua dung.
- Khong them fallback neu chua co benchmark moi chung minh can thiet.

5. Chay project/UI de doi chieu
- Sau khi router output da dung/gần dung, moi chay full project hoac UI.
- So `router output` voi `UI/project output` de bat loi mapping/merge o frontend.

6. Lap lai den khi dung
- Lap vong `doi chieu -> tim nguyen nhan sai -> fix` den khi bo anh cua phien hien tai cho ket qua dung.

7. Regression cuoi cung
- Sau khi fix xong bo anh cua phien hien tai, moi chay regression rong hon.
