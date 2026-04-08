# Rule Rut Gon Cho 3 Loai Van Ban

Ngay tong ket: 2026-04-07

## Nguyen tac chung

- Neu `tai_san` la `quyen su dung dat` thi ca 3 loai van ban deu dung chung 1 nguyen tac nhan dien.
- Khong uu tien cat tu cum mo dau dai nhu `Doi tuong cua Hop dong nay la ...`.
- Uu tien tim cum:
  - `quyen su dung dat`
  - hoac `quyen su dung dat va tai san gan lien voi dat`
- Sau cum nay phai co `co dia chi tai`.
- Co the xem day la anchor chinh cua block `tai_san`:
  - `quyen su dung dat ... co dia chi tai`

## Rule Lay `tai_san`

### Diem bat dau

- Bat dau tu cum `quyen su dung dat` khi phia sau co `co dia chi tai`.
- Ap dung chung cho:
  - Hop dong chuyen nhuong
  - Van ban cam ket tai san rieng
  - Van ban huy bo/sua doi/bo sung lien quan den hop dong chuyen nhuong

### Diem ket thuc

- Uu tien lay dung 1 block tai san, khong an sang doan sau.
- Dung truoc cac marker chuyen y, neu xuat hien:
  - `1.2`
  - `Dieu 2`
  - `Bang Hop dong nay`
  - `Bang van ban nay chung toi xac dinh`
  - `Hai vo chong chung toi cam doan`
  - `va duoc Cong chung vien`
- Neu la mau ngan, dung khi het phan thong tin:
  - Giay chung nhan
  - so vao so
  - ngay cap
  - cap nhat bien dong

## Theo Tung Loai Van Ban

### 1. Hop dong chuyen nhuong

- `tai_san` thuong la block day du.
- Van dung rule chung:
  - bat dau tu `quyen su dung dat ... co dia chi tai`
  - lay den het block thong tin dat/GCN

### 2. Van ban cam ket tai san rieng

- Mo ta `tai_san` ve cot loi khong khac voi hop dong chuyen nhuong.
- Neu noi dung la `quyen su dung dat` thi van dung cung rule:
  - bat dau tu `quyen su dung dat ... co dia chi tai`
  - lay den het block thong tin dat/GCN

### 3. Van ban huy bo / sua doi / bo sung

- Nhom nay nhan dien boi cac cum:
  - `huy bo`
  - `sua doi`
  - `bo sung`
- Co the xep vao nhom `cam ket - thoa thuan`.
- `tai_san` van theo cung nguyen tac nhan dien nhu tren, chi khac la doan lay thuong ngan hon, mang tinh tham chieu.
- Rule thuc te:
  - tim cum `quyen su dung dat ... co dia chi tai`
  - lay den het phan thong tin GCN / ngay cap / cap nhat bien dong

## Ket Luan Ngan

- Rule cot loi khong nen tach qua phuc tap theo 3 loai van ban.
- Neu `tai_san` la `quyen su dung dat` thi dung 1 rule chung:
  - start = `quyen su dung dat ... co dia chi tai`
  - end = het block thong tin dat/GCN, dung truoc doan noi y khac
- Khac nhau chu yeu o do dai block:
  - chuyen nhuong: day du hon
  - cam ket: gan nhu giong chuyen nhuong
  - huy bo/sua doi/bo sung: ngan hon, mang tinh tham chieu
