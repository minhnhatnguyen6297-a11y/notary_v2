import os
import json
import shutil
import traceback
import time
import faulthandler
import logging

from celery_app import celery_app
from database import SessionLocal
from models import OCRJob
from routers.ocr_local import local_ocr_batch_from_inputs, local_ocr_from_bytes

faulthandler.enable()
logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger("ocr_worker")

def _delete_file(path: str | None):
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _delete_path(path: str | None):
    if not path:
        return
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _parse_json_array(raw: str | None):
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


@celery_app.task(name="process_ocr_job")
def process_ocr_job(job_id: str, qr_text: str | None = None, client_qr_failed: bool = False):
    db = SessionLocal()
    job = None
    try:
        t0 = time.time()
        job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()
        _logger.info("OCR job %s started", job_id)

        if not job.temp_file_path or not os.path.exists(job.temp_file_path):
            raise FileNotFoundError("Khong tim thay file tam")

        with open(job.temp_file_path, "rb") as f:
            file_bytes = f.read()

        result = local_ocr_from_bytes(
            file_bytes,
            qr_text=qr_text,
            client_qr_failed=client_qr_failed,
        )
        job.result_json = result
        job.status = "completed"
        job.error_message = None
        db.commit()
        _logger.info("OCR job %s completed in %.2fs", job_id, time.time() - t0)
    except Exception as e:
        if job:
            job.status = "failed"
            job.error_message = str(e)
            try:
                db.commit()
            except Exception:
                pass
        _logger.exception("OCR job %s failed: %s", job_id, e)
        traceback.print_exc()
    finally:
        if job:
            _delete_file(job.temp_file_path)
        db.close()


@celery_app.task(name="process_ocr_batch_job")
def process_ocr_batch_job(
    job_id: str,
    qr_texts_json: str | None = None,
    client_qr_failed_json: str | None = None,
):
    db = SessionLocal()
    job = None
    try:
        t0 = time.time()
        job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()
        _logger.info("OCR batch job %s started", job_id)

        batch_dir = job.temp_file_path or ""
        if not batch_dir or not os.path.isdir(batch_dir):
            raise FileNotFoundError("Khong tim thay thu muc batch tam")

        manifest_path = os.path.join(batch_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError("Khong tim thay manifest batch")

        with open(manifest_path, "r", encoding="utf-8") as fr:
            manifest = json.load(fr) or {}
        items = manifest.get("items") if isinstance(manifest, dict) else []
        if not isinstance(items, list):
            items = []

        file_items = []
        for item in sorted(items, key=lambda x: int(x.get("index", 0)) if isinstance(x, dict) else 0):
            if not isinstance(item, dict):
                continue
            idx = int(item.get("index", 0))
            filename = item.get("filename") or f"image_{idx + 1}.jpg"
            stored_name = item.get("stored_name") or ""
            file_path = os.path.join(batch_dir, stored_name)
            if not stored_name or not os.path.exists(file_path):
                raise FileNotFoundError(f"Khong tim thay file batch: {stored_name}")
            with open(file_path, "rb") as fr:
                file_bytes = fr.read()
            file_items.append({"index": idx, "filename": filename, "bytes": file_bytes})

        qr_texts = _parse_json_array(qr_texts_json)
        qr_failed_flags = _parse_json_array(client_qr_failed_json)
        result = local_ocr_batch_from_inputs(
            file_items,
            qr_texts=qr_texts,
            client_qr_failed=qr_failed_flags,
        )

        job.result_json = result
        job.status = "completed"
        job.error_message = None
        db.commit()
        _logger.info("OCR batch job %s completed in %.2fs", job_id, time.time() - t0)
    except Exception as e:
        if job:
            job.status = "failed"
            job.error_message = str(e)
            try:
                db.commit()
            except Exception:
                pass
        _logger.exception("OCR batch job %s failed: %s", job_id, e)
        traceback.print_exc()
    finally:
        if job:
            _delete_path(job.temp_file_path)
        db.close()
