import os
import json
import shutil
import traceback
import time
import faulthandler
import logging
import sys

from celery_app import celery_app
from database import SessionLocal
from models import OCRJob
from observability import configure_process_logging
from routers.ocr_local import _cleanup_stale_local_ocr_sessions, _load_local_ocr_session_file_items, local_ocr_batch_from_inputs

faulthandler.enable()
_logger = logging.getLogger("ocr_worker")
_WORKER_LOGGING_READY = False


def _ensure_worker_logging() -> None:
    global _WORKER_LOGGING_READY
    if _WORKER_LOGGING_READY:
        return
    argv = " ".join(sys.argv).lower()
    is_celery_runtime = "celery" in argv or os.getenv("FORCE_WORKER_LOGGING", "0") == "1"
    if not is_celery_runtime:
        return
    worker_log_path = configure_process_logging("worker")
    _logger.info("Worker logging initialized at %s", worker_log_path)
    _WORKER_LOGGING_READY = True


_ensure_worker_logging()


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
    _ensure_worker_logging()
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

        t_read = time.perf_counter()
        if not job.temp_file_path or not os.path.exists(job.temp_file_path):
            raise FileNotFoundError("Khong tim thay file tam")
        if os.path.isdir(job.temp_file_path):
            file_items = _load_local_ocr_session_file_items(job.temp_file_path)
            if not file_items:
                raise FileNotFoundError("Khong tim thay file OCR session")
        else:
            with open(job.temp_file_path, "rb") as f:
                file_bytes = f.read()
            file_items = [{"index": 0, "filename": "single_upload.jpg", "bytes": file_bytes}]
        read_file_ms = _ms(time.perf_counter() - t_read)
        t_ocr = time.perf_counter()

        result = local_ocr_batch_from_inputs(
            file_items,
            qr_texts=[qr_text or ""],
            client_qr_failed=[client_qr_failed],
            trace_id=job_id,
        )
        local_ocr_ms = _ms(time.perf_counter() - t_ocr)
        job.result_json = result
        job.status = "completed"
        job.error_message = None
        db.commit()
        _logger.info("OCR job %s completed in %.2fs", job_id, time.time() - t0)
        summary_timing = ((result.get("summary", {}) or {}).get("timing_ms", {}) or result.get("timing_ms", {}))
        _timing_log(
            "single_job_done",
            job_id=job_id,
            total_ms=_ms(time.perf_counter() - t_job),
            read_file_ms=read_file_ms,
            local_ocr_ms=local_ocr_ms,
            triage_phase_ms=summary_timing.get("triage_phase_ms", 0.0),
            targeted_extract_phase_ms=summary_timing.get("targeted_extract_phase_ms", 0.0),
            merge_phase_ms=summary_timing.get("merge_phase_ms", 0.0),
            fallback_phase_ms=summary_timing.get("fallback_phase_ms", 0.0),
            summary_timing=summary_timing,
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
        _cleanup_stale_local_ocr_sessions(db)
        db.close()


@celery_app.task(name="process_ocr_batch_job")
def process_ocr_batch_job(
    job_id: str,
    qr_texts_json: str | None = None,
    client_qr_failed_json: str | None = None,
):
    _ensure_worker_logging()
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
        manifest_ms = _ms(time.perf_counter() - t_manifest)
        t_read_files = time.perf_counter()
        file_items = _load_local_ocr_session_file_items(batch_dir)
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
        _cleanup_stale_local_ocr_sessions(db)
        db.close()
