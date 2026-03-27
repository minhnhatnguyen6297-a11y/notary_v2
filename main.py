import os
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=True)

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from database import engine, Base, migrate_customers_nullable, migrate_inheritance_cases_schema, migrate_properties_schema
from routers import customers, properties, cases, participants, ocr, ocr_local

# Migrate schema trước khi create_all (chuyển customers sang nullable)
migrate_customers_nullable()
migrate_inheritance_cases_schema()
migrate_properties_schema()
# Tạo tất cả bảng trong database khi khởi động
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app):
    """Khởi tạo các model nặng khi startup."""
    import warnings
    warnings.filterwarnings("ignore")
    try:
        from routers.ocr_local import warmup_local_ocr
        warmup_local_ocr()
        print("[startup] Local OCR warmup OK")
    except Exception as e:
        print(f"[startup] Local OCR warmup skipped: {e}")
    yield  # server runs here

app = FastAPI(title="Hệ thống Quản lý Hồ sơ Công chứng", version="1.0.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Đăng ký các router (nhóm tính năng)
app.include_router(customers.router,    prefix="/customers",    tags=["Khách hàng"])
app.include_router(properties.router,   prefix="/properties",   tags=["Tài sản"])
app.include_router(cases.router,        prefix="/cases",        tags=["Hồ sơ thừa kế"])
app.include_router(participants.router, prefix="/participants",  tags=["Người tham gia"])
app.include_router(ocr.router,          prefix="/api/ocr",       tags=["OCR"])
app.include_router(ocr_local.router,    prefix="/api/ocr",       tags=["OCR_Local"])

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
