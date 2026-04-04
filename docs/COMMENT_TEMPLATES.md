# COMMENT TEMPLATES

Tai lieu nay la bo mau copy-paste nhanh cho Python, JavaScript, va Jinja/HTML.
Dung khi them logic moi hoac khi backfill comment cho block cu kho hieu.

## 1) Python - block nghiep vu chinh

```python
# [WHY] Vi sao block nay ton tai?
# [CONTEXT] Rule nghiep vu / edge case / contract nao dang duoc bao ve?
# [INPUT/OUTPUT] Dau vao-dau ra nao dev sau can nhin ngay?
# [RISK] Sua sai thi loi se lan ra dau?
# [CHANGE RULE] Muon doi logic thi phai test/manh ghep nao truoc?
```

## 2) Python - magic number / threshold / regex

```python
# [WHY] `0.20` la nguong toi thieu de MRZ score con du tin cay tren anh mo/chup lech.
# [RISK] Ha nguong qua thap se tang false positive, ghep sai mat truoc-mat sau.
# [CHANGE RULE] Neu doi threshold, phai so sanh lai precision/recall tren bo anh regression.
LOCAL_OCR_TRIAGE_MRZ_MIN_SCORE = 0.20
```

```python
# [WHY] Regex nay chi lay CCCD 12 so sau prefix `IDVNM` de tranh an nham dong MRZ nhiu.
# [RISK] Sua regex ma khong test co the lam rot ID hop le hoac nhat nham chuoi khac.
# [CHANGE RULE] Khi doi regex, test ca mat truoc, mat sau, va anh blur nhe.
match = re.search(r"IDVNM\\d{10}(\\d{12})", text)
```

## 3) Python - fallback / workaround

```python
# [WHY] Wide fallback chi chay khi triage that bai de uu tien toc do cho case binh thuong.
# [CONTEXT] OCR local dang toi uu cho Windows CPU; fallback rong rat ton thoi gian.
# [RISK] Chay fallback som hon co the lam tang latency cho toan bo batch.
# [CHANGE RULE] Neu muon doi thu tu fallback, do lai timing va warning rate truoc khi merge.
if triage_state == TRIAGE_STATE_UNKNOWN:
    ...
```

## 4) JavaScript - browser / UX / worker

```javascript
// [WHY] Giu worker nay o client de giam round-trip len server cho nhung QR doc duoc ngay.
// [CONTEXT] Frontend co the decode truoc, backend chi rescue khi client fail.
// [RISK] Dua het len server se tang do tre upload va tao them tai cho worker OCR.
// [CHANGE RULE] Neu doi vi tri decode, can do lai thoi gian upload va ti le `client_qr_failed`.
```

```javascript
// [WHY] Contrast duoc day cao hon ban goc vi QR mo tren anh chup den vang rat kho bat.
// [RISK] Tang qua tay co the mat chi tiet va lam jsQR fail voi anh sang manh.
// [CHANGE RULE] Neu doi gain/bias, test lai tren tap anh toi, anh loe sang, va anh chup xa.
const highContrast = applyLinearContrast(gray, 1.45, -18);
```

## 5) Jinja / HTML - dieu kien giao dien

```jinja2
{# [WHY] Mac dinh lay gia tri tu `form` truoc `obj` de giu input nguoi dung sau lan submit loi. #}
{# [RISK] Neu dao thu tu uu tien, user se mat du lieu vua nhap va kho sua loi validation. #}
value="{{ form_value if form_value else (obj.field if obj else '') }}"
```

```jinja2
{# [WHY] Canh bao nay chi danh cho luong tao moi; che do edit da co ngu canh du lieu san. #}
{# [CHANGE RULE] Neu doi dieu kien hien thi, kiem tra ca create va edit de tranh thong diep sai ngu canh. #}
{% if not obj %}
  ...
{% endif %}
```

## 6) Ban rut gon cho block nho

### Python

```python
# [WHY] ...
# [RISK] ...
```

### JavaScript

```javascript
// [WHY] ...
// [RISK] ...
```

### Jinja

```jinja2
{# [WHY] ... #}
{# [RISK] ... #}
```

## 7) Mau commit/PR khi bo sung comment

Dung khi PR chu yeu de lam ro logic ma khong doi hanh vi:

```text
docs(code-comments): backfill WHY/RISK notes for OCR fallback and form retention rules
```

## 8) Nho nhanh truoc khi merge

- Comment co giai thich "vi sao" khong?
- Comment co noi ro rui ro neu sua sai khong?
- Comment co chi ra test, contract, hoac bo du lieu can kiem tra lai khong?
- Comment co sat ngay block logic ma no mo ta khong?
