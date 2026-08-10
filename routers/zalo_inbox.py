from __future__ import annotations

import atexit
import json
import math
import os
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import ZaloBatch, ZaloConnectorAccount, ZaloMedia, ZaloSource
from routers import ocr_ai
from services.zalo_inbox import (
    InboxConflict,
    InboxConfigurationError,
    InboxError,
    InboxLimits,
    apply_intake_consent,
    cleanup_expired_batch,
    confirm_batch,
    connector_state,
    create_batch,
    freeze_outputs,
    ingest_webhook_event,
    prepare_batch,
    public_qr,
    retry_cached_ocr,
    retry_export,
    request_source_sync,
    resolve_media_object,
    run_outputs,
    set_source_policy,
    source_ready,
    _aware,
    update_preview,
    utcnow,
    verify_webhook_signature,
)

router = APIRouter(prefix="/zalo-inbox", tags=["zalo-inbox"])
templates = Jinja2Templates(directory="frontend/templates")
UTC = timezone.utc
_connector_process: subprocess.Popen | None = None
_connector_lock = threading.RLock()
_connector_error: str | None = None
CONNECTOR_STOPPED_MESSAGE = "Zalo connector đã dừng. Kiểm tra cấu hình và thử lại."


def get_session_factory() -> Callable[[], Session]:
    return SessionLocal


def _storage_root() -> Path:
    return Path(os.getenv("ZALO_INBOX_STORAGE_ROOT", "runtime/zalo_inbox/source"))


def _batch_root() -> Path:
    return Path(os.getenv("ZALO_INBOX_BATCH_ROOT", "runtime/zalo_inbox/batches"))


def _connector_entrypoint() -> Path:
    return Path(__file__).resolve().parents[1] / "zalo_connector" / "bin" / "run.mjs"


def _connector_environment(*, force_qr: bool = False) -> dict[str, str]:
    required = (
        "ZALO_INBOX_BOOTSTRAP_SECRET",
        "ZALO_INBOX_WEBHOOK_SECRET",
        "ZALO_CONNECTOR_QUOTA_BYTES",
        "ZALO_CONNECTOR_RETENTION_HOURS",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise InboxConfigurationError(f"Thiếu cấu hình connector: {', '.join(missing)}")
    try:
        quota_bytes = int(os.environ["ZALO_CONNECTOR_QUOTA_BYTES"])
    except ValueError as exc:
        raise InboxConfigurationError("ZALO_CONNECTOR_QUOTA_BYTES không hợp lệ") from exc
    if quota_bytes <= 0 or quota_bytes > 2**53 - 1:
        raise InboxConfigurationError("ZALO_CONNECTOR_QUOTA_BYTES không hợp lệ")
    try:
        retention_hours = float(os.environ["ZALO_CONNECTOR_RETENTION_HOURS"])
    except ValueError as exc:
        raise InboxConfigurationError("ZALO_CONNECTOR_RETENTION_HOURS không hợp lệ") from exc
    if not math.isfinite(retention_hours) or retention_hours <= 0:
        raise InboxConfigurationError("ZALO_CONNECTOR_RETENTION_HOURS không hợp lệ")
    child_env = {
        name: os.environ[name]
        for name in ("PATH", "Path", "SYSTEMROOT", "SystemRoot", "TEMP", "TMP")
        if name in os.environ
    }
    child_env.update(
        {
            "ZALO_INBOX_BACKEND_URL": os.getenv("ZALO_INBOX_BACKEND_URL", "http://127.0.0.1:8000"),
            "ZALO_INBOX_BOOTSTRAP_SECRET": os.environ["ZALO_INBOX_BOOTSTRAP_SECRET"],
            "ZALO_INBOX_WEBHOOK_SECRET": os.environ["ZALO_INBOX_WEBHOOK_SECRET"],
            "ZALO_INBOX_STORAGE_ROOT": str(_storage_root().resolve()),
            "ZALO_CONNECTOR_QUOTA_BYTES": os.environ["ZALO_CONNECTOR_QUOTA_BYTES"],
            "ZALO_CONNECTOR_RETENTION_HOURS": os.environ["ZALO_CONNECTOR_RETENTION_HOURS"],
            "ZALO_CONNECTOR_PARENT_PID": str(os.getpid()),
            "ZALO_CONNECTOR_STATE_ROOT": os.getenv(
                "ZALO_CONNECTOR_STATE_ROOT",
                str(Path(__file__).resolve().parents[1] / "runtime" / "zalo_connector"),
            ),
        }
    )
    if force_qr:
        child_env["ZALO_CONNECTOR_FORCE_QR"] = "1"
    return child_env


def _terminate_connector_process() -> None:
    global _connector_error, _connector_process
    with _connector_lock:
        process = _connector_process
        _connector_process = None
        _connector_error = None
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass


def _receiving_connector_identity() -> tuple[str, int] | None:
    db = SessionLocal()
    try:
        account = db.query(ZaloConnectorAccount).order_by(ZaloConnectorAccount.created_at.asc()).first()
        if account is not None and account.session_state == "usable":
            return account.id, account.listener_generation
        return None
    finally:
        db.close()


def _record_connector_gap(identity: tuple[str, int] | None) -> None:
    if identity is None:
        return
    account_id, listener_generation = identity
    db = SessionLocal()
    try:
        account = db.query(ZaloConnectorAccount).filter(ZaloConnectorAccount.id == account_id).first()
        if (
            account is not None
            and account.session_state == "usable"
            and account.listener_generation == listener_generation
            and account.gap_started_at is None
        ):
            account.gap_started_at = utcnow()
            db.commit()
    finally:
        db.close()


def _watch_connector_process(process: subprocess.Popen, identity: tuple[str, int] | None) -> None:
    process.wait(timeout=None)
    global _connector_error, _connector_process
    with _connector_lock:
        if _connector_process is not process:
            return
        _connector_process = None
        _connector_error = CONNECTOR_STOPPED_MESSAGE
        _record_connector_gap(identity)


def _connector_runtime_error() -> str | None:
    global _connector_error, _connector_process
    with _connector_lock:
        if _connector_process is not None and _connector_process.poll() is not None:
            _connector_error = CONNECTOR_STOPPED_MESSAGE
    return _connector_error


def _start_connector_process(*, force_restart: bool = False, force_qr: bool = False) -> bool:
    global _connector_error, _connector_process
    with _connector_lock:
        if _connector_process is not None and _connector_process.poll() is None:
            if not force_restart:
                return False
            _terminate_connector_process()
        entrypoint = _connector_entrypoint()
        if not entrypoint.is_file():
            raise InboxConfigurationError("Không tìm thấy Zalo connector")
        child_env = _connector_environment(force_qr=force_qr)
        identity = _receiving_connector_identity()
        try:
            _connector_process = subprocess.Popen(
                ["node", str(entrypoint)],
                cwd=str(entrypoint.parents[2]),
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError as exc:
            raise InboxConfigurationError("Không thể khởi động Zalo connector") from exc
        _connector_error = None
        if _connector_process.poll() is not None:
            _connector_process = None
            _connector_error = CONNECTOR_STOPPED_MESSAGE
            raise InboxConfigurationError(CONNECTOR_STOPPED_MESSAGE)
        process = _connector_process
        threading.Thread(target=_watch_connector_process, args=(process, identity), daemon=True).start()
        return True


atexit.register(_terminate_connector_process)
router.add_event_handler("shutdown", _terminate_connector_process)


def _as_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


def _raise_http(exc: InboxError) -> None:
    if isinstance(exc, InboxConfigurationError):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        code = status.HTTP_409_CONFLICT if isinstance(exc, InboxConflict) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=str(exc)) from exc


def _public_batch(batch: ZaloBatch) -> dict[str, Any]:
    items = []
    for item in sorted(list(batch.items_json or []), key=lambda value: value.get("order", 0)):
        items.append(
            {
                "input_item_id": item.get("input_item_id"),
                "source_media_id": item.get("source_media_id"),
                "source_display_name": item.get("source_display_name"),
                "sent_at": item.get("sent_at"),
                "page_number": item.get("page_number"),
                "page_count": item.get("page_count"),
                "order": item.get("order"),
                "status": item.get("status"),
                "error": item.get("error"),
                "use_crop": bool(item.get("use_crop")),
                "crop_available": bool(item.get("crop_path")),
                "preview_url": f"/zalo-inbox/api/batches/{batch.id}/items/{item.get('input_item_id')}/preview",
            }
        )
    outputs = {
        name: {key: value for key, value in state.items() if key != "path"}
        for name, state in dict(batch.outputs_json or {}).items()
    }
    for name, state in outputs.items():
        if state.get("status") == "ready":
            state["download_url"] = f"/zalo-inbox/api/batches/{batch.id}/download/{name}"
    return {
        "id": batch.id,
        "status": batch.status,
        "items": items,
        "selection": list(batch.selection_json or []),
        "ocr_status": batch.ocr_status,
        "ocr_result": batch.confirmed_json if batch.ocr_status == "confirmed" else batch.raw_ocr_json,
        "ocr_read_only": batch.ocr_status == "confirmed",
        "outputs": outputs,
        "error": batch.error_message,
        "created_at": _as_iso(batch.created_at),
        "expires_at": _as_iso(batch.expires_at),
    }


def _batch_unfinished(batch: ZaloBatch) -> bool:
    return batch.status not in {"completed", "expired"}


class SourceToggle(BaseModel):
    enabled: bool


class ConnectorStart(BaseModel):
    force_restart: bool = False
    force_qr: bool = False


class BatchCreate(BaseModel):
    media_ids: list[str] = Field(min_length=1)


class PreviewItem(BaseModel):
    input_item_id: str
    use_crop: bool = False


class PreviewUpdate(BaseModel):
    items: list[PreviewItem]


class OutputSelection(BaseModel):
    outputs: list[str] = Field(min_length=1)


class Confirmation(BaseModel):
    persons: list[dict[str, Any]]
    properties: list[dict[str, Any]]


class RetryRequest(BaseModel):
    step: str
    output_type: str | None = None


def _prepare_job(batch_id: str, session_factory: Callable[[], Session]) -> None:
    db = session_factory()
    try:
        prepare_batch(db, batch_id, batch_root=_batch_root())
    finally:
        db.close()


async def _output_job(batch_id: str, session_factory: Callable[[], Session]) -> None:
    db = session_factory()
    try:
        await run_outputs(
            db,
            batch_id,
            batch_root=_batch_root(),
            ocr_analyzer=ocr_ai.analyze_images,
            cached_parser=ocr_ai.shape_cached_ocr,
        )
    finally:
        db.close()


@router.get("/")
def inbox_page(request: Request):
    return templates.TemplateResponse(request, "zalo_inbox.html", {"initial_batch_id": None})


@router.get("/batches/{batch_id}")
def batch_page(request: Request, batch_id: str):
    return templates.TemplateResponse(request, "zalo_inbox.html", {"initial_batch_id": batch_id})


@router.post("/api/connectors/onboard")
def onboard_connector(
    x_zalo_bootstrap: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    expected = os.getenv("ZALO_INBOX_BOOTSTRAP_SECRET", "")
    if not expected or x_zalo_bootstrap != expected:
        raise HTTPException(status_code=403, detail="Bootstrap secret không hợp lệ")
    account = db.query(ZaloConnectorAccount).order_by(ZaloConnectorAccount.created_at.asc()).first()
    if account is None:
        account = ZaloConnectorAccount(id=str(uuid.uuid4()), session_state="login_required", listener_generation=0)
        db.add(account)
        db.commit()
        db.refresh(account)
    return {"connector_account_id": account.id}


@router.post("/api/connectors/start")
def start_connector(response: Response, body: ConnectorStart | None = None, db: Session = Depends(get_db)):
    try:
        force_qr = bool(body and body.force_qr)
        account = db.query(ZaloConnectorAccount).order_by(ZaloConnectorAccount.created_at.asc()).first()
        if account is not None:
            account.qr_image = None
            account.qr_generated_at = None
            account.qr_expires_at = None
            db.commit()
        started = _start_connector_process(
            force_restart=bool(body and body.force_restart) or force_qr,
            force_qr=force_qr,
        )
    except InboxError as exc:
        _raise_http(exc)
    response.status_code = status.HTTP_202_ACCEPTED if started else status.HTTP_200_OK
    return {"status": "starting" if started else "running"}


@router.post("/api/webhook")
async def webhook(
    request: Request,
    x_zalo_timestamp: str | None = Header(default=None),
    x_zalo_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    body = await request.body()
    try:
        verify_webhook_signature(
            body,
            x_zalo_timestamp or "",
            x_zalo_signature or "",
            os.getenv("ZALO_INBOX_WEBHOOK_SECRET", ""),
        )
        payload = json.loads(body)
        result = ingest_webhook_event(db, payload, storage_root=_storage_root())
    except (json.JSONDecodeError, InboxError) as exc:
        if isinstance(exc, InboxError):
            db.rollback()
            _raise_http(exc)
        raise HTTPException(status_code=400, detail="Webhook JSON không hợp lệ") from exc
    if payload.get("event_type") == "message":
        return {"ack": True, "components": result["components"]}
    if payload.get("event_type") in {"policy_ack", "source_sync_ack"}:
        return {"ack": True, **result}
    return {"ack": True, "id": getattr(result, "id", None)}


@router.get("/api/connectors/{account_id}/config")
def connector_config(
    account_id: str,
    x_zalo_timestamp: str | None = Header(default=None),
    x_zalo_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    try:
        verify_webhook_signature(
            b"",
            x_zalo_timestamp or "",
            x_zalo_signature or "",
            os.getenv("ZALO_INBOX_WEBHOOK_SECRET", ""),
        )
    except InboxError as exc:
        _raise_http(exc)
    account = db.query(ZaloConnectorAccount).filter(ZaloConnectorAccount.id == account_id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy connector")
    sources = db.query(ZaloSource).filter(ZaloSource.connector_account_id == account_id).all()
    now = datetime.now(UTC)
    active_batches = (
        db.query(ZaloBatch)
        .filter(
            ZaloBatch.connector_account_id == account_id,
            ZaloBatch.status != "expired",
            ZaloBatch.expires_at > now,
        )
        .all()
    )
    protected_media_ids = {
        str(item.get("source_media_id"))
        for batch in active_batches
        for item in (batch.items_json or [])
        if item.get("source_media_id")
    }
    protected_keys = []
    if protected_media_ids:
        protected_keys = [
            row.media_object_key
            for row in db.query(ZaloMedia).filter(ZaloMedia.id.in_(protected_media_ids)).all()
        ]
    return {
        "listener_generation": account.listener_generation,
        "policy_version": account.policy_version,
        "policy_acked_version": account.policy_acked_version,
        "source_sync_request_version": account.source_sync_request_version,
        "source_sync_acked_version": account.source_sync_acked_version,
        "sources": [
            {
                "conversation_id": source.conversation_id,
                "display_name": source.display_name,
                "source_type": source.source_type,
                "enabled": bool(source.enabled),
                "desired_enabled": bool(source.enabled),
                "acked_enabled": source.acked_enabled,
                "policy_version": source.policy_version,
            }
            for source in sources
        ],
        "protected_media_object_keys": protected_keys,
    }


@router.post("/api/connectors/{account_id}/consent")
def consent_intake(account_id: str, db: Session = Depends(get_db)):
    try:
        return {"policy_version": apply_intake_consent(db, account_id)}
    except InboxError as exc:
        _raise_http(exc)


@router.post("/api/connectors/{account_id}/sources/refresh")
def refresh_sources(account_id: str, db: Session = Depends(get_db)):
    try:
        return {"source_sync_request_version": request_source_sync(db, account_id)}
    except InboxError as exc:
        _raise_http(exc)


@router.get("/api/state")
def state_snapshot(db: Session = Depends(get_db)):
    connector_error = _connector_runtime_error()
    account = db.query(ZaloConnectorAccount).order_by(ZaloConnectorAccount.created_at.asc()).first()
    all_sources = (
        db.query(ZaloSource).filter(ZaloSource.connector_account_id == account.id).all() if account else []
    )
    sort_sources = lambda rows: sorted(
        rows,
        key=lambda source: (
            source.last_activity_at is None,
            -(_aware(source.last_activity_at).timestamp() if source.last_activity_at else 0),
            source.display_name.casefold(),
        ),
    )
    sources = sort_sources(source for source in all_sources if source.source_type != "stranger")
    stranger_sources = sort_sources(source for source in all_sources if source.source_type == "stranger")
    media_rows = (
        db.query(ZaloMedia)
        .join(ZaloSource, ZaloMedia.source_id == ZaloSource.id)
        .filter(
            ZaloSource.connector_account_id == account.id if account else False,
            ZaloSource.enabled.is_(True),
        )
        .order_by(ZaloMedia.sent_at.asc(), ZaloMedia.created_at.asc())
        .limit(500)
        .all()
    )
    latest = (
        db.query(ZaloBatch)
        .filter(ZaloBatch.connector_account_id == account.id)
        .order_by(ZaloBatch.created_at.desc())
        .first()
        if account
        else None
    )
    return {
        "connector": (
            {
                "id": account.id,
                "state": "disconnected" if connector_error else connector_state(account),
                "storage_full": bool(account.storage_full),
                "qr_image": None if connector_error else public_qr(account),
                "qr_generated_at": _as_iso(account.qr_generated_at),
                "qr_expires_at": _as_iso(account.qr_expires_at),
                "error": connector_error,
                "last_seen_at": _as_iso(account.last_seen_at),
            }
            if account
            else {
                "state": "login_required",
                "storage_full": False,
                "qr_image": None,
                "qr_generated_at": None,
                "qr_expires_at": None,
                "error": connector_error,
            }
        ),
        "consent_required": not bool(account and account.intake_consented_at),
        "my_documents_verification_required": True,
        "policy_pending": bool(
            account
            and (
                account.policy_version != account.policy_acked_version
                or any(not source_ready(source) for source in all_sources)
            )
        ),
        "sources": [
            {
                "id": source.id,
                "display_name": source.display_name,
                "conversation_type": source.conversation_type,
                "source_type": source.source_type,
                "last_activity_at": _as_iso(source.last_activity_at),
                "enabled": bool(source.enabled),
                "desired_enabled": bool(source.enabled),
                "acked_enabled": source.acked_enabled,
                "pending": not source_ready(source),
            }
            for source in sources
        ],
        "stranger_sources": [
            {
                "id": source.id,
                "display_name": source.display_name,
                "conversation_type": source.conversation_type,
                "source_type": source.source_type,
                "last_activity_at": _as_iso(source.last_activity_at),
                "enabled": bool(source.enabled),
                "desired_enabled": bool(source.enabled),
                "acked_enabled": source.acked_enabled,
                "pending": not source_ready(source),
            }
            for source in stranger_sources
        ],
        "media": [
            {
                "id": media.id,
                "source_id": media.source_id,
                "mime_type": media.mime_type,
                "size_bytes": media.size_bytes,
                "sent_at": _as_iso(media.sent_at),
                "content_url": f"/zalo-inbox/api/media/{media.id}/content",
            }
            for media in media_rows
        ],
        "latest_batch": (
            {
                "id": latest.id,
                "status": latest.status,
                "url": f"/zalo-inbox/batches/{latest.id}",
                "unfinished": _batch_unfinished(latest),
            }
            if latest
            else None
        ),
    }


@router.patch("/api/sources/{source_id}")
def toggle_source(source_id: str, body: SourceToggle, db: Session = Depends(get_db)):
    try:
        set_source_policy(db, source_id, body.enabled)
    except InboxError as exc:
        _raise_http(exc)
    source = db.query(ZaloSource).filter(ZaloSource.id == source_id).one()
    return {
        "id": source.id,
        "enabled": bool(source.enabled),
        "desired_enabled": bool(source.enabled),
        "acked_enabled": source.acked_enabled,
        "pending": not source_ready(source),
    }


@router.get("/api/media/{media_id}/content")
def media_content(media_id: str, db: Session = Depends(get_db)):
    media = db.query(ZaloMedia).filter(ZaloMedia.id == media_id).first()
    if media is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy media")
    try:
        path = resolve_media_object(
            _storage_root(),
            media.connector_account_id,
            media.media_object_key,
            media.mime_type,
            media.size_bytes,
        )
    except InboxError as exc:
        _raise_http(exc)
    return FileResponse(path, media_type=media.mime_type)


@router.post("/api/batches", status_code=202)
def new_batch(
    body: BatchCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
):
    try:
        batch = create_batch(
            db,
            body.media_ids,
            storage_root=_storage_root(),
            batch_root=_batch_root(),
            limits=InboxLimits.from_env(),
        )
    except InboxError as exc:
        _raise_http(exc)
    background_tasks.add_task(_prepare_job, batch.id, session_factory)
    return {"batch_id": batch.id, "url": f"/zalo-inbox/batches/{batch.id}"}


@router.get("/api/batches/{batch_id}")
def batch_snapshot(batch_id: str, db: Session = Depends(get_db)):
    batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lô")
    cleanup_expired_batch(db, batch.id, batch_root=_batch_root())
    db.refresh(batch)
    return _public_batch(batch)


@router.get("/api/batches/{batch_id}/items/{input_item_id}/preview")
def item_preview(batch_id: str, input_item_id: str, db: Session = Depends(get_db)):
    batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if batch is not None:
        cleanup_expired_batch(db, batch.id, batch_root=_batch_root())
        db.refresh(batch)
    item = next((value for value in (batch.items_json if batch else []) if value.get("input_item_id") == input_item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy item")
    path = Path(str(item.get("crop_path") if item.get("use_crop") and item.get("crop_path") else item.get("full_path") or ""))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Preview không còn")
    return FileResponse(path, media_type="image/jpeg")


@router.patch("/api/batches/{batch_id}/preview")
def save_preview(batch_id: str, body: PreviewUpdate, db: Session = Depends(get_db)):
    try:
        batch = update_preview(db, batch_id, [item.model_dump() for item in body.items])
    except InboxError as exc:
        _raise_http(exc)
    return _public_batch(batch)


@router.post("/api/batches/{batch_id}/outputs", status_code=202)
def select_outputs(
    batch_id: str,
    body: OutputSelection,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
):
    try:
        batch = freeze_outputs(db, batch_id, body.outputs)
    except InboxError as exc:
        _raise_http(exc)
    background_tasks.add_task(_output_job, batch.id, session_factory)
    return {"batch_id": batch.id, "selection": batch.selection_json}


@router.post("/api/batches/{batch_id}/confirm")
def confirm_ocr(batch_id: str, body: Confirmation, db: Session = Depends(get_db)):
    try:
        batch = confirm_batch(db, batch_id, body.model_dump(), batch_root=_batch_root())
    except InboxError as exc:
        _raise_http(exc)
    return _public_batch(batch)


@router.post("/api/batches/{batch_id}/retry", status_code=202)
def retry_step(
    batch_id: str,
    body: RetryRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
):
    batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lô")
    if body.step == "preparation" and batch.status == "error" and batch.selection_json is None:
        background_tasks.add_task(_prepare_job, batch.id, session_factory)
    elif body.step == "ocr" and batch.ocr_status == "error":
        errors = list((batch.raw_ocr_json or {}).get("errors") or [])
        if errors and all(str(error.get("stage") or "model") in {"parse", "pair", "shape"} for error in errors):
            try:
                retry_cached_ocr(db, batch.id, ocr_ai.shape_cached_ocr)
            except InboxError as exc:
                _raise_http(exc)
        else:
            batch.ocr_status = "running"
            db.commit()
            background_tasks.add_task(_output_job, batch.id, session_factory)
    elif body.step == "output" and body.output_type:
        try:
            retry_export(db, batch.id, body.output_type, batch_root=_batch_root())
        except InboxError as exc:
            _raise_http(exc)
    else:
        raise HTTPException(status_code=409, detail="Bước này không thể thử lại")
    return {"batch_id": batch.id, "step": body.step}


@router.get("/api/batches/{batch_id}/download/{output_type}")
def download_output(batch_id: str, output_type: str, db: Session = Depends(get_db)):
    batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if batch is not None:
        cleanup_expired_batch(db, batch.id, batch_root=_batch_root())
        db.refresh(batch)
    if batch is None or batch.status == "expired":
        raise HTTPException(status_code=404, detail="File không tồn tại hoặc đã hết hạn")
    output = dict(batch.outputs_json or {}).get(output_type) or {}
    path = Path(str(output.get("path") or ""))
    if output.get("status") != "ready" or not path.is_file():
        raise HTTPException(status_code=404, detail="File chưa sẵn sàng")
    return FileResponse(path, filename=str(output.get("filename") or path.name))
