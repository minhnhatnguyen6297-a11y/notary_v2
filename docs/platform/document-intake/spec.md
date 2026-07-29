# Cloud AI OCR — Platform specification

Status: active
Owner: platform/document-intake
Source of truth: Cloud AI OCR flow, endpoints, response contracts, and QR exclusion
**Cap nhat:** 2026-07-10
**Files lien quan:** `routers/ocr_ai.py`, `frontend/templates/cases/form.html`
**API endpoint:** `POST /api/ocr/analyze`, `GET /api/ocr/config`

---

## Muc tieu

OCR AI la pipeline cloud active cho person CCCD OCR.

Huong hien tai da chot:
- OCR AI khong con dung QR path.
- 100% request OCR duoc gui qua API cua Qwen.
- Muc tieu la lay raw OCR tu Qwen, sau do backend parse/shape ve JSON contract hien tai.
- QR neu can lam tiep se duoc phat trien thanh huong/chuc nang rieng; hien chua chot architecture va khong duoc ngam quay lai OCR AI path.
- Chuc nang OCR se tiep tuc phat trien rieng trong module AI path, khong troi sang local/research path.

Batch input co the gom:
- nhieu anh cung luc
- thu tu lon xon
- nhieu CCCD khac nhau
- anh khong phai CCCD

Ket qua tra ve phai dung contract JSON hien tai.

---

## Nguyen tac da chot

- Route AI giu nguyen de khong vo UI:
  - `POST /api/ocr/analyze`
  - `GET /api/ocr/config`
- AI path khong dung QR server, khong client QR, khong QR rescue, khong QR-first routing.
- AI path goi Qwen OCR cho moi anh, sau do backend parse text, suy side, pair front/back, va shape response.
- Khong keo triage/fallback/heuristic nghien cuu tu local OCR vao day neu chua co scope ro.
- Muc tieu uu tien la dung nghiep vu cuoi cung, khong chi dep raw text.
- Neu gap ca sai ma khong ro rule nghiep vu, phai log ro case sai va hoi lai user truoc khi quyet dinh logic.

---

## Flow hien tai / huong target

```text
[AI button]
  -> frontend gui toan bo files len /api/ocr/analyze
  -> routers/ocr_ai.py doc tung file
  -> goi Qwen OCR theo tung anh
  -> backend nhan raw text / raw OCR payload
  -> backend parse text lines
  -> backend detect side
  -> backend pair front/back theo quy tac da chot
  -> backend normalize field text neu co rule an toan
  -> tra response JSON
```

---

## Logging

`routers/ocr_ai.py` co logger rieng `ocr_ai`.

Log bat buoc:
- request-level:
  - `event=ocr_ai_done`
  - `model`
  - `images`
  - `total_ms`
  - `ocr_native_ms`
  - `backend_parse_ms`
  - `pair_ms`
  - `normalize_ms` (neu co layer normalize rieng)
- per AI call:
  - `event=qwen_call`
  - `filename`
  - `model`
  - `latency_ms`
  - `status=ok|error`

Neu co layer normalize text/field, log them:
- `event=ocr_normalize`
- `filename`
- `field`
- `before`
- `after`
- `rule_source=prompt|backend_rule|dictionary`

Khong log PII raw o muc qua rong trong production log; chi log mau/co che redact khi can.

---

## Frontend policy cho AI button

Trong `frontend/templates/cases/form.html`:
- AI button chi goi server route.
- Frontend khong duoc tu scan QR truoc khi goi server cho AI path.
- UI khong duoc gia dinh source `QR`; source cua AI path la OCR/Qwen.
- Preview `Xem anh` phai tiep tuc giu dung anh nguon tren tung person card.

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
- `paired_persons` duoc tinh sau khi backend pair front/back.
- `summary` co telemetry cho native OCR path: `ocr_native_ms`, `backend_parse_ms`, `pair_ms`.
- Neu them normalize layer, `summary` co the them `normalize_ms` va `normalized_fields`.

---

## Vietnamese normalization direction

OCR AI can xu ly 2 bai toan khac nhau:
1. **OCR raw extraction**: doc text tu anh
2. **Normalization / correction**: chuan hoa text tieng Viet thuong gap

Vi du mong muon:
- `nguyen thi A` -> rat co kha nang `Nguyễn Thị A`
- `y yen, nam dinh` -> co the chuan hoa thanh `Ý Yên, Nam Định`

### Nguyen tac cho normalize

- Khong duoc silently invent business data khi do tin cay thap.
- Phan normalize phai tach ro khoi phan OCR raw.
- Rule nao la **100% deterministic** moi duoc auto-apply khong can canh bao.
- Rule nao chi la **very likely / probabilistic** thi nen:
  - luu raw value
  - luu normalized value
  - danh dau confidence / warning
  - hoac cho user review

### Design options (non-normative)

This section records exploration, not the current runtime contract. The explicit current direction remains guidance until implemented and tested.

#### Huong A - Prompt-based normalization trong Qwen call

Y tuong:
- Gui kem 1 file markdown/rulebook trong system prompt moi lan call AI.
- AI vua OCR vua co gang chuan hoa text theo cac rule thuong gap.

Uu diem:
- Don gian de thu nghiem nhanh.
- Co the sua rule ma khong can viet nhieu code parse backend.
- Co the xu ly nhieu pattern ngon ngu linh hoat hon dictionary cung.

Nhuoc diem:
- Kho kiem soat tinh xac dinh.
- Cung mot input co the normalize khac nhau giua cac lan/model version.
- Kho audit: khong ro AI sua theo rule nao neu prompt qua rong.
- Tang token/prompt size moi request.
- De lam mo ranh gioi giua OCR raw va field correction.

#### Huong B - Backend normalization sau khi AI tra raw text

Y tuong:
- Qwen chi OCR raw text.
- Backend parse xong moi chay mot layer normalize rieng.
- Layer nay co the la script/ruleset/dictionary/lookup.

Uu diem:
- Deterministic hon, de test hon, de audit hon.
- Co the tach `raw_value` va `normalized_value` ro rang.
- De viet regression test cho tung field.
- De gioi han auto-fix chi o cac rule an toan.

Nhuoc diem:
- Can them code va bo rule rieng.
- Nhung pattern mo ho/linh hoat se kho cover hon prompt AI.

### Huong de xuat hien tai

De xuat uu tien:
1. **Qwen chi OCR raw**
2. **Backend normalize sau**
3. Chia normalize thanh 2 lop:
   - **Deterministic rules**: auto-apply
   - **Probabilistic suggestions**: warning/review, khong silent overwrite

Vi du:
- Dia danh hanh chinh co dictionary chot ro (`Y Yen, Nam Dinh` -> `Ý Yên, Nam Định`) => co the dua vao deterministic mapping neu nguon mapping da duoc chot.
- Ho ten nguoi (`nguyen thi a`) => khong nen auto-khang-dinh 100% ngay chi bang heuristic dau cau; nen can nhac giu raw + normalized suggestion tru khi da co rule/lexicon du tin cay.

### Cau truc toi thieu de sau nay them normalize

Neu lam backend normalize, nen co 1 layer rieng, vi du:
- `services/ocr_ai_normalize.py`
- hoac `services/ocr_normalization/`

Output field co the can nhac:

```json
{
  "ho_ten_raw": "nguyen thi a",
  "ho_ten": "Nguyễn Thị A",
  "ho_ten_normalize_confidence": "suggested"
}
```

Hoac neu chua muon doi contract:
- giu `ho_ten`
- them warning/metadata noi bo trong `raw_results` / `summary`
- de UI quyet dinh co hien badge can review hay khong

---

## Decision notes 2026-07-10

- OCR AI duoc dinh huong lai thanh Qwen-only OCR path.
- Cac thong tin/chien luoc lien quan QR da khong con la huong target cua plan nay.
- Local OCR khong phai noi de tham chieu trong plan nay, tru khi can so sanh/ranh gioi pham vi o muc rat ngan.
- Bai toan normalize tieng Viet da duoc mo ra, nhung chua chot architecture cuoi cung.
- De xuat hien tai la: OCR raw bang Qwen, normalize hau xu ly o backend bang layer rieng de de test/audit.

---

## Khi debug

Route concrete OCR failures through the normal debugging and test workflow, without entering the parked local/research path unless explicitly scoped.
