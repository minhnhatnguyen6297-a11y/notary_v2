import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import get_db
from models import Property

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


def parse_date(s):
    if s and str(s).strip():
        try:
            return datetime.strptime(str(s).strip(), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _normalize_land_rows(
    raw_rows: Optional[str],
    *,
    fallback_type: str = "",
    fallback_area: str = "",
    fallback_term: str = "",
):
    raw_rows = (raw_rows or "").strip()
    if raw_rows:
        try:
            source_rows = json.loads(raw_rows)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Danh sách loại đất không hợp lệ") from exc
        if not isinstance(source_rows, list):
            raise ValueError("Danh sách loại đất không hợp lệ")
    elif fallback_type or fallback_area or fallback_term:
        source_rows = [{
            "loai_dat": fallback_type,
            "dien_tich": fallback_area,
            "thoi_han": fallback_term,
        }]
    else:
        source_rows = []

    rows = []
    total_area = 0.0
    for source_row in source_rows:
        if not isinstance(source_row, dict):
            raise ValueError("Mỗi dòng loại đất phải là một đối tượng")
        land_type = str(source_row.get("loai_dat", "") or "").strip()
        area = str(source_row.get("dien_tich", "") or "").strip()
        term = str(source_row.get("thoi_han", "") or "").strip()
        if not (land_type or area or term):
            continue
        if area:
            try:
                area_value = float(area.replace(",", "."))
            except ValueError as exc:
                raise ValueError(f"Diện tích '{area}' không hợp lệ") from exc
            if area_value < 0:
                raise ValueError("Diện tích không được âm")
            total_area += area_value
        rows.append({"loai_dat": land_type, "dien_tich": area, "thoi_han": term})

    descriptions = []
    for row in rows:
        parts = [row["loai_dat"]]
        if row["dien_tich"]:
            parts.append(f'{row["dien_tich"]}m2')
        if row["thoi_han"]:
            parts.append(row["thoi_han"])
        descriptions.append(" | ".join(part for part in parts if part))

    return {
        "rows": rows,
        "json": json.dumps(rows, ensure_ascii=False) if rows else None,
        "description": "; ".join(descriptions) or None,
        "total_area": total_area if rows and total_area > 0 else None,
        "first_term": rows[0]["thoi_han"] if rows else None,
    }


def _property_land_rows(prop: Property):
    try:
        normalized = _normalize_land_rows(
            prop.land_rows_json,
            fallback_type=prop.loai_dat or "",
            fallback_area=str(prop.dien_tich) if prop.dien_tich is not None else "",
            fallback_term=prop.thoi_han or "",
        )
        return normalized["rows"]
    except ValueError:
        return []


@router.get("/")
def list_properties(request: Request, db: Session = Depends(get_db), q: str = ""):
    query = db.query(Property)
    if q:
        query = query.filter(
            or_(Property.so_serial.contains(q), Property.dia_chi.contains(q),
                Property.so_thua_dat.contains(q))
        )
    props = query.order_by(Property.id.desc()).all()
    return templates.TemplateResponse("properties/list.html", {
        "request": request,
        "properties": props,
        "property_land_rows": {prop.id: _property_land_rows(prop) for prop in props},
        "q": q,
    })


@router.get("/create")
def create_form(request: Request):
    form = {
        "so_serial": "", "so_vao_so": "", "so_thua_dat": "", "so_to_ban_do": "",
        "dia_chi": "", "dien_tich": "", "loai_so": "", "loai_dat": "", "hinh_thuc_su_dung": "",
        "thoi_han": "", "nguon_goc": "", "ngay_cap": "", "co_quan_cap": "",
        "land_rows": "[]",
    }
    return templates.TemplateResponse("properties/form.html", {
        "request": request, "obj": None, "errors": [], "field_errors": {}, "form": form
    })


@router.post("/inline-create")
def inline_create(
    so_serial: Optional[str] = Form(None),
    so_vao_so: Optional[str] = Form(None),
    so_thua_dat: Optional[str] = Form(None),
    so_to_ban_do: Optional[str] = Form(None),
    dia_chi: Optional[str] = Form(None),
    loai_so: Optional[str] = Form(None),
    hinh_thuc_su_dung: Optional[str] = Form(None),
    nguon_goc: Optional[str] = Form(None),
    ngay_cap: Optional[str] = Form(None),
    co_quan_cap: Optional[str] = Form(None),
    land_rows: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    form = {
        "so_serial": (so_serial or "").strip(),
        "so_vao_so": (so_vao_so or "").strip(),
        "so_thua_dat": (so_thua_dat or "").strip(),
        "so_to_ban_do": (so_to_ban_do or "").strip(),
        "dia_chi": (dia_chi or "").strip(),
        "loai_so": (loai_so or "").strip(),
        "hinh_thuc_su_dung": (hinh_thuc_su_dung or "").strip(),
        "nguon_goc": (nguon_goc or "").strip(),
        "ngay_cap": (ngay_cap or "").strip(),
        "co_quan_cap": (co_quan_cap or "").strip(),
        "land_rows": (land_rows or "").strip(),
    }
    errors = {}
    if not form["so_serial"]:
        errors["so_serial"] = "Bat buoc"
    if not form["dia_chi"]:
        errors["dia_chi"] = "Bat buoc"
    if form["ngay_cap"] and parse_date(form["ngay_cap"]) is None:
        errors["ngay_cap"] = "Ngay khong hop le"
    try:
        land_data = _normalize_land_rows(form["land_rows"])
    except ValueError as exc:
        errors["land_rows"] = str(exc)

    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)

    p = Property(
        so_serial=form["so_serial"], so_vao_so=form["so_vao_so"] or None,
        so_thua_dat=form["so_thua_dat"] or None, so_to_ban_do=form["so_to_ban_do"] or None,
        dia_chi=form["dia_chi"], loai_dat=land_data["description"],
        dien_tich=land_data["total_area"], loai_so=form["loai_so"] or None,
        land_rows_json=land_data["json"],
        hinh_thuc_su_dung=form["hinh_thuc_su_dung"] or None,
        thoi_han=land_data["first_term"],
        nguon_goc=form["nguon_goc"] or None, ngay_cap=parse_date(form["ngay_cap"]),
        co_quan_cap=form["co_quan_cap"] or None
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return JSONResponse({
        "ok": True,
        "property": {
            "id": p.id,
            "so_serial": p.so_serial,
            "so_thua_dat": p.so_thua_dat or "",
            "dia_chi": p.dia_chi or "",
            "ngay_cap": p.ngay_cap.isoformat() if p.ngay_cap else "",
            "dien_tich": p.dien_tich,
        }
    })


@router.post("/create")
def create(
    request: Request,
    so_serial: Optional[str] = Form(None),
    so_vao_so: Optional[str] = Form(None),
    so_thua_dat: Optional[str] = Form(None),
    so_to_ban_do: Optional[str] = Form(None),
    dia_chi: Optional[str] = Form(None),
    dien_tich: Optional[str] = Form(None),
    loai_so: Optional[str] = Form(None),
    loai_dat: Optional[str] = Form(None),
    hinh_thuc_su_dung: Optional[str] = Form(None),
    thoi_han: Optional[str] = Form(None),
    nguon_goc: Optional[str] = Form(None),
    ngay_cap: Optional[str] = Form(None),
    co_quan_cap: Optional[str] = Form(None),
    land_rows: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    form = {
        "so_serial": (so_serial or "").strip(),
        "so_vao_so": (so_vao_so or "").strip(),
        "so_thua_dat": (so_thua_dat or "").strip(),
        "so_to_ban_do": (so_to_ban_do or "").strip(),
        "dia_chi": (dia_chi or "").strip(),
        "dien_tich": (dien_tich or "").strip(),
        "loai_so": (loai_so or "").strip(),
        "loai_dat": (loai_dat or "").strip(),
        "hinh_thuc_su_dung": (hinh_thuc_su_dung or "").strip(),
        "thoi_han": (thoi_han or "").strip(),
        "nguon_goc": (nguon_goc or "").strip(),
        "ngay_cap": (ngay_cap or "").strip(),
        "co_quan_cap": (co_quan_cap or "").strip(),
        "land_rows": (land_rows or "").strip(),
    }
    errors = []
    field_errors = {}
    if not form["so_serial"]:
        field_errors["so_serial"] = "Bat buoc"
    if not form["dia_chi"]:
        field_errors["dia_chi"] = "Bat buoc"
    if form["ngay_cap"] and parse_date(form["ngay_cap"]) is None:
        field_errors["ngay_cap"] = "Ngay khong hop le"

    try:
        land_data = _normalize_land_rows(
            form["land_rows"],
            fallback_type=form["loai_dat"],
            fallback_area=form["dien_tich"],
            fallback_term=form["thoi_han"],
        )
    except ValueError as exc:
        field_errors["land_rows"] = str(exc)

    if field_errors:
        return templates.TemplateResponse("properties/form.html", {
            "request": request, "obj": None, "errors": errors,
            "field_errors": field_errors, "form": form
        })

    p = Property(
        so_serial=form["so_serial"], so_vao_so=form["so_vao_so"] or None,
        so_thua_dat=form["so_thua_dat"] or None, so_to_ban_do=form["so_to_ban_do"] or None,
        dia_chi=form["dia_chi"], dien_tich=land_data["total_area"],
        loai_so=form["loai_so"] or None, loai_dat=land_data["description"],
        land_rows_json=land_data["json"],
        hinh_thuc_su_dung=form["hinh_thuc_su_dung"] or None, thoi_han=land_data["first_term"],
        nguon_goc=form["nguon_goc"] or None, ngay_cap=parse_date(form["ngay_cap"]),
        co_quan_cap=form["co_quan_cap"] or None
    )
    db.add(p)
    db.commit()
    return RedirectResponse("/properties", status_code=302)


@router.get("/{pid}")
def detail(pid: int, request: Request, db: Session = Depends(get_db)):
    p = db.query(Property).filter(Property.id == pid).first()
    if not p:
        raise HTTPException(404)
    return templates.TemplateResponse("properties/detail.html", {"request": request, "obj": p})


@router.get("/{pid}/edit")
def edit_form(pid: int, request: Request, db: Session = Depends(get_db)):
    p = db.query(Property).filter(Property.id == pid).first()
    if not p:
        raise HTTPException(404)
    form = {
        "so_serial": p.so_serial or "",
        "so_vao_so": p.so_vao_so or "",
        "so_thua_dat": p.so_thua_dat or "",
        "so_to_ban_do": p.so_to_ban_do or "",
        "dia_chi": p.dia_chi or "",
        "dien_tich": str(p.dien_tich) if p.dien_tich is not None else "",
        "loai_so": p.loai_so or "",
        "loai_dat": p.loai_dat or "",
        "hinh_thuc_su_dung": p.hinh_thuc_su_dung or "",
        "thoi_han": p.thoi_han or "",
        "nguon_goc": p.nguon_goc or "",
        "ngay_cap": p.ngay_cap.isoformat() if p.ngay_cap else "",
        "co_quan_cap": p.co_quan_cap or "",
        "land_rows": json.dumps(_property_land_rows(p), ensure_ascii=False),
    }
    return templates.TemplateResponse("properties/form.html", {
        "request": request, "obj": p, "errors": [], "field_errors": {}, "form": form
    })


@router.post("/{pid}/edit")
def edit(
    pid: int, request: Request,
    so_serial: Optional[str] = Form(None), so_vao_so: Optional[str] = Form(None),
    so_thua_dat: Optional[str] = Form(None), so_to_ban_do: Optional[str] = Form(None),
    dia_chi: Optional[str] = Form(None), dien_tich: Optional[str] = Form(None),
    loai_so: Optional[str] = Form(None), loai_dat: Optional[str] = Form(None),
    hinh_thuc_su_dung: Optional[str] = Form(None), thoi_han: Optional[str] = Form(None),
    nguon_goc: Optional[str] = Form(None), ngay_cap: Optional[str] = Form(None),
    co_quan_cap: Optional[str] = Form(None),
    land_rows: Optional[str] = Form(None), return_to: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    p = db.query(Property).filter(Property.id == pid).first()
    if not p:
        raise HTTPException(404)
    form = {
        "so_serial": (so_serial or "").strip(),
        "so_vao_so": (so_vao_so or "").strip(),
        "so_thua_dat": (so_thua_dat or "").strip(),
        "so_to_ban_do": (so_to_ban_do or "").strip(),
        "dia_chi": (dia_chi or "").strip(),
        "dien_tich": (dien_tich or "").strip(),
        "loai_so": (loai_so or "").strip(),
        "loai_dat": (loai_dat or "").strip(),
        "hinh_thuc_su_dung": (hinh_thuc_su_dung or "").strip(),
        "thoi_han": (thoi_han or "").strip(),
        "nguon_goc": (nguon_goc or "").strip(),
        "ngay_cap": (ngay_cap or "").strip(),
        "co_quan_cap": (co_quan_cap or "").strip(),
        "land_rows": (land_rows or "").strip(),
    }
    errors = []
    field_errors = {}
    if not form["so_serial"]:
        field_errors["so_serial"] = "Bat buoc"
    if not form["dia_chi"]:
        field_errors["dia_chi"] = "Bat buoc"
    if form["ngay_cap"] and parse_date(form["ngay_cap"]) is None:
        field_errors["ngay_cap"] = "Ngay khong hop le"

    try:
        land_data = _normalize_land_rows(
            form["land_rows"],
            fallback_type=form["loai_dat"],
            fallback_area=form["dien_tich"],
            fallback_term=form["thoi_han"],
        )
    except ValueError as exc:
        field_errors["land_rows"] = str(exc)

    if field_errors:
        return templates.TemplateResponse("properties/form.html", {
            "request": request, "obj": p, "errors": errors,
            "field_errors": field_errors, "form": form
        })

    p.so_serial = form["so_serial"]
    p.so_vao_so = form["so_vao_so"] or None
    p.so_thua_dat = form["so_thua_dat"] or None
    p.so_to_ban_do = form["so_to_ban_do"] or None
    p.dia_chi = form["dia_chi"]
    p.dien_tich = land_data["total_area"]
    p.loai_so = form["loai_so"] or None
    p.loai_dat = land_data["description"]
    p.land_rows_json = land_data["json"]
    p.hinh_thuc_su_dung = form["hinh_thuc_su_dung"] or None
    p.thoi_han = land_data["first_term"]
    p.nguon_goc = form["nguon_goc"] or None
    p.ngay_cap = parse_date(form["ngay_cap"])
    p.co_quan_cap = form["co_quan_cap"] or None
    db.commit()
    target = "/properties" if return_to == "/properties" else f"/properties/{pid}"
    return RedirectResponse(target, status_code=302)


@router.post("/{pid}/delete")
def delete(pid: int, db: Session = Depends(get_db)):
    p = db.query(Property).filter(Property.id == pid).first()
    if p:
        db.delete(p)
        db.commit()
    return RedirectResponse("/properties", status_code=302)
