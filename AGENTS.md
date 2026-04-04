# Repo AGENTS - notary_v2

Quy uoc trong file nay bo sung cho cac huong dan chung o repo cha.
Muc tieu la giup Codex tu hieu session dang tap trung vao chuc nang nao.

## Session context mac dinh

- Moi session thuong chi tap trung vao mot chuc nang. Hay giu nguyen context do
  cho den khi user noi ro rang da chuyen sang chuc nang khac.
- Truoc khi hoi lai mot bug report, Codex phai tu xac dinh `active context`
  bang cach uu tien doc cac dau hieu sau:
  1. branch hien tai
  2. file dang dirty trong `git status`
  3. file user vua mo / vua nhac toi
  4. cac tu khoa trong lich su message cua session
- Lenh uu tien de bootstrap ngu canh:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\session_context_check.ps1
```

- Khi da suy ra `active context`, xem nhu do la context mac dinh cua session.
  Khong bat user lap lai "dang lam chuc nang nao" neu session da ro.

## Vong debug mac dinh

Khi user mo ta loi, hoi quy, hoac can "kiem tra giup", Codex phai tu dong lam
theo thu tu nay truoc khi hoi them:

- Codex uu tien log, reproduce, DB state, va call chain hon screenshot.
- Screenshot chi la tin hieu phu cho bug UI / render / layout; khong dung
  screenshot lam nguon chan doan chinh cho bug backend / business logic.
- Flow nay ap dung theo tang. `BOOTSTRAP`, `LOG TRIAGE`, `CODE PATH TRACE`,
  `HYPOTHESIS`, `FIX + VERIFY`, va `REPORT` la mac dinh. `REPRODUCE`,
  `DB SNAPSHOT`, va `minimal reproduce script` chi dung khi bug phu hop.

1. `BOOTSTRAP`
   - Chay `session_context_check.ps1`.
   - Ghi lai: `branch`, `active_context`, va app `ready/not ready`.

2. `LOG TRIAGE`
   - Doc cac log gan `active_context` nhat.
   - Neu co exception, keo day du traceback gan nhat; khong chi dung `tail`.
   - Ghi lai: timestamp loi, exception type, va `file:line` trong traceback.
   - Neu co `request id`, `task id`, hoac dau vet tuong duong, trace sang log
     tuong ung.

3. `REPRODUCE` (khi bug phu hop)
   - Dung cho bug runtime / API / form submit / Celery / OCR, hoac khi can tai
     hien de xac nhan root cause.
   - Uu tien replay request bang payload an toan tu log hoac DB, hoac tai hien
     bang input that lien quan.
   - Neu can, duoc dung `minimal reproduce script` tam thoi de xac nhan nguyen
     nhan. Script nay khong mac dinh commit vao repo; co the la inline command
     hoac file tam trong `tmp/`.
   - Khong ghi binary upload, secret, cookie, token, hay du lieu nhay cam vao
     AGENTS hay log debug moi.

4. `DB SNAPSHOT` (khi bug lien quan data)
   - Dung cho bug nghiep vu, tinh toan, quan he ban ghi, hoac khi data tren UI,
     API, va DB khong khop nhau.
   - Chi query cac ban ghi lien quan truc tiep toi bug; tranh dump qua rong
     hoac doc toan bang neu khong can.
   - Xac nhan data co hop le khong truoc khi ket luan loi nam o code.

5. `CODE PATH TRACE`
   - Doc theo call chain that cua request hoac hanh vi loi:
     `router -> service/helper -> model -> template/static/task` neu lien quan.
   - Khong scan lan man file khong nam trong duong di cua data.

6. `HYPOTHESIS`
   - Truoc khi sua, bat buoc ghi mot dong:
     `suspected: <file>:<line> - <ly do>`.
   - Neu hypothesis sai sau khi test, ghi lai tai sao bi bac bo roi moi dua ra
     hypothesis moi.

7. `FIX + VERIFY`
   - Chi fix sau khi da co hypothesis ro rang.
   - Chi sua file thuoc scope bug.
   - Sau moi lan sua, bat buoc chay `python -m py_compile` cho tat ca file
     Python da sua.
   - Bat buoc chay `pytest` lien quan den `active_context`.
   - Bat buoc smoke test phu hop: endpoint that, flow UI that, hoac runtime flow
     that neu bug co tinh chat runtime.

8. `REPORT`
   - Bao lai `active_context` dang dung va log nao da doc.
   - Neu ro duoc root cause, noi ro hypothesis nao da duoc xac nhan; neu sai,
     noi ro hypothesis nao da bi bac bo.
   - Ghi ro noi da sua (`file:line` neu co the), test / smoke check da chay,
     va ket qua.
   - Neu con blocker, noi ro blocker cuoi cung va vi sao chua the ket luan.

## Nguyen tac hoi lai

- Chi hoi them user sau khi da:
  - co ket qua tu script bootstrap
  - doc log / code / test sat voi `active context`
  - co gang reproduce bang local stack neu bug co tinh chat runtime
- Neu do tin cay cua `active context` con thap, Codex nen noi ro context dang
  doan la gi roi tiep tuc kiem tra thay vi dung lai qua som.

## Mo rong co che context

- Chi tiet co che suy ra context nam trong `docs/SESSION_CONTEXT.md`.
- Neu repo co them lenh bootstrap khac, cap nhat `scripts/session_context_check.ps1`
  thay vi tao script rieng cho tung module.
