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
from observability import configure_process_logging
from routers.ocr_local import local_ocr_batch_from_inputs, local_ocr_from_bytes

faulthandler.enable()
WORKER_LOG_PATH = configure_process_logging("worker")
_logger = logging.getLogger("ocr_worker")
_logger.info("Worker logging initialized at %s", WORKER_LOG_PATH)


def _ms(seconds: float) -> float:
    return round(max(0.0, float(seconds)) * 1000.0, 2)


def _timing_log(event: str, **fields) -> None:
    payload = {"event": event, **fields}
    try:
        line = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        line = str(payload)
    _logger.info("[OCR_WORKER_TIMING] %s", line)

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
        t_job = time.perf_counter()
        job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()
        _logger.info("OCR job %s started", job_id)
        _timing_log("single_job_start", job_id=job_id, client_qr_failed=bool(client_qr_failed), qr_seeded=bool((qr_text or "").strip()))

        if not job.temp_file_path or not os.path.exists(job.temp_file_path):
            raise FileNotFoundError("Khong tim thay file tam")

        t_read = time.perf_counter()
        with open(job.temp_file_path, "rb") as f:
            file_bytes = f.read()
        read_file_ms = _ms(time.perf_counter() - t_read)
        t_ocr = time.perf_counter()

        result = local_ocr_from_bytes(
            file_bytes,
            qr_text=qr_text,
            client_qr_failed=client_qr_failed,
            trace_id=job_id,
        )
        local_ocr_ms = _ms(time.perf_counter() - t_ocr)
        job.result_json = result
        job.status = "completed"
        job.error_message = None
        db.commit()
        _logger.info("OCR job %s completed in %.2fs", job_id, time.time() - t0)
        _timing_log(
            "single_job_done",
            job_id=job_id,
            total_ms=_ms(time.perf_counter() - t_job),
            read_file_ms=read_file_ms,
            local_ocr_ms=local_ocr_ms,
            triage_phase_ms=(result.get("timing_ms", {}) or {}).get("triage_phase_ms", 0.0),
            targeted_extract_phase_ms=(result.get("timing_ms", {}) or {}).get("targeted_extract_phase_ms", 0.0),
            merge_phase_ms=(result.get("timing_ms", {}) or {}).get("merge_phase_ms", 0.0),
            fallback_phase_ms=(result.get("timing_ms", {}) or {}).get("fallback_phase_ms", 0.0),
            summary_timing=result.get("timing_ms", {}),
        )
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
        t_job = time.perf_counter()
        job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()
        _logger.info("OCR batch job %s started", job_id)
        _timing_log(
            "batch_job_start",
            job_id=job_id,
            qr_texts_json_len=len(qr_texts_json or ""),
            client_qr_failed_json_len=len(client_qr_failed_json or ""),
        )

        batch_dir = job.temp_file_path or ""
        if not batch_dir or not os.path.isdir(batch_dir):
            raise FileNotFoundError("Khong tim thay thu muc batch tam")

        t_manifest = time.perf_counter()
        manifest_path = os.path.join(batch_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError("Khong tim thay manifest batch")

        with open(manifest_path, "r", encoding="utf-8") as fr:
            manifest = json.load(fr) or {}
        manifest_ms = _ms(time.perf_counter() - t_manifest)
        items = manifest.get("items") if isinstance(manifest, dict) else []
        if not isinstance(items, list):
            items = []

        t_read_files = time.perf_counter()
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
        read_files_ms = _ms(time.perf_counter() - t_read_files)

        t_parse_flags = time.perf_counter()
        qr_texts = _parse_json_array(qr_texts_json)
        qr_failed_flags = _parse_json_array(client_qr_failed_json)
        parse_flags_ms = _ms(time.perf_counter() - t_parse_flags)
        t_ocr = time.perf_counter()
        result = local_ocr_batch_from_inputs(
            file_items,
            qr_texts=qr_texts,
            client_qr_failed=qr_failed_flags,
            trace_id=job_id,
        )
        local_ocr_ms = _ms(time.perf_counter() - t_ocr)

        job.result_json = result
        job.status = "completed"
        job.error_message = None
        db.commit()
        _logger.info("OCR batch job %s completed in %.2fs", job_id, time.time() - t0)
        _timing_log(
            "batch_job_done",
            job_id=job_id,
            total_ms=_ms(time.perf_counter() - t_job),
            manifest_ms=manifest_ms,
            read_files_ms=read_files_ms,
            parse_flags_ms=parse_flags_ms,
            local_ocr_ms=local_ocr_ms,
            total_files=len(file_items),
            triage_phase_ms=((result.get("summary", {}) or {}).get("timing_ms", {}) or {}).get("triage_phase_ms", 0.0),
            targeted_extract_phase_ms=((result.get("summary", {}) or {}).get("timing_ms", {}) or {}).get("targeted_extract_phase_ms", 0.0),
            merge_phase_ms=((result.get("summary", {}) or {}).get("timing_ms", {}) or {}).get("merge_phase_ms", 0.0),
            fallback_phase_ms=((result.get("summary", {}) or {}).get("timing_ms", {}) or {}).get("fallback_phase_ms", 0.0),
            summary=result.get("summary", {}),
        )
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
