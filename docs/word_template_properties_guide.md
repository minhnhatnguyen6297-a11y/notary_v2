# Huong dan dat ten properties cho mau Word

Tai lieu nay dung de quy uoc ten bien khi ghep du lieu vao mau Word, theo kieu:

`<truong_chinh>_<thu_tu_nguoi>_<vai_tro_phu>`

Vi du:
- `ho_ten_1_chu_dat`
- `ngay_sinh_2_vo_chong`
- `so_giay_to_3_con`

## 1) Cau truc dat ten

- `truong_chinh`: ten truong du lieu (bat buoc)
- `thu_tu_nguoi`: so thu tu nguoi (bat buoc)
- `vai_tro_phu`: mo ta vai tro (khong bat buoc)

Cong thuc ngan:
- Toi thieu: `truong_chinh_thu_tu`
- Day du: `truong_chinh_thu_tu_vai_tro_phu`

## 2) Co bat buoc phai co vai tro phu khong?

Khong bat buoc.

Chi can `truong_chinh + thu_tu` la du de map, neu:
- thu tu nguoi da co nghia ro rang trong nghiep vu,
- va moi slot thu tu chi dung cho 1 nguoi duy nhat.

Nen them `vai_tro_phu` neu:
- muon de doc/de kiem soat template,
- co kha nang doi vai tro theo tung ho so,
- can tranh nham khi team sua mau.

Khuyen nghi van hanh:
- Dung day du `truong_chinh_thu_tu_vai_tro_phu` cho cac mau dung lau dai.

## 3) Danh sach truong_chinh de dung

- `ho_ten`
- `gioi_tinh`
- `ngay_sinh`
- `ngay_chet`
- `so_giay_to`
- `ngay_cap`
- `dia_chi`
- `loai_cc`
- `noi_cap_cc`
- `nhan_dia_chi`
- `ty_le_nhan`
- `co_nhan_tai_san`

## 4) Quy uoc thu tu nguoi

- `1`: chu dat (uu tien nam neu can theo mau cu)
- `2`: vo/chong chu dat
- `3`: nguoi nhan di san uu tien
- `4` tro di: cac nguoi con lai theo thu tu nghiep vu

## 5) Vi du thuc te

Ban toi thieu:
- `ho_ten_1`
- `ngay_sinh_1`
- `ho_ten_2`

Ban day du:
- `ho_ten_1_chu_dat`
- `ngay_sinh_1_chu_dat`
- `ho_ten_2_vo_chong`
- `ngay_chet_3_con`
- `ty_le_nhan_3_con`

## 6) Luu y ky thuat

- Dung chu thuong, ngan cach bang dau gach duoi `_`.
- Khong dung dau tieng Viet trong ten property.
- Khong dung khoang trang.
- Giu on dinh ten sau khi chot mau de tranh loi map.

