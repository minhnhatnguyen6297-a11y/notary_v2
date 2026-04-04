# CODE COMMENT POLICY

Muc tieu cua policy nay la bien comment thanh "tin nhan de lai cho dev sau".
Comment khong duoc chi nhac lai code dang lam gi; no phai giai thich vi sao block do ton tai, dang bao ve rule nao, va neu sua sai thi vo o dau.

## 1) Nguyen tac cot loi

- Viet comment ngay tren block logic kho, khong day xuong cuoi ham hoac gom thanh mot doan docstring xa ngu canh.
- Uu tien 3 thu quan trong nhat: `WHY`, `RISK`, `CHANGE RULE`.
- Comment ngan, that, co tinh cam ket. Neu khong chac, ghi ro gia dinh thay vi viet mo ho.
- Comment phai duoc cap nhat cung luc voi code. Comment cu ma sai nguy hiem hon khong co comment.
- Neu mot block qua kho de giai thich trong 3-5 dong, uu tien tach ham/trich xuat logic truoc.

## 2) Bat buoc phai co comment

Bat buoc dat comment cho cac truong hop sau:

- Logic nghiep vu kho hieu hoac co quy tac phap ly/noi bo.
- Fallback, retry, merge, state transition, hoac thu tu uu tien anh huong ket qua.
- Magic number, threshold, regex, crop ratio, score gate, hard-code co y do.
- Workaround cho framework, OCR engine, browser, file mau Word, hoac du lieu ban.
- Block "tam thoi" nhung de rat de bi giu lai qua lau.
- Bat ky doan nao ma dev moi doc 2 phut van khong biet "tai sao lai lam vay".

## 3) Khong can comment

Khong bat buoc comment cho:

- Mapping CRUD don gian, ten bien/ten ham da tu giai thich ro.
- Vong lap, if/else, assign co nghia ro rang.
- Code boilerplate cua framework neu khong co bien tau nghiep vu.
- Comment kieu "gan gia tri vao bien", "goi ham de xu ly", "tang i len 1".

## 4) Format chuan

Dung format day du nay cho block quan trong:

```python
# [WHY] Vi sao can block nay?
# [CONTEXT] Dang bao ve rule, edge case, hay nghiep vu nao?
# [INPUT/OUTPUT] Dau vao/dau ra quan trong neu nhin code khong ro.
# [RISK] Sua sai thi se vo ket qua nao?
# [CHANGE RULE] Muon doi logic thi phai kiem tra/test gi truoc?
```

Neu block ngan hon, co the dung ban rut gon:

```python
# [WHY] ...
# [RISK] ...
# [CHANGE RULE] ...
```

## 5) Vi du gan voi notary_v2

### Python - OCR / merge / fallback

```python
# [WHY] Uu tien QR truoc OCR text de lay khoa chinh on dinh nhat cho cap mat truoc/mat sau.
# [CONTEXT] Anh CCCD moi de bi loi dau va nham ky tu khi chi dua vao OCR text.
# [RISK] Doi thu tu uu tien co the ghep sai 2 mat cua 2 nguoi khac nhau.
# [CHANGE RULE] Neu sua rule nay, bat buoc chay lai bo regression anh CCCD va kiem tra warning unpaired.
primary_key = qr_value or detected_id or mrz_id
```

### Python - rule nghiep vu route/service

```python
# [WHY] Khong cho dua `ngay_het_han` vao participant nghiep vu vi field nay chi dung de tham khao OCR.
# [CONTEXT] UI va mau van ban dang su dung `ngay_cap` + `so_giay_to` la nguon hop le.
# [RISK] Neu ghi nham vao du lieu chinh, ho so co the hien thong tin khong duoc phep su dung.
# [CHANGE RULE] Neu muon luu field nay, phai cap nhat schema, form, template Word va rule review nghiep vu.
payload.pop("ngay_het_han", None)
```

### JavaScript - worker / browser fallback

```javascript
// [WHY] Thu 4 goc xoay truoc khi ket luan QR fail vi anh chup tu dien thoai thuong bi le huong.
// [CONTEXT] jsQR khong tu xoay anh; worker phai tu tao bien the de giam false negative.
// [RISK] Bo buoc nay se lam tang so ca roi xuong OCR/server rescue.
// [CHANGE RULE] Neu bo hoac giam so goc, can do lai ty le doc QR thanh cong tren anh thuc te.
for (const angle of [0, 90, 180, 270]) {
  ...
}
```

### Jinja / HTML - dieu kien hien thi

```jinja2
{# [WHY] Chi hien canh bao nay khi tao moi de nhac nguoi dung nhap tung nguoi mot. #}
{# [RISK] Neu hien o che do edit, user de hieu nham la dang tao nguoi moi thay vi sua du lieu cu. #}
{% if not obj %}
  ...
{% endif %}
```

## 6) Quy tac viet comment de khong thanh "comment rac"

- Comment phai tra loi cau hoi "vi sao" nhanh hon "lam gi".
- Moi comment nen co 1 y chinh; tranh viet doan van dai 10 dong.
- Ghi ro ten contract, API, file mau, test, bien moi truong neu block phu thuoc vao chung.
- Neu block la workaround, ghi ro dieu kien de sau nay xoa duoc.
- Neu co ticket/issue noi bo, dat ma tham chieu ngay trong comment.

## 7) Cach ap dung trong repo nay

- Code moi: moi block logic khong tu giai thich duoc phai co comment truoc khi merge.
- Code legacy: neu da cham vao block kho hieu, backfill comment cho chinh block vua sua.
- Review: reviewer co quyen yeu cau bo sung comment neu thay logic quan trong khong co `WHY`.
- Refactor: khi xoa hoac doi rule, cap nhat comment truoc hoac cung luc voi code.

## 8) Checklist review nhanh

- Nguoi moi doc block trong 2 phut co biet vi sao no ton tai khong?
- Neu doi mot threshold/regex, co comment giai thich nguon goc va rui ro khong?
- Neu day la fallback/workaround, co ghi ro khi nao duoc phep bo di khong?
- Neu logic lien quan OCR/ho so/mau Word, co `CHANGE RULE` de nguoi sau biet can test gi khong?
