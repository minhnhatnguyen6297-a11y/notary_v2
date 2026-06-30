# Case user flow spec

Tai lieu nay mo ta flow thao tac that cua user trong man hinh ho so.
Agent phai doc file nay truoc khi lam task dai lien quan `frontend/templates/cases/form.html`,
OCR CCCD nguoi, stage/pool/diagram, preview, hoac export Word.

Muc tieu cua spec la giup agent hieu user se bam gi, input la gi, output mong muon la gi,
va nut nao duoc phep tac dong vao du lieu.

## 1. Nguyen tac thao tac

- Han che 1 nut thuc hien qua nhieu chuc nang khong lien quan.
- Moi nut chi thuc hien dung nhiem vu duoc chi dinh trong flow.
- Han che 1 chuc nang duoc gan vao nhieu nut.
- Dac biet voi hanh vi xoa/clear/reset du lieu: phai chi ro nut nao duoc quyen xoa.
- Nut `x` tren modal mac dinh chi la an/minimize modal, khong duoc luu, xoa, clear, flush, reset du lieu.
- Neu can gan hanh vi xoa du lieu vao nut moi, agent phai neu ro nut nao, xoa vung du lieu nao, va hoi user truoc.
- Khi mot du lieu hien o nhieu noi, muc tieu dai han la dong bo 1 source of truth: sua 1 noi thi cac noi khac cap nhat theo.
- Neu chua co source of truth ro rang, khong duoc tu dong them logic merge/sync phuc tap de "doan y user".

## 2. Pham vi phase hien tai

Phase hien tai chi ap dung cho OCR CCCD nguoi bang `AI OCR`.

Khong ap dung trong phase nay:
- OCR tai san.
- Local OCR. Mac dinh bo qua Local OCR vi user se xoa va lam lai toan dien sau.
- Thay doi OCR backend/router neu task chi dang noi ve UI flow modal/stage.

## 3. Flow OCR CCCD nguoi: chon anh -> AI OCR -> cua so OCR

### Input

User chon 1 hoac nhieu anh CCCD, doi anh load vao queue, bam `AI OCR`.

### Output mong muon

- Ket qua OCR xuat tam trong cua so OCR.
- Anh nguon duoc giu tam trong cua so OCR.
- Moi dong du lieu nguoi co nut nho `Xem anh`.
- Bam `Xem anh` phai hien dung anh nguon cua dong du lieu do.
- Neu 1 dong du lieu duoc tao tu 2 anh, vi du mat truoc + mat sau, `Xem anh` phai xem duoc ca 2 anh.
- Ket qua OCR moi khong tu dong day xuong stage neu user chua bam `Luu`.

### Invariant

- Cua so OCR la vung tam thoi de user xem, sua, doi chieu anh nguon.
- Stage la vung tong hop du lieu cho case.
- Tu cua so OCR sang stage chi duoc thuc hien boi hanh vi `Luu` duoc user chi dinh.

## 4. Flow OCR: nut Luu

### Input

User bam nut `Luu` trong footer cua so OCR.
Nut nay thay cho nut `Dong` cu neu footer dang dung nut `Dong`.

### Output mong muon

- Du lieu tam trong cua so OCR duoc day xuong vung stage.
- Cua so OCR van giu ket qua va anh tam sau khi luu.
- Cho phep day du lieu xuong stage bat ke thieu mat truoc hay thieu mat sau.
- Sau khi luu, neu cung du lieu hien o ca cua so OCR va stage, dinh huong la can dong bo duoc voi nhau.

### Dong bo voi stage

User muon du lieu co the hien o nhieu noi nhung dong bo voi nhau: sua 1 cho thi cac cho khac cap nhat theo.
Da chot o Phase 2: stage la source of truth UI duy nhat cho danh sach nguoi trong case.
Neu du lieu cung hien o cua so OCR va stage, cac vung lien quan phai dong bo theo stage sau khi user bam `Cap nhat`.
Agent khong duoc tao source of truth khac cho pool/diagram/OCR modal neu chua duoc user duyet.

## 5. Flow OCR: nut x tren modal

### Input

User bam nut `x` tren cua so OCR.

### Output mong muon

- Chi an/minimize cua so OCR.
- Khong day du lieu xuong stage.
- Khong clear queue anh.
- Khong clear ket qua OCR tam.
- Khi mo lai cua so OCR, user van thay tiep ket qua va anh tam dang co.

### Invariant

Nut `x` khong duoc gan hanh vi luu, xoa, clear, reset, flush, hay auto-stage.

## 6. Flow OCR: chon them anh sau lan OCR dau

### Input

User da co ket qua OCR tam trong cua so OCR.
User chon them anh moi, doi anh load, bam `AI OCR`.

### Output mong muon

- Ket qua OCR moi duoc them vao cua so OCR.
- Ket qua moi uu tien hien len tren.
- Ket qua OCR cu van giu lai va bi day xuong duoi.
- Khong xoa ket qua cu.
- Neu OCR lai cung mot CCCD, tao dong moi. User se tu xoa thu cong neu can.

### Ly do

Khong tu merge dong trung CCCD trong phase nay de tranh sinh them logic an, kho debug, va de user kiem soat ro du lieu nao bi xoa.

## 7. Phase 2: vung stage

### Vai tro cua stage

Stage la vung tong hop du lieu goc cua 1 ho so thua ke.
User nhin vao stage de biet ho so dang co bao nhieu nguoi, thong tin tung nguoi dung chua,
va sua truc tiep neu sai.
Stage la source of truth UI duy nhat cho danh sach nguoi trong case.

Stage nhan du lieu tu nhieu nguon:
- Excel.
- OCR CCCD nguoi.
- Cac chuc nang nhap/sinh du lieu khac trong tuong lai.

### Input

Du lieu thong tin nguoi da duoc dua vao stage tu mot hoac nhieu nguon.

### Output mong muon

Moi nguoi la 1 dong trong stage.
Moi dong la du lieu chuan dang field/object, toi thieu gom:
- `ho_ten`
- `ngay_sinh`
- `ngay_chet`
- `so_giay_to`
- `ngay_cap`
- `dia_chi`

Thiet ke stage phai cho phep mo rong them truong phu trong tuong lai.
Cac truong tren stage co the sua thu cong.

### Invariant

- Khong tu y xoa du lieu o stage.
- Stage la vung du lieu goc cua ho so trong UI, khong phai cache tam.
- Stage la source of truth UI duy nhat cho nguoi trong case.
- Pool/diagram va cac vung lien quan phai dong bo theo stage sau khi user bam `Cap nhat`.
- Chi nut xoa o cuoi tung dong stage moi duoc phep xoa dong do.
- Cac nut khac khong duoc clear/reset/remove dong stage.
- Neu can them hanh vi xoa stage o cho khac, agent phai hoi user truoc.

## 8. Phase 2: nut Cap nhat cua stage

Nut stage khong goi la `Luu` de tranh trung voi nut `Luu` trong cua so OCR.
Ten nut stage la `Cap nhat`.

### Input

User sua hoac kiem tra du lieu trong stage, sau do bam `Cap nhat`.

### Output mong muon

- Lay trang thai moi nhat cua tung dong stage lam du lieu chuan.
- Cap nhat cac vung hien thi lien quan theo du lieu stage moi nhat.
- Xuat/cap nhat the nguoi xuong pool voi dung trang thai moi nhat.
- Sau khi `Cap nhat`, xoa du lieu va anh dang luu tam trong cua so OCR.
- Sau khi `Cap nhat`, user khong con xem lai duoc anh nguon va ket qua OCR tam trong cua so OCR.
- Luu DB ngay tai buoc `Cap nhat`; khong co mot nut luu DB tong rieng cho toan bo flow.

### Y nghia cua Cap nhat

Khi user bam `Cap nhat`, mac dinh la user da kiem tra lai du lieu trong stage.
Luc nay stage tro thanh ban du lieu hien hanh de cac vung khac dong bo theo.
Cua so OCR chi la nguon tam da hoan thanh nhiem vu, nen duoc clear sau `Cap nhat`.
Day cung la moc persist DB cho du lieu stage.

### Sua truc tiep nhung chua Cap nhat

Neu user sua du lieu truc tiep trong stage nhung chua bam `Cap nhat`:
- Thay doi chi nam o UI hien tai.
- Cac vung khac chua bat buoc phai cap nhat theo.
- Neu load lai trang, cac thay doi chua `Cap nhat` co the bi mat.

### Cascade khi stage thay doi

Khi user xoa 1 dong stage roi bam `Cap nhat`:
- Neu the nguoi do dang o pool, xoa the khoi pool.
- Neu the nguoi do da drop vao diagram, xoa the khoi diagram.
- Neu the do sinh ra cac nhanh quan he trong diagram, xoa nhanh do.
- Cac the lien quan phia sau ma van con trong stage thi tra ve pool.
- The nao da bi xoa khoi stage thi xoa luon, khong tra ve pool.
- Khong can canh bao khi xoa/cascade theo stage.

Chi tiet cascade diagram se duoc viet o phase sau.
Tinh than cot loi da chot: stage la source of truth UI duy nhat.

## 9. Phase 3: pool

### Vai tro cua pool

Pool la vung truc quan hoa trung gian giua stage va diagram.
Pool khong phai source of truth du lieu nguoi.
Pool giup user yeu cong nghe thao tac keo tha de dua nguoi tu stage sang diagram.

Stage luu du lieu thuc cua nguoi.
Diagram the hien quan he giua nguoi voi nhau.
Pool chi hien cac the nguoi co trong stage nhung chua duoc gan vao diagram.

### Input: bam Cap nhat o stage

User bam `Cap nhat` o stage.

### Output mong muon

- Cac dong stage hop le duoc truc quan hoa thanh the trong pool.
- The trong pool phai dung du lieu moi nhat tu stage.
- Neu mot nguoi da nam trong diagram, nguoi do khong hien lai trong pool.
- Neu mot nguoi bi xoa khoi stage roi bam `Cap nhat`, the tuong ung bi xoa khoi pool/diagram theo cascade stage.

### Input: drag tu pool sang diagram

User drag mot the tu pool va drop vao 1 node trong diagram.

### Output mong muon

- The chuyen sang diagram tai node duoc drop.
- The do bien mat khoi pool.
- Du lieu nguoi van lay tu stage, pool/diagram chi la bieu dien vi tri/trang thai.

### Input: xoa the trong diagram bang nut x

User bam nut `x` tren the dang nam trong diagram.

### Output mong muon

- Xoa the do khoi diagram.
- Tra the do ve pool neu nguoi do van con trong stage.
- Neu the do co nhanh phat sinh trong diagram, xoa nhanh phat sinh tu vi tri cua the bi remove.
- Cac the phu thuoc trong nhanh bi xoa duoc tra ve pool neu nguoi tuong ung van con trong stage.
- The nao khong con trong stage thi xoa luon, khong tra ve pool.

### Input: move the giua cac node trong diagram

User drag/drop the tu node nay sang node khac trong diagram.

### Output mong muon

- Xoa the o node cu.
- Gan the vao node moi.
- Khong hien lai the do trong pool trong qua trinh move.
- Neu node cu co nhanh phat sinh tu the bi move, xoa nhanh phat sinh tu vi tri node cu.
- Cac the phu thuoc trong nhanh bi xoa duoc tra ve pool neu nguoi tuong ung van con trong stage.
- The nao khong con trong stage thi xoa luon, khong tra ve pool.

### Invariant

- Pool la computed/view-state tu stage va diagram, khong phai source of truth rieng.
- Mot nguoi chi duoc co 1 vi tri hien hanh: pool hoac diagram.
- Neu nguoi dang o diagram thi khong hien trong pool.
- Neu nguoi dang o pool thi chua duoc gan vao diagram.
- Moi thao tac xoa/move trong diagram khong duoc xoa du lieu stage.
- Stage moi co quyen quyet dinh nguoi nao ton tai trong case.

## 10. Phase 4: diagram

### Vai tro cua diagram

Diagram la noi the hien quan he giua nguoi voi nhau va trang thai phan chia thua ke.
Diagram khong phai noi luu du lieu goc cua nguoi; du lieu goc van la stage.
Diagram luu trang thai gan nguoi vao node, quan he, nhanh phat sinh, engine state, va cac metadata can de render/tinh toan.

Day la phan nang nghiep vu va ky thuat, khong chi la flow input/output.
Khi code diagram, agent phai bam chat quy dinh thua ke Viet Nam, rule "nuoc chay", va bai toan mau da duoc user chot.

### Tai lieu bat buoc doc khi lam diagram

- `docs/plans/inheritance_diagram.md`: tai lieu nghiep vu goc cho so do thua ke, rule "nuoc chay", hang thua ke, the vi, tai san chung vo chong.
- `docs/plans/inheritance_diagram_v2_refactor_wip.md`: co ban ghi bai toan mau X/Y/D/Z va fixture ket qua bat buoc `M=N=O=59/192`, `Z2=Z3=5/128`. File nay co mot so phan WIP/superseded, nhung fixture va rule nuoc chay van la can cu quan trong.
- `docs/plans/cases_dataflow_v2.md`: tham khao kien truc stage/pool/diagram va invariant pool computed tu stage - diagram.
- `docs/plans/unified-orbiting-pebble.md`: tham khao cac quyet dinh cu ve recursion, flow edge, person active max, va persist tree state. Neu co mau thuan voi spec hien tai, uu tien spec hien tai cho flow user va source of truth UI.

### Goal nghiep vu

- Tuan thu spec Phase 3: pool chi la vung trung gian, diagram nhan the tu pool, remove/move trong diagram chi tac dong pool/diagram va khong xoa stage.
- Tuan thu rule "nuoc chay": nuoc chay vao ai, neu nguoi do chet thi mo vong lap thua ke moi voi cung quy tac.
- Tuan thu quy dinh thua ke Viet Nam khi tinh hang thua ke, thua ke the vi, nguoi chet truoc/sau/cung thoi diem, va tai san chung vo chong.
- Bai toan mau X/Y/D/Z la fixture bat buoc khi implement engine diagram. Neu engine khong pass fixture nay thi chua duoc xem la dung nghiep vu.
- Khi gap rule nghiep vu mo ho hoac mau thuan voi thuc te ho so, agent phai ghi ro case va hoi user, khong tu doan.

### Goal giao dien

- Tree phan nhanh phai co bo cuc ro rang, de user nhin duoc quan he.
- Node/card hien tai co the giu huong thiet ke dang on, khong refactor giao dien neu khong can.
- Mui ten/edge moi la diem can tap trung: mui ten phai noi dung tu card/node nguon den card/node dich, gon gang, khong lech, khong long vong kho nhin.
- Can phan biet mui ten quan he huyet thong va mui ten dong chay thua ke neu engine can hien thi ca hai loai.
- Khi sua connector/edge, phai uu tien tinh dung va de nhin hon hieu ung trang tri.

### Luu trang thai diagram

Nut `Luu ho so` o khu vuc diagram can duoc dinh nghia lai thanh hanh vi luu trang thai hien tai cua pool va diagram.

Input:
- User bam nut luu trong khu vuc diagram.

Output mong muon:
- Luu trang thai hien tai cua pool va diagram.
- Luu assignments/node state/edge state/engine state can thiet de mo lai dung trang thai diagram.
- Khong sua du lieu stage.
- Khong xoa, clear, reset stage.
- Khong ghi de field nguoi trong stage.

### Invariant

- Stage la source of truth UI duy nhat cho du lieu nguoi.
- Diagram chi luu quan he, vi tri/trang thai gan node, engine output, va trang thai render/tinh toan.
- Save diagram khong duoc tac dong du lieu stage.
- Moi nguoi trong diagram phai reference ve 1 nguoi ton tai trong stage.
- Neu stage xoa nguoi va bam `Cap nhat`, diagram phai bi cascade theo stage nhu Phase 2/3.
- Chi tiet ky thuat engine, schema state, va test harness se ban o task rieng.

## 11. Nut duoc phep xoa du lieu

Mac dinh trong phase OCR CCCD nguoi:
- Nut `x` modal: khong xoa.
- Nut `Luu`: khong xoa.
- Bam `AI OCR`: khong xoa ket qua OCR cu.
- Neu co nut thung rac/xoa tat ca anh, agent phai coi day la nut xoa ro rang va khong gan hanh vi xoa nay cho nut khac.

Mac dinh trong phase stage:
- Moi dong stage co nut xoa `.stage-remove-btn` o cuoi dong.
- Bam nut xoa: xoa row khoi DOM ngay, khong canh bao, khong confirm.
- Xoa row chi la UI draft; cascade pool/diagram chi xay ra sau khi user bam `Cap nhat`.
- Nut `Cap nhat` khong xoa stage.
- Nut `Cap nhat` duoc phep clear du lieu/anh tam trong cua so OCR sau khi da day du lieu stage sang cac vung lien quan.

Mac dinh trong phase pool/diagram:
- Drop tu pool sang diagram chi xoa the khoi pool, khong xoa nguoi khoi stage.
- Nut `x` tren the diagram chi remove khoi diagram va tra ve pool neu nguoi con trong stage.
- Move the giua cac node diagram khong xoa stage va khong hien the lai trong pool.
- Cascade nhanh diagram chi tac dong pool/diagram, khong xoa stage.
- Nut luu trong khu vuc diagram chi luu trang thai pool/diagram, khong xoa/sua stage.

Neu task sau nay can thay doi hanh vi xoa:
- Ghi ro nut nao xoa.
- Ghi ro xoa queue anh, ket qua OCR tam, stage, hay tat ca.
- Ghi ro co can confirm hay khong.
- Hoi user neu scope chua ro.

## 12. Checklist cho agent khi nhan task lien quan flow nay

Truoc khi sua code, agent phai tra loi duoc:
- Task dang cham flow nao: OCR modal, stage, pool/diagram, preview, hay Word export?
- Nut nao la input cua user?
- Output mong muon cua nut do la gi?
- Nut do co duoc phep luu, xoa, clear, reset, flush, hay auto-stage khong?
- Du lieu dang o vung nao: queue anh, ket qua OCR tam, stage, pool, diagram, DB?
- Neu mot dong du lieu co anh nguon, nut `Xem anh` co con xem dung anh khong?
- Neu data hien o nhieu noi, da ton trong invariant stage la source of truth UI duy nhat chua?
- Neu sua stage, da xac dinh thay doi chi o UI, da `Cap nhat`, hay da luu DB chua?
- Neu xoa stage, co dung nut xoa cuoi dong khong?
- Neu thao tac pool/diagram, nguoi do dang o pool hay diagram?
- Neu xoa/move the trong diagram, co nhanh phat sinh can xoa va the phu thuoc can tra ve pool khong?
- Neu tra the ve pool, nguoi do co con ton tai trong stage khong?
- Neu task cham diagram engine, da doc `docs/plans/inheritance_diagram.md` va fixture trong `docs/plans/inheritance_diagram_v2_refactor_wip.md` chua?
- Neu task cham connector/edge, mui ten co noi dung card/node nguon-dich, gon va khong lech khong?
- Neu bam luu trong diagram, co dam bao chi luu pool/diagram va khong sua stage khong?

Neu khong tra loi duoc cac cau tren, dung lai va hoi user truoc khi sua logic.

## 13. Open issue register by phase

Muc nay la tracker bat buoc cho agent.
Khi nhan task cham phase nao, agent phai doc lai phase do va nhac cac open issue chua giai quyet truoc khi sua code.
Khi mot issue da duoc fix va verify, cap nhat trang thai sang `resolved` kem ngay va bang chung test.

### Phase 1: OCR CCCD nguoi

Status hien tai: `resolved for current Phase 1 OCR modal flow`.
Plan thuc thi: `docs/superpowers/plans/2026-06-17-phase-1-ocr-flow-alignment.md`.

Open issues trai spec:
- `OCR-1`: resolved 2026-06-17. Nut `x`/hidden modal khong con auto-stage hay clear `ocrResults`/`imageQueue`. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `OCR-2`: resolved 2026-06-17. Footer OCR da co nut `Luu` rieng, khong dung footer dismiss-only close button. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `OCR-3`: resolved 2026-06-17. `AI OCR` khong con reset ket qua cu; ket qua moi duoc chen len tren. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `OCR-4`: resolved 2026-06-17. Da bo co che flush/auto-stage khi modal dang an; OCR chi day xuong stage qua nut `Luu`. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `OCR-5`: resolved 2026-06-17. `autoStageOcrResults()` khong con block dong warning thieu mat khi save OCR sang stage. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `OCR-6`: resolved 2026-06-17. Save OCR sang stage cho phep duplicate CCCD bang cach bo duplicate guard o path OCR -> stage. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `OCR-7`: resolved 2026-06-17. Local OCR khong con duoc expose trong person OCR modal Phase 1. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `OCR-8`: resolved 2026-06-17. Person OCR modal bo qua non-person results va khong render tai san/hon nhan trong Phase 1. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.

Open issues can them rule:
- `OCR-R1`: resolved 2026-06-22. Stage la source of truth UI sau khi OCR `Luu` day du lieu xuong Stage; sua lai card OCR tam khong dong bo ngam vao dong Stage da tao. Neu user muon dua ban sua moi tu OCR card xuong Stage thi bam `Luu` tiep de tao dong Stage moi, user tu xoa dong thua. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.
- `OCR-R2`: resolved 2026-06-22. Bo han nut thung rac/xoa tay khoi person OCR modal Phase 1. Chi `Cap nhat` o Stage moi duoc clear queue anh va ket qua OCR tam qua `clearOcrTempAfterStageCommit()`. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `OCR-R3`: resolved 2026-06-22. Khi `Luu` nhieu lan cung mot card OCR da day xuong Stage, tao them dong Stage moi moi lan; khong update an dong da tao. Ly do: tranh hidden link/merge logic, user tu xoa dong thua bang nut xoa Stage. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.
- `OCR-R4`: resolved 2026-06-22. Person OCR modal phase nay bo qua/an `properties`/`marriages` neu endpoint nguoi tra ve; khong render tai san/hon nhan trong phase OCR CCCD nguoi. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.

### Phase 2: Stage

Status hien tai: `resolved for current Stage source-of-truth scope`.

Open issues trai spec:
- `STAGE-1`: resolved 2026-06-18. Nut stage da doi thanh `Cap nhat`. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\venv\Scripts\python.exe -m unittest tests.test_diagram_payload_parser`.
- `STAGE-2`: resolved 2026-06-18 cho case da co id. `Cap nhat` van luu/tao `Customer` cho tung row, sau do persist snapshot stage vao `InheritanceCase.case_state_json` qua `POST /cases/{cid}/stage-update`. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\venv\Scripts\python.exe -m unittest tests.test_diagram_payload_parser`.
- `STAGE-3`: resolved 2026-06-22. Pool chi tinh tu committed Stage snapshot tru diagram assignments; da bo fallback legacy theo workflow flag `inPool` trong `derivePoolVisibility()`. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.
- `STAGE-4`: resolved 2026-06-18. Submit ho so khong con tu goi `saveParticipantDraftRows`; `case_state_json` khi submit lay tu committed stage snapshot, khong lay draft DOM chua `Cap nhat`. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.
- `STAGE-5`: resolved 2026-06-22. Khi `Cap nhat`, person bi xoa khoi stage bi mark deleted khoi pool/workflow; React diagram dung `removedIds` de prune nhanh phu thuoc, xoa card khong con trong Stage, va tra dependent people con trong Stage ve pool. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.
- `STAGE-6`: superseded 2026-06-26. Them lai nut xoa `.stage-remove-btn` tren tung dong Stage draft; bam xoa row khoi DOM ngay, khong canh bao. Cascade pool/diagram chi xay ra sau khi user bam `Cap nhat` (via `removedIds` trong `persistCommittedStageSnapshot`). Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.
- `STAGE-7`: resolved 2026-06-23. Legacy pool/tree workflow khong con duoc tu set `inStaging: false` khi keo tha, restore participant, hay tra nguoi ve pool; membership Stage chi doi tai Stage commit/xoa hop le. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `STAGE-8`: resolved 2026-06-23. Workflow flag `deleted: true` chi duoc dat trong duong Stage commit khi `removedIds` roi khoi committed Stage; pool/tree/diagram khong co quyen tu danh dau xoa nguoi khoi ho so. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `STAGE-9`: resolved 2026-06-23. Workflow patch `deleted: false` chi hop le khi nguoi dang duoc dua vao Stage (`inStaging: true`); pool/tree/diagram khong duoc tu revive nguoi da bi loai khoi Stage. Tang guard `setCustomerWorkflowState()` se giu `deleted: true` neu patch undelete khong di kem Stage flow hop le. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.

Open issues can them rule:
- `STAGE-R1`: resolved 2026-06-22. Contract: case da co id thi `Cap nhat` persist snapshot vao `InheritanceCase.case_state_json` qua `/cases/{cid}/stage-update`; case moi chua co id thi `Cap nhat` chi cap nhat hidden `case_state_json` cho lan submit `Tao ho so`. Khong co nut luu DB tong rieng. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\venv\Scripts\python.exe -m unittest tests.test_diagram_payload_parser`.
- `STAGE-R2`: resolved 2026-06-22. Sau `Cap nhat`, identity UI/diagram la `Customer.id`; duplicate CCCD/so giay to nhung khac Stage row id van la 2 dong doc lap va khong bi gop/xoa tu dong. Row draft chua co DB id van la DOM draft cho den khi `Cap nhat` tao/cap nhat Customer. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.
- `STAGE-R3`: resolved 2026-06-22. Stage UI hien thi va cho phep nhap/sua ngay theo `dd/mm/yyyy`; cac path render Stage dung `_fmtDate(...)` de khong ro ri ISO vao input UI, trong khi backend/load legacy van parse duoc payload hien co. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `STAGE-R4`: resolved 2026-06-22. Case cu co participants nhung chua co `case_state_json` duoc backend derive `case_state_json.stage` khi mo edit form; khong ghi de Stage da co. DB snapshot se duoc persist khi user bam `Cap nhat`, khong chay migration DB rieng. Verify: `.\venv\Scripts\python.exe -m unittest tests.test_diagram_payload_parser`.

### Phase 3: Pool

Status hien tai: `resolved for current Stage -> Pool data-flow`.

Open issues trai spec:
- `POOL-1`: resolved 2026-06-18 cho luong committed Stage. `derivePoolVisibility()` tinh pool tu committed stage snapshot tru diagram assigned ids; `loadPool()` lay candidate tu committed Stage khi co snapshot. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.
- `POOL-2`: resolved 2026-06-22. Import Excel/them nguoi chi tao Stage draft; pool khong refresh/commit truc tiep truoc `Cap nhat`. Stage save bo duong `commitCustomerToPool()` legacy va pool chi refresh sau `persistCommittedStageSnapshot()`. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.
- `POOL-3`: resolved 2026-06-22 cho data-flow hien tai. Drop/remove/move co bridge workflow; assign khong tinh displaced tu preview stale, move khong swap vao occupied target, dependent branch van tra ve pool. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.
- `POOL-4`: resolved 2026-06-22. Tim/nap customer vao registry va click ket qua search trong khu pool khong duoc set `inPool: true` truc tiep; search chi them nguoi vao Stage draft, user phai bam `Cap nhat` de pool render tu committed Stage. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.

Open issues can them rule:
- `POOL-R1`: resolved 2026-06-18. Nguon tinh pool sau `Cap nhat` la committed Stage rows tru diagram assignments; workflow flags chi con fallback legacy khi chua co committed Stage snapshot.
- `POOL-R2`: decided 2026-06-19. Neu mot person duplicate CCCD/so giay to nhung khac Stage row id thi van la 2 dong doc lap; he thong khong tu gop/xoa, user tu xoa dong thua bang nut xoa cuoi dong Stage.
- `POOL-R3`: resolved 2026-06-18 cho luong hien tai. Pool khong persist rieng; render lai tu committed Stage va diagram state.
- `POOL-R4`: resolved 2026-06-22. Moi nguon them nguoi vao ho so, ke ca search customer co san trong pool panel, phai di qua Stage draft truoc; khong co nut/handler nao duoc day thang nguoi vao pool neu chua `Cap nhat`.

### Phase 4: Diagram

Status hien tai: `partial`.

Open issues trai spec:
- `DIAGRAM-1`: resolved 2026-06-18 cho case da co id. Nut diagram da doi label `Luu so do`, dong dung markup, va submit hien tai goi `POST /cases/{cid}/diagram-update` de luu `case_state_json`/`diagram_payload`/`engine_state_json`; backend merge diagram nhung preserve `stage` da luu trong DB. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\venv\Scripts\python.exe -m unittest tests.test_diagram_payload_parser`.
- `DIAGRAM-2`: resolved 2026-06-22 cho data-flow non-visual. Remove/move trong diagram prune nhanh phu thuoc theo `parentSlotId/sourceId`; `removeWithWorkflow()` va `moveWithinDiagram()` tra dependent people ve pool neu ho van con trong Stage. Drop/move vao node dang co nguoi bi block, khong replace, khong swap. Verify: `node --test tests/cases_ui_dataflow_static.test.mjs`.
- `DIAGRAM-3`: deferred 2026-06-19. Edge/arrow visual se tach thanh task lon rieng de user mo ta chi tiet; khong tron vao task on dinh data-flow hien tai.

Open issues can them rule:
- `DIAGRAM-R1`: partial 2026-06-22. Luong hien tai van persist song song `case_state_json.diagram.assignments`, `case_state_json.diagram.engineState`, `engine_state_json`, va participants legacy. Da khoa them invariant save: `POST /cases/{cid}/diagram-update` uu tien `case_state_json.diagram.engineState` lam nguon truth cho save diagram; neu `diagram_payload` stale/leak nguoi ngoai Stage thi backend prune theo Stage truoc khi derive participant va luu `engine_state_json`. Da khoa them bang test rang trong cung mot request, `engine_state_json` stale cung khong duoc phep ghi de `case_state_json.diagram.engineState`: nodes va `updatedAt` phai theo snapshot diagram moi nhat trong `case_state_json`, roi moi dong bo nguoc vao `engine_state_json`. Cung da khoa them rang `diagram_payload` tra ve ngay sau save phai dong bo cung snapshot moi nhat nay; frontend khong duoc nhan lai payload stale chi vi hidden field `engine_state_json` gui len da cu. Sau prune, backend dong bo nguoc assignments/engineState da duoc giu lai vao chinh `case_state_json` de khong con lech giua 2 snapshot save. Da khoa them bang test rang `assignments` stale cho slot dang trong cung phai bi don khi save; backend phai recompute assignments tu active person nodes thay vi tin mapping cu, tranh pool/diagram reload bi mat nguoi oan. `assignments` sau save chi duoc giu node active; node `hidden/deleted` khong con giu assignment active, tranh lam pool bi mat nguoi khi reload. Reload path frontend cung bo qua node `hidden/deleted` trong `hydrateEngineStateNodes()`, tranh hien lai node da bi an/xoa thanh node song khi mo ho so. Save path backend da preserve `engineState.edges` va prune edge nao tro toi node bi loai sau save, de reload diagram khong roi edge state hop le. Da khoa them bang test rang edge duoc giu lai sau save phai preserve ca custom metadata nhu `label`, `markerEnd`, `style`; khong duoc chi giu `id/source/target` roi lam roi thong tin render. Cung da khoa them rang `diagram_payload` response sau save phai giu chinh metadata edge nay, tranh frontend vua save xong lai mat nhan/dinh dang du DB da dung. Tangg normalize cung da co test chung minh metadata phu cua edge van duoc giu khi parse `diagram_payload`, tranh truong hop state bi roi ngay tu lop normalize truoc khi vao save path. Normalize layer cua `case_state_json` cung prune edge mo coi neu `source/target` khong con ton tai trong `engineState.nodes`, tranh luu state noi bo mau thuan ngay ca truoc khi vao save path. Merge layer `_merge_case_state_diagram()` cung da co test khoa invariant: du backend giu lai `stage` cu trong DB, `diagram.assignments` va supplemental `engineState` moi nhat tu request van phai duoc preserve nguyen ven, gom `allocations`, `warnings`, `trace`, `viewport`, `layoutMeta`; khong duoc mat chi vi buoc merge thay `stage`. Backend normalize/save path da preserve them supplemental `engineState` nhu `allocations`, `warnings`, `trace`; khong con rut gon engine state thanh chi `nodes/edges` khi `Luu so do`. Da khoa them bang test rang supplemental render metadata ngoai schema cung, vi du `viewport` va `layoutMeta`, cung phai duoc giu nhat quan o tat ca cac tang trung gian lien quan: `_normalize_diagram_payload`, `_normalize_case_state_json`, `_merge_case_state_diagram()`, save/reload, va `diagram_payload` response sau save. Frontend khong duoc mat allocation/warning/layout chi vi mot tang trung gian lam roi field. Khong duoc lam roi chi vi backend khong biet ten field. Chua chot schema edge/render metadata rieng beyond prune/preserve state. Verify: `.\venv\Scripts\python.exe -m unittest tests.test_diagram_payload_parser`, `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `DIAGRAM-R2`: partial 2026-06-22. Rule ky thuat hien tai coi dependent branch la node reachable tu anchor qua `parentSlotId` va sibling qua `sourceId`; da du cho cascade remove/move UI. Da khoa them invariant backend cho save/reload: ghost node khong duoc tham gia participant active hay `diagram.assignments`; neu payload loi gan `personId` vao node `kind="ghost"` thi backend loai node do khoi save path thay vi coi nhu node that. Da khoa them duplicate policy o tang save: neu payload loi tao 2 node active cung `person.id`, backend prune node duplicate va dong bo lai `engineState/assignments` da prune. Policy hien tai khong con phu thuoc thu tu payload: node canonical cua tree goc/slot uu tien (owner/spouse/parent, con truc tiep cua owner) duoc giu truoc node nhanh sau nhu grandchild/branch duplicate. Khi prune duplicate, `flowFrom` cua node bi loai duoc merge bo sung vao node canonical duoc giu lai de metadata reuse node khong bi roi sau `Luu so do` -> reload. Da khoa them bang test rang empty structural slot neo vao duplicate branch bi loai cung phai bi prune theo sau o save path; backend khong duoc giu lai slot `branchSpouse/grandchild` mo coi neu `parentSlotId/sourceId` cua no tro toi node duplicate vua bi loai. Cung da khoa them rang edge bam vao slot mo coi bi prune gian tiep nay phai bi loai khoi ca `case_state_json`, `engine_state_json`, va `diagram_payload` response; khong duoc de lai edge stale du node da mat. Frontend `ReactFlowApp` gio cung hydrate `flowFrom` tu `initialEngineState.nodes` va pass-through lai vao `buildEngineInput()` / `runDiagramEngine()` de reload xong save tiep khong bi roi metadata nay o vong sau. Frontend cung giu `bucket`, `allowsShare`, `removable` trong `buildEngineInput()` va `runDiagramEngine().engineState.nodes`, tranh viec save -> reload bien slot goc thanh removable hoac doi bucket/layout logic. Backend `_normalize_diagram_payload()` gio cung preserve `bucket`, `allowsShare`, `removable` trong normalized `engineState.nodes`; truoc do frontend da gui dung nhung backend lai lam roi metadata nay khi save. Neu `inheritance_engine.js` chua tai duoc, branch fallback van phai luu `engineState.nodes` tu `buildEngineInput(models)` kem warning `engine_missing`; khong duoc de snapshot diagram chi con warning ma mat het node sau `Luu so do`. `runDiagramEngine()` hien chi con 1 branch `engine_missing` duy nhat, tranh code chet/2 nguon fallback khac nhau cho cung mot invariant save-reload. Save path frontend gio persist `engineState.nodes` tu tat ca `models.filter(node.kind === "person")`, khong chi tu occupied person nodes; nhung slot `owner/spouse/cha/me/con...` dang trong van phai ton tai sau `Luu so do -> mo lai` de user tiep tuc keo tha dung vi tri. Backend `update_diagram()` da co test chung minh giu lai empty structural slot hop le trong `engineState.nodes`, nhung van khong dua slot trong vao `diagram.assignments` hay participants active; bao gom ca empty spouse slot khong co assignment, empty spouseParent slot co `sourceId = spouse`, empty child slot co `parentSlotId/sourceId = owner`, empty sibling slot co `parentPersonId/sourceId` tro toi parent dang song, empty grandchild slot co `parentSlotId/sourceId` tro toi child branch dang song, va empty branch spouse slot co `parentSlotId/sourceId` tro toi child branch dang song, tranh mat cho drop o nhanh vo-chong/cha-me vo-chong/nhanh con/nhanh chau/nhanh dau-re sau khi reload. Warning fallback `engine_missing` tren frontend da duoc chuan hoa thanh chuoi doc duoc (`Chua tai duoc inheritance_engine.js.`), tranh thong bao vo chu khi engine client chua tai. Chua chot day du nghiep vu cho moi loai ghost/materialized node trong engine inheritance. Verify: `.\venv\Scripts\python.exe -m unittest tests.test_diagram_payload_parser`, `node --test tests/cases_ui_dataflow_static.test.mjs`, `.\verify.bat`.
- `DIAGRAM-R3`: deferred theo task visual diagram rieng; luc lam task do can chot acceptance test cho connector/edge bang fixture hoac screenshot.
- `DIAGRAM-R4`: resolved 2026-06-22. Case da co id: nut/action trong khu vuc diagram la `Luu so do` va goi `/cases/{cid}/diagram-update`. Case moi chua co id: nut/action la `Tao ho so`; `Luu so do` khong fallback full submit tao ho so.
