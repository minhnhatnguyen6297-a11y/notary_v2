"""
Module quản lý Người (Customer).
Bao gồm: CRUD, upload hàng loạt từ Excel, tải file mẫu.
"""

import io
from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from datetime import date, datetime

from database import get_db
from models import Customer

router = APIRouter()
templates = Jinja2Templates(directory="templates")

EXCEL_COLUMNS = ["ho_ten","gioi_tinh","ngay_sinh","ngay_chet","so_giay_to","ngay_cap","dia_chi"]


def parse_date(s) -> Optional[date]:
    if s is None:
        return None
    if isinstance(s, date):
        return s
    if isinstance(s, datetime):
        return s.date()
    s = str(s).strip()
    if not s or s.lower() in ("nan", "none", ""):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


@router.get("/")
def list_customers(request: Request, db: Session = Depends(get_db), q: str = ""):
    query = db.query(Customer)
    if q:
        query = query.filter(or_(Customer.ho_ten.contains(q), Customer.so_giay_to.contains(q), Customer.dia_chi.contains(q)))
    customers = query.order_by(Customer.ho_ten).all()
    return templates.TemplateResponse("customers/list.html", {"request": request, "customers": customers, "q": q})


@router.get("/download-template")
def download_template():
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Danh sách người"

    header_fill = PatternFill("solid", fgColor="0F2443")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = [
        ("ho_ten",     "ho_ten\n(Họ và tên - BẮT BUỘC)",                  32),
        ("gioi_tinh",  "gioi_tinh\n(Nam/Nữ - BẮT BUỘC)",                  18),
        ("ngay_sinh",  "ngay_sinh\n(Ngày sinh - BẮT BUỘC)\nVD: 01/01/1970", 24),
        ("ngay_chet",  "ngay_chet\n(Ngày mất)\nĐể trống nếu còn sống",    24),
        ("so_giay_to", "so_giay_to\n(Số CCCD/Khai tử - BẮT BUỘC)",        26),
        ("ngay_cap",   "ngay_cap\n(Ngày cấp - BẮT BUỘC)\nVD: 15/03/2021", 24),
        ("dia_chi",    "dia_chi\n(Địa chỉ thường trú - BẮT BUỘC)",         44),
    ]

    for col_idx, (field, label, width) in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
        from openpyxl.utils import get_column_letter
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.row_dimensions[1].height = 52

    ex1 = ["NGUYỄN VĂN A","Nam","01/01/1970","","034056789012","15/03/2021","Xóm 5, Yên Đồng, Ý Yên, Nam Định"]
    ex2 = ["TRẦN THỊ B","Nữ","20/05/1945","10/01/2023","Giấy khai tử số 001/2023","10/01/2023","Xóm 8, Yên Đồng, Ý Yên, Nam Định"]

    ex_fill = PatternFill("solid", fgColor="EEF3FF")
    for col_idx, val in enumerate(ex1, start=1):
        cell = ws.cell(row=2, column=col_idx, value=val)
        cell.fill = ex_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="left", vertical="center")

    for col_idx, val in enumerate(ex2, start=1):
        cell = ws.cell(row=3, column=col_idx, value=val)
        cell.border = border
        cell.alignment = Alignment(horizontal="left", vertical="center")

    ws.cell(row=5, column=1, value="Lưu ý quan trọng:").font = Font(bold=True, color="CC0000")
    ws.cell(row=6, column=1, value="1. Các cột BẮT BUỘC không được để trống").font = Font(italic=True, color="666666")
    ws.cell(row=7, column=1, value="2. Ngày nhập theo định dạng DD/MM/YYYY hoặc YYYY-MM-DD").font = Font(italic=True, color="666666")
    ws.cell(row=8, column=1, value="3. Số giấy tờ phải duy nhất — nếu trùng hệ thống sẽ bỏ qua dòng đó").font = Font(italic=True, color="666666")
    ws.cell(row=9, column=1, value="4. Xóa 2 dòng ví dụ (dòng 2, 3) trước khi nhập dữ liệu thật").font = Font(italic=True, color="FF6600")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=mau_nhap_nguoi.xlsx"}
    )


@router.post("/upload-excel")
async def upload_excel(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    import openpyxl

    if not file.filename.endswith((".xlsx", ".xls")):
        return templates.TemplateResponse("customers/upload_result.html", {
            "request": request, "error_global": "Chỉ chấp nhận file .xlsx",
            "results": [], "added": 0, "skipped": 0, "errors": 0, "total": 0
        })

    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception as e:
        return templates.TemplateResponse("customers/upload_result.html", {
            "request": request, "error_global": f"Không thể mở file: {e}",
            "results": [], "added": 0, "skipped": 0, "errors": 0, "total": 0
        })

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    if len(rows) < 2:
        return templates.TemplateResponse("customers/upload_result.html", {
            "request": request, "error_global": "File không có dữ liệu.",
            "results": [], "added": 0, "skipped": 0, "errors": 0, "total": 0
        })

    # Nhận diện cột theo dòng đầu — chấp nhận cả tên cột tiếng Việt lẫn tên field
    raw_headers = [str(h).strip() if h else "" for h in rows[0]]

    def find_col(keywords):
        for kw in keywords:
            for i, h in enumerate(raw_headers):
                if kw.lower() in h.lower():
                    return i
        return None

    col = {
        "ho_ten":     find_col(["ho_ten", "họ", "tên", "full_name"]),
        "gioi_tinh":  find_col(["gioi_tinh", "giới", "gender"]),
        "ngay_sinh":  find_col(["ngay_sinh", "ngày sinh", "sinh", "birth"]),
        "ngay_chet":  find_col(["ngay_chet", "ngày mất", "mất", "death", "chết"]),
        "so_giay_to": find_col(["so_giay_to", "cccd", "giấy tờ", "id_number", "khai tử", "so_cccd"]),
        "ngay_cap":   find_col(["ngay_cap", "ngày cấp", "cấp", "issue"]),
        "dia_chi":    find_col(["dia_chi", "địa chỉ", "address"]),
    }

    missing = [f for f in ["ho_ten","gioi_tinh","ngay_sinh","so_giay_to","ngay_cap","dia_chi"] if col[f] is None]
    if missing:
        return templates.TemplateResponse("customers/upload_result.html", {
            "request": request,
            "error_global": f"Không nhận diện được cột: {', '.join(missing)}. Hãy dùng file mẫu.",
            "results": [], "added": 0, "skipped": 0, "errors": 0, "total": 0
        })

    results = []
    added = skipped = errors = 0

    for row_num, row in enumerate(rows[1:], start=2):
        def get(field):
            idx = col.get(field)
            if idx is None or idx >= len(row):
                return None
            v = row[idx]
            return str(v).strip() if v is not None else None

        ho_ten = get("ho_ten")
        so_gt  = get("so_giay_to")

        if not ho_ten and not so_gt:
            continue  # Dòng trống

        row_errors = []
        if not ho_ten:       row_errors.append("Thiếu họ tên")
        if not so_gt:        row_errors.append("Thiếu số giấy tờ")
        if not get("dia_chi"): row_errors.append("Thiếu địa chỉ")

        ngay_sinh = parse_date(get("ngay_sinh"))
        ngay_cap  = parse_date(get("ngay_cap"))
        ngay_chet = parse_date(get("ngay_chet"))

        if not ngay_sinh: row_errors.append("Ngày sinh không hợp lệ")
        if not ngay_cap:  row_errors.append("Ngày cấp không hợp lệ")

        if row_errors:
            results.append({"row": row_num, "name": ho_ten or "?", "status": "error", "message": " | ".join(row_errors)})
            errors += 1
            continue

        # Chuẩn hoá giới tính
        gt_raw = get("gioi_tinh") or ""
        gioi_tinh = "Nữ" if "n" in gt_raw.lower() and ("ữ" in gt_raw or "u" in gt_raw.lower()) else "Nam"

        # Kiểm tra trùng
        if db.query(Customer).filter(Customer.so_giay_to == so_gt).first():
            results.append({"row": row_num, "name": ho_ten, "status": "skip", "message": f"Số '{so_gt}' đã tồn tại → bỏ qua"})
            skipped += 1
            continue

        try:
            c = Customer(ho_ten=ho_ten.upper(), gioi_tinh=gioi_tinh,
                         ngay_sinh=ngay_sinh, ngay_chet=ngay_chet,
                         so_giay_to=so_gt, ngay_cap=ngay_cap, dia_chi=get("dia_chi"))
            db.add(c); db.commit()
            results.append({"row": row_num, "name": ho_ten, "status": "ok", "message": "Thêm thành công"})
            added += 1
        except Exception as e:
            db.rollback()
            results.append({"row": row_num, "name": ho_ten, "status": "error", "message": f"Lỗi: {e}"})
            errors += 1

    return templates.TemplateResponse("customers/upload_result.html", {
        "request": request, "error_global": None,
        "results": results, "added": added, "skipped": skipped, "errors": errors,
        "total": added + skipped + errors
    })


@router.get("/create")
def create_form(request: Request):
    return templates.TemplateResponse("customers/form.html", {"request": request, "obj": None, "errors": []})


@router.post("/create")
def create(
    request: Request,
    ho_ten: str = Form(...), gioi_tinh: str = Form(...),
    ngay_sinh: str = Form(...), ngay_chet: Optional[str] = Form(None),
    so_giay_to: str = Form(...), ngay_cap: str = Form(...),
    dia_chi: str = Form(...),
    db: Session = Depends(get_db)
):
    errors = []
    if db.query(Customer).filter(Customer.so_giay_to == so_giay_to.strip()).first():
        errors.append(f"Số giấy tờ '{so_giay_to}' đã tồn tại!")
    if errors:
        return templates.TemplateResponse("customers/form.html", {"request": request, "obj": None, "errors": errors})
    c = Customer(ho_ten=ho_ten.strip(), gioi_tinh=gioi_tinh, ngay_sinh=parse_date(ngay_sinh),
                 ngay_chet=parse_date(ngay_chet), so_giay_to=so_giay_to.strip(),
                 ngay_cap=parse_date(ngay_cap), dia_chi=dia_chi.strip())
    db.add(c); db.commit()
    return RedirectResponse("/customers", status_code=302)


@router.get("/{cid}")
def detail(cid: int, request: Request, db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == cid).first()
    if not c: raise HTTPException(404)
    return templates.TemplateResponse("customers/detail.html", {"request": request, "obj": c})


@router.get("/{cid}/edit")
def edit_form(cid: int, request: Request, db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == cid).first()
    if not c: raise HTTPException(404)
    return templates.TemplateResponse("customers/form.html", {"request": request, "obj": c, "errors": []})


@router.post("/{cid}/edit")
def edit(
    cid: int, request: Request,
    ho_ten: str = Form(...), gioi_tinh: str = Form(...),
    ngay_sinh: str = Form(...), ngay_chet: Optional[str] = Form(None),
    so_giay_to: str = Form(...), ngay_cap: str = Form(...),
    dia_chi: str = Form(...),
    db: Session = Depends(get_db)
):
    c = db.query(Customer).filter(Customer.id == cid).first()
    if not c: raise HTTPException(404)
    errors = []
    dup = db.query(Customer).filter(Customer.so_giay_to == so_giay_to.strip(), Customer.id != cid).first()
    if dup: errors.append(f"Số giấy tờ '{so_giay_to}' đã tồn tại!")
    if errors:
        return templates.TemplateResponse("customers/form.html", {"request": request, "obj": c, "errors": errors})
    c.ho_ten = ho_ten.strip(); c.gioi_tinh = gioi_tinh
    c.ngay_sinh = parse_date(ngay_sinh); c.ngay_chet = parse_date(ngay_chet)
    c.so_giay_to = so_giay_to.strip(); c.ngay_cap = parse_date(ngay_cap)
    c.dia_chi = dia_chi.strip()
    db.commit()
    return RedirectResponse(f"/customers/{cid}", status_code=302)


@router.post("/{cid}/delete")
def delete(cid: int, db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == cid).first()
    if c: db.delete(c); db.commit()
    return RedirectResponse("/customers", status_code=302)
