from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime
import io

from database import get_db
from models import InheritanceCase, Customer, Property, InheritanceParticipant

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
def list_cases(request: Request, db: Session = Depends(get_db), q: str = ""):
    cases = db.query(InheritanceCase).order_by(InheritanceCase.id.desc()).all()
    if q:
        cases = [c for c in cases if q.lower() in c.nguoi_chet.ho_ten.lower()]
    return templates.TemplateResponse("cases/list.html", {"request": request, "cases": cases, "q": q})


@router.get("/create")
def create_form(request: Request, db: Session = Depends(get_db)):
    all_customers = db.query(Customer).order_by(Customer.ho_ten).all()
    # Người chết = có ngày chết
    deceased = [c for c in all_customers if c.ngay_chet is not None]
    properties = db.query(Property).order_by(Property.id.desc()).all()
    return templates.TemplateResponse("cases/form.html", {
        "request": request, "obj": None,
        "deceased": deceased, "properties": properties, "errors": []
    })


@router.post("/create")
def create(
    request: Request,
    nguoi_chet_id: int = Form(...),
    tai_san_id: int = Form(...),
    ngay_lap_ho_so: str = Form(...),
    loai_van_ban: str = Form("khai_nhan"),
    ghi_chu: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    c = InheritanceCase(
        nguoi_chet_id=nguoi_chet_id, tai_san_id=tai_san_id,
        ngay_lap_ho_so=datetime.strptime(ngay_lap_ho_so, "%Y-%m-%d").date(),
        loai_van_ban=loai_van_ban, ghi_chu=ghi_chu or None
    )
    db.add(c); db.commit(); db.refresh(c)
    return RedirectResponse(f"/cases/{c.id}", status_code=302)


@router.get("/{cid}")
def detail(cid: int, request: Request, db: Session = Depends(get_db)):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if not case: raise HTTPException(404)
    all_customers = db.query(Customer).order_by(Customer.ho_ten).all()
    participant_ids = {p.customer_id for p in case.participants}
    available = [c for c in all_customers if c.id not in participant_ids and c.id != case.nguoi_chet_id]
    return templates.TemplateResponse("cases/detail.html", {
        "request": request, "case": case, "available": available,
        "vai_tro_options": ["Vợ/Chồng", "Con", "Cha/Mẹ", "Anh/Chị/Em"]
    })


@router.get("/{cid}/edit")
def edit_form(cid: int, request: Request, db: Session = Depends(get_db)):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if not case: raise HTTPException(404)
    if case.is_locked:
        return RedirectResponse(f"/cases/{cid}", status_code=302)
    all_customers = db.query(Customer).order_by(Customer.ho_ten).all()
    deceased = [c for c in all_customers if c.ngay_chet is not None]
    properties = db.query(Property).order_by(Property.id.desc()).all()
    return templates.TemplateResponse("cases/form.html", {
        "request": request, "obj": case,
        "deceased": deceased, "properties": properties, "errors": []
    })


@router.post("/{cid}/edit")
def edit(
    cid: int,
    nguoi_chet_id: int = Form(...), tai_san_id: int = Form(...),
    ngay_lap_ho_so: str = Form(...), loai_van_ban: str = Form("khai_nhan"),
    ghi_chu: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if not case or case.is_locked: raise HTTPException(400)
    case.nguoi_chet_id = nguoi_chet_id; case.tai_san_id = tai_san_id
    case.ngay_lap_ho_so = datetime.strptime(ngay_lap_ho_so, "%Y-%m-%d").date()
    case.loai_van_ban = loai_van_ban; case.ghi_chu = ghi_chu or None
    db.commit()
    return RedirectResponse(f"/cases/{cid}", status_code=302)


@router.post("/{cid}/lock")
def lock(cid: int, db: Session = Depends(get_db)):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if case: case.trang_thai = "locked"; db.commit()
    return RedirectResponse(f"/cases/{cid}", status_code=302)


@router.post("/{cid}/unlock")
def unlock(cid: int, db: Session = Depends(get_db)):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if case: case.trang_thai = "draft"; db.commit()
    return RedirectResponse(f"/cases/{cid}", status_code=302)


@router.post("/{cid}/delete")
def delete(cid: int, db: Session = Depends(get_db)):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if case and not case.is_locked:
        db.delete(case); db.commit()
    return RedirectResponse("/cases", status_code=302)


@router.get("/{cid}/export-word")
def export_word(cid: int, db: Session = Depends(get_db)):
    """Xuất hồ sơ thừa kế ra file Word."""
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if not case: raise HTTPException(404)

    doc = Document()

    # Tiêu đề
    title = doc.add_heading("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph("Độc lập - Tự do - Hạnh phúc")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    van_ban_name = "VĂN BẢN KHAI NHẬN DI SẢN THỪA KẾ" if case.loai_van_ban == "khai_nhan" else "VĂN BẢN THỎA THUẬN PHÂN CHIA DI SẢN THỪA KẾ"
    h = doc.add_heading(van_ban_name, level=2)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    # Thông tin người chết
    doc.add_heading("I. THÔNG TIN NGƯỜI ĐỂ LẠI DI SẢN", level=3)
    nd = case.nguoi_chet
    doc.add_paragraph(f"Họ và tên: {nd.ho_ten}")
    doc.add_paragraph(f"Ngày sinh: {nd.ngay_sinh.strftime('%d/%m/%Y') if nd.ngay_sinh else ''}")
    doc.add_paragraph(f"Ngày mất: {nd.ngay_chet.strftime('%d/%m/%Y') if nd.ngay_chet else ''}")
    doc.add_paragraph(f"Số CCCD/Giấy tờ: {nd.so_giay_to}")
    doc.add_paragraph(f"Địa chỉ thường trú: {nd.dia_chi}")

    doc.add_paragraph()

    # Thông tin tài sản
    doc.add_heading("II. TÀI SẢN", level=3)
    ts = case.tai_san
    doc.add_paragraph(f"Số serial GCN: {ts.so_serial}")
    doc.add_paragraph(f"Số vào sổ: {ts.so_vao_so or ''}")
    doc.add_paragraph(f"Số thửa: {ts.so_thua_dat or ''} - Tờ bản đồ số: {ts.so_to_ban_do or ''}")
    doc.add_paragraph(f"Địa chỉ: {ts.dia_chi}")
    doc.add_paragraph(f"Loại đất: {ts.loai_dat or ''}")
    doc.add_paragraph(f"Thời hạn sử dụng: {ts.thoi_han or ''}")
    doc.add_paragraph(f"Cơ quan cấp: {ts.co_quan_cap or ''}")

    doc.add_paragraph()

    # Người thừa kế
    doc.add_heading("III. NHỮNG NGƯỜI THỪA KẾ", level=3)
    nhan = [p for p in case.participants if p.co_nhan_tai_san]
    tuchoi = [p for p in case.participants if not p.co_nhan_tai_san]

    if nhan:
        doc.add_paragraph("Những người nhận thừa kế:")
        for i, p in enumerate(nhan, 1):
            c = p.customer
            line = f"{i}. {c.ho_ten} - {p.vai_tro} - Tỷ lệ: {p.ty_le:.1f}%"
            doc.add_paragraph(line, style="List Number")

    if tuchoi:
        doc.add_paragraph()
        doc.add_paragraph("Những người từ chối nhận di sản:")
        for p in tuchoi:
            doc.add_paragraph(f"- {p.customer.ho_ten} ({p.vai_tro}): Từ chối nhận")

    doc.add_paragraph()
    doc.add_paragraph(f"Ngày lập văn bản: {case.ngay_lap_ho_so.strftime('%d tháng %m năm %Y')}")

    doc.add_paragraph()
    doc.add_paragraph("CÔNG CHỨNG VIÊN")
    doc.add_paragraph()
    doc.add_paragraph()
    doc.add_paragraph("(Ký và đóng dấu)")

    # Xuất ra stream
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    filename = f"ho_so_thua_ke_{cid}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
