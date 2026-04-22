# Quy tắc OCR Tài sản (Sổ đỏ / Sổ hồng)

> File này mô tả logic regex + scoring hiện tại trong `routers/ocr_ai.py`.
> Khi muốn thay đổi rule, sửa file này trước rồi giao Codex implement theo.
> Cập nhật: 22/04/2026

---

## Các field được extract

| Field | Mô tả |
|---|---|
| `so_serial` | Số phát hành (in trên phôi sổ) |
| `so_vao_so` | Số vào sổ GCN |
| `so_thua_dat` | Số thửa đất |
| `so_to_ban_do` | Số tờ bản đồ |
| `dia_chi` | Địa chỉ thửa đất |
| `chu_su_dung` | Chủ sử dụng đất *(additive, chưa persist DB)* |
| `loai_so` | Loại sổ (cũ / hồng / 2024) |
| `hinh_thuc_su_dung` | Hình thức sử dụng |
| `nguon_goc` | Nguồn gốc sử dụng đất |
| `ngay_cap` | Ngày cấp GCN |
| `co_quan_cap` | Cơ quan cấp GCN |
| `loai_dat` | Loại đất (mã hoặc tên) |
| `thoi_han` | Thời hạn sử dụng đất |
| `dien_tich` | Diện tích (m²) |

---

## Phân loại loại sổ (`loai_so`)

```
Sổ đỏ cũ  : "Giay chung nhan quyen su dung dat"
Sổ hồng đầy đủ : "Giay chung nhan quyen su dung dat, quyen so huu nha o va tai san khac gan lien voi dat"
Sổ hồng ngắn  : "Giay chung nhan quyen su dung dat, quyen so huu tai san gan lien voi dat"
```

---

## Nhận diện tài liệu là sổ đỏ (`_looks_like_property_doc`)

Tài liệu được nhận là sổ đỏ nếu **một trong** các điều kiện sau:
- Tiêu đề chứa "giay chung nhan" hoặc "gcn"
- Có label "so vao so" / "so cap gcn"
- Có label "thua dat" hoặc "thua so"
- Có label "to ban do" hoặc "to so"
- Parse được serial theo pattern `[A-Z]{2}\d{6,8}`

**Classifier fallback (Codex thêm — cần xem xét):**
Nếu không nhận được từ tiêu đề nhưng parse được ≥ 2 trong 8 strong fields
(`so_serial`, `so_vao_so`, `so_thua_dat`, `so_to_ban_do`, `dien_tich`, `dia_chi`, `loai_dat`, `chu_su_dung`)
→ vẫn nhận là sổ đỏ.
*Chưa có negative test — cần xác nhận có muốn giữ không.*

---

## `so_serial` — Số phát hành

**Pattern chính:** `[A-Z]{2}\d{6,8}` → ví dụ `BM 1451111`, `AA 12467547`

**Label nhận diện (có label → score cao hơn):**
- `"so phat hanh"`, `"so serial"`, `"serial"`, `"so seri"`, `"ma phoi"`

**Scoring:**
| Điều kiện | Điểm |
|---|---|
| Match `[A-Z]{2}\d{6,8}` | +10 |
| Match `[A-Z]\d{6,8}` (chữ đơn) | +7 |
| Match `[A-Z]{1,4}\d{4,12}(/\d{1,8})?` | +3 |
| Có label serial | +6 |
| Context serial (dòng bắt đầu bằng "so") | +4 |
| Cả dòng chỉ là giá trị này | +5 |
| Bắt đầu bằng `VP`, `QD`, `UB` mà không có label | -8 |
| Dòng là label khác (thua dat, to ban do...) | -5 |
| Dòng chứa `"van phong dang ky"`, `"ngay "`, `"thang "` | -3 |
| Có dấu `/` trong code | -2 |

**Loại trừ so với `so_vao_so`:** nếu candidate trùng với `so_vao_so` → trừ 20 điểm.

---

## `so_vao_so` — Số vào sổ GCN

**Label nhận diện:**
- Trực tiếp: `"so vao so"`, `"so vao so cap gcn"`, `"so vao so cap giay chung nhan"`, `"vao so cap gcn"`
- Noise OCR: `"so vach so cap gcn"`, `"so van so cap gcn"`, `"so voch so cap gcn"` (và các biến thể)

**Pattern code:** `[A-Z]{1,4}\s*\d{3,12}(?:/\d{1,8})?`

**Ưu tiên:** lấy giá trị sau `:` trên cùng dòng → nếu không có thì lấy 1-2 dòng kế tiếp.

---

## `so_thua_dat` — Số thửa

**Regex inline:** `\bthua\s*(?:dat|so)?\b[^0-9]{0,24}(\d{1,6})`

**Label fallback:** `"thua dat"`, `"thua so"` → lấy số đầu tiên trên dòng kế tiếp.

---

## `so_to_ban_do` — Số tờ bản đồ

**Regex inline:** `\bto\s*(?:ban\s*do|so)\b[^0-9]{0,24}(\d{1,6})`

**Label fallback:** `"to ban do"`, `"to so"` → lấy số đầu tiên trên dòng kế tiếp.

*Lưu ý: hỗ trợ dòng gộp kiểu `"Thửa đất số: 342; tờ bản đồ số: 22"` bằng split theo `;`.*

---

## `dien_tich` — Diện tích

**Label:** `"dien tich"`

**Regex:** `(\d+(?:[.,]\d+)?)(?:\s*(?:m2|m²|m\^2|met vuong))?`

**Normalize dấu `,` và `.`:**
- Nếu có cả hai: dấu nào đứng sau là dấu thập phân
- Nếu chỉ có `,`: chuyển thành `.`

---

## `dia_chi` — Địa chỉ thửa đất

**Label:** `"dia chi"`, `"dia chi thua dat"`

**Thu thập:** lấy giá trị sau `:` + tối đa 3 dòng kế tiếp.

**Stop conditions (dừng thu thập khi gặp):**
- Label khác: `"so thua"`, `"to ban do"`, `"dien tich"`, `"loai dat"`, `"thoi han"`, `"nguon goc"`, `"chu su dung"`, `"ngay cap"`, `"co quan cap"`, `"so vao so"`
- Dòng footer date: pattern `^[địa danh,]* ngay \d` → ví dụ `"Nam Dinh, ngay 10/07/2023"` ← *phân biệt với `"tinh Nam Dinh"` (không stop)*
- Dòng chứa: `"van phong dang ky"`, `"uy ban nhan dan"`, `"so tai nguyen"`

**Scoring địa chỉ (chọn candidate tốt nhất nếu có nhiều):**
| Điều kiện | Điểm |
|---|---|
| Mỗi dấu `,` | +1 |
| ≥ 4 từ | +2 |
| Chứa từ địa lý (`thon`, `xa`, `phuong`, `huyen`, `tinh`...) | +1/từ |
| Chứa `"van phong dang ky"` / `"uy ban nhan dan"` / `"ngay "` / `"thang "` | -8 |

---

## `chu_su_dung` — Chủ sử dụng đất

*(Field mới, Codex thêm — chưa persist DB, chỉ trả về trong response OCR)*

**Label:** `"chu su dung"`, `"nguoi su dung dat"`, `"ho ten"` (và biến thể)

**Scoring:**
- Cộng điểm: chứa tên người (chữ hoa, có dấu tiếng Việt, độ dài hợp lý)
- Trừ điểm: chứa tên cơ quan, số, ký tự lạ

---

## `ngay_cap` — Ngày cấp GCN

**Format nhận:** `DD/MM/YYYY` hoặc `D/M/YYYY`

**Merge rule (khi có 2 ảnh):**
1. Chỉ xét candidate parse được `DD/MM/YYYY` đầy đủ
2. Parse thành ngày hợp lệ trong khoảng `1900-01-01` → hôm nay
3. Trong các candidate hợp lệ: ưu tiên ngày **mới hơn**
4. Nếu hòa: fallback về scoring chung

---

## `co_quan_cap` — Cơ quan cấp GCN

**Merge rule (khi có 2 ảnh):**
1. Ưu tiên candidate có marker mạnh: `UBND`, `SO TAI NGUYEN`, `VAN PHONG DANG KY`, `CHI NHANH`
2. Ưu tiên authority score cao hơn
3. Ưu tiên ngắn + sạch hơn
4. Fallback về scoring chung

---

## `loai_dat` — Loại đất

**Mã loại đất được nhận:**
`ONT`, `ODT`, `CLN`, `NTS`, `LUC`, `BHK`, `SKC`, `TMD`, `DV`, `DGT`, `DKV`, `DHT`

**Tên đầy đủ → mã:**
- `"dat o tai nong thon"` → `ONT`
- `"dat o tai do thi"` → `ODT`
- *(và các tên khác trong `_LAND_NAME_TO_CODE`)*

---

## Merge front/back (`_merge_property_pair`)

- Mỗi ảnh được parse **độc lập**
- Merge theo field, không phụ thuộc thứ tự upload
- Ưu tiên mặc định: `so_serial`, `loai_so` lấy từ front; `so_vao_so`, `ngay_cap`, `co_quan_cap` lấy từ back — nhưng nếu một bên trống thì lấy bên còn lại
- `land_rows`: merge row-level, dedupe theo thửa, recompute `dien_tich`/`loai_dat`/`thoi_han`
- Footer date rescue: **TẮT** trong pair flow (flag nội bộ `enable_footer_date_rescue=False`)

---

## Những gì KHÔNG làm

- Không sửa OCR engine (Qwen, RapidOCR, VietOCR)
- Không đổi tên endpoint, Celery task, DB schema
- `chu_su_dung` chưa persist vào DB / form fill
- `text_lines` và `footer_date_rescue` KHÔNG xuất hiện trong API response (đang cần revert)
