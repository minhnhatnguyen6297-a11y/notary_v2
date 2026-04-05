# Session context

Tai lieu nay dinh nghia cach Codex tu dong giu dung ngu canh theo session.

## Muc tieu

- Khong bat user lap lai ten chuc nang trong moi message.
- Agent tu suy ra session dang tap trung vao module nao.
- Sau khi co `active context`, agent uu tien doc dung log, dung file code, va
  dung test lien quan.

## Cach suy ra `active context`

Codex uu tien tong hop cac nguon sau:

1. Branch hien tai.
2. File dang dirty trong `git status`.
3. File user dang mo hoac vua nhac den.
4. Tu khoa xuat hien lap lai trong lich su session.

## Heuristic nen dung

- Branch:
  - tach branch theo `/`, `-`, `_`
  - bo cac token chung nhu `feature`, `fix`, `refactor`, `chore`, `bug`
  - giu lai token dac trung nhu `ocr`, `cases`, `customers`, `properties`

- File path:
  - `routers/<name>.py` -> context `<name>`
  - `templates/<name>/...` -> context `<name>`
  - `tests/test_<name>*` -> context `<name>`
  - neu khong ro, lay thu muc hoac filename co xuat hien nhieu nhat

- Lich su session:
  - neu user da mo ta "dang lam OCR", "dang sua cases", "dang xem customer"
    thi giu context do cho cac message sau

## Vong xu ly bug mac dinh

1. Chay:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\session_context_check.ps1
```

2. Doc:
   - `active context`
   - branch hien tai
   - file dang dirty
   - log duoc de xuat

3. Mo code gan nhat voi `active context`.

4. Neu sua Python:
   - `python -m py_compile` cho tat ca file da sua
   - `pytest` voi test lien quan den `active context`

5. Bao lai user:
   - dang su dung context nao
   - da doc log nao
   - da reproduce duoc chua
   - da test gi

## Khi context chua ro

- Neu co 2 context ngang nhau, Codex nen noi ro 2 ung vien dang nghi ngo va
  uu tien context sat nhat voi file user vua mo.
- Chi hoi user khi khong the phan tach bang branch, file, log, hoac session
  history.
