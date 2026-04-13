import logging
import os
from contextlib import asynccontextmanager
from time import perf_counter

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import (
    Base,
    engine,
    migrate_customers_nullable,
    migrate_inheritance_cases_schema,
    migrate_properties_schema,
)
from observability import configure_process_logging
from routers import cases, customers, ocr_ai, ocr_local, participants, properties

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

WEB_LOG_PATH = configure_process_logging("web")
app_logger = logging.getLogger("notary.web")
app_logger.info("Web logging initialized at %s", WEB_LOG_PATH)

# Run schema migration before create_all.
migrate_customers_nullable()
migrate_inheritance_cases_schema()
migrate_properties_schema()
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import warnings

    warnings.filterwarnings("ignore")
    try:
        from routers.ocr_local import warmup_local_ocr

        warmup_ok, warmup_error = warmup_local_ocr()
        if warmup_ok:
            app_logger.info("[startup] Local OCR warmup OK")
        else:
            app_logger.warning("[startup] Local OCR warmup skipped: %s", warmup_error or "unknown")
    except Exception as e:
        app_logger.exception("[startup] Local OCR warmup skipped: %s", e)
    try:
        ai_ocr_settings = ocr._get_ai_ocr_settings()
        ocr.init_ai_preprocess_pool(int(ai_ocr_settings.get("preprocess_workers", 0) or 0))
        if ai_ocr_settings.get("preprocess_warmup", True):
            ocr.warmup_ai_preprocess_pool()
    except Exception as e:
        app_logger.exception("[startup] AI OCR preprocess pool warmup skipped: %s", e)
    yield
    try:
        ocr.shutdown_ai_preprocess_pool()
    except Exception as e:
        app_logger.exception("[shutdown] AI OCR preprocess pool shutdown failed: %s", e)


app = FastAPI(
    title="He thong Quan ly Ho so Cong chung",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def http_timing_log(request: Request, call_next):
    path = request.url.path
    should_log = path.startswith("/api/ocr/")
    start = perf_counter()
    if not should_log:
        return await call_next(request)

    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed_ms = round((perf_counter() - start) * 1000.0, 2)
        app_logger.exception(
            "[HTTP_TIMING] method=%s path=%s status=500 elapsed_ms=%s client=%s error=%s",
            request.method,
            path,
            elapsed_ms,
            request.client.host if request.client else "-",
            exc,
        )
        raise

    elapsed_ms = round((perf_counter() - start) * 1000.0, 2)
    level = logging.WARNING if response.status_code >= 500 else logging.INFO
    app_logger.log(
        level,
        "[HTTP_TIMING] method=%s path=%s status=%s elapsed_ms=%s client=%s",
        request.method,
        path,
        response.status_code,
        elapsed_ms,
        request.client.host if request.client else "-",
    )
    return response


app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")

app.include_router(customers.router, prefix="/customers", tags=["Khach hang"])
app.include_router(properties.router, prefix="/properties", tags=["Tai san"])
app.include_router(cases.router, prefix="/cases", tags=["Ho so thua ke"])
app.include_router(participants.router, prefix="/participants", tags=["Nguoi tham gia"])
app.include_router(ocr_ai.router, prefix="/api/ocr", tags=["OCR"])
app.include_router(ocr_local.router, prefix="/api/ocr", tags=["OCR_Local"])


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/api/stats")
async def stats():
    from database import SessionLocal
    from models import Customer, InheritanceCase, Property

    db = SessionLocal()
    try:
        return {
            "customers": db.query(Customer).count(),
            "properties": db.query(Property).count(),
            "cases": db.query(InheritanceCase).count(),
            "locked": db.query(InheritanceCase).filter(InheritanceCase.trang_thai == "locked").count(),
        }
    finally:
        db.close()
