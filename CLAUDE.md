# CLAUDE.md - notary_v2

Tai lieu van hanh nhanh cho team khi lam viec voi du an `notary_v2`.
Cap nhat: 13/04/2026.

## Nguyen tac van hanh mac dinh
- Mac dinh phat trien va test tren local.
- OCR toc do cao mac dinh `no fallback`:
  - Khong them fallback theo thoi quen.
  - Chi them fallback khi co benchmark moi chung minh recall tang dang ke va latency van chap nhan duoc.
  - Cloud AI hien tai: `server QR raw_only -> false => AI ngay`.
  - Local OCR la pipeline nghien cuu rieng; neu can fallback/triage/rotate thi ly do phai nam trong local, khong keo sang AI.
- Muc tieu OCR la **dung nghiep vu truoc**, khong phai chi dep output:
  - Khi thay output sai, phai ghi ro case sai va stage sai.
  - Neu gap cho mo ho nghiep vu, khong duoc tu quyet rule.
  - Phai hoi lai user de chot huong truoc khi sua logic nghiep vu.
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
  - Flow trong `routers/ocr_ai.py`: QR server `raw_only` va Qwen native OCR chay song song theo tung anh -> QR hit thi uu tien QR -> QR miss thi backend parse text/MRZ/suy side -> pair deterministic theo ID 12 so.
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
  - QR hit thi uu tien QR cho anh do; AI ket qua anh do bi discard.
  - Qwen native OCR chi doc text (`text_recognition`); backend parse field/suy side/pair.
  - Frontend AI path khong duoc scan QR client-side truoc khi goi server.
- OCR Local:
  - Uu tien nghien cuu/chinh xac/pairing.
  - Duoc giu triage, rotate, crop, QR rescue, deterministic merge.
- Khong import helper QR/parser giua AI va Local. Neu can giong nhau thi duplicate co chu dich de giu kha nang debug doc lap.

## Vong lap kiem thu OCR bat buoc
- Skill `test-ocr` trong `.claude/skills/test-ocr/SKILL.md` la wrapper auto-trigger cho muc nay.
- Muc nay chi kich hoat khi user dang yeu cau thuc thi `test OCR`, `debug OCR`, `kiem thu OCR`, `doi chieu OCR`, `OCR sai`, hoac sua OCR tren case/batch anh cu the.
- Khong kich hoat muc nay cho cau hoi giai thich, review kien truc, brainstorming, hay phan tich ly thuyet khong chay test that.
- Dieu kien bat dau:
  - Claude phai chot ro `batch anh` dang debug.
  - Claude phai chot ro `expected`/ket qua ky vong cho tung anh, tung cap, hoac tung JSON cuoi cung.
  - Neu thieu `batch anh` hoac `expected`, Claude phai hoi lai va dung tai do; chua duoc goi Codex, chua duoc chay UI/project.
- Thu tu bat buoc:
  1. Lay `direct output` truc tiep o tang ham/router tren chinh bo anh dang debug.
  2. Neu `direct output` chua khop `expected`, phai fix/tinh lai o tang ham/router truoc; chua duoc nhay sang UI/project.
  3. Chi khi da co `direct output` du can cu moi chay `project/UI test` tren cung batch anh.
  4. Lap bao cao doi chieu theo thu tu `expected -> direct output -> project/UI output`.
  5. Khoanh ro tang nghi ngo sai: QR, preprocess, AI/local OCR, normalize, pairing, router adapter, hay UI mapping.
  6. Neu sai lien quan nghiep vu hoac rule mapping, phai ghi ro case sai va hoi lai user neu chua du can cu.
  7. Moi vong chi duoc fix 1 tang nghi ngo da co bang chung; khong sua dong thoi nhieu tang lam mat kha nang truy nguyen nguyen nhan.
  8. Sau moi lan fix, bat buoc lay lai `direct output`, chay lai `project/UI test`, va cap nhat bao cao doi chieu.
  9. Chi duoc ket thuc thanh cong khi `direct output` khop `expected` va `project/UI output` khop `direct output`.
  10. Cuoi cung moi chay regression rong hon.
- Format bao cao bat buoc cho moi vong:
  - `batch anh`:
  - `expected`:
  - `direct output`:
  - `project/UI output`:
  - `tang nghi ngo sai`:
  - `hanh dong ke tiep`:
  - `trang thai`: `match` | `mismatch` | `blocked`
- Phai bao `blocked` thay vi loop vo han neu:
  - Khong lay duoc `direct output`.
  - Khong chay duoc `project/UI test`.
  - Du lieu dau vao flake/khong on dinh giua cac lan chay.
  - `expected` mo ho, mau thuan, hoac user chua chot.
  - Gap rule nghiep vu mo ho can user xac nhan.
- Neu bo anh dang debug la anh local cua phien hien tai, uu tien dung bo anh do truoc bo regression cu.
- Muc tieu dung la ket qua JSON/cu phap nghiep vu cuoi cung, khong chi la text OCR tho.

## Chay du an
```bash
# Windows
run.bat

# Hoac chay tay
python -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO
python -m uvicorn main:app --port 8000
```

URL mac dinh: `http://127.0.0.1:8000`

## Local OCR - RapidOCR Only

- Engine: `RapidOCR det + VietOCR rec (CPU)`, model `vgg_transformer`.
- Pipeline: Smart Crop → Triage V2 (4 huong) → Targeted Extraction → Deterministic Merge → Wide Fallback.
- Chi tiet buoc xu ly, env vars, ROI presets, luat du lieu: `docs/plans/ocr_local.md`.

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
- Worker startup: `python -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO`

## Script setup/run
- `run.bat`: tao venv, tao `.env`, cai dependency, khoi dong worker/server.
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
- **Word Template tuy bien sau** (deferred — 17/04/2026):
  - Hien tai dung simple `[placeholder]` replace. Tam chap nhan vi luong van ban lon, code logic nghiep vu cho tung doan rat mat thoi gian.
  - Y tuong: Them dynamic block markers `{%DS_HANG_THUA_KE%}`, `{%DOAN_VO_CHONG%}`... de backend tu generate/xoa doan van tuy dieu kien case (so nguoi, co/khong vo chong, co/khong nguoi tu choi, khai_nhan vs thoa_thuan).
  - User cuoi chi sua text/format trong Word, logic dieu kien do developer quan ly trong code.
  - Module moi: `services/word_engine.py` — chua engine xu ly block markers, chay truoc `_replace_in_doc()`.
  - Backward compatible: template cu khong co markers van chay binh thuong.
  - Plan chi tiet: xem commit hoac file `docs/plans/word_template_v2.md` khi bat dau trien khai.

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

## Kiem tra nhanh truoc khi ban giao
```bash
python -m py_compile routers/ocr_local.py tasks.py
rg -n "rapidocr|onnxruntime|opencv-python|LOCAL_OCR_TRIAGE" .env.example CLAUDE.md run.bat
```

## Quy trinh Claudex — Lam viec voi Codex

Claudex la quy trinh chuan khi giao task lon: Claude va Codex debate plan, user duyet, Codex implement.

### Cach su dung
Goi trong Claude Code:
```
/claudex "module/feature: mo ta task"
```

Vi du:
```
/claudex "cases/OCR AI: fix pairing bug khi batch lon hon 4 anh"
/claudex "cases/Word: them field nguoi chung kien vao template"
```

### Cau truc ben duoi (tools/codex_relay.py)
- `draft`: Planner → Critic → PlannerFinalizer chay tuan tu, luu artifact vao `runtime/codex_relay/<timestamp>/`
- `approve`: Danh dau run da duoc user duyet
- `execute`: Executor implement + Reviewer kiem tra sau
- `status`: Xem trang thai bat ky run

Chay thu cong (neu khong dung slash command):
```powershell
# Tao plan tu file task
python tools/codex_relay.py draft --task runtime/codex_relay_task_tmp.md

# Duyet plan (sau khi doc final_plan.md)
python tools/codex_relay.py approve --run-dir "runtime\codex_relay\<ten-thu-muc>"

# Implement
python tools/codex_relay.py execute --run-dir "runtime\codex_relay\<ten-thu-muc>" --with-review
```

### State machine cua moi run
```
awaiting_approval → approved → completed
                            ↘ (loi) giu nguyen approved, chay lai execute
```
Khong co state failed — khi loi giu nguyen state cu, chay lai tu buoc bi hong.

### Luu y van hanh
- Runtime data tai `runtime/codex_relay/` — da gitignore, khong commit.
- Codex CLI phai da login: kiem tra bang `cmd /c codex.cmd --version`
- Tuyet doi khong implement truoc khi co lenh `approve` — day la invariant cung cua workflow.
- Sau moi task, slash command tu dong cap nhat CLAUDE.md section "Lich su chuc nang".

### Relay OCR giua Claude va Codex
- Khi task la `test OCR`/`debug OCR`/`kiem thu OCR`, Claude la ben tu chay vong doi chieu. Claude khong duoc goi Codex de "doan bug" truoc khi da doi chieu xong theo muc `Vong lap kiem thu OCR bat buoc`.
- Claude chi duoc relay sang Codex khi da co du:
  - `batch anh`
  - `expected`
  - `direct output`
  - `project/UI output`
  - `tang nghi ngo sai`
  - `muc tieu fix cua vong hien tai`
- Neu thieu bat ky muc nao o tren, Claude phai tiep tuc tu chay test, hoi user, hoac bao `blocked`; khong duoc mo Claudex run.
- Khi relay OCR sang Codex, request/to-do bat buoc phai ghi toi thieu:
```text
Lam gi: <fix OCR o tang dang nghi ngo cho vong hien tai>
Sua phan nao: <tang nghi ngo sai>
Pham vi: <chi tang dang nghi ngo cua vong hien tai>
Muc tieu: <direct output khop expected, project/UI output khop direct output>
Batch anh: <liet ke bo anh dang debug>
Expected: <ket qua ky vong da chot>
Direct output: <ket qua lay truc tiep o tang ham/router>
Project/UI output: <ket qua khi chay project/UI>
Tang nghi ngo sai: <mot tang cu the>
Muc tieu fix vong nay: <ly do goi Codex trong vong nay>
```
- Codex chi sua dung tang da duoc Claude khoanh bang bang chung doi chieu; khong tu mo rong sang tang khac neu chua co bang chung moi.
- Sau khi Codex implement xong, Claude phai tu chay lai vong doi chieu va cap nhat bao cao `match/mismatch/blocked`; khong duoc xem task da xong chi vi "da sua code".

## Lich su chuc nang

<!-- claudex-history-start -->
### cases > OCR tai san
**[Mo ta]:** Nang cap OCR so do/so hong: doc serial dang `BM 1451111`/`AA 12467547` du dung mot minh khong co label, merge front/back khong con phu thuoc thu tu upload, bo sung field `chu_su_dung` trong response. Da fix 4 bug reviewer phat hien (run 2).
**[Tech]:**
- Endpoint: `POST /api/ocr/analyze-property`, `POST /api/ocr/analyze-property-pair` -> `routers/ocr_ai.py`
- Tests: `tests/test_ocr_ai.py` (32/32 OK sau run 2), +5 regression test moi cho bug #2-#4
- Quyet dinh: parse tung anh doc lap, merge theo field; `chu_su_dung` additive trong response OCR, khong persist DB; footer date rescue tat trong pair flow (flag noi bo)
- Regex moi: `[A-Z]{2}\s*\d{6,8}` standalone cho `so_serial`; stop condition `"nam "` da duoc thu hep, giu duoc `"tinh Nam Dinh"`; merge `ngay_cap` uu tien date day du + hop le + moi hon
- **Bug con lai (reviewer run 2 flag, can fix):**
  - `High`: `per_side.*.text_lines` bi them vao `/analyze-property-pair` response -> contract violation + ro ri raw OCR PII
  - `High`: `summary.footer_date_rescue` bi them vao `/analyze-property` response -> contract violation ngoai scope
  - `Medium`: `chu_su_dung` bi push vao merged payload va classifier bi noi rong ("co 2 strong fields") -> scope violation, khong co negative test
- Run dir (fix 4 bug): `runtime/codex_relay/20260422-135359-fix-4-bug-ma-reviewer-phat-hien-o-run-oc/`
- Cap nhat: 22/04/2026
### cases > OCR test skill
**[Mo ta]:** Them skill `test-ocr` de ép Claude chay dung vong lap kiem thu OCR bat buoc moi khi gap tu khoa "test OCR", "debug OCR", "OCR sai". Skill chi la trigger/wrapper, source of truth la muc `Vong lap kiem thu OCR bat buoc` trong CLAUDE.md.
**[Tech]:**
- File tao moi: `.claude/skills/test-ocr/SKILL.md` (trigger + dan chieu CLAUDE.md)
- File cap nhat: `CLAUDE.md` (them rule intent, dieu kien bat dau, decision gate truoc khi goi Codex, guardrail `blocked state`, format bao cao doi chieu), `.claude/commands/claudex.md` (them gate: OCR task phai co du `batch anh`, `expected`, `direct output`, `project/UI output`, `tang nghi ngo sai` truoc khi draft relay sang Codex)
- Quyet dinh: `SKILL.md` = trigger, `CLAUDE.md` = source of truth, `claudex.md` = relay gate; khong lam lui logic OCR engine
- Bug con lai: chua co smoke test runtime positive/negative trigger; `claudex.md` co bat nhat menu `[d]` can sua; scope hoi bi keo rong sang `Phase 4 KNOWLEDGE CAPTURE` can tach rieng neu can
- Cap nhat: 22/04/2026
### cases > diagram data flow
**[Mô tả]:** Fix luồng dữ liệu OCR → staging → pool → diagram: dữ liệu không còn bị mất khi user bấm nút xóa, xóa cascade, kéo thả thất bại, hoặc lưu hồ sơ bị lỗi server. Pool luôn biết ai đang ở đâu.
**[Tech]:**
- File: `frontend/templates/cases/form.html`, `frontend/static/ReactFlowApp.jsx`
- Kiến trúc mới: `window.__CUSTOMER_REGISTRY__` (canonical data) + `window.__CUSTOMER_WORKFLOW__` (state flags: inStaging/inPool/inTree/inDiagram/deleted) thay thế cho DOM-as-source-of-truth
- Adapter hai chiều: `normalizeCustomerRecord`, `mergeCustomerRecord`, `toReactPersonShape`, `toPoolRowShape` — tất cả entry points (OCR, import, search, inline-create) đều upsert qua registry
- React bridge: `removeWithWorkflow` phát event trả người về pool khi xóa node, `validateAssignment` là rule duy nhất cho cả preflight và commit
- localStorage staging lưu `{id, snapshot}` thay vì chỉ ID — restore được khi server không có data
- `localStorage.removeItem(stagingKey)` đã bỏ khỏi native submit path
- Bug còn lại (reviewer flag): import Excel chưa auto-refresh pool ngay (chỉ hiện nút Làm mới), `commitAssign()` có thể có half-state nhỏ nếu setLogicalNodes updater race
- Cập nhật: 23/04/2026
<!-- claudex-history-end -->
