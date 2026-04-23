---
name: test-ocr
description: Kich hoat khi user yeu cau thuc thi test OCR, chay test OCR, debug OCR, kiem thu OCR, doi chieu OCR, OCR sai, hoac sua OCR tren case/batch anh cu the. Chi dung cho intent thuc thi va sua loi OCR that; khong dung cho giai thich ly thuyet, review kien truc, hay brainstorming. Khi match, phai tuan theo muc "Vong lap kiem thu OCR bat buoc" va relay gate OCR trong AGENTS.md truoc khi goi Codex.
---

# Test OCR

Skill nay chi la lop kich hoat va nhac rule.

- Kich hoat khi prompt co cac cue nhu `test OCR`, `chay test OCR`, `debug OCR`, `kiem thu OCR`, `doi chieu OCR`, `OCR sai`, hoac user yeu cau chay/sua OCR tren case cu the.
- Khong kich hoat cho:
  - cau hoi giai thich vi sao OCR sai o muc ly thuyet
  - review kien truc/pipeline OCR
  - brainstorming chien luoc debug/test OCR
- Khi skill nay duoc load:
  - dung `AGENTS.md`, muc `Vong lap kiem thu OCR bat buoc` lam source of truth duy nhat cho workflow
  - neu can relay sang Codex, dung them `AGENTS.md`, muc `Quy trinh Claudex - Lam viec voi Codex`, phan `Relay OCR giua Codex va Codex`
- Khong dinh nghia lai workflow chi tiet o day. Neu co mau thuan, uu tien `AGENTS.md`.
