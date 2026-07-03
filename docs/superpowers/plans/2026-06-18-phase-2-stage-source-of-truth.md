# Ke hoach trien khai Phase 2 - Stage la Source of Truth

> **Cho agent thuc thi:** BAT BUOC dung `superpowers:writing-plans` neu lap plan lai, va dung `superpowers:executing-plans` hoac `superpowers:subagent-driven-development` truoc khi implement. Theo doi tien do bang checklist.

**Muc tieu:** Dong bo flow Stage cua case voi `docs/case_user_flow_spec.md` Phase 2 de Stage tro thanh UI source of truth duy nhat cho du lieu nguoi trong ho so, nut `Cap nhat` tro thanh diem commit duy nhat cua Stage, va moi vung lien quan deu phai di theo trang thai Stage moi nhat da commit.

**Huong kien truc:** Xem Stage la danh sach chuan, co the sua truc tiep, cua nguoi trong ho so. OCR modal, pool, diagram va cac nguon them sau nay chi la tang nap du lieu hoac tang projection. Trong Phase 2 phai khoa ro 3 bien: `sua o Stage`, `commit bang Cap nhat`, va `xoa chi bang nut xoa o cuoi dong`.

**Goi y model de implement:** `gpt-5.5` voi reasoning `xhigh` cho cac task con lai cua Phase 2/3, vi flow nay cham nhieu state UI, persistence, pool va diagram.

**Trang thai 2026-06-18:** Da trien khai lan 1. Stage button da la `Cap nhat`, submit tong khong auto-commit draft Stage, committed Stage snapshot duoc persist vao `case_state_json` cho case da co id, OCR temp chi clear sau commit thanh cong, va diagram remove person khong con trong committed Stage. Van con `STAGE-3`, phan cascade nhanh phu thuoc sau hon cua `STAGE-5`, va cac rule partial `STAGE-R1/R2/R3/R4`.

---

## Pham vi

Plan nay chi trien khai hanh vi Phase 2 cua Stage va cac contract toi thieu xuyen tang can co de Stage dieu khien cac vung phia sau.

Trong pham vi:
- Stage la UI source of truth duy nhat cho cac dong nguoi trong case.
- Doi ten nut hanh dong cua Stage tu `Luu` thanh `Cap nhat`.
- Bien `Cap nhat` thanh diem commit ro rang cho moi sua doi trong Stage.
- Persist du lieu Stage tai thoi diem `Cap nhat`.
- Day trang thai Stage da commit sang cac vung lien quan sau khi `Cap nhat`.
- Chi xoa du lieu OCR tam va anh OCR nguon sau khi `Cap nhat` thanh cong.
- Cho phep sua truc tiep trong Stage truoc khi commit.
- Cho phep xoa dong truc tiep trong Stage ma khong canh bao.
- Dinh nghia ro du lieu nao la draft, du lieu nao la committed trong vong doi hien tai cua trang.
- Bo sung test bao ve cac invariant rieng cua Stage.

Ngoai pham vi cua phase nay:
- Thiet ke lai toan bo UX cua pool/diagram.
- Thay doi engine rule thua ke trong diagram.
- Flow OCR tai san.
- Thiet ke lai xuat Word.
- Refactor schema lon vuot qua contract persistence toi thieu ma Stage can.

## Cac van de mo cua phase nay phai luon duoc nhac lai

Truoc moi task implement Phase 2 trong tuong lai, agent phai nhac lai cac muc chua xong sau:

- `STAGE-1`: Nut cua Stage van dang la `Luu`, chua doi thanh `Cap nhat`.
- `STAGE-2`: Luong save hien tai dang persist update tung customer, chua ro persist source of truth cap case.
- `STAGE-3`: Stage chua phai UI source of truth duy nhat; pool van co state/workflow rieng.
- `STAGE-4`: Luong save/submit case hien tai van co the persist draft rows ben ngoai moc `Cap nhat`.
- `STAGE-5`: Xoa dong o Stage chua cascade sach sang pool/diagram theo spec.
- `STAGE-R1`: Contract persistence cho `Cap nhat` chua duoc chot day du.
- `STAGE-R2`: Chien luoc identity cho dong tam va truong hop duplicate CCCD chua duoc chot.
- `STAGE-R3`: Contract hien thi/lưu ngay thang chua duoc chot.
- `STAGE-R4`: Cach hydrate/migrate case cu chua duoc chot.

Neu sau mot task van con muc nao o tren chua giai quyet, task ke tiep bat buoc phai nhac lai truoc khi code.

## Tier

**Tier de xuat:** `MAJOR`

Ly do:
- Stage se tro thanh ranh gioi state canonical cho OCR, pool, diagram va persistence.
- Thay doi nay kha nang cao se cham ca frontend orchestration lan backend save/load.
- Sua nua vung se de tai dien cung mot lop bug duoi ten goi khac.

## File du kien lien quan

File chinh kha nang cao se dung:
- `docs/case_user_flow_spec.md`
- `frontend/templates/cases/form.html`
- `frontend/static/ReactFlowApp.jsx`
- `routers/cases.py`
- `frontend/templates/cases/edit.html` hoac template case lien quan neu action Stage bi tach ra
- `tests/cases_ui_dataflow_static.test.mjs`
- Cac test Python lien quan save/load case neu da co san

File co the can them neu contract persistence bat buoc:
- `models.py`
- `database.py`
- `docs/plans/cases_dataflow_v2.md`

## Cong viec bat buoc truoc khi implement

- [ ] Doc `AGENTS.md` section 1 va 2.
- [ ] Doc `docs/case_user_flow_spec.md` phan 7, 8, 13 `Phase 2: Stage`, va cac note phu thuoc sang Phase 3.
- [ ] Doc `docs/plans/cases_dataflow_v2.md` chi de tham khao nen, khong duoc thay the spec da duoc user chot.
- [ ] Nhac lai toan bo cac muc `STAGE-*` va `STAGE-R*` con mo truoc khi sua code.
- [ ] In scope lock truoc khi code.

## Mau scope lock cho luc implement

```text
TASK: Dong bo Phase 2 Stage voi spec single-source-of-truth
TIER: MAJOR
FILE SE DUNG:
- frontend/templates/cases/form.html
- frontend/static/ReactFlowApp.jsx
- routers/cases.py
- tests/cases_ui_dataflow_static.test.mjs
- docs/case_user_flow_spec.md
FILE KHONG DUNG:
- routers/ocr_ai.py
- routers/ocr_local.py
- tasks.py
- cac file word export
RUI RO:
- state Stage/pool/diagram hien dang giao thoa
- de vo tinh persist draft state o sai checkpoint
- de xoa nham OCR temp hoac du lieu Stage neu mo ho commit boundary
TEST:
- node --test tests/cases_ui_dataflow_static.test.mjs
- .\verify.bat
TRANG THAI SCOPE: LOCKED
```

Neu trong luc implement can cham schema hoac migration ngoai danh sach file da lock, agent phai dung lai va bao `SCOPE BREAK REQUEST`.

## Hanh vi dich can dat

### 1. Quyen so huu du lieu cua Stage

- Stage la danh sach canonical duy nhat, co the sua truc tiep, cua nguoi trong case tren UI.
- OCR modal co the tao du lieu tam, nhung sau khi handoff thi khong duoc tro thanh mot source of truth khac.
- Pool va diagram chi la projection cua Stage da commit cong voi state assignment, khong phai noi so huu su that cua person.

### 2. Phan tach draft va committed

- Moi sua doi truc tiep trong Stage la draft cho den khi user bam `Cap nhat`.
- Reload truoc khi `Cap nhat` co the lam mat cac thay doi chua commit.
- Sau khi `Cap nhat` thanh cong, snapshot Stage da commit la trang thai authoritative moi nhat cua case.

### 3. Xoa du lieu

- Chi nut xoa o cuoi dong Stage moi duoc phep xoa mot nguoi o Stage.
- Khong nut nao khac duoc phep am tham xoa du lieu Stage.
- Xoa o Stage khong can hop thoai canh bao.
- Sau `Cap nhat`, hanh vi xoa tro thanh authoritative doi voi cac vung phia sau.

### 4. Moc xoa OCR temp

- Du lieu OCR tam va preview anh nguon phai con ton tai cho den khi `Cap nhat` thanh cong.
- `Cap nhat` chi duoc xoa OCR temp sau khi commit Stage thanh cong.
- Neu commit that bai thi khong duoc xoa OCR temp.

## Cac pha implement

### Phase 2A. Khoa ranh gioi hanh dong cua Stage

- [ ] Doi ten nut hien thi cua Stage tu `Luu` thanh `Cap nhat`.
- [ ] Audit tat ca button va handler co kha nang kich hoat persistence cua Stage.
- [ ] Bo cac entry point save Stage trung lap de chi `Cap nhat` moi duoc commit Stage.
- [ ] Dam bao viec sua inline thong thuong khong auto-save am tham.

Dieu kien dat:
- User co the sua Stage ma chua persist ngay.
- Chi `Cap nhat` moi commit thay doi cua Stage.

### Phase 2B. Dinh nghia va implement contract persistence

- [ ] Chon contract persistence toi thieu nhung van dung voi spec da chot.
- [ ] Ghi ro contract duoc chon vao code comment va `docs/case_user_flow_spec.md`.
- [ ] Dam bao `Cap nhat` persist toan bo Stage da commit o cap case, khong chi la cac delta roi rac theo tung customer.
- [ ] Dam bao luc load trang co the doc lai dung snapshot Stage da commit do.

Huong uu tien:
- Trang thai cap case phai doc lai duoc nhu mot khoi va phai la du lieu dung de render Stage khi reload.
- Cac bang derived hoac cau truc legacy van co the duoc cap nhat de tuong thich, nhung khong duoc thay Stage lam source of truth cua case UI.

Decision gate:
- Neu khong the lam sach phase nay neu thieu `case_state_json` hoac mot payload case-level tuong duong, phai bao `SCOPE BREAK REQUEST` thay vi che di khoang trong.

### Phase 2C. Day Stage da commit sang cac vung lien quan

- [ ] Sau `Cap nhat`, render lai pool tu Stage da commit va state assignment hien tai cua diagram.
- [ ] Cap nhat cac vung hien thi khac dang mirror label/thong tin cua person.
- [ ] Dam bao dong Stage bi xoa se bien mat khoi pool.
- [ ] Neu van con diem cascade cua diagram phai de sang Phase 3 thi ghi ro vao spec/task note.

Dieu kien dat:
- Sau `Cap nhat`, downstream UI phai phan anh snapshot Stage da commit moi nhat, khong duoc di theo OCR stale hoac workflow flag cu.

### Phase 2D. Xoa OCR temp an toan

- [ ] Chi xoa record OCR tam va reference anh nguon trong modal sau khi `Cap nhat` thanh cong.
- [ ] Neu save that bai, OCR temp phai duoc giu nguyen.
- [ ] Xac nhan mo lai OCR modal sau `Cap nhat` thanh cong thi bat dau bang mot temp state sach.

### Phase 2E. Them regression protection

- [ ] Them test static hoac DOM-oriented cho ownership cua action:
  - `Cap nhat` la action commit Stage duy nhat.
  - Sua Stage ma chua `Cap nhat` thi chua commit.
  - Xoa Stage chi di duong tu row delete button.
  - OCR temp phai song den khi `Cap nhat` thanh cong.
- [ ] Them regression test cho save/load neu co doi persistence backend.

## Cac rule can duoc chot them

Nhung muc nay chua can fix ngay trong plan, nhung luc implement phai hoac chot hoac dung lai de hoi:

### `STAGE-R1` Contract persistence

Can chot ro Stage da commit se song o dau:
- `InheritanceCase.case_state_json`
- mot field JSON case-level moi/legacy
- bang participant chi la projection derived
- customer records cong voi case snapshot

Huong de xuat:
- mot snapshot case-level duy nhat cho Stage truth
- cac bang derived chi de tuong thich

### `STAGE-R2` Identity cua dong

Can chot ro mot dong Stage duoc dinh danh the nao truoc khi co DB id on dinh:
- temp client id
- UUID-style local id
- khong nen dung composite identity

Huong de xuat:
- moi dong Stage duoc gan `ui_id` on dinh ngay tu dau
- DB id, neu co, chi la secondary

### `STAGE-R3` Contract ngay thang

Can chot mot quy tac ro cho hien thi/lưu:
- hien thi `dd/mm/yyyy`, store ISO
- hoac hien thi ISO truc tiep

Huong de xuat:
- hien thi `dd/mm/yyyy`
- normalize/store payload theo ISO neu co the

### `STAGE-R4` Hydration case cu

Can chot ro mo case cu se lam gi neu case do chua co Stage truth theo format moi.

Huong de xuat:
- hydrate tu du lieu legacy tot nhat hien co khi load
- den lan `Cap nhat` thanh cong tiep theo thi ghi snapshot canonical moi

## Rui ro

- `form.html` hien dang tron OCR, Stage va save flow; coupling an rat de xay ra.
- Pool hien co lich su/workflow rieng, co the chong lai mo hinh Stage-first.
- Endpoint save/submit hien tai co the persist partial state som hon y dinh.
- Xoa dong Stage khi chua co contract identity sach co the xoa nham card phia sau.

## Xac minh

Voi cac task implement theo plan nay:

- [ ] Chay test frontend/static tap trung truoc.
- [ ] Chay `.\verify.bat` truoc khi bao xong.
- [ ] Neu co doi save/load hoac hydration, bat buoc test:
  - sua Stage nhung chua `Cap nhat` roi reload
  - `Cap nhat` roi reload
  - xoa dong Stage roi `Cap nhat`
  - handoff OCR xuong Stage roi `Cap nhat`

## Tieu chi ban giao

Muc toi thieu de coi Phase 2 dat:
- Nut Stage da la `Cap nhat`.
- Stage la UI source of truth duy nhat cho du lieu nguoi.
- Chi `Cap nhat` moi commit thay doi cua Stage.
- OCR temp chi bi clear sau `Cap nhat` thanh cong.
- Pool refresh tu Stage da commit.
- Cac muc mo cua Phase 2 trong `docs/case_user_flow_spec.md` duoc cap nhat ro muc nao da xong, muc nao chua.

## Ghi chu handoff cho task sau

Khi co task sau noi "lam Phase 2" hoac cham vao Stage truoc khi Phase 2 dong hoan toan, agent bat buoc mo dau bang viec nhac lai:
- Stage la UI source of truth duy nhat.
- Chi nut xoa o cuoi dong moi duoc xoa du lieu Stage.
- Chi `Cap nhat` moi duoc commit thay doi cua Stage.
- OCR temp chi duoc clear sau `Cap nhat` thanh cong.
- Toan bo cac muc `STAGE-*` va `STAGE-R*` con mo trong `docs/case_user_flow_spec.md`.
