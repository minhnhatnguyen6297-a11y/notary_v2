from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import InheritanceParticipant, InheritanceCase

router = APIRouter()


@router.post("/add")
def add(
    ho_so_id: int = Form(...),
    customer_id: int = Form(...),
    vai_tro: str = Form(...),
    hang_thua_ke: int = Form(1),
    co_nhan_tai_san: Optional[str] = Form(None),
    ty_le: float = Form(0.0),
    ghi_chu: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == ho_so_id).first()
    if not case or case.is_locked:
        raise HTTPException(400, "Hồ sơ đã khoá hoặc không tồn tại")

    # Tránh thêm trùng
    exists = db.query(InheritanceParticipant).filter(
        InheritanceParticipant.ho_so_id == ho_so_id,
        InheritanceParticipant.customer_id == customer_id
    ).first()
    if not exists:
        p = InheritanceParticipant(
            ho_so_id=ho_so_id, customer_id=customer_id,
            vai_tro=vai_tro, hang_thua_ke=hang_thua_ke,
            co_nhan_tai_san=(co_nhan_tai_san == "on"),
            ty_le=ty_le, ghi_chu=ghi_chu or None
        )
        db.add(p); db.commit()
    return RedirectResponse(f"/cases/{ho_so_id}", status_code=302)


@router.post("/{pid}/edit")
def edit(
    pid: int,
    vai_tro: str = Form(...),
    hang_thua_ke: int = Form(1),
    co_nhan_tai_san: Optional[str] = Form(None),
    ty_le: float = Form(0.0),
    ghi_chu: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    p = db.query(InheritanceParticipant).filter(InheritanceParticipant.id == pid).first()
    if not p: raise HTTPException(404)
    if p.ho_so.is_locked: raise HTTPException(400, "Hồ sơ đã khoá")

    p.vai_tro = vai_tro; p.hang_thua_ke = hang_thua_ke
    p.co_nhan_tai_san = (co_nhan_tai_san == "on")
    p.ty_le = ty_le; p.ghi_chu = ghi_chu or None
    db.commit()
    return RedirectResponse(f"/cases/{p.ho_so_id}", status_code=302)


@router.post("/{pid}/delete")
def delete(pid: int, db: Session = Depends(get_db)):
    p = db.query(InheritanceParticipant).filter(InheritanceParticipant.id == pid).first()
    if not p: raise HTTPException(404)
    if p.ho_so.is_locked: raise HTTPException(400, "Hồ sơ đã khoá")
    case_id = p.ho_so_id
    db.delete(p); db.commit()
    return RedirectResponse(f"/cases/{case_id}", status_code=302)
