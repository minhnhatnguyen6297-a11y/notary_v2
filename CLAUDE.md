# CLAUDE.md - notary_v2

Tai lieu van hanh nhanh cho team khi lam viec voi du an `notary_v2`.
Cap nhat: 13/04/2026.

## Skills — Doc truoc khi lam bat ky task nao

Truoc khi viet plan hoac soan Codex prompt, Claude PHAI:

1. Doc `.agent/skills_router.md`.
2. Xac dinh loai task (viet code / debug / review / tai lieu).
3. Doc cac skill file tuong ung trong bang dinh tuyen.
4. Ghi ro skills da chon vao section `## Skills can ap dung` trong Codex prompt.

Khong can user nhac lai. Day la buoc bat buoc, khong phai tuy chon.

## Nguyen tac van hanh mac dinh
- Mac dinh phat trien va test tren local.
- VPS la moi truong chay/deploy; chi thao tac tren VPS khi can cai dat, restart service, xem log hoac dong bo ban da chot.
- Truoc khi day len VPS, local phai ro trang thai git va commit/push day du.
- Tai lieu workflow VPS: `docs/VPS_WORKFLOW.md`.
- Sau khi sua/cai dat tren VPS, phai uu tien restart va kiem tra lai:
  - `bash install_vps.sh --skip-system-packages` neu co doi dependency
  - `bash deploy/vps/manage_services.sh restart`
  - `bash deploy/vps/manage_services.sh logs`
- Neu commit local va VPS bi lech nhau, phai xac minh ro ben nao la ban moi nhat truoc khi tiep tuc, khong duoc mac dinh local la nguon dung.
- OCR toc do cao mac dinh `no fallback`:
  - Khong them fallback theo thoi quen.
  - Chi them fallback khi co benchmark moi chung minh recall tang dang ke va latency van chap nhan duoc.
  - Cloud AI hien tai: `server QR raw_only -> false => AI ngay`.
  - Local OCR la pipeline nghien cuu rieng; neu can fallback/triage/rotate thi ly do phai nam trong local, khong keo sang AI.
## Tong quan
- Ung dung quan ly ho so thua ke dat dai cho van phong cong chung.
- Backend: FastAPI + SQLAlchemy + SQLite.
- Frontend: Jinja2 + Bootstrap + Vanilla JS.
- Local OCR: RapidOCR detection + VietOCR recognition (CPU-only).

## Cach doc repo nay
- Khong doc lai toan bo codebase tu dau moi khi debug.
- Bat dau tu `CLAUDE.md` de xac dinh dung entrypoint, sau do mo file plan trong `docs/plans/`, roi moi doc file code lien quan.
- Neu sua 1 flow lon ma thay `CLAUDE.md` khong con dung nua, phai cap nhat lai ngay. `CLAUDE.md` la ban do repo, khong chi la ghi chu chung chung.

## Ban do repo / ownership
- `main.py`
  - Tao FastAPI app.
  - Load `.env`.
  - Chay DB migrations nhe truoc `create_all`.
  - Mount static/templates.
  - Include routers.
  - Warmup Local OCR luc startup.
- `database.py`
  - Engine, `SessionLocal`, `Base`, va cac ham migrate schema.
- `models.py`
  - Core tables: `Customer`, `Property`, `InheritanceCase`, `OCRJob`, `ExtractedDocument`.
- `routers/`
  - `customers.py`: CRUD/import khach hang.
  - `properties.py`: CRUD tai san.
  - `cases.py`: man hinh trung tam cua nghiep vu ho so, gom form/detail/preview/template.
  - `participants.py`: API nguoi tham gia.
  - `ocr_ai.py`: Cloud OCR / AI OCR sync, tach rieng khoi local.
  - `ocr_local.py`: Local OCR core + async submit/status/save.
- `tasks.py`
  - Celery worker cho Local OCR async.
  - Khong tu viet OCR, chi doc file tam, goi `routers.ocr_local`, luu ket qua vao `OCRJob`.
- `frontend/templates/`
  - `cases/form.html` la UI lon nhat va la noi OCR duoc goi tu frontend.
  - `customers/*.html`, `properties/*.html`, `cases/*.html` di kem tung router cung ten.
- `frontend/static/`
  - `ocr_qr_worker.js`: QR worker phia client.
  - `ReactFlowApp.jsx`: UI ReactFlow nhung van duoc embed tu `cases/form.html`.
- `docs/plans/`
  - Noi giu decision record theo feature. Sua feature nao thi doc plan do truoc.

## Quan he goi nhau quan trong
- App startup
  - `main.py` -> load env -> migrate DB -> include routers -> warmup `routers.ocr_local.warmup_local_ocr()`.
- Cloud OCR sync
  - Frontend `frontend/templates/cases/form.html` -> `POST /api/ocr/analyze` -> `routers/ocr_ai.py:analyze_images()`.
  - Flow trong `routers/ocr_ai.py`: server QR `raw_only` 1 lan -> neu QR hop le thi tra QR result rieng -> neu khong co QR thi preprocess nhe -> goi Qwen/AI model -> normalize JSON -> khong auto-ghep front/back o backend.
- Local OCR async
  - Frontend `frontend/templates/cases/form.html` -> `POST /api/ocr/local/submit-batch`.
  - `routers/ocr_local.py` tao `OCRJob`, luu file tam, enqueue `tasks.process_ocr_batch_job`.
  - `tasks.py` doc `manifest.json` + bytes -> goi `local_ocr_batch_from_inputs()` -> luu `result_json` vao `OCRJob`.
  - Frontend poll `GET /api/ocr/local/status/{job_id}`.
  - Frontend co the goi `POST /api/ocr/local/confirm-save` de luu `ExtractedDocument`.
- OCR UI relation
  - `frontend/templates/cases/form.html` la diem noi giua OCR AI, OCR Local, QR worker, va mapping ket qua vao form.
  - `frontend/static/ocr_qr_worker.js` la telemetry/QR support phia client, khong phai source of truth cua OCR server.
  - `frontend/static/ReactFlowApp.jsx` la UI ReactFlow duoc nhung vao `cases/form.html`, khong phai mot app frontend tach rieng.
  - AI button va Local button phai duoc debug nhu 2 flow doc lap; khong duoc mac dinh chung helper neu khong co ly do rat ro.

## Khi debug, mo file nao truoc
- Bug Cloud OCR / AI OCR
  - Doc `docs/plans/ocr_ai.md` -> `routers/ocr_ai.py` -> `.env` -> `frontend/templates/cases/form.html`.
- Bug Local OCR / pairing / front-back / merge
  - Doc `docs/plans/ocr_local.md` -> `routers/ocr_local.py` -> `tasks.py` -> `models.py` (`OCRJob`).
- Bug OCR UI tren form ho so
  - `frontend/templates/cases/form.html` -> `frontend/static/ocr_qr_worker.js` -> `routers/ocr_ai.py` hoac `routers/ocr_local.py` tuy endpoint.
- Bug queue / pending job / worker
  - `tasks.py` -> `models.py` (`OCRJob`) -> `logs/worker.log`.
- Bug startup / route khong mount / env khong load
  - `main.py` -> `.env` -> `database.py`.
- Bug man hinh ho so, preview, template
  - `routers/cases.py` -> `frontend/templates/cases/*.html` -> `frontend/static/ReactFlowApp.jsx` neu lien quan flow graph.
- Bug khach hang
  - `routers/customers.py` -> `frontend/templates/customers/*.html`.
- Bug tai san
  - `routers/properties.py` -> `frontend/templates/properties/*.html`.

## Bai toan OCR tong the
- Day khong phai bai toan OCR thuan `1 anh -> 1 doan text`.
- Input thuong la nhieu anh cung luc, thu tu lon xon, co the chen mat truoc, mat sau, nhieu CCCD khac nhau, va ca anh khong phai CCCD.
- He thong phai giai dong thoi cac bai toan nho sau:
  - Nhan dien anh nao la CCCD, anh nao khong phai CCCD.
  - Nhan dien mat truoc / mat sau.
  - Ghep cap dung cac anh thuoc cung 1 CCCD.
  - Trich xuat du lieu va tra JSON dung contract.
- Nguyen tac thiet ke bat buoc:
  - Luon danh gia bai toan theo `batch end-to-end`, khong toi uu tung buoc rieng le neu tong thoi gian lai tang.
  - Uu tien pipeline giai nhieu bai toan trong cung mot luong xu ly neu do chinh xac van dat yeu cau.
  - Moi thay doi OCR phai kiem tra lai xem co dang giai quyet ket hop ca `phan loai + nhan dien side + ghep cap + trich xuat JSON` nhanh hon hay khong.
  - Khong coi accuracy OCR text don le la metric duy nhat; metric dung la do dung cua ket qua JSON cuoi cung tren ca batch anh lon xon.

## Boundary AI vs Local
- `routers/ocr_ai.py` va `routers/ocr_local.py` la 2 pipeline tach rieng.
- OCR AI:
  - Uu tien latency.
  - QR chi scan 1 lan tren server, `raw_only`.
  - QR hit thi tra ket qua rieng; khong xoay, khong triage, khong auto-pair front/back o backend.
  - Frontend AI path khong duoc scan QR client-side truoc khi goi server.
- OCR Local:
  - Uu tien nghien cuu/chinh xac/pairing.
  - Duoc giu triage, rotate, crop, QR rescue, deterministic merge.
- Khong import helper QR/parser giua AI va Local. Neu can giong nhau thi duplicate co chu dich de giu kha nang debug doc lap.

## Chay du an
```bash
# Windows
run.bat

# Hoac chay tay
python -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO
python -m uvicorn main:app --port 8000
```

URL mac dinh: `http://127.0.0.1:8000`

## VPS one-click
```bash
bash install_vps.sh
```

Sau khi cai dat:
- Quan ly service: `bash deploy/vps/manage_services.sh status|restart|logs`
- Tai lieu chi tiet: `docs/VPS_ONE_CLICK_SETUP.md`
- Workflow van hanh/mac dinh: `docs/VPS_WORKFLOW.md`
- Windows wrappers:
  - `launch_vps_app.bat`
  - `connect_vps.bat`
  - `view_vps_logs.bat`
- Log file tren VPS: `logs/web.log`, `logs/worker.log`

## Local OCR - RapidOCR Only

### Muc tieu
- On dinh tren may Windows local.
- Giam phu thuoc nang.
- Uu tien toc do va kha nang debug.

### Pipeline xu ly hien tai
1. Nhan anh tu client.
2. Tien xu ly nhe:
   - sharpen kernel `[[0,-1,0],[-1,5,-1],[0,-1,0]]`.
   - Khong dung bilateral filter.
3. Cat tai lieu:
   - Smart Crop OpenCV (Canny + contour) voi soft fallback ve full image.
   - Chuan hoa anh OCR voi `max_side_len=1200`.
4. Triage V2 (feature flag):
   - Tao proxy image, thu 4 huong `0/90/180/270`.
   - Detect nhanh Face + QR + MRZ-score.
   - Gan state: `front_old`, `front_new`, `back_new`, `back_old` (hoac `unknown`).
   - Xoay anh goc high-res theo huong da chon.
5. Targeted extraction:
   - RapidOCR chi dung cho text detection, khong dung recognition.
   - VietOCR `vgg_transformer` doc batch cac dong chu da cat tu bounding boxes.
   - ROI loc theo `triage_state` (`front_old`, `front_new`, `back_new`, `back_old`, `unknown`) thay vi crop cung.
   - Regex MRZ: `IDVNM\\d{10}(\\d{12})`.
6. Deterministic merge:
   - Ghep cap tuyet doi theo CCCD 12 so.
   - Anh khong co ID dua vao `unpaired` + warning.
   - Delta merge bo sung field thieu theo side/profile.
7. Wide fallback:
   - Neu triage `unknown`, he thong thu `id_front` -> `id_back` -> `detail` ROI rong.
   - Khong con legacy fallback va khong con score rollback.
8. Tra ket qua + warnings cho frontend de human-in-the-loop.
9. Co log timing/telemetry chi tiet theo stage.

### Engine / nhan dang
- `summary.local_engine`: `RapidOCR det + VietOCR rec (CPU)`
- `summary.rec_model_mode`: `vgg_transformer`
- Bien moi truong Local OCR chinh:
  - `LOCAL_OCR_DET_MAX_SIDE_LEN`
  - `LOCAL_OCR_VIETOCR_MODEL`
  - `LOCAL_OCR_VIETOCR_BATCH_SIZE`
  - `LOCAL_OCR_TORCH_THREADS`
  - `LOCAL_OCR_DENOISE`
  - `LOCAL_OCR_REC_PAD_RATIO`
  - `LOCAL_OCR_REC_MIN_HEIGHT`
  - `LOCAL_OCR_REC_MAX_SCALE`

### Luat du lieu quan trong
- Ten: uu tien QR > mat truoc > MRZ (MRZ chi fallback).
- Dia chi:
  - CCCD cu (truoc 01/07/2024): block `Noi thuong tru` o mat truoc.
  - CCCD moi (sau 01/07/2024): block `Noi cu tru` o mat sau.
- `ngay_het_han` khong dua vao du lieu participant nghiep vu.

## API Local OCR
- `POST /api/ocr/local/submit`
- `POST /api/ocr/local/submit-batch`
- `GET /api/ocr/local/status/{job_id}`

### Co `client_qr_failed`
- `client_qr_failed` la telemetry tu frontend; backend van co quyen QR rescue.
- Batch dung `client_qr_failed_json` (list bool theo thu tu file).

## Task worker
- Task name giu nguyen:
  - `process_ocr_job`
  - `process_ocr_batch_job`
- Worker startup chuan:
  - Local Windows qua `run.bat`: `python -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO`
  - VPS Linux/systemd: `python -m celery -A celery_app.celery_app worker --pool=prefork --concurrency=3 --loglevel=INFO`

## Script setup/run
- `run.bat`: script local duy nhat. Tu tao venv, tao `.env`, cai dependency app + PyTorch CPU + VietOCR/RapidOCR, khoi dong worker/server.
- `install_vps.sh`: script VPS duy nhat cho one-click install/start service.
- `requirements-gpu.txt`: optional cho may NVIDIA (onnxruntime-gpu).

## Bien moi truong lien quan Local OCR
- `LOCAL_OCR_SMART_CROP_MIN_CONF`
- `LOCAL_OCR_DET_MAX_SIDE_LEN`
- `LOCAL_OCR_VIETOCR_MODEL`
- `LOCAL_OCR_VIETOCR_BATCH_SIZE`
- `LOCAL_OCR_TORCH_THREADS`
- `LOCAL_OCR_DENOISE`
- `LOCAL_OCR_TIMING_LOG`
- `LOCAL_OCR_TIMING_SLOW_MS`
- `LOCAL_OCR_DEBUG_LOG`
- `LOCAL_OCR_DEBUG_MAX_BOX_LOG`
- `LOCAL_OCR_REC_PAD_RATIO`
- `LOCAL_OCR_REC_MIN_HEIGHT`
- `LOCAL_OCR_REC_MAX_SCALE`
- `LOCAL_OCR_TRIAGE_V2`
- `LOCAL_OCR_TRIAGE_PROXY_MAX_SIDE`
- `LOCAL_OCR_TRIAGE_MRZ_MIN_SCORE`
- `OCR_TEXT_LLM_MODEL`

## Backlog / Roadmap
- LLM Fallback (tu dong sua dau / bu truong) dang tam tat de toi uu toc do Local OCR.
- Da chuyen sang co che canh bao do tren UI de nguoi dung tu sua tay.
- Se phat trien lai LLM Fallback o giai doan sau.

## Quy uoc khi sua code
- Uu tien fix theo huong giu contract API hien tai.
- Khong doi ten task Celery.
- Khong thay doi schema DB neu khong bat buoc.
- Neu sua flow OCR, phai test lai bo anh regression 10 anh CCCD.

## Feature Plans — Doc truoc khi sua code

Moi chuc nang lon co file plan rieng trong `docs/plans/`. Agent phai mo va doc plan truoc khi lam viec voi chuc nang do.

| Lam viec voi... | Doc plan nay truoc |
|---|---|
| `routers/ocr_ai.py` (Cloud OCR, AI OCR) | `docs/plans/ocr_ai.md` |
| `routers/ocr_local.py`, `tasks.py` (Local OCR) | `docs/plans/ocr_local.md` |

Index day du: `docs/plans/_INDEX.md`

**Quy tac:** Sau khi chot quyet dinh thiet ke moi hoac thay doi approach → cap nhat file plan tuong ung.

## Quy trinh Claude–Codex collaboration

Claude goi Codex truc tiep qua MCP tools — khong can copy-paste giua 2 cua so chat.
Tai lieu day du: `docs/plans/agent_collab_protocol.md`

**Buoc tom tat:**
1. User giao task → Claude nghien cuu codebase, viet draft plan vao `docs/plans/{feature}.md`
2. Claude goi `mcp__codex__codex(sandbox="read-only")` → Codex review plan, tra ✅/⚠️/❌
3. Claude cap nhat plan → goi `mcp__codex__codex-reply` → lap den khi chot
4. Claude xuat plan → User approve
5. Claude goi `mcp__codex__codex(sandbox="workspace-write")` → Codex implement
6. Claude review implementation theo checklist trong CLAUDE.md

**Sandbox policy:**
- Review plan: `sandbox="read-only"`
- Implement code: `sandbox="workspace-write"`, `approval_policy="on-request"`

## Kiem tra nhanh truoc khi ban giao
```bash
python -m py_compile routers/ocr_local.py tasks.py
rg -n "rapidocr|onnxruntime|opencv-python|LOCAL_OCR_TRIAGE" .env.example CLAUDE.md run.bat
```

---

## Vai tro Claude — Giam sat kho tinh

Claude dong vai **code reviewer nghiem khac** — khong phai tho code. Moi code do Codex (hoac agent khac) viet deu phai qua Claude review truoc khi chap nhan.

### Quy trinh review bat buoc

1. **Loi logic**: luong xu ly, edge case, tinh toan thua ke theo Luat Thua ke Viet Nam
2. **Bao mat**: SQL injection, XSS, command injection, validate input, file upload MIME/size, khong lo thong tin nhay cam
3. **API contract**: khong thay doi endpoint/method/response — neu can thi versioning `/v2/`
4. **Schema DB**: khong doi ten bang/cot ma khong co migration script (upgrade + downgrade, khong drop)
5. **Ten Celery task**: khong doi ten task da ton tai, task moi dat theo `notary.<module>.<action>`
6. **Nghiep vu cong chung**: thu tu thua ke Dieu 651 BLDS 2015, thua ke the vi, di chuc hop le Dieu 630, phan khong the truat quyen 2/3

### Khi phat hien loi

Claude **khong sua truc tiep**. Thay vao do:
1. Liet ke tung loi: file, dong, mo ta van de va ly do
2. Goi y huong sua — Codex tu implement
3. Yeu cau Codex submit lai PR sau khi sua, review lai tu dau

**Khong merge khi con loi chua duoc xac nhan da fix.**

### Khi nhan yeu cau implement moi

Claude **khong viet code**. Soan prompt cho Codex theo cau truc:

```
## Nhiem vu
[Mo ta ro yeu cau — what, not how]

## File can sua
- `path/to/file.py` — ly do can sua

## Yeu cau ky thuat
- [Constraint: khong thay doi API contract, ...]

## Input / Output mong doi
[Vi du cu the neu co]

## KHONG duoc lam
- [Dieu cam]

## Kiem tra sau khi xong
- [Test case]

## Skills can ap dung
- [Ten skill] — [ly do ap dung]
(Xoa muc nay neu task khong can skill nao)
```

Claude chi viet code khi user **yeu cau ro rang** Claude tu lam (khong qua Codex).
