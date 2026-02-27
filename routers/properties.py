from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from datetime import date, datetime

from database import get_db
from models import Property

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def parse_date(s):
    if s and s.strip():
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    return None


@router.get("/")
def list_properties(request: Request, db: Session = Depends(get_db), q: str = ""):
    query = db.query(Property)
    if q:
        query = query.filter(
            or_(Property.so_serial.contains(q), Property.dia_chi.contains(q),
                Property.so_thua_dat.contains(q))
        )
    props = query.order_by(Property.id.desc()).all()
    return templates.TemplateResponse("properties/list.html", {"request": request, "properties": props, "q": q})


@router.get("/create")
def create_form(request: Request):
    return templates.TemplateResponse("properties/form.html", {"request": request, "obj": None, "errors": []})


@router.post("/create")
def create(
    request: Request,
    so_serial: str = Form(...),
    so_vao_so: Optional[str] = Form(None),
    so_thua_dat: Optional[str] = Form(None),
    so_to_ban_do: Optional[str] = Form(None),
    dia_chi: str = Form(...),
    loai_dat: Optional[str] = Form(None),
    hinh_thuc_su_dung: Optional[str] = Form(None),
    thoi_han: Optional[str] = Form(None),
    nguon_goc: Optional[str] = Form(None),
    ngay_cap: Optional[str] = Form(None),
    co_quan_cap: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    errors = []
    if db.query(Property).filter(Property.so_serial == so_serial.strip()).first():
        errors.append(f"Số serial '{so_serial}' đã tồn tại!")
    if errors:
        return templates.TemplateResponse("properties/form.html", {"request": request, "obj": None, "errors": errors})

    p = Property(
        so_serial=so_serial.strip(), so_vao_so=so_vao_so or None,
        so_thua_dat=so_thua_dat or None, so_to_ban_do=so_to_ban_do or None,
        dia_chi=dia_chi.strip(), loai_dat=loai_dat or None,
        hinh_thuc_su_dung=hinh_thuc_su_dung or None, thoi_han=thoi_han or None,
        nguon_goc=nguon_goc or None, ngay_cap=parse_date(ngay_cap),
        co_quan_cap=co_quan_cap or None
    )
    db.add(p); db.commit()
    return RedirectResponse("/properties", status_code=302)


@router.get("/{pid}")
def detail(pid: int, request: Request, db: Session = Depends(get_db)):
    p = db.query(Property).filter(Property.id == pid).first()
    if not p: raise HTTPException(404)
    return templates.TemplateResponse("properties/detail.html", {"request": request, "obj": p})


@router.get("/{pid}/edit")
def edit_form(pid: int, request: Request, db: Session = Depends(get_db)):
    p = db.query(Property).filter(Property.id == pid).first()
    if not p: raise HTTPException(404)
    return templates.TemplateResponse("properties/form.html", {"request": request, "obj": p, "errors": []})


@router.post("/{pid}/edit")
def edit(
    pid: int, request: Request,
    so_serial: str = Form(...), so_vao_so: Optional[str] = Form(None),
    so_thua_dat: Optional[str] = Form(None), so_to_ban_do: Optional[str] = Form(None),
    dia_chi: str = Form(...), loai_dat: Optional[str] = Form(None),
    hinh_thuc_su_dung: Optional[str] = Form(None), thoi_han: Optional[str] = Form(None),
    nguon_goc: Optional[str] = Form(None), ngay_cap: Optional[str] = Form(None),
    co_quan_cap: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    p = db.query(Property).filter(Property.id == pid).first()
    if not p: raise HTTPException(404)
    errors = []
    dup = db.query(Property).filter(Property.so_serial == so_serial.strip(), Property.id != pid).first()
    if dup: errors.append(f"Số serial '{so_serial}' đã tồn tại!")
    if errors:
        return templates.TemplateResponse("properties/form.html", {"request": request, "obj": p, "errors": errors})

    p.so_serial = so_serial.strip(); p.so_vao_so = so_vao_so or None
    p.so_thua_dat = so_thua_dat or None; p.so_to_ban_do = so_to_ban_do or None
    p.dia_chi = dia_chi.strip(); p.loai_dat = loai_dat or None
    p.hinh_thuc_su_dung = hinh_thuc_su_dung or None; p.thoi_han = thoi_han or None
    p.nguon_goc = nguon_goc or None; p.ngay_cap = parse_date(ngay_cap)
    p.co_quan_cap = co_quan_cap or None
    db.commit()
    return RedirectResponse(f"/properties/{pid}", status_code=302)


@router.post("/{pid}/delete")
def delete(pid: int, db: Session = Depends(get_db)):
    p = db.query(Property).filter(Property.id == pid).first()
    if p: db.delete(p); db.commit()
    return RedirectResponse("/properties", status_code=302)
