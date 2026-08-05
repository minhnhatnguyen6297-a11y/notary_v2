from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz
import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import ZaloBatch, ZaloConnectorAccount, ZaloMedia, ZaloSource
from services.zalo_inbox import (
    InboxConfigurationError,
    InboxConflict,
    InboxLimits,
    InboxTerminalError,
    InboxValidationError,
    apply_connector_report,
    cleanup_expired_batch,
    connector_state,
    create_batch,
    confirm_batch,
    export_filename,
    freeze_outputs,
    ingest_webhook_event,
    prepare_batch,
    retry_cached_ocr,
    retry_export,
    run_outputs,
    update_preview,
    verify_webhook_signature,
    write_excel_export,
)

UTC = timezone.utc


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _account(db, *, account_id="11111111-1111-4111-8111-111111111111"):
    row = ZaloConnectorAccount(
        id=account_id,
        session_state="login_required",
        listener_generation=1,
    )
    db.add(row)
    db.commit()
    return row


def _source(db, account, conversation_id="thread-1"):
    row = ZaloSource(
        id="22222222-2222-4222-8222-222222222222",
        connector_account_id=account.id,
        conversation_id=conversation_id,
        conversation_type="user",
        display_name="Nguồn kiểm thử",
        enabled=True,
    )
    db.add(row)
    db.commit()
    return row


def _png(path: Path, size=(20, 10), color="white") -> None:
    Image.new("RGB", size, color).save(path, format="PNG")


def _media(db, account, source, root: Path, *, media_id: str, object_name: str, sent_at=None):
    object_path = root / account.id / object_name
    object_path.parent.mkdir(parents=True, exist_ok=True)
    _png(object_path)
    payload = {
        "connector_account_id": account.id,
        "conversation_id": source.conversation_id,
        "msg_id": f"msg-{media_id}",
        "attachment_index": 0,
        "media_object_key": f"{account.id}/{object_name}",
        "mime_type": "image/png",
        "size_bytes": object_path.stat().st_size,
    }
    row = ZaloMedia(
        id=media_id,
        connector_account_id=account.id,
        source_id=source.id,
        conversation_id=source.conversation_id,
        msg_id=payload["msg_id"],
        attachment_index=0,
        media_object_key=payload["media_object_key"],
        mime_type="image/png",
        size_bytes=payload["size_bytes"],
        sent_at=sent_at or datetime(2026, 8, 4, 2, 30, tzinfo=UTC),
        payload_digest=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
    )
    db.add(row)
    db.commit()
    return row


def test_expired_qr_is_not_public_state(db):
    account = _account(db)
    account.qr_image = "data:image/png;base64,stale"
    account.qr_generated_at = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)
    account.qr_expires_at = datetime(2026, 8, 4, 3, 1, 40, tzinfo=UTC)
    db.commit()

    from services.zalo_inbox import public_qr

    assert public_qr(account, now=datetime(2026, 8, 4, 3, 2, tzinfo=UTC)) is None


def test_connector_state_priority_and_generation(db):
    account = _account(db)
    now = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)

    assert connector_state(account, now=now) == "login_required"
    assert apply_connector_report(account, "connected", 1, now, qr_login_success=False) is False
    assert connector_state(account, now=now) == "login_required"

    assert apply_connector_report(
        account, "connected", 2, now, qr_login_success=True, bound_zalo_id="zalo-owner-1"
    ) is True
    assert connector_state(account, now=now) == "connected"

    assert apply_connector_report(account, "login_required", 3, now + timedelta(seconds=1)) is True
    assert apply_connector_report(
        account,
        "connected",
        2,
        now + timedelta(seconds=2),
        qr_login_success=True,
        bound_zalo_id="zalo-owner-1",
    ) is False
    assert connector_state(account, now=now + timedelta(seconds=60)) == "login_required"

    assert apply_connector_report(
        account,
        "connected",
        4,
        now + timedelta(seconds=61),
        qr_login_success=True,
        bound_zalo_id="zalo-owner-1",
    ) is True
    assert connector_state(account, now=now + timedelta(seconds=107), stale_after_seconds=45) == "disconnected"


def test_connector_disconnect_and_receipt_time_are_authoritative(db):
    account = _account(db)
    connector_clock = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)
    received_at = connector_clock + timedelta(seconds=30)

    assert apply_connector_report(
        account,
        "connected",
        1,
        received_at,
        qr_login_success=True,
        bound_zalo_id="zalo-owner-1",
    ) is True
    assert account.last_seen_at == received_at

    assert apply_connector_report(account, "disconnected", 1, received_at + timedelta(seconds=1)) is True
    assert account.session_state == "disconnected"
    assert connector_state(account, now=received_at + timedelta(seconds=2)) == "disconnected"

    assert apply_connector_report(account, "connected", 1, received_at + timedelta(seconds=3)) is True
    assert account.session_state == "usable"


def test_ingest_uses_backend_receipt_time_not_connector_clock(db, monkeypatch):
    account = _account(db)
    received_at = datetime(2026, 8, 4, 4, 0, tzinfo=UTC)
    monkeypatch.setattr("services.zalo_inbox.utcnow", lambda: received_at)

    ingest_webhook_event(
        db,
        {
            "schema_version": 1,
            "event_type": "state",
            "connector_account_id": account.id,
            "state": "login_required",
            "listener_generation": 1,
            "observed_at": "2026-08-04T03:59:30Z",
        },
        storage_root=".",
    )

    assert account.last_seen_at.replace(tzinfo=UTC) == received_at


def test_qr_login_binds_first_zalo_account_and_rejects_a_different_one(db):
    account = _account(db)
    observed = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)

    assert apply_connector_report(
        account,
        "connected",
        2,
        observed,
        qr_login_success=True,
        bound_zalo_id="zalo-owner-1",
    ) is True
    assert account.bound_zalo_id == "zalo-owner-1"

    with pytest.raises(InboxConflict, match="tài khoản Zalo khác"):
        apply_connector_report(
            account,
            "connected",
            3,
            observed + timedelta(seconds=1),
            qr_login_success=True,
            bound_zalo_id="zalo-owner-2",
        )
    assert account.bound_zalo_id == "zalo-owner-1"

    with pytest.raises(InboxConflict, match="tài khoản Zalo khác"):
        apply_connector_report(
            account,
            "connected",
            4,
            observed + timedelta(seconds=2),
            bound_zalo_id="zalo-owner-2",
        )
    assert account.bound_zalo_id == "zalo-owner-1"


def test_webhook_signature_and_replay_window():
    body = b'{"event_type":"heartbeat"}'
    secret = "test-secret"
    now = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)
    timestamp = str(int(now.timestamp()))
    signature = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()

    verify_webhook_signature(body, timestamp, signature, secret, now=now)
    with pytest.raises(InboxValidationError, match="signature"):
        verify_webhook_signature(body, timestamp, "00" * 32, secret, now=now)
    with pytest.raises(InboxValidationError, match="replay"):
        verify_webhook_signature(body, timestamp, signature, secret, now=now + timedelta(minutes=6))


def test_webhook_duplicate_is_idempotent_and_conflict_is_rejected(db, tmp_path):
    account = _account(db)
    source = _source(db, account)
    object_path = tmp_path / account.id / "media.png"
    object_path.parent.mkdir()
    _png(object_path)
    payload = {
        "schema_version": 1,
        "event_type": "media",
        "connector_account_id": account.id,
        "conversation_id": source.conversation_id,
        "conversation_type": "user",
        "source_display_name": source.display_name,
        "msg_id": "m-1",
        "sent_at": "2026-08-04T03:00:00Z",
        "attachment_index": 0,
        "media_object_key": f"{account.id}/media.png",
        "mime_type": "image/png",
        "size_bytes": object_path.stat().st_size,
    }

    first = ingest_webhook_event(db, payload, storage_root=tmp_path)
    second = ingest_webhook_event(db, payload, storage_root=tmp_path)
    assert first.id == second.id
    assert db.query(ZaloMedia).count() == 1

    changed = dict(payload, size_bytes=payload["size_bytes"] + 1)
    with pytest.raises(InboxConflict):
        ingest_webhook_event(db, changed, storage_root=tmp_path)


def test_webhook_acks_but_does_not_publish_media_from_disabled_source(db, tmp_path):
    account = _account(db)
    source = _source(db, account)
    source.enabled = False
    db.commit()
    object_path = tmp_path / account.id / "disabled.png"
    object_path.parent.mkdir()
    _png(object_path)
    result = ingest_webhook_event(
        db,
        {
            "schema_version": 1,
            "event_type": "media",
            "connector_account_id": account.id,
            "conversation_id": source.conversation_id,
            "conversation_type": "user",
            "source_display_name": source.display_name,
            "msg_id": "disabled-message",
            "sent_at": "2026-08-04T03:00:00Z",
            "attachment_index": 0,
            "media_object_key": f"{account.id}/disabled.png",
            "mime_type": "image/png",
            "size_bytes": object_path.stat().st_size,
        },
        storage_root=tmp_path,
    )
    assert result == {"ignored": True}
    assert db.query(ZaloMedia).count() == 0


def test_batch_validation_is_atomic(db, tmp_path):
    account = _account(db)
    source = _source(db, account)
    good = _media(db, account, source, tmp_path / "source", media_id="m-good", object_name="good.png")
    missing = ZaloMedia(
        id="m-missing",
        connector_account_id=account.id,
        source_id=source.id,
        conversation_id=source.conversation_id,
        msg_id="msg-missing",
        attachment_index=0,
        media_object_key=f"{account.id}/missing.png",
        mime_type="image/png",
        size_bytes=10,
        sent_at=datetime.now(UTC),
        payload_digest="missing",
    )
    db.add(missing)
    db.commit()

    with pytest.raises(InboxValidationError, match="File nguồn không còn"):
        create_batch(
            db,
            [good.id, missing.id],
            storage_root=tmp_path / "source",
            batch_root=tmp_path / "batches",
            limits=InboxLimits(max_file_bytes=1024 * 1024, max_items=100, max_total_bytes=2 * 1024 * 1024, max_pixels=10000),
        )

    assert db.query(ZaloBatch).count() == 0
    assert list((tmp_path / "batches").glob("*")) == [] if (tmp_path / "batches").exists() else True


def test_pdf_expands_at_original_position(db, tmp_path):
    account = _account(db)
    source = _source(db, account)
    a = _media(db, account, source, tmp_path / "source", media_id="m-a", object_name="a.png")

    pdf_path = tmp_path / "source" / account.id / "two-pages.pdf"
    document = fitz.open()
    document.new_page(width=72, height=72)
    document.new_page(width=72, height=72)
    document.save(pdf_path)
    pdf = ZaloMedia(
        id="m-pdf",
        connector_account_id=account.id,
        source_id=source.id,
        conversation_id=source.conversation_id,
        msg_id="msg-pdf",
        attachment_index=0,
        media_object_key=f"{account.id}/two-pages.pdf",
        mime_type="application/pdf",
        size_bytes=pdf_path.stat().st_size,
        sent_at=datetime.now(UTC),
        payload_digest="pdf",
    )
    db.add(pdf)
    db.commit()
    b = _media(db, account, source, tmp_path / "source", media_id="m-b", object_name="b.png")

    batch = create_batch(
        db,
        [a.id, pdf.id, b.id],
        storage_root=tmp_path / "source",
        batch_root=tmp_path / "batches",
        limits=InboxLimits(max_file_bytes=1024 * 1024, max_items=100, max_total_bytes=4 * 1024 * 1024, max_pixels=100000),
    )
    prepare_batch(db, batch.id, batch_root=tmp_path / "batches")
    db.refresh(batch)

    assert batch.status == "review"
    assert [item["source_media_id"] for item in batch.items_json] == [a.id, pdf.id, pdf.id, b.id]
    assert [item.get("page_number") for item in batch.items_json] == [None, 1, 2, None]

    pdf_item_ids = [item["input_item_id"] for item in batch.items_json if item["source_media_id"] == pdf.id]
    retried = [dict(item) for item in batch.items_json]
    retried[-1]["status"] = "error"
    batch.items_json = retried
    batch.status = "error"
    db.commit()
    prepare_batch(db, batch.id, batch_root=tmp_path / "batches")
    db.refresh(batch)
    assert [item["input_item_id"] for item in batch.items_json if item["source_media_id"] == pdf.id] == pdf_item_ids
    assert batch.status == "review"


def test_output_selection_freezes_once_and_exact_replay_is_idempotent(db):
    account = _account(db)
    batch = ZaloBatch(
        id="33333333-3333-4333-8333-333333333333",
        connector_account_id=account.id,
        status="review",
        items_json=[{"input_item_id": "item-1", "status": "ready", "order": 0}],
        outputs_json={},
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=72),
    )
    db.add(batch)
    db.commit()

    first = freeze_outputs(db, batch.id, ["pdf", "json"])
    replay = freeze_outputs(db, batch.id, ["json", "pdf"])
    assert first.selection_json == replay.selection_json == ["json", "pdf"]
    with pytest.raises(InboxConflict, match="chốt"):
        freeze_outputs(db, batch.id, ["excel"])


def test_cleanup_keeps_only_tombstone(db, tmp_path):
    account = _account(db)
    batch_dir = tmp_path / "batches" / "batch-expired"
    batch_dir.mkdir(parents=True)
    (batch_dir / "secret.json").write_text("pii", encoding="utf-8")
    batch = ZaloBatch(
        id="batch-expired",
        connector_account_id=account.id,
        status="review",
        items_json=[{"input_item_id": "sensitive"}],
        outputs_json={"json": {"status": "ready", "path": str(batch_dir / "secret.json")}},
        raw_ocr_json={"persons": [{"ho_ten": "PII"}]},
        confirmed_json={"persons": [{"ho_ten": "PII"}]},
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        expires_at=datetime(2026, 8, 4, tzinfo=UTC),
    )
    db.add(batch)
    db.commit()

    assert cleanup_expired_batch(db, batch.id, batch_root=tmp_path / "batches", now=datetime(2026, 8, 4, 1, tzinfo=UTC))
    db.refresh(batch)
    assert batch.status == "expired"
    assert batch.items_json == []
    assert batch.raw_ocr_json is None and batch.confirmed_json is None
    assert batch.outputs_json == {"json": {"status": "expired"}}
    assert not batch_dir.exists()


def test_excel_empty_is_terminal_and_rows_include_provenance(tmp_path):
    with pytest.raises(InboxTerminalError, match="Không có dữ liệu để xuất Excel"):
        write_excel_export({"persons": [], "properties": [], "raw_results": []}, tmp_path / "empty.xlsx")

    data = {
        "persons": [{"ho_ten": "Nguyễn Văn A", "source_refs": ["item-1"]}],
        "properties": [],
        "raw_results": [
            {
                "input_item_id": "item-1",
                "source_display_name": "Nhóm A",
                "sent_at": "2026-08-04T03:00:00Z",
                "page_number": 2,
                "page_count": 3,
            }
        ],
    }
    path = tmp_path / "data.xlsx"
    write_excel_export(data, path)
    assert path.exists() and path.stat().st_size > 0

    import openpyxl

    workbook = openpyxl.load_workbook(path)
    sheet = workbook["Nguoi"]
    headers = [cell.value for cell in sheet[1]]
    row = dict(zip(headers, [cell.value for cell in sheet[2]]))
    assert row["Nguồn"] == "Nhóm A"
    assert row["Thời điểm"] == "2026-08-04T03:00:00Z"
    assert row["Trang"] == "2/3"


def test_empty_excel_is_terminal_and_finishes_batch_without_retry(db, tmp_path):
    account = _account(db)
    batch = ZaloBatch(
        id="77777777-7777-4777-8777-777777777777",
        connector_account_id=account.id,
        status="processing",
        items_json=[{"input_item_id": "item-1", "status": "ready", "order": 0}],
        selection_json=["excel"],
        outputs_json={"excel": {"status": "awaiting_confirmation", "retryable": False}},
        ocr_status="awaiting_confirmation",
        raw_ocr_json={
            "persons": [],
            "properties": [],
            "marriages": [],
            "raw_results": [{"input_item_id": "item-1"}],
            "errors": [],
            "summary": {},
        },
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=72),
    )
    db.add(batch)
    db.commit()
    confirm_batch(db, batch.id, {"persons": [], "properties": []}, batch_root=tmp_path / "batches")
    db.refresh(batch)
    assert batch.outputs_json["excel"] == {
        "status": "error",
        "retryable": False,
        "error": "Không có dữ liệu để xuất Excel",
    }
    assert batch.status == "completed"


def test_export_filename_uses_ho_chi_minh_time():
    created = datetime(2026, 8, 4, 3, 30, tzinfo=UTC)
    assert export_filename("abcdef123456", "json", created) == "lo-20260804-1030-abcdef.json"


def test_end_to_end_outputs_keep_frozen_order_and_provenance(db, tmp_path):
    account = _account(db)
    source = _source(db, account)
    first = _media(db, account, source, tmp_path / "source", media_id="m-first", object_name="first.png")
    second = _media(db, account, source, tmp_path / "source", media_id="m-second", object_name="second.png")
    batch = create_batch(
        db,
        [first.id, second.id],
        storage_root=tmp_path / "source",
        batch_root=tmp_path / "batches",
        limits=InboxLimits(max_file_bytes=1024 * 1024, max_items=10, max_total_bytes=2 * 1024 * 1024, max_pixels=10000),
        now=datetime(2026, 8, 4, 3, 30, tzinfo=UTC),
    )
    prepare_batch(db, batch.id, batch_root=tmp_path / "batches")
    db.refresh(batch)
    original_ids = [item["input_item_id"] for item in batch.items_json]
    update_preview(
        db,
        batch.id,
        [
            {"input_item_id": original_ids[1], "use_crop": False},
            {"input_item_id": original_ids[0], "use_crop": False},
        ],
    )
    freeze_outputs(db, batch.id, ["pdf", "json", "excel"])

    async def fake_ocr(files):
        names = [upload.filename for upload in files]
        assert names == [original_ids[1], original_ids[0]]
        return {
            "persons": [{"ho_ten": "NGUYỄN VĂN A", "_files": [names[0]]}],
            "properties": [],
            "marriages": [],
            "raw_results": [
                {"filename": name, "doc_type": "person", "text_lines": [f"raw-{index}"]}
                for index, name in enumerate(names)
            ],
            "errors": [],
            "summary": {"total_images": len(names)},
        }

    asyncio.run(run_outputs(db, batch.id, batch_root=tmp_path / "batches", ocr_analyzer=fake_ocr))
    db.refresh(batch)
    assert batch.outputs_json["pdf"]["status"] == "ready"
    assert Path(batch.outputs_json["pdf"]["path"]).exists()
    assert batch.ocr_status == "awaiting_confirmation"
    assert batch.raw_ocr_json["persons"][0]["source_refs"] == [original_ids[1]]
    raw = {item["input_item_id"]: item for item in batch.raw_ocr_json["raw_results"]}
    assert raw[original_ids[1]]["source_display_name"] == source.display_name

    confirm_batch(
        db,
        batch.id,
        {
            "persons": [{"ho_ten": "NGUYỄN VĂN A", "source_refs": [original_ids[1]]}],
            "properties": [],
        },
        batch_root=tmp_path / "batches",
    )
    db.refresh(batch)
    assert batch.status == "completed"
    assert batch.outputs_json["json"]["status"] == "ready"
    assert batch.outputs_json["excel"]["status"] == "ready"
    exported = json.loads(Path(batch.outputs_json["json"]["path"]).read_text(encoding="utf-8"))
    assert exported["raw_results"][0]["source_display_name"] == source.display_name


def test_preview_cannot_change_after_output_freeze(db):
    account = _account(db)
    batch = ZaloBatch(
        id="44444444-4444-4444-8444-444444444444",
        connector_account_id=account.id,
        status="review",
        items_json=[{"input_item_id": "item-1", "status": "ready", "order": 0, "crop_path": None}],
        outputs_json={},
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=72),
    )
    db.add(batch)
    db.commit()
    freeze_outputs(db, batch.id, ["pdf"])
    with pytest.raises(InboxConflict, match="đóng băng"):
        update_preview(db, batch.id, [{"input_item_id": "item-1", "use_crop": False}])


def test_expired_batch_rejects_preview_mutation(db):
    account = _account(db)
    batch = ZaloBatch(
        id="88888888-8888-4888-8888-888888888888",
        connector_account_id=account.id,
        status="review",
        items_json=[{"input_item_id": "item-1", "status": "ready", "order": 0, "crop_path": None}],
        outputs_json={},
        created_at=datetime.now(UTC) - timedelta(hours=73),
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db.add(batch)
    db.commit()
    with pytest.raises(InboxConflict, match="hết hạn"):
        update_preview(db, batch.id, [{"input_item_id": "item-1", "use_crop": False}])


def test_runtime_limits_require_deployment_values(monkeypatch):
    for name in (
        "ZALO_INBOX_MAX_FILE_BYTES",
        "ZALO_INBOX_MAX_ITEMS",
        "ZALO_INBOX_MAX_TOTAL_BYTES",
        "ZALO_INBOX_MAX_RENDERED_PIXELS",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(InboxConfigurationError, match="Thiếu cấu hình"):
        InboxLimits.from_env()


def test_ocr_model_retry_uploads_only_failed_item(db, tmp_path):
    account = _account(db)
    source = _source(db, account)
    first = _media(db, account, source, tmp_path / "source", media_id="retry-a", object_name="retry-a.png")
    second = _media(db, account, source, tmp_path / "source", media_id="retry-b", object_name="retry-b.png")
    batch = create_batch(
        db,
        [first.id, second.id],
        storage_root=tmp_path / "source",
        batch_root=tmp_path / "batches",
        limits=InboxLimits(max_file_bytes=1024 * 1024, max_items=10, max_total_bytes=2 * 1024 * 1024, max_pixels=10000),
    )
    prepare_batch(db, batch.id, batch_root=tmp_path / "batches")
    db.refresh(batch)
    item_ids = [item["input_item_id"] for item in batch.items_json]
    freeze_outputs(db, batch.id, ["json"])
    calls = []

    async def analyzer(files):
        names = [upload.filename for upload in files]
        calls.append(names)
        if len(calls) == 1:
            return {
                "persons": [{"ho_ten": "A", "_files": [item_ids[0]]}],
                "properties": [],
                "marriages": [],
                "raw_results": [{"filename": item_ids[0], "text_lines": ["A"]}],
                "errors": [{"filename": item_ids[1], "error": "timeout", "stage": "model"}],
                "summary": {},
            }
        return {
            "persons": [{"ho_ten": "B", "_files": [item_ids[1]]}],
            "properties": [],
            "marriages": [],
            "raw_results": [{"filename": item_ids[1], "text_lines": ["B"]}],
            "errors": [],
            "summary": {},
        }

    def parser(raw_results):
        return {
            "persons": [
                {"ho_ten": raw["text_lines"][0], "_files": [raw.get("input_item_id") or raw["filename"]]}
                for raw in raw_results
            ],
            "properties": [],
            "marriages": [],
            "raw_results": raw_results,
            "errors": [],
            "summary": {},
        }

    asyncio.run(run_outputs(db, batch.id, batch_root=tmp_path / "batches", ocr_analyzer=analyzer, cached_parser=parser))
    db.refresh(batch)
    assert batch.ocr_status == "error"
    asyncio.run(run_outputs(db, batch.id, batch_root=tmp_path / "batches", ocr_analyzer=analyzer, cached_parser=parser))
    db.refresh(batch)
    assert calls == [item_ids, [item_ids[1]]]
    assert batch.ocr_status == "awaiting_confirmation"
    assert {row["ho_ten"] for row in batch.raw_ocr_json["persons"]} == {"A", "B"}


def test_parse_retry_uses_raw_cache(db):
    account = _account(db)
    batch = ZaloBatch(
        id="55555555-5555-4555-8555-555555555555",
        connector_account_id=account.id,
        status="processing",
        items_json=[
            {
                "input_item_id": "item-raw",
                "source_display_name": "Nguồn A",
                "sent_at": "2026-08-04T03:00:00Z",
                "page_number": None,
                "page_count": None,
            }
        ],
        selection_json=["json"],
        outputs_json={"json": {"status": "error", "retryable": True}},
        ocr_status="error",
        raw_ocr_json={
            "persons": [],
            "properties": [],
            "raw_results": [{"filename": "item-raw", "input_item_id": "item-raw", "text_lines": ["cached"]}],
            "errors": [{"filename": "item-raw", "input_item_id": "item-raw", "stage": "parse", "error": "bad shape"}],
            "summary": {},
        },
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=72),
    )
    db.add(batch)
    db.commit()
    calls = []

    def parser(raw_results):
        calls.append(raw_results)
        return {
            "persons": [{"ho_ten": "CACHE", "_files": ["item-raw"]}],
            "properties": [],
            "marriages": [],
            "raw_results": raw_results,
            "errors": [],
            "summary": {"cache_reparse": True},
        }

    retry_cached_ocr(db, batch.id, parser)
    db.refresh(batch)
    assert len(calls) == 1
    assert batch.ocr_status == "awaiting_confirmation"
    assert batch.raw_ocr_json["persons"][0]["ho_ten"] == "CACHE"


def test_retry_export_reuses_confirmed_snapshot(db, tmp_path):
    account = _account(db)
    confirmed = {
        "persons": [{"ho_ten": "NGUYỄN VĂN A", "source_refs": ["item-1"]}],
        "properties": [],
        "raw_results": [{"input_item_id": "item-1", "source_display_name": "Nguồn A"}],
        "errors": [],
        "summary": {},
    }
    batch = ZaloBatch(
        id="66666666-6666-4666-8666-666666666666",
        connector_account_id=account.id,
        status="processing",
        items_json=[],
        selection_json=["json"],
        outputs_json={"json": {"status": "error", "retryable": True, "error": "disk busy"}},
        ocr_status="confirmed",
        confirmed_json=confirmed,
        created_at=datetime(2026, 8, 4, 3, 30, tzinfo=UTC),
        expires_at=datetime(2026, 8, 7, 3, 30, tzinfo=UTC),
    )
    db.add(batch)
    db.commit()

    retry_export(db, batch.id, "json", batch_root=tmp_path / "batches")
    db.refresh(batch)
    assert batch.selection_json == ["json"]
    assert batch.ocr_status == "confirmed"
    assert batch.outputs_json["json"]["status"] == "ready"
    exported = json.loads(Path(batch.outputs_json["json"]["path"]).read_text(encoding="utf-8"))
    assert exported == confirmed
