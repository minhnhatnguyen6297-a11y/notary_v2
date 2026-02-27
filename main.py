from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from database import engine, Base
from routers import customers, properties, cases, participants

# Tạo tất cả bảng trong database khi khởi động
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Hệ thống Quản lý Hồ sơ Công chứng", version="1.0.0")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Đăng ký các router (nhóm tính năng)
app.include_router(customers.router,    prefix="/customers",    tags=["Khách hàng"])
app.include_router(properties.router,   prefix="/properties",   tags=["Tài sản"])
app.include_router(cases.router,        prefix="/cases",        tags=["Hồ sơ thừa kế"])
app.include_router(participants.router, prefix="/participants",  tags=["Người tham gia"])


@app.get("/")
async def home(request: Request):
    """Trang chủ — dashboard."""
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/api/stats")
async def stats():
    """API trả về số liệu thống kê cho dashboard."""
    from database import SessionLocal
    from models import Customer, Property, InheritanceCase
    db = SessionLocal()
    try:
        return {
            "customers":  db.query(Customer).count(),
            "properties": db.query(Property).count(),
            "cases":      db.query(InheritanceCase).count(),
            "locked":     db.query(InheritanceCase).filter(InheritanceCase.trang_thai == "locked").count(),
        }
    finally:
        db.close()
