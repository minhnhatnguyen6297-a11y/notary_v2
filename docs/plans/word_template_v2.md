# Word Template V2 - Placeholder Catalog va Resolver

Cap nhat: 03/07/2026

## Muc tieu

Tao he thong placeholder Word de nguoi dung cong chung co the tu chinh file `.docx`
bang cac placeholder co san, con logic nghiep vu van khoa trong code.
Khi can placeholder moi, user mo ta y nghia va dev/agent cap nhat catalog, resolver va test.

## Quyet dinh da chot

| # | Quyet dinh |
|---|---|
| 1 | Catalog chinh la `word_templates/placeholder_mapping.md`. |
| 2 | Placeholder public dung tieng Viet co dau trong dau `[]`, vi du `[Họ tên chủ đất]`. |
| 3 | Placeholder cu nhu `[Tên 1]`, `[CCCD 1]` duoc giu lam alias tuong thich. |
| 4 | Khong cho user tu them placeholder trong app. Placeholder moi phai qua dev/agent. |
| 5 | V1 chi ho tro truong le va doan du lieu dung san. Chua lam block engine `if/for`. |
| 6 | Code khong tu doan nghiep vu tu ten placeholder moi. Resolver phai khai bao ro. |
| 7 | Template snake_case/reference la noi bo, khong hien trong danh sach export cho user. |
| 8 | Logic Word export nam trong `services/word_engine.py`; router chi dieu phoi request/response. |

## Pham vi V1

- Nhom ho so: loai van ban, ngay lap, noi niem yet, ghi chu.
- Nhom tai san: serial, so vao so, thua/to, dia chi, dien tich, loai dat, loai so,
  hinh thuc su dung, thoi han, nguon goc, ngay/co quan cap so.
- Nhom nguoi: ho ten, gioi tinh, ngay/nam sinh, ngay/nam chet, so/loai giay to,
  ngay/noi cap, dia chi, nhan dia chi, vai tro, hang thua ke, trang thai nhan/tu choi, ty le.
- Nhom vai tro diagram public: `chu_dat`, `vo_chong`, `cha`, `me`, `cha_vo_chong`,
  `me_vo_chong`, `con`, `anh_chi_em`, `chau`, `vo_chong_nhanh`.
- Doan dung san chi liet ke du lieu: danh sach nguoi nhan, tu choi, thua ke,
  tom tat quan he, tom tat phan chia.

## Huong phat trien sau

- Sau khi catalog V1 on dinh moi tinh den block engine cho lap/bo doan Word.
- Block engine neu lam phai backward compatible: template khong co block marker van thay placeholder binh thuong.
- Moi thay doi nghiep vu trong doan phap ly phai co case mau va user chot truoc.

## Kiem thu

- Test resolver trong `tests/test_word_engine.py`.
- Kiem tra thay placeholder trong paragraph, table, header/footer va split runs.
- Kiem tra alias cu khong hong template hien tai.
- Kiem tra template reference/snake_case khong hien trong danh sach builtin export.
- Chay `.\verify.bat` truoc khi ban giao.
