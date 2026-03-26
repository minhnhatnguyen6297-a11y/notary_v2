import os
import traceback

from celery_app import celery_app
from database import SessionLocal
from models import OCRJob
from routers.ocr_local import local_ocr_from_bytes


def _delete_file(path: str | None):
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


@celery_app.task(name="process_ocr_job")
def process_ocr_job(job_id: str, qr_text: str | None = None):
    db = SessionLocal()
    job = None
    try:
        job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        if not job.temp_file_path or not os.path.exists(job.temp_file_path):
            raise FileNotFoundError("Khong tim thay file tam")

        with open(job.temp_file_path, "rb") as f:
            file_bytes = f.read()

        result = local_ocr_from_bytes(file_bytes, qr_text=qr_text)
        job.result_json = result
        job.status = "completed"
        job.error_message = None
        db.commit()
    except Exception as e:
        if job:
            job.status = "failed"
            job.error_message = str(e)
            try:
                db.commit()
            except Exception:
                pass
        traceback.print_exc()
    finally:
        if job:
            _delete_file(job.temp_file_path)
        db.close()
