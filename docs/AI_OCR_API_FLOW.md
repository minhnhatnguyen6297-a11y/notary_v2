# AI OCR API Flow

Tai lieu nay mo ta flow hien tai cua `POST /api/ocr/analyze` sau refactor QR/MRZ-first.

## Muc tieu
- Giu nguyen request/response contract cua `/api/ocr/analyze`.
- Uu tien QR va MRZ truoc AI de tiet kiem token.
- Chi goi AI cho field con thieu, co fallback sang model lon hon khi can.

## Tong quan flow hien tai
1. Frontend van gui `files[]` len `/api/ocr/analyze`.
2. Backend doc tung anh va tao `row` noi bo cho moi file:
   - chuan hoa EXIF rotation
   - encode anh day du ra base64
   - scan QR server-side
   - thu extract MRZ local neu local OCR helper co san
   - detect face proxy de nhan dien ung vien mat truoc
3. Backend gan state deterministic ban dau:
   - `QR + khong MRZ -> front_old`
   - `QR + MRZ -> back_new`
   - `MRZ + khong QR -> back_old`
   - `khong QR + khong MRZ -> front_unknown`
4. Backend thu pair `front_unknown` voi back da co key:
   - uu tien match theo stem filename
   - fallback theo thu tu khi so luong con lai 1-1
   - `front_unknown + back_new -> front_new`
   - `front_unknown + back_old -> front_old`
5. Backend merge du lieu deterministic vao moi row theo precedence:
   - `so_giay_to`: QR > MRZ > AI
   - `ngay_sinh`: QR > MRZ > AI
   - `gioi_tinh`: QR > MRZ > AI
   - `ho_ten`: QR > AI > MRZ ASCII
   - `dia_chi`: QR > AI tu `front_old` hoac `back_new`
   - `ngay_cap`: QR > AI tu mat sau
   - `ngay_het_han`: QR > MRZ > AI
6. Backend lap AI plan cho tung row:
   - `front_old` co QR day du -> skip AI
   - `back_old` co MRZ va da co `front_old` QR -> skip AI
   - `back_new` co QR day du -> skip AI
   - `front_new` da duoc pair voi `back_new` QR -> skip AI
   - `back_new/back_old` co MRZ nhung chua du thong tin -> crop va hoi field thieu
   - `front_old/front_new` thieu key field -> crop va hoi field thieu
   - truong hop khong phan loai chac chan -> full-card fallback
7. AI requests duoc group theo `prompt + model + token budget`:
   - model primary: `AI_OCR_PRIMARY_MODEL` (fallback ve `OCR_MODEL` neu chua set)
   - model escalation: `AI_OCR_ESCALATION_MODEL`
   - OpenAI/Gemini requests van duoc chen `SOURCE_IMAGE_INDEX`
8. Sau pass 1, backend validate row:
   - `so_giay_to` phai du 12 so
   - `ngay_sinh`, `ngay_cap` phai la ngay hop le
   - `dia_chi` phai co o `front_old/back_new`
   - neu row chua complete thi lap escalation plan
9. Backend merge ket qua AI ve lai row:
   - update profile neu AI cho thay mat sau moi/co dia chi back
   - dong bo `pair_key` theo QR/MRZ truoc, chi dung AI key khi khong con key deterministic
10. Tu cac row da chot, backend tao `raw_results` va goi `group_documents()`:
   - ghép theo `pair_key` uu tien QR/MRZ
   - khong cho AI so giay to ghi de key deterministic
   - sinh `persons`, `properties`, `marriages`, `raw_results`, `summary`

## Telemetry noi bo
- `skip_ai`: so anh khong can AI
- `mrz_rows`: so anh co MRZ local
- `ai_crops`: tong so crop gui AI (primary + escalation)
- `escalated_rows`: so row phai retry model lon hon

## Bien moi truong lien quan
- `AI_OCR_PRIMARY_MODEL`
- `AI_OCR_ESCALATION_MODEL`
- `AI_OCR_ENABLE_TARGETED_FIELDS`
- `AI_OCR_ENABLE_MRZ_LOCAL`
- `AI_OCR_BATCH_SIZE`
- `AI_OCR_MAX_CONCURRENCY`
- `AI_OCR_TIMEOUT_SECONDS`
- `AI_OCR_RETRY_COUNT`
- `AI_OCR_RETRY_BASE_DELAY_MS`
- `AI_OCR_OPENAI_MAX_TOKENS_PER_IMAGE`
- `AI_OCR_TIMING_LOG`
- `AI_OCR_TIMING_SLOW_MS`

## Luu y nghiep vu quan trong
- CCCD cu truoc `01/07/2024`: QR o mat truoc.
- Can cuoc moi sau `01/07/2024`: QR o mat sau.
- Mat truoc the moi khong co dia chi; dia chi nam o mat sau.
- `ngay_het_han` van extract neu co, nhung chi la advisory field.
