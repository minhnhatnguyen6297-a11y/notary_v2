from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import fitz
from fastapi import UploadFile
from openpyxl import Workbook
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import ZaloBatch, ZaloConnectorAccount, ZaloDataSyncRun, ZaloMedia, ZaloMessageText, ZaloSource

UTC = timezone.utc
QR_TTL_SECONDS = 100
MY_DOCUMENTS_REALTIME_VERIFIED = False
SUPPORTED_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}
PERSON_FIELDS = (
    "ho_ten",
    "so_giay_to",
    "ngay_sinh",
    "gioi_tinh",
    "dia_chi",
    "ngay_cap",
    "noi_cap",
    "ngay_het_han",
    "place_of_origin",
    "ngay_chet",
)
PROPERTY_FIELDS = (
    "loai_so",
    "so_serial",
    "so_vao_so",
    "so_thua_dat",
    "so_to_ban_do",
    "dien_tich",
    "dia_chi",
    "chu_su_dung",
    "ngay_cap",
    "co_quan_cap",
    "loai_dat",
    "thoi_han",
    "hinh_thuc_su_dung",
    "nguon_goc",
)


class InboxError(Exception):
    pass


class InboxValidationError(InboxError):
    pass


class InboxConfigurationError(InboxError):
    pass


class InboxConflict(InboxError):
    pass


class InboxTerminalError(InboxError):
    pass


@dataclass(frozen=True)
class InboxLimits:
    max_file_bytes: int
    max_items: int
    max_total_bytes: int
    max_pixels: int

    @classmethod
    def from_env(cls) -> "InboxLimits":
        names = {
            "max_file_bytes": "ZALO_INBOX_MAX_FILE_BYTES",
            "max_items": "ZALO_INBOX_MAX_ITEMS",
            "max_total_bytes": "ZALO_INBOX_MAX_TOTAL_BYTES",
            "max_pixels": "ZALO_INBOX_MAX_RENDERED_PIXELS",
        }
        missing = [name for name in names.values() if not os.getenv(name)]
        if missing:
            raise InboxConfigurationError(f"Thiếu cấu hình triển khai: {', '.join(missing)}")
        try:
            values = {field: int(os.environ[name]) for field, name in names.items()}
        except ValueError as exc:
            raise InboxConfigurationError("Giới hạn Zalo Inbox phải là số nguyên") from exc
        if any(value <= 0 for value in values.values()):
            raise InboxConfigurationError("Giới hạn Zalo Inbox phải lớn hơn 0")
        return cls(**values)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _require_active_batch(batch: ZaloBatch, *, now: datetime | None = None) -> None:
    expires = _aware(batch.expires_at)
    if expires is not None and expires <= (_aware(now) or utcnow()):
        raise InboxConflict("Lô đã hết hạn")


def _iso(value: datetime) -> str:
    aware = _aware(value) or value
    return aware.isoformat().replace("+00:00", "Z")


def public_qr(account: ZaloConnectorAccount, *, now: datetime | None = None) -> str | None:
    if not account.qr_image:
        return None
    expires = _aware(account.qr_expires_at)
    if expires is None or expires <= (_aware(now) or utcnow()):
        return None
    return account.qr_image


def connector_state(
    account: ZaloConnectorAccount,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = 45,
) -> str:
    if account.session_state == "login_required":
        return "login_required"
    if account.session_state == "disconnected":
        return "disconnected"
    seen = _aware(account.last_seen_at)
    current = _aware(now) or utcnow()
    if seen is None or current - seen > timedelta(seconds=stale_after_seconds):
        return "disconnected"
    return "connected"


SOURCE_TYPES = {"friend", "group", "stranger", "my_documents"}


def _source_default(source_type: str | None) -> bool:
    return source_type in {"friend", "group", "my_documents"}


def _restage_policy_snapshot(db: Session, account: ZaloConnectorAccount) -> int:
    db.execute(
        update(ZaloConnectorAccount)
        .where(ZaloConnectorAccount.id == account.id)
        .values(policy_version=ZaloConnectorAccount.policy_version + 1)
    )
    db.flush()
    db.refresh(account)
    db.query(ZaloSource).filter(ZaloSource.connector_account_id == account.id).update(
        {ZaloSource.policy_version: account.policy_version}, synchronize_session=False
    )
    return account.policy_version


def _account_or_error(db: Session, account_id: str) -> ZaloConnectorAccount:
    account = db.query(ZaloConnectorAccount).filter(ZaloConnectorAccount.id == account_id).first()
    if account is None:
        raise InboxValidationError("connector_account_id chưa onboard")
    return account


def source_ready(source: ZaloSource) -> bool:
    return (
        source.acked_enabled is not None
        and source.policy_version == source.policy_acked_version
        and bool(source.enabled) == bool(source.acked_enabled)
    )


def apply_intake_consent(db: Session, account_id: str) -> int:
    account = _account_or_error(db, account_id)
    account.intake_consented_at = utcnow()
    for source in db.query(ZaloSource).filter(ZaloSource.connector_account_id == account.id).all():
        if source.enabled_explicit is None:
            source.enabled = _source_default(source.source_type)
            source.enabled_explicit = False
    _restage_policy_snapshot(db, account)
    db.commit()
    return account.policy_version


def set_source_policy(db: Session, source_id: str, enabled: bool) -> int:
    source = db.query(ZaloSource).filter(ZaloSource.id == source_id).first()
    if source is None:
        raise InboxValidationError("Không tìm thấy nguồn")
    account = _account_or_error(db, source.connector_account_id)
    source.enabled = bool(enabled)
    source.enabled_explicit = True
    _restage_policy_snapshot(db, account)
    db.commit()
    return account.policy_version


def ack_policy(db: Session, account_id: str, policy_version: int) -> int:
    account = _account_or_error(db, account_id)
    if policy_version != account.policy_version:
        raise InboxValidationError("policy_version không phải bản hiện hành")
    if policy_version == account.policy_acked_version:
        return policy_version
    for source in db.query(ZaloSource).filter(ZaloSource.connector_account_id == account.id):
        source.acked_enabled = bool(source.enabled)
        source.policy_acked_version = policy_version
    account.policy_acked_version = policy_version
    db.commit()
    return policy_version


def request_source_sync(db: Session, account_id: str) -> int:
    account = _account_or_error(db, account_id)
    db.execute(
        update(ZaloConnectorAccount)
        .where(ZaloConnectorAccount.id == account.id)
        .values(source_sync_request_version=ZaloConnectorAccount.source_sync_request_version + 1)
    )
    db.flush()
    db.refresh(account)
    db.commit()
    return account.source_sync_request_version


def ack_source_sync(db: Session, account_id: str, source_sync_request_version: int) -> int:
    account = _account_or_error(db, account_id)
    if source_sync_request_version != account.source_sync_request_version:
        raise InboxValidationError("source_sync_request_version không phải bản hiện hành")
    if source_sync_request_version == account.source_sync_acked_version:
        return source_sync_request_version
    account.source_sync_acked_version = source_sync_request_version
    db.commit()
    return source_sync_request_version


def _ack_version(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool):
        raise InboxValidationError(f"{field} không hợp lệ")
    if isinstance(value, str):
        try:
            value = int(value)
        except ValueError as exc:
            raise InboxValidationError(f"{field} không hợp lệ") from exc
    if not isinstance(value, int) or value < 0:
        raise InboxValidationError(f"{field} không hợp lệ")
    return value


def apply_connector_report(
    account: ZaloConnectorAccount,
    reported_state: str,
    generation: int,
    observed_at: datetime,
    *,
    qr_login_success: bool = False,
    qr_image: str | None = None,
    storage_full: bool | None = None,
    bound_zalo_id: str | None = None,
) -> bool:
    previous_generation = account.listener_generation or 0
    was_receiving = account.session_state == "usable"
    if generation < previous_generation:
        return False
    if reported_state not in {"connected", "login_required", "disconnected"}:
        raise InboxValidationError("Trạng thái connector không hợp lệ")
    incoming_zalo_id = str(bound_zalo_id or "").strip()
    if bound_zalo_id is not None and not incoming_zalo_id:
        raise InboxValidationError("Định danh tài khoản Zalo không hợp lệ")
    if incoming_zalo_id and account.bound_zalo_id and account.bound_zalo_id != incoming_zalo_id:
        raise InboxConflict("Connector đã bind với tài khoản Zalo khác")
    if qr_login_success:
        if not incoming_zalo_id:
            raise InboxValidationError("Thiếu định danh tài khoản Zalo")
        account.bound_zalo_id = incoming_zalo_id

    account.listener_generation = generation
    if qr_image is not None:
        account.qr_image = qr_image
        if qr_image:
            account.qr_generated_at = observed_at
            account.qr_expires_at = observed_at + timedelta(seconds=QR_TTL_SECONDS)
        else:
            account.qr_generated_at = None
            account.qr_expires_at = None
    if storage_full is not None:
        account.storage_full = storage_full

    if reported_state == "login_required":
        account.session_state = "login_required"
        account.last_seen_at = observed_at
        if was_receiving and account.gap_started_at is None:
            account.gap_started_at = observed_at
        return True
    if account.session_state == "login_required" and not qr_login_success:
        return False
    if reported_state == "disconnected":
        account.session_state = "disconnected"
        account.last_seen_at = observed_at
        if was_receiving and account.gap_started_at is None:
            account.gap_started_at = observed_at
        return True
    if reported_state == "connected":
        if was_receiving and generation > previous_generation and account.gap_started_at is None:
            account.gap_started_at = observed_at
        account.session_state = "usable"
        account.last_seen_at = observed_at
        if qr_login_success:
            account.qr_image = None
            account.qr_generated_at = None
            account.qr_expires_at = None
        return True
    return False


def verify_webhook_signature(
    body: bytes,
    timestamp: str,
    signature: str,
    secret: str,
    *,
    now: datetime | None = None,
    replay_window_seconds: int = 300,
) -> None:
    if not secret:
        raise InboxValidationError("Webhook secret chưa được cấu hình")
    try:
        sent_at = datetime.fromtimestamp(int(timestamp), tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise InboxValidationError("Webhook timestamp không hợp lệ") from exc
    current = _aware(now) or utcnow()
    if abs((current - sent_at).total_seconds()) > replay_window_seconds:
        raise InboxValidationError("Webhook replay window đã hết")
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        raise InboxValidationError("Webhook signature không hợp lệ")


def _canonical_digest(payload: dict[str, Any]) -> str:
    packed = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(packed.encode()).hexdigest()


def _uuid() -> str:
    return str(uuid.uuid4())


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _aware(value) or value
    if not isinstance(value, str):
        raise InboxValidationError("Timestamp bắt buộc")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise InboxValidationError("Timestamp không hợp lệ") from exc


def resolve_media_object(
    storage_root: str | Path,
    connector_account_id: str,
    media_object_key: str,
    mime_type: str,
    size_bytes: int,
) -> Path:
    if mime_type not in SUPPORTED_MIME:
        raise InboxValidationError("Loại media không được hỗ trợ")
    key = Path(media_object_key)
    if key.is_absolute() or ".." in key.parts or not key.parts or key.parts[0] != connector_account_id:
        raise InboxValidationError("media_object_key nằm ngoài storage cho phép")
    root = Path(storage_root).resolve()
    path = (root / key).resolve()
    if root != path and root not in path.parents:
        raise InboxValidationError("media_object_key nằm ngoài storage cho phép")
    if not path.is_file():
        raise InboxValidationError("File nguồn không còn")
    actual_size = path.stat().st_size
    if actual_size != int(size_bytes):
        raise InboxValidationError("Kích thước media không khớp metadata")
    prefix = path.read_bytes()[:8]
    matches = {
        "image/jpeg": prefix.startswith(b"\xff\xd8\xff"),
        "image/png": prefix.startswith(b"\x89PNG\r\n\x1a\n"),
        "application/pdf": prefix.startswith(b"%PDF-"),
    }
    if not matches[mime_type]:
        raise InboxValidationError("Nội dung media không khớp MIME")
    return path


def _source_from_payload(db: Session, payload: dict[str, Any], *, require_source_type: bool = False) -> ZaloSource:
    account_id = str(payload.get("connector_account_id") or "")
    conversation_id = str(payload.get("conversation_id") or "")
    conversation_type = str(payload.get("conversation_type") or "")
    display_name = str(payload.get("source_display_name") or "").strip()
    source_type = str(payload.get("source_type") or "")
    if (
        not account_id
        or not conversation_id
        or conversation_type not in {"user", "group"}
        or not display_name
        or (require_source_type and source_type not in SOURCE_TYPES)
    ):
        if require_source_type and source_type not in SOURCE_TYPES:
            raise InboxValidationError("source_type không hợp lệ")
        raise InboxValidationError("Metadata nguồn không hợp lệ")
    last_activity_provided = "last_activity_at" in payload
    last_activity = payload.get("last_activity_at")
    if last_activity is not None:
        last_activity = _parse_timestamp(last_activity)
    account = _account_or_error(db, account_id)
    source = (
        db.query(ZaloSource)
        .filter(
            ZaloSource.connector_account_id == account_id,
            ZaloSource.conversation_id == conversation_id,
        )
        .first()
    )
    if source is None:
        enabled = _source_default(source_type) if account.intake_consented_at and source_type else False
        source = ZaloSource(
            id=_uuid(),
            connector_account_id=account_id,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            display_name=display_name,
            source_type=source_type or None,
            enabled=enabled,
            enabled_explicit=False if account.intake_consented_at else None,
            policy_version=account.policy_version,
            last_activity_at=last_activity,
        )
        db.add(source)
        db.flush()
        if account.intake_consented_at:
            _restage_policy_snapshot(db, account)
        if account.intake_consented_at is None:
            db.query(ZaloSource).filter(ZaloSource.id == source.id).update(
                {ZaloSource.enabled_explicit: None}, synchronize_session=False
            )
            db.refresh(source)
    else:
        source.display_name = display_name
        source.conversation_type = conversation_type
        if last_activity_provided:
            source.last_activity_at = last_activity
        if source_type:
            default_enabled = _source_default(source_type)
            if account.intake_consented_at and source.enabled_explicit is not True and source.enabled != default_enabled:
                source.enabled = default_enabled
                _restage_policy_snapshot(db, account)
            source.source_type = source_type
    return source


def _positive_env_int(name: str) -> int:
    try:
        value = int(os.environ[name])
    except (KeyError, ValueError) as exc:
        raise InboxConfigurationError(f"{name} phải là số nguyên dương") from exc
    if value <= 0:
        raise InboxConfigurationError(f"{name} phải là số nguyên dương")
    return value


DATA_SYNC_COUNTERS = (
    "received", "duplicates", "imported_text", "imported_media", "media_download_failures",
)


def start_data_sync(db: Session, account_id: str, now: datetime | None = None) -> ZaloDataSyncRun:
    account = _account_or_error(db, account_id)
    current = _aware(now) or utcnow()
    sources = db.query(ZaloSource).filter(ZaloSource.connector_account_id == account.id).all()
    if account.intake_consented_at is None:
        raise InboxValidationError("Chưa đồng ý tiếp nhận dữ liệu")
    if connector_state(account, now=current) != "connected":
        raise InboxConflict("Connector chưa kết nối")
    if account.policy_version != account.policy_acked_version or any(not source_ready(source) for source in sources):
        raise InboxConflict("Chính sách nguồn đang chờ đồng bộ")
    source_ids = sorted(
        source.conversation_id for source in sources
        if source.enabled and source.acked_enabled and source_ready(source)
        and source.source_type != "my_documents"
    )
    if not source_ids:
        raise InboxValidationError("Không có nguồn phù hợp để đồng bộ")
    run = ZaloDataSyncRun(
        id=_uuid(), connector_account_id=account.id, status="running",
        cutoff_at=current,
        deadline_at=current + timedelta(seconds=_positive_env_int("ZALO_DATA_SYNC_TIMEOUT_SECONDS")),
        source_ids_json=source_ids,
        counters_json={key: 0 for key in DATA_SYNC_COUNTERS},
        started_at=current,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "zalo_data_sync_runs.connector_account_id" not in str(getattr(exc, "orig", exc)).lower():
            raise
        raise InboxConflict("Đang có Data Sync hoạt động") from exc
    db.refresh(run)
    return run


def _timeout_data_sync_run(db: Session, run: ZaloDataSyncRun, account_id: str, current: datetime) -> bool:
    return db.query(ZaloDataSyncRun).filter(
            ZaloDataSyncRun.id == run.id,
            ZaloDataSyncRun.connector_account_id == account_id,
            ZaloDataSyncRun.status == "running",
            ZaloDataSyncRun.deadline_at <= current,
        ).update(
            {
                ZaloDataSyncRun.status: "error",
                ZaloDataSyncRun.error_message: "timeout",
                ZaloDataSyncRun.completed_at: current,
            },
            synchronize_session=False,
        ) == 1


def data_sync_command(db: Session, account_id: str, now: datetime | None = None) -> dict[str, Any] | None:
    run = db.query(ZaloDataSyncRun).filter_by(connector_account_id=account_id, status="running").first()
    if run is None:
        return None
    current = _aware(now) or utcnow()
    if (_aware(run.deadline_at) or run.deadline_at) <= current:
        if _timeout_data_sync_run(db, run, account_id, current):
            db.commit()
        else:
            db.rollback()
            db.expire_all()
        return None
    return {
        "command_type": "data_sync", "run_id": run.id,
        "cutoff_at": _iso(run.cutoff_at), "deadline_at": _iso(run.deadline_at),
        "source_ids": run.source_ids_json,
    }


def apply_data_sync_report(db: Session, payload: dict[str, Any]) -> ZaloDataSyncRun:
    event_type = payload.get("event_type")
    expected = {"schema_version", "event_type", "connector_account_id", "run_id", "counters"}
    if event_type == "data_sync_failed":
        expected.add("error_code")
    if payload.get("schema_version") != 1 or set(payload) != expected:
        raise InboxValidationError("Data Sync report không hợp lệ")
    if event_type not in {"data_sync_progress", "data_sync_complete", "data_sync_failed"}:
        raise InboxValidationError("Data Sync event không hợp lệ")
    counters = payload.get("counters")
    if not isinstance(counters, dict) or set(counters) != set(DATA_SYNC_COUNTERS) or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counters.values()
    ):
        raise InboxValidationError("Data Sync counters không hợp lệ")
    error_code = payload.get("error_code")
    if event_type == "data_sync_failed" and (
        not isinstance(error_code, str) or not re.fullmatch(r"[a-z0-9_]{1,64}", error_code)
    ):
        raise InboxValidationError("Data Sync error_code không hợp lệ")
    run_id = str(payload.get("run_id") or "")
    account_id = str(payload.get("connector_account_id") or "")
    terminal_status = {"data_sync_complete": "completed_best_effort", "data_sync_failed": "error"}.get(event_type)
    for _attempt in range(3):
        db.expire_all()
        run = db.query(ZaloDataSyncRun).filter_by(id=run_id).first()
        if run is None or run.connector_account_id != account_id:
            raise InboxConflict("Data Sync report không khớp account/run")
        if run.status != "running":
            if terminal_status == run.status and run.counters_json == counters and run.error_message == error_code:
                return run
            raise InboxConflict("Data Sync run đã kết thúc")
        current = utcnow()
        if (_aware(run.deadline_at) or run.deadline_at) <= current:
            if _timeout_data_sync_run(db, run, account_id, current):
                db.commit()
                raise InboxConflict("Data Sync run đã hết hạn")
            db.rollback()
            continue
        prior_counters = dict(run.counters_json)
        if any(counters[key] < prior_counters[key] for key in DATA_SYNC_COUNTERS):
            raise InboxConflict("Data Sync counters không được giảm")
        values = {ZaloDataSyncRun.counters_json: dict(counters)}
        if terminal_status:
            values.update({
                ZaloDataSyncRun.status: terminal_status,
                ZaloDataSyncRun.error_message: error_code,
                ZaloDataSyncRun.completed_at: utcnow(),
            })
        updated = db.query(ZaloDataSyncRun).filter(
            ZaloDataSyncRun.id == run_id,
            ZaloDataSyncRun.connector_account_id == account_id,
            ZaloDataSyncRun.status == "running",
            ZaloDataSyncRun.counters_json == prior_counters,
        ).update(values, synchronize_session=False)
        if updated == 1:
            db.commit()
            db.expire_all()
            return db.query(ZaloDataSyncRun).filter_by(id=run_id).one()
        db.rollback()
    raise InboxConflict("Data Sync report xung đột đồng thời")


def ingest_message_envelope(db: Session, payload: dict[str, Any], storage_root: str | Path) -> dict[str, Any]:
    required = ("connector_account_id", "conversation_id", "conversation_type", "source_type", "source_display_name", "msg_id", "sender_id", "sent_at")
    if payload.get("schema_version") != 1 or payload.get("event_type") != "message" or any(payload.get(field) is None for field in required):
        raise InboxValidationError("Message envelope thiếu field bắt buộc")
    account_id = str(payload["connector_account_id"])
    conversation_id = str(payload["conversation_id"])
    msg_id = str(payload["msg_id"])
    sender_id = str(payload["sender_id"])
    if not account_id or not conversation_id or not msg_id or not sender_id:
        raise InboxValidationError("Message envelope có định danh không hợp lệ")
    account = _account_or_error(db, account_id)
    sent_at = _parse_timestamp(payload["sent_at"])
    raw_text = payload.get("raw_text")
    if raw_text is not None and not isinstance(raw_text, str):
        raise InboxValidationError("raw_text không hợp lệ")
    attachments = payload.get("attachments", [])
    if not isinstance(attachments, list):
        raise InboxValidationError("attachments không hợp lệ")

    checked: list[tuple[dict[str, Any], int, str]] = []
    indexes: set[int] = set()
    for attachment in attachments:
        if not isinstance(attachment, dict) or any(attachment.get(field) is None for field in ("attachment_index", "media_object_key", "mime_type", "size_bytes")):
            raise InboxValidationError("Attachment thiếu field bắt buộc")
        index = attachment["attachment_index"]
        size = attachment["size_bytes"]
        if isinstance(index, bool) or not isinstance(index, int) or index < 0 or index in indexes:
            raise InboxValidationError("attachment_index không hợp lệ")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise InboxValidationError("size_bytes không hợp lệ")
        indexes.add(index)
        resolve_media_object(storage_root, account_id, str(attachment["media_object_key"]), str(attachment["mime_type"]), size)
        component = {
            "connector_account_id": account_id,
            "conversation_id": conversation_id,
            "msg_id": msg_id,
            "attachment_index": index,
            "media_object_key": str(attachment["media_object_key"]),
            "mime_type": str(attachment["mime_type"]),
            "size_bytes": size,
            "sent_at": _iso(sent_at),
        }
        checked.append((component, index, _canonical_digest(component)))

    text_component = {
        "connector_account_id": account_id,
        "conversation_id": conversation_id,
        "msg_id": msg_id,
        "sender_id": sender_id,
        "sent_at": _iso(sent_at),
        "raw_text": raw_text,
    }
    existing_text = None
    if raw_text is not None:
        existing_text = db.query(ZaloMessageText).filter_by(
            connector_account_id=account_id, conversation_id=conversation_id, msg_id=msg_id
        ).first()
        if existing_text is not None and existing_text.payload_digest != _canonical_digest(text_component):
            raise InboxConflict("Message text trùng khóa nhưng payload khác")
    existing_media: dict[int, ZaloMedia] = {}
    for _component, index, digest in checked:
        row = db.query(ZaloMedia).filter_by(
            connector_account_id=account_id, conversation_id=conversation_id, msg_id=msg_id, attachment_index=index
        ).first()
        if row is not None and row.payload_digest != digest:
            raise InboxConflict("Message media trùng khóa nhưng payload khác")
        if row is not None:
            existing_media[index] = row

    source_payload = dict(payload, last_activity_at=_iso(sent_at))
    source = _source_from_payload(db, source_payload, require_source_type=True)
    eligible = (
        account.intake_consented_at is not None
        and source_ready(source)
        and bool(source.enabled)
        and source.source_type != "stranger"
        and (source.source_type != "my_documents" or MY_DOCUMENTS_REALTIME_VERIFIED)
    )
    text_status = "absent" if raw_text is None else ("duplicate" if existing_text is not None else "ignored")
    media_statuses = [
        {"attachment_index": index, "status": "duplicate" if index in existing_media else "ignored"}
        for _component, index, _digest in checked
    ]
    text_id = existing_text.id if existing_text is not None else None
    media_ids = [existing_media[index].id for _component, index, _digest in checked if index in existing_media]

    if eligible:
        if raw_text is not None and existing_text is None:
            try:
                quota = _positive_env_int("ZALO_INBOX_TEXT_QUOTA_BYTES")
                retention = _positive_env_int("ZALO_INBOX_TEXT_RETENTION_HOURS")
            except InboxConfigurationError:
                account.text_storage_full = True
            else:
                cutoff = utcnow() - timedelta(hours=retention)
                db.query(ZaloMessageText).filter(ZaloMessageText.received_at < cutoff).delete(synchronize_session=False)
                rows = db.query(ZaloMessageText).filter(ZaloMessageText.connector_account_id == account_id).order_by(ZaloMessageText.received_at.asc()).all()
                needed = len(raw_text.encode("utf-8"))
                usage = sum(len(row.raw_text.encode("utf-8")) for row in rows)
                if needed <= quota:
                    for row in rows:
                        if usage + needed <= quota:
                            break
                        usage -= len(row.raw_text.encode("utf-8"))
                        db.delete(row)
                if needed <= quota and usage + needed <= quota:
                    text = ZaloMessageText(
                        id=_uuid(), connector_account_id=account_id, source_id=source.id,
                        conversation_id=conversation_id, msg_id=msg_id, sender_id=sender_id,
                        sent_at=sent_at, received_at=utcnow(), raw_text=raw_text,
                        payload_digest=_canonical_digest(text_component),
                    )
                    db.add(text)
                    text_id = text.id
                    text_status = "imported"
                    account.text_storage_full = False
                else:
                    account.text_storage_full = True
        for component, index, digest in checked:
            if index in existing_media:
                continue
            media = ZaloMedia(
                id=_uuid(), connector_account_id=account_id, source_id=source.id,
                conversation_id=conversation_id, msg_id=msg_id, attachment_index=index,
                media_object_key=component["media_object_key"], mime_type=component["mime_type"],
                size_bytes=component["size_bytes"], sent_at=sent_at, payload_digest=digest,
            )
            db.add(media)
            media_ids.append(media.id)
            next(item for item in media_statuses if item["attachment_index"] == index)["status"] = "imported"
    db.commit()
    return {
        "text_id": text_id,
        "media_ids": media_ids,
        "ignored": not eligible,
        "components": {"text": text_status, "media": media_statuses},
    }


def ingest_webhook_event(db: Session, payload: dict[str, Any], *, storage_root: str | Path) -> Any:
    if payload.get("schema_version") != 1:
        raise InboxValidationError("schema_version không được hỗ trợ")
    event_type = payload.get("event_type")
    account_id = str(payload.get("connector_account_id") or "")
    account = db.query(ZaloConnectorAccount).filter(ZaloConnectorAccount.id == account_id).first()
    if account is None:
        raise InboxValidationError("connector_account_id chưa onboard")

    if event_type == "discovery":
        source = _source_from_payload(db, payload, require_source_type=True)
        db.commit()
        return source
    if event_type == "policy_ack":
        if set(payload) != {"schema_version", "event_type", "connector_account_id", "policy_version"}:
            raise InboxValidationError("policy_ack không hợp lệ")
        return {"policy_version": ack_policy(db, account_id, _ack_version(payload, "policy_version"))}
    if event_type == "source_sync_ack":
        if set(payload) != {"schema_version", "event_type", "connector_account_id", "source_sync_request_version"}:
            raise InboxValidationError("source_sync_ack không hợp lệ")
        return {
            "source_sync_request_version": ack_source_sync(
                db, account_id, _ack_version(payload, "source_sync_request_version")
            )
        }
    if event_type in {"heartbeat", "state"}:
        _parse_timestamp(payload.get("observed_at"))
        received_at = utcnow()
        changed = apply_connector_report(
            account,
            str(payload.get("state") or ""),
            int(payload.get("listener_generation", 0)),
            received_at,
            qr_login_success=bool(payload.get("qr_login_success")),
            qr_image=payload.get("qr_image"),
            storage_full=payload.get("storage_full"),
            bound_zalo_id=payload.get("bound_zalo_id"),
        )
        db.commit()
        return {"changed": changed, "state": connector_state(account)}
    if event_type == "message":
        return ingest_message_envelope(db, payload, storage_root)
    if event_type in {"data_sync_progress", "data_sync_complete", "data_sync_failed"}:
        return apply_data_sync_report(db, payload)
    if event_type != "media":
        raise InboxValidationError("event_type không được hỗ trợ")

    required = ("msg_id", "attachment_index", "media_object_key", "mime_type", "size_bytes", "sent_at")
    if any(payload.get(field) is None for field in required):
        raise InboxValidationError("Webhook media thiếu field bắt buộc")
    digest = _canonical_digest(payload)
    existing = (
        db.query(ZaloMedia)
        .filter(
            ZaloMedia.connector_account_id == account_id,
            ZaloMedia.conversation_id == str(payload["conversation_id"]),
            ZaloMedia.msg_id == str(payload["msg_id"]),
            ZaloMedia.attachment_index == int(payload["attachment_index"]),
        )
        .first()
    )
    if existing is not None:
        if existing.payload_digest != digest:
            raise InboxConflict("Webhook trùng khóa nhưng payload khác")
        return existing

    source = _source_from_payload(db, payload)
    if account.intake_consented_at is None or not source_ready(source) or not source.enabled:
        db.commit()
        return {"ignored": True}
    resolve_media_object(
        storage_root,
        account_id,
        str(payload["media_object_key"]),
        str(payload["mime_type"]),
        int(payload["size_bytes"]),
    )

    media = ZaloMedia(
        id=_uuid(),
        connector_account_id=account_id,
        source_id=source.id,
        conversation_id=str(payload["conversation_id"]),
        msg_id=str(payload["msg_id"]),
        attachment_index=int(payload["attachment_index"]),
        media_object_key=str(payload["media_object_key"]),
        mime_type=str(payload["mime_type"]),
        size_bytes=int(payload["size_bytes"]),
        sent_at=_parse_timestamp(payload["sent_at"]),
        payload_digest=digest,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def _inspect_media(path: Path, mime_type: str) -> tuple[int, int]:
    if mime_type == "application/pdf":
        try:
            document = fitz.open(path)
            if document.needs_pass:
                raise InboxValidationError("PDF có mật khẩu")
            pages = document.page_count
            pixels = 0
            for page in document:
                rect = page.rect
                pixels += int(rect.width * 2) * int(rect.height * 2)
            document.close()
            if pages < 1:
                raise InboxValidationError("PDF không có trang")
            return pages, pixels
        except InboxValidationError:
            raise
        except Exception as exc:
            raise InboxValidationError("PDF hỏng hoặc không đọc được") from exc
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            return 1, image.width * image.height
    except Exception as exc:
        raise InboxValidationError("Ảnh hỏng hoặc không đọc được") from exc


def create_batch(
    db: Session,
    media_ids: list[str],
    *,
    storage_root: str | Path,
    batch_root: str | Path,
    limits: InboxLimits | None = None,
    now: datetime | None = None,
) -> ZaloBatch:
    limits = limits or InboxLimits.from_env()
    if not media_ids or len(media_ids) != len(set(media_ids)):
        raise InboxValidationError("Lô phải có media duy nhất")
    media_rows = db.query(ZaloMedia).filter(ZaloMedia.id.in_(media_ids)).all()
    by_id = {row.id: row for row in media_rows}
    if len(by_id) != len(media_ids):
        raise InboxValidationError("Media không tồn tại")
    ordered = [by_id[media_id] for media_id in media_ids]
    account_ids = {row.connector_account_id for row in ordered}
    if len(account_ids) != 1:
        raise InboxValidationError("Lô không được trộn connector account")

    checked: list[tuple[ZaloMedia, Path, int]] = []
    total_bytes = 0
    total_items = 0
    total_pixels = 0
    for row in ordered:
        if row.size_bytes > limits.max_file_bytes:
            raise InboxValidationError(f"File vượt giới hạn {limits.max_file_bytes} bytes")
        path = resolve_media_object(storage_root, row.connector_account_id, row.media_object_key, row.mime_type, row.size_bytes)
        item_count, pixels = _inspect_media(path, row.mime_type)
        total_bytes += row.size_bytes
        total_items += item_count
        total_pixels += pixels
        if total_bytes > limits.max_total_bytes:
            raise InboxValidationError("Lô vượt giới hạn tổng dung lượng")
        if total_items > limits.max_items:
            raise InboxValidationError("Lô vượt giới hạn ảnh/trang")
        if total_pixels > limits.max_pixels:
            raise InboxValidationError("Lô vượt giới hạn pixel")
        checked.append((row, path, item_count))

    created = _aware(now) or utcnow()
    batch_id = _uuid()
    batch_dir = Path(batch_root) / batch_id
    source_dir = batch_dir / "source"
    items: list[dict[str, Any]] = []
    try:
        source_dir.mkdir(parents=True, exist_ok=False)
        for order, (row, source_path, page_count) in enumerate(checked):
            suffix = SUPPORTED_MIME[row.mime_type]
            copied = source_dir / f"{order:03d}{suffix}"
            shutil.copy2(source_path, copied)
            source = db.query(ZaloSource).filter(ZaloSource.id == row.source_id).first()
            items.append(
                {
                    "input_item_id": _uuid(),
                    "source_media_id": row.id,
                    "source_display_name": source.display_name if source else "",
                    "sent_at": _iso(row.sent_at),
                    "mime_type": row.mime_type,
                    "source_path": str(copied),
                    "page_count": page_count if row.mime_type == "application/pdf" else None,
                    "page_number": None,
                    "order": order,
                    "status": "pending",
                    "use_crop": False,
                }
            )
        batch = ZaloBatch(
            id=batch_id,
            connector_account_id=ordered[0].connector_account_id,
            status="preparing",
            items_json=items,
            selection_json=None,
            outputs_json={},
            ocr_status="not_selected",
            created_at=created,
            expires_at=created + timedelta(hours=72),
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)
        return batch
    except Exception:
        db.rollback()
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise


def _proposed_crop(image: Image.Image) -> tuple[int, int, int, int] | None:
    gray = ImageOps.autocontrast(ImageOps.grayscale(image))
    inverted = ImageOps.invert(gray)
    mask = inverted.point(lambda value: 255 if value > 24 else 0)
    bbox = mask.getbbox()
    if not bbox:
        return None
    width, height = image.size
    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    ratio = area / max(1, width * height)
    if ratio < 0.40 or ratio > 0.97:
        return None
    return bbox


def _write_processed_image(image: Image.Image, target_dir: Path, input_item_id: str) -> tuple[Path, Path | None]:
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
    image = image.filter(ImageFilter.MedianFilter(size=3))
    image = ImageEnhance.Contrast(image).enhance(1.12)
    full_path = target_dir / f"{input_item_id}-full.jpg"
    image.save(full_path, "JPEG", quality=90, optimize=True)
    bbox = _proposed_crop(image)
    if bbox is None:
        return full_path, None
    crop_path = target_dir / f"{input_item_id}-crop.jpg"
    image.crop(bbox).save(crop_path, "JPEG", quality=90, optimize=True)
    return full_path, crop_path


def prepare_batch(db: Session, batch_id: str, *, batch_root: str | Path) -> ZaloBatch:
    batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if batch is None:
        raise InboxValidationError("Không tìm thấy lô")
    _require_active_batch(batch)
    if batch.status not in {"preparing", "error"}:
        return batch
    processed_dir = Path(batch_root) / batch.id / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    output_items: list[dict[str, Any]] = []
    any_error = False

    for original in sorted(batch.items_json or [], key=lambda item: item["order"]):
        if original.get("status") == "ready":
            output_items.append(dict(original))
            continue
        source_path = Path(original["source_path"])
        generated: list[Path] = []
        try:
            if original["mime_type"] == "application/pdf":
                document = fitz.open(source_path)
                page_items: list[dict[str, Any]] = []
                for index, page in enumerate(document):
                    item_id = _uuid()
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    rendered = processed_dir / f"{item_id}-rendered.png"
                    pixmap.save(rendered)
                    generated.append(rendered)
                    with Image.open(rendered) as image:
                        full_path, crop_path = _write_processed_image(image, processed_dir, item_id)
                    generated.extend(path for path in (full_path, crop_path) if path)
                    page_items.append(
                        {
                            **{key: value for key, value in original.items() if key not in {"input_item_id", "status"}},
                            "input_item_id": item_id,
                            "page_number": index + 1,
                            "page_count": document.page_count,
                            "full_path": str(full_path),
                            "crop_path": str(crop_path) if crop_path else None,
                            "use_crop": bool(crop_path),
                            "status": "ready",
                        }
                    )
                document.close()
                output_items.extend(page_items)
            else:
                item_id = original["input_item_id"]
                with Image.open(source_path) as image:
                    full_path, crop_path = _write_processed_image(image, processed_dir, item_id)
                output_items.append(
                    {
                        **original,
                        "full_path": str(full_path),
                        "crop_path": str(crop_path) if crop_path else None,
                        "use_crop": bool(crop_path),
                        "status": "ready",
                    }
                )
        except Exception as exc:
            any_error = True
            for generated_path in generated:
                generated_path.unlink(missing_ok=True)
            output_items.append({**original, "status": "error", "error": str(exc)[:240]})

    for order, item in enumerate(output_items):
        item["order"] = order
    batch.items_json = output_items
    batch.status = "error" if any_error else "review"
    batch.error_message = "Có item chuẩn bị lỗi" if any_error else None
    db.commit()
    db.refresh(batch)
    return batch


def freeze_outputs(db: Session, batch_id: str, outputs: list[str]) -> ZaloBatch:
    selected = sorted(set(outputs))
    if not selected or any(output not in {"json", "excel", "pdf"} for output in selected):
        raise InboxValidationError("Output không hợp lệ")
    current = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if current is None:
        raise InboxValidationError("Không tìm thấy lô")
    _require_active_batch(current)
    if current.selection_json is not None:
        if sorted(current.selection_json) == selected:
            return current
        raise InboxConflict("Output của lô đã được chốt")
    if current.status != "review" or not current.items_json or any(item.get("status") != "ready" for item in current.items_json):
        raise InboxConflict("Lô chưa sẵn sàng để chốt output")

    output_state = {output: {"status": "creating", "retryable": True} for output in selected}
    updated = (
        db.query(ZaloBatch)
        .filter(ZaloBatch.id == batch_id, ZaloBatch.selection_json.is_(None), ZaloBatch.status == "review")
        .update(
            {
                ZaloBatch.selection_json: selected,
                ZaloBatch.outputs_json: output_state,
                ZaloBatch.status: "processing",
                ZaloBatch.ocr_status: "running" if {"json", "excel"} & set(selected) else "not_selected",
            },
            synchronize_session=False,
        )
    )
    db.commit()
    db.expire_all()
    frozen = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if updated == 1:
        return frozen
    if frozen is not None and sorted(frozen.selection_json or []) == selected:
        return frozen
    raise InboxConflict("Output của lô đã được chốt")


def cleanup_expired_batch(
    db: Session,
    batch_id: str,
    *,
    batch_root: str | Path,
    now: datetime | None = None,
) -> bool:
    batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if batch is None or batch.status == "expired":
        return False
    current = _aware(now) or utcnow()
    expires = _aware(batch.expires_at)
    if expires is None or current < expires:
        return False
    shutil.rmtree(Path(batch_root) / batch.id, ignore_errors=True)
    batch.status = "expired"
    batch.items_json = []
    batch.selection_json = None
    batch.raw_ocr_json = None
    batch.confirmed_json = None
    batch.ocr_status = "expired"
    batch.error_message = None
    batch.outputs_json = {name: {"status": "expired"} for name in (batch.outputs_json or {})}
    db.commit()
    return True


def _provenance(raw_results: list[dict[str, Any]], refs: list[str]) -> tuple[str, str, str]:
    by_id = {str(item.get("input_item_id")): item for item in raw_results}
    names: list[str] = []
    sent_values: list[str] = []
    pages: list[str] = []
    for ref in refs:
        item = by_id.get(str(ref), {})
        name = str(item.get("source_display_name") or "")
        sent = str(item.get("sent_at") or "")
        page = ""
        if item.get("page_number"):
            page = f"{item['page_number']}/{item.get('page_count') or item['page_number']}"
        for value, target in ((name, names), (sent, sent_values), (page, pages)):
            if value and value not in target:
                target.append(value)
    return "; ".join(names), "; ".join(sent_values), "; ".join(pages)


def write_excel_export(data: dict[str, Any], path: str | Path) -> Path:
    persons = list(data.get("persons") or [])
    properties = list(data.get("properties") or [])
    if not persons and not properties:
        raise InboxTerminalError("Không có dữ liệu để xuất Excel")
    workbook = Workbook()
    workbook.remove(workbook.active)
    raw_results = list(data.get("raw_results") or [])

    def add_sheet(name: str, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
        if not rows:
            return
        sheet = workbook.create_sheet(name)
        headers = [*fields, "Nguồn", "Thời điểm", "Trang"]
        sheet.append(headers)
        for row in rows:
            source_name, sent_at, page = _provenance(raw_results, list(row.get("source_refs") or []))
            sheet.append([*[row.get(field, "") for field in fields], source_name, sent_at, page])

    add_sheet("Nguoi", persons, PERSON_FIELDS)
    add_sheet("So_do", properties, PROPERTY_FIELDS)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)
    return output


def export_filename(batch_id: str, output_type: str, created_at: datetime) -> str:
    local = (_aware(created_at) or created_at).astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    return f"lo-{local:%Y%m%d-%H%M}-{batch_id[:6]}.{output_type}"


def update_preview(db: Session, batch_id: str, requested_items: list[dict[str, Any]]) -> ZaloBatch:
    batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if batch is None:
        raise InboxValidationError("Không tìm thấy lô")
    _require_active_batch(batch)
    if batch.selection_json is not None:
        raise InboxConflict("Preview đã đóng băng")
    if batch.status not in {"review", "error"}:
        raise InboxConflict("Preview chưa sẵn sàng")
    ids = [str(item.get("input_item_id") or "") for item in requested_items]
    if len(ids) != len(set(ids)):
        raise InboxValidationError("Preview chứa item trùng")
    current = {str(item["input_item_id"]): item for item in (batch.items_json or [])}
    if any(item_id not in current for item_id in ids):
        raise InboxValidationError("Preview chứa item không thuộc lô")

    updated: list[dict[str, Any]] = []
    for order, patch in enumerate(requested_items):
        item = dict(current[str(patch["input_item_id"])])
        use_crop = bool(patch.get("use_crop")) and bool(item.get("crop_path"))
        item["use_crop"] = use_crop
        item["order"] = order
        updated.append(item)
    batch.items_json = updated
    batch.status = "error" if any(item.get("status") == "error" for item in updated) else "review"
    batch.error_message = "Có item chuẩn bị lỗi" if batch.status == "error" else None
    db.commit()
    db.refresh(batch)
    return batch


def _selected_image_path(item: dict[str, Any]) -> Path:
    selected = item.get("crop_path") if item.get("use_crop") and item.get("crop_path") else item.get("full_path")
    path = Path(str(selected or ""))
    if not path.is_file():
        raise InboxValidationError("Ảnh xử lý không còn")
    return path


def _write_pdf(items: list[dict[str, Any]], path: Path) -> None:
    images: list[Image.Image] = []
    try:
        for item in sorted(items, key=lambda value: value["order"]):
            with Image.open(_selected_image_path(item)) as opened:
                images.append(opened.convert("RGB").copy())
        if not images:
            raise InboxValidationError("Lô không còn item")
        path.parent.mkdir(parents=True, exist_ok=True)
        images[0].save(path, "PDF", save_all=True, append_images=images[1:], resolution=150.0)
    finally:
        for image in images:
            image.close()


def _materialize_ocr(result: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    item_by_id = {str(item["input_item_id"]): item for item in items}
    raw_results: list[dict[str, Any]] = []
    for raw in list(result.get("raw_results") or []):
        input_id = str(raw.get("filename") or raw.get("input_item_id") or "")
        item = item_by_id.get(input_id)
        if item is None:
            continue
        raw_results.append(
            {
                **raw,
                "filename": input_id,
                "input_item_id": input_id,
                "source_display_name": item.get("source_display_name", ""),
                "sent_at": item.get("sent_at", ""),
                "page_number": item.get("page_number"),
                "page_count": item.get("page_count"),
            }
        )

    def normalized(rows: Any) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for row in list(rows or []):
            candidates = row.get("source_refs") or row.get("_files") or [row.get("_file")]
            refs = []
            for value in candidates:
                ref = str(value or "")
                if ref in item_by_id and ref not in refs:
                    refs.append(ref)
            output.append({**row, "source_refs": refs})
        return output

    errors = []
    for error in list(result.get("errors") or []):
        filename = str(error.get("filename") or "")
        errors.append(
            {
                **error,
                "filename": filename,
                "input_item_id": filename if filename in item_by_id else None,
            }
        )

    return {
        "persons": normalized(result.get("persons")),
        "properties": normalized(result.get("properties")),
        "marriages": list(result.get("marriages") or []),
        "raw_results": raw_results,
        "errors": errors,
        "summary": dict(result.get("summary") or {}),
    }


def _replace_retried_raw(
    previous: dict[str, Any],
    current: dict[str, Any],
    retried_ids: set[str],
) -> list[dict[str, Any]]:
    kept = [
        raw
        for raw in list(previous.get("raw_results") or [])
        if str(raw.get("input_item_id") or raw.get("filename") or "") not in retried_ids
    ]
    return [*kept, *list(current.get("raw_results") or [])]


def _set_ocr_result(batch: ZaloBatch, materialized: dict[str, Any], outputs: dict[str, Any]) -> None:
    batch.raw_ocr_json = materialized
    selected_ocr = {"json", "excel"} & set(batch.selection_json or [])
    if materialized["errors"]:
        batch.ocr_status = "error"
        for output_type in selected_ocr:
            outputs[output_type] = {"status": "error", "retryable": True, "error": "OCR chưa hoàn tất"}
    else:
        batch.ocr_status = "awaiting_confirmation"
        for output_type in selected_ocr:
            outputs[output_type] = {"status": "awaiting_confirmation", "retryable": False}


def _output_batch_status(outputs: dict[str, Any]) -> str:
    states = list(outputs.values())
    if states and all(
        value.get("status") == "ready"
        or (value.get("status") == "error" and not value.get("retryable"))
        for value in states
    ):
        return "completed"
    if any(value.get("status") == "error" for value in states):
        return "error"
    return "processing"


async def run_outputs(
    db: Session,
    batch_id: str,
    *,
    batch_root: str | Path,
    ocr_analyzer,
    cached_parser=None,
) -> ZaloBatch:
    batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if batch is None or batch.selection_json is None:
        raise InboxValidationError("Lô chưa chốt output")
    _require_active_batch(batch)
    items = sorted(list(batch.items_json or []), key=lambda item: item["order"])
    outputs = dict(batch.outputs_json or {})
    output_dir = Path(batch_root) / batch.id / "outputs"

    if "pdf" in batch.selection_json and outputs.get("pdf", {}).get("status") != "ready":
        try:
            filename = export_filename(batch.id, "pdf", batch.created_at)
            path = output_dir / filename
            _write_pdf(items, path)
            outputs["pdf"] = {"status": "ready", "retryable": False, "filename": filename, "path": str(path)}
        except Exception as exc:
            outputs["pdf"] = {"status": "error", "retryable": True, "error": str(exc)[:240]}
        batch.outputs_json = outputs
        db.commit()

    needs_ocr = bool({"json", "excel"} & set(batch.selection_json))
    if needs_ocr and batch.ocr_status not in {"awaiting_confirmation", "confirmed"}:
        uploads: list[UploadFile] = []
        try:
            previous = dict(batch.raw_ocr_json or {})
            retry_ids: set[str] = set()
            if previous:
                item_ids = {str(item["input_item_id"]) for item in items}
                retry_ids = {
                    str(error.get("input_item_id") or error.get("filename") or "")
                    for error in list(previous.get("errors") or [])
                    if str(error.get("stage") or "model") in {"model", "transport"}
                    and str(error.get("input_item_id") or error.get("filename") or "") in item_ids
                }
                if not retry_ids:
                    raise InboxConflict("Lỗi parser/pair phải retry từ raw OCR cache")
            selected_items = [item for item in items if not retry_ids or str(item["input_item_id"]) in retry_ids]
            for item in selected_items:
                data = _selected_image_path(item).read_bytes()
                uploads.append(UploadFile(filename=str(item["input_item_id"]), file=io.BytesIO(data)))
            result = await ocr_analyzer(uploads)
            current = _materialize_ocr(result, items)
            if previous and cached_parser:
                combined_raw = _replace_retried_raw(previous, current, retry_ids)
                materialized = _materialize_ocr(cached_parser(combined_raw), items)
                remaining_errors = [
                    error
                    for error in list(previous.get("errors") or [])
                    if str(error.get("input_item_id") or error.get("filename") or "") not in retry_ids
                ]
                materialized["errors"] = [*remaining_errors, *materialized["errors"]]
            elif previous:
                materialized = {
                    **current,
                    "raw_results": _replace_retried_raw(previous, current, retry_ids),
                    "persons": [*list(previous.get("persons") or []), *current["persons"]],
                    "properties": [*list(previous.get("properties") or []), *current["properties"]],
                }
            else:
                materialized = current
            _set_ocr_result(batch, materialized, outputs)
        except Exception as exc:
            batch.ocr_status = "error"
            for output_type in {"json", "excel"} & set(batch.selection_json):
                outputs[output_type] = {"status": "error", "retryable": True, "error": str(exc)[:240]}
        finally:
            for upload in uploads:
                await upload.close()
        batch.outputs_json = outputs

    if not needs_ocr and all(value.get("status") == "ready" for value in outputs.values()):
        batch.status = "completed"
    db.commit()
    db.refresh(batch)
    return batch


def retry_cached_ocr(db: Session, batch_id: str, parser) -> ZaloBatch:
    batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if batch is None or batch.ocr_status != "error" or not batch.raw_ocr_json:
        raise InboxConflict("Không có raw OCR cache để retry")
    _require_active_batch(batch)
    cached = dict(batch.raw_ocr_json)
    errors = list(cached.get("errors") or [])
    if not errors or any(str(error.get("stage") or "model") not in {"parse", "pair", "shape"} for error in errors):
        raise InboxConflict("Lỗi model phải retry đúng item lỗi")
    materialized = _materialize_ocr(
        parser(list(cached.get("raw_results") or [])),
        list(batch.items_json or []),
    )
    outputs = dict(batch.outputs_json or {})
    _set_ocr_result(batch, materialized, outputs)
    batch.outputs_json = outputs
    db.commit()
    db.refresh(batch)
    return batch


def _validate_confirmed_refs(data: dict[str, Any], raw_results: list[dict[str, Any]]) -> None:
    valid = {str(item.get("input_item_id")) for item in raw_results}
    for group in ("persons", "properties"):
        rows = data.get(group)
        if not isinstance(rows, list):
            raise InboxValidationError(f"{group} phải là danh sách")
        for row in rows:
            if not isinstance(row, dict) or any(str(ref) not in valid for ref in row.get("source_refs") or []):
                raise InboxValidationError("source_refs không hợp lệ")


def confirm_batch(
    db: Session,
    batch_id: str,
    edited: dict[str, Any],
    *,
    batch_root: str | Path,
) -> ZaloBatch:
    batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if batch is None:
        raise InboxValidationError("Không tìm thấy lô")
    _require_active_batch(batch)
    if batch.ocr_status == "confirmed":
        return batch
    if batch.ocr_status != "awaiting_confirmation" or not batch.raw_ocr_json:
        raise InboxConflict("OCR chưa chờ xác nhận")
    raw = dict(batch.raw_ocr_json)
    _validate_confirmed_refs(edited, list(raw.get("raw_results") or []))
    confirmed = {
        "persons": list(edited.get("persons") or []),
        "properties": list(edited.get("properties") or []),
        "marriages": list(raw.get("marriages") or []),
        "raw_results": list(raw.get("raw_results") or []),
        "errors": [],
        "summary": dict(raw.get("summary") or {}),
    }
    output_dir = Path(batch_root) / batch.id / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = dict(batch.outputs_json or {})

    if "json" in (batch.selection_json or []):
        filename = export_filename(batch.id, "json", batch.created_at)
        path = output_dir / filename
        try:
            path.write_text(json.dumps(confirmed, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            outputs["json"] = {"status": "ready", "retryable": False, "filename": filename, "path": str(path)}
        except Exception as exc:
            outputs["json"] = {"status": "error", "retryable": True, "error": str(exc)[:240]}
    if "excel" in (batch.selection_json or []):
        filename = export_filename(batch.id, "xlsx", batch.created_at)
        path = output_dir / filename
        try:
            write_excel_export(confirmed, path)
            outputs["excel"] = {"status": "ready", "retryable": False, "filename": filename, "path": str(path)}
        except InboxTerminalError as exc:
            outputs["excel"] = {"status": "error", "retryable": False, "error": str(exc)}
        except Exception as exc:
            outputs["excel"] = {"status": "error", "retryable": True, "error": str(exc)[:240]}

    batch.confirmed_json = confirmed
    batch.ocr_status = "confirmed"
    batch.outputs_json = outputs
    batch.status = _output_batch_status(outputs)
    db.commit()
    db.refresh(batch)
    return batch


def retry_export(db: Session, batch_id: str, output_type: str, *, batch_root: str | Path) -> ZaloBatch:
    batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).first()
    if batch is None:
        raise InboxValidationError("Không tìm thấy lô")
    _require_active_batch(batch)
    output = dict(batch.outputs_json or {}).get(output_type) or {}
    if output.get("status") != "error" or not output.get("retryable"):
        raise InboxConflict("Output này không thể thử lại")
    outputs = dict(batch.outputs_json or {})
    output_dir = Path(batch_root) / batch.id / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if output_type == "pdf":
            filename = export_filename(batch.id, "pdf", batch.created_at)
            path = output_dir / filename
            _write_pdf(list(batch.items_json or []), path)
        elif output_type == "json" and batch.confirmed_json:
            filename = export_filename(batch.id, "json", batch.created_at)
            path = output_dir / filename
            path.write_text(json.dumps(batch.confirmed_json, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        elif output_type == "excel" and batch.confirmed_json:
            filename = export_filename(batch.id, "xlsx", batch.created_at)
            path = output_dir / filename
            write_excel_export(dict(batch.confirmed_json), path)
        else:
            raise InboxConflict("Output chưa có dữ liệu đã xác nhận")
        outputs[output_type] = {"status": "ready", "retryable": False, "filename": filename, "path": str(path)}
    except InboxTerminalError as exc:
        outputs[output_type] = {"status": "error", "retryable": False, "error": str(exc)}
    except InboxConflict:
        raise
    except Exception as exc:
        outputs[output_type] = {"status": "error", "retryable": True, "error": str(exc)[:240]}
    batch.outputs_json = outputs
    batch.status = _output_batch_status(outputs)
    db.commit()
    db.refresh(batch)
    return batch
