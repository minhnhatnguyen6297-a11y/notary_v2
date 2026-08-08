from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import fitz
import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from database import Base
from models import (
    Customer,
    InheritanceCase,
    InheritanceParticipant,
    Property,
    ZaloBatch,
    ZaloConnectorAccount,
    ZaloDataSyncRun,
    ZaloMedia,
    ZaloMessageText,
    ZaloSource,
)
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
    apply_intake_consent,
    ack_policy,
    ack_source_sync,
    request_source_sync,
    set_source_policy,
    source_ready,
)

UTC = timezone.utc


def _columns(db_path: Path, table: str) -> set[str]:
    return set(_table_info(db_path, table))


def _table_info(db_path: Path, table: str) -> dict[str, tuple[str, int, str | None]]:
    with sqlite3.connect(db_path) as connection:
        return {
            row[1]: (row[2], row[3], row[4])
            for row in connection.execute(f"PRAGMA table_info({table})")
        }


def _foreign_keys(db_path: Path, table: str) -> set[tuple[str, str, str]]:
    with sqlite3.connect(db_path) as connection:
        return {
            (row[2], row[3], row[4])
            for row in connection.execute(f"PRAGMA foreign_key_list({table})")
        }


def _indexes(db_path: Path, table: str) -> dict[str, tuple[int, tuple[str, ...]]]:
    with sqlite3.connect(db_path) as connection:
        return {
            row[1]: (
                row[2],
                tuple(
                    index_row[2]
                    for index_row in connection.execute(f"PRAGMA index_info({row[1]})")
                ),
            )
            for row in connection.execute(f"PRAGMA index_list({table})")
        }


def _scalar(db_path: Path, sql: str):
    with sqlite3.connect(db_path) as connection:
        return connection.execute(sql).fetchone()[0]


def _fresh_zalo_schema(db_path: Path) -> None:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    database.enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    engine.dispose()


def _foreign_key_check(db_path: Path) -> list[tuple]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute("PRAGMA foreign_key_check").fetchall()


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.enable_sqlite_foreign_keys(engine)
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


def _message_text(*, row_id: str, account_id: str, source_id: str) -> ZaloMessageText:
    return ZaloMessageText(
        id=row_id,
        connector_account_id=account_id,
        source_id=source_id,
        conversation_id="thread-1",
        msg_id=f"message-{row_id}",
        sender_id="sender-1",
        sent_at=datetime(2026, 8, 4, 3, 0, tzinfo=UTC),
        received_at=datetime(2026, 8, 4, 3, 1, tzinfo=UTC),
        raw_text="Nội dung kiểm thử",
        payload_digest="a" * 64,
    )


def _sync_run(*, row_id: str, account_id: str) -> ZaloDataSyncRun:
    return ZaloDataSyncRun(
        id=row_id,
        connector_account_id=account_id,
        status="completed",
        cutoff_at=datetime(2026, 8, 4, 3, 0, tzinfo=UTC),
        deadline_at=datetime(2026, 8, 4, 3, 5, tzinfo=UTC),
        source_ids_json=[],
        counters_json={},
        started_at=datetime(2026, 8, 4, 3, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 4, 3, 1, tzinfo=UTC),
    )


def test_sqlite_foreign_keys_are_enabled_for_production_and_test_engines(db, tmp_path):
    assert db.connection().exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    engine = create_engine(f"sqlite:///{(tmp_path / 'production-style.db').as_posix()}")
    database.enable_sqlite_foreign_keys(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    engine.dispose()


def test_zalo_message_text_rejects_orphan_account_and_source_but_accepts_valid_records(db):
    account = _account(db)
    source = _source(db, account)

    db.add(_message_text(row_id="valid-text", account_id=account.id, source_id=source.id))
    db.commit()

    db.add(_message_text(row_id="orphan-account", account_id="missing-account", source_id=source.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(_message_text(row_id="orphan-source", account_id=account.id, source_id="missing-source"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_zalo_data_sync_run_rejects_orphan_account_but_accepts_valid_record(db):
    account = _account(db)

    db.add(_sync_run(row_id="valid-run", account_id=account.id))
    db.commit()

    db.add(_sync_run(row_id="orphan-run", account_id="missing-account"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_fk_enforcement_keeps_valid_inheritance_records_insertable(db):
    deceased = Customer(ho_ten="Người để lại di sản")
    heir = Customer(ho_ten="Người thừa kế")
    property_row = Property(so_serial="GCN-FK-1", dia_chi="Hồ Chí Minh")
    db.add_all([deceased, heir, property_row])
    db.commit()

    case = InheritanceCase(
        nguoi_chet_id=deceased.id,
        tai_san_id=property_row.id,
        ngay_lap_ho_so=date(2026, 8, 4),
    )
    db.add(case)
    db.commit()
    db.add(
        InheritanceParticipant(
            ho_so_id=case.id,
            customer_id=heir.id,
            vai_tro="Con",
        )
    )
    db.commit()

    assert db.connection().exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_zalo_migration_preflight_rejects_existing_foreign_key_violation(tmp_path, monkeypatch):
    db_path = tmp_path / "invalid.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=OFF;
            CREATE TABLE parent (id INTEGER PRIMARY KEY);
            CREATE TABLE child (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER NOT NULL REFERENCES parent(id)
            );
            INSERT INTO child (id, parent_id) VALUES (1, 999);
            """
        )
    monkeypatch.setattr(database, "DB_PATH", db_path)

    with pytest.raises(RuntimeError, match="foreign key check failed"):
        database.migrate_zalo_schema()


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


def test_zalo_policy_migration_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE zalo_connector_accounts (id VARCHAR(36) PRIMARY KEY);
            CREATE TABLE zalo_sources (
                id VARCHAR(36) PRIMARY KEY,
                connector_account_id VARCHAR(36) NOT NULL,
                conversation_id VARCHAR(200) NOT NULL,
                conversation_type VARCHAR(20) NOT NULL,
                display_name VARCHAR(300) NOT NULL,
                enabled BOOLEAN NOT NULL
            );
            INSERT INTO zalo_connector_accounts (id) VALUES ('account-1');
            INSERT INTO zalo_sources (
                id, connector_account_id, conversation_id, conversation_type, display_name, enabled
            ) VALUES ('source-1', 'account-1', 'thread-1', 'user', 'Legacy source', 1);
            """
        )
    monkeypatch.setattr(database, "DB_PATH", db_path)

    database.migrate_zalo_schema()
    database.migrate_zalo_schema()

    assert _foreign_key_check(db_path) == []

    assert {
        "source_type",
        "enabled_explicit",
        "acked_enabled",
        "policy_version",
        "policy_acked_version",
        "last_activity_at",
    } <= _columns(db_path, "zalo_sources")
    assert {
        "intake_consented_at",
        "policy_version",
        "policy_acked_version",
        "source_sync_request_version",
        "source_sync_acked_version",
        "gap_started_at",
        "text_storage_full",
    } <= _columns(db_path, "zalo_connector_accounts")
    assert _columns(db_path, "zalo_message_texts")
    assert _columns(db_path, "zalo_data_sync_runs")
    assert _scalar(db_path, "SELECT enabled_explicit FROM zalo_sources WHERE id='source-1'") is None
    assert _scalar(db_path, "SELECT enabled FROM zalo_sources WHERE id='source-1'") == 1
    index_sql = _scalar(
        db_path,
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='uq_zalo_data_sync_running_account'",
    )
    assert " ".join(index_sql.split()) == (
        "CREATE UNIQUE INDEX uq_zalo_data_sync_running_account "
        "ON zalo_data_sync_runs(connector_account_id) WHERE status = 'running'"
    )


def test_zalo_policy_migration_matches_fresh_schema_contract(tmp_path, monkeypatch):
    migrated_path = tmp_path / "migrated.db"
    fresh_path = tmp_path / "fresh.db"
    with sqlite3.connect(migrated_path) as connection:
        connection.executescript(
            """
            CREATE TABLE zalo_connector_accounts (id VARCHAR(36) PRIMARY KEY);
            CREATE TABLE zalo_sources (
                id VARCHAR(36) PRIMARY KEY,
                connector_account_id VARCHAR(36) NOT NULL,
                conversation_id VARCHAR(200) NOT NULL,
                conversation_type VARCHAR(20) NOT NULL,
                display_name VARCHAR(300) NOT NULL,
                enabled BOOLEAN NOT NULL
            );
            INSERT INTO zalo_connector_accounts (id) VALUES ('account-1');
            INSERT INTO zalo_sources (
                id, connector_account_id, conversation_id, conversation_type, display_name, enabled
            ) VALUES ('source-1', 'account-1', 'thread-1', 'user', 'Legacy source', 1);
            """
        )
    monkeypatch.setattr(database, "DB_PATH", migrated_path)

    database.migrate_zalo_schema()
    _fresh_zalo_schema(fresh_path)

    assert _foreign_key_check(migrated_path) == []
    assert _foreign_key_check(fresh_path) == []

    expected_defaults = {
        "zalo_connector_accounts": {
            "policy_version": ("INTEGER", 1, "0"),
            "policy_acked_version": ("INTEGER", 1, "0"),
            "source_sync_request_version": ("INTEGER", 1, "0"),
            "source_sync_acked_version": ("INTEGER", 1, "0"),
            "text_storage_full": ("BOOLEAN", 1, "0"),
        },
        "zalo_sources": {
            "policy_version": ("INTEGER", 1, "0"),
            "policy_acked_version": ("INTEGER", 1, "0"),
        },
        "zalo_message_texts": {
            "sender_id": ("VARCHAR(200)", 1, None),
            "sent_at": ("DATETIME", 1, None),
            "received_at": ("DATETIME", 1, None),
            "created_at": ("DATETIME", 1, "CURRENT_TIMESTAMP"),
        },
        "zalo_data_sync_runs": {
            "source_ids_json": ("JSON", 1, "'[]'"),
            "counters_json": ("JSON", 1, "'{}'"),
        },
    }
    for table, columns in expected_defaults.items():
        fresh_columns = _table_info(fresh_path, table)
        migrated_columns = _table_info(migrated_path, table)
        for column, expected in columns.items():
            assert fresh_columns[column] == expected
            assert migrated_columns[column] == expected

    assert _table_info(fresh_path, "zalo_sources")["enabled_explicit"] == ("BOOLEAN", 0, "0")
    assert _table_info(migrated_path, "zalo_sources")["enabled_explicit"] == ("BOOLEAN", 0, None)
    assert _scalar(migrated_path, "SELECT enabled_explicit FROM zalo_sources WHERE id='source-1'") is None

    expected_text_fks = {
        ("zalo_connector_accounts", "connector_account_id", "id"),
        ("zalo_sources", "source_id", "id"),
    }
    assert _foreign_keys(fresh_path, "zalo_message_texts") == expected_text_fks
    assert _foreign_keys(migrated_path, "zalo_message_texts") == expected_text_fks
    assert _foreign_keys(fresh_path, "zalo_data_sync_runs") == {
        ("zalo_connector_accounts", "connector_account_id", "id"),
    }
    assert _foreign_keys(migrated_path, "zalo_data_sync_runs") == {
        ("zalo_connector_accounts", "connector_account_id", "id"),
    }

    for db_path in (fresh_path, migrated_path):
        indexes = _indexes(db_path, "zalo_message_texts")
        assert (1, ("connector_account_id", "conversation_id", "msg_id")) in set(
            indexes.values()
        )
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO zalo_message_texts (
                    id, connector_account_id, source_id, conversation_id, msg_id, sender_id,
                    sent_at, received_at, raw_text, payload_digest
                ) VALUES ('text-1', 'account-1', 'source-1', 'thread-1', 'message-1', 'sender-1',
                          '2026-08-04 03:00:00', '2026-08-04 03:01:00', 'text', 'digest')
                """
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO zalo_message_texts (
                        id, connector_account_id, source_id, conversation_id, msg_id, sender_id,
                        sent_at, received_at, raw_text, payload_digest
                    ) VALUES ('text-2', 'account-1', 'source-1', 'thread-1', 'message-1', 'sender-2',
                              '2026-08-04 03:02:00', '2026-08-04 03:03:00', 'text', 'digest')
                    """
                )


def test_zalo_policy_migration_models_have_additive_defaults(db):
    account = _account(db)
    source = _source(db, account)

    assert account.intake_consented_at is None
    assert account.policy_version == account.policy_acked_version == 0
    assert account.source_sync_request_version == account.source_sync_acked_version == 0
    assert account.gap_started_at is None
    assert account.text_storage_full is False
    assert source.source_type is None
    assert source.enabled_explicit is False
    assert source.acked_enabled is None
    assert source.policy_version == source.policy_acked_version == 0
    assert source.last_activity_at is None


def test_consent_applies_type_defaults_only_to_legacy_sources_and_waits_for_ack(db):
    account = _account(db)
    legacy_friend = _source(db, account, "friend-1")
    legacy_friend.source_type = "friend"
    legacy_friend.enabled_explicit = None
    explicit_stranger = ZaloSource(
        id="source-explicit",
        connector_account_id=account.id,
        conversation_id="stranger-1",
        conversation_type="user",
        display_name="Explicit stranger",
        source_type="stranger",
        enabled=True,
        enabled_explicit=True,
    )
    my_documents = ZaloSource(
        id="source-documents",
        connector_account_id=account.id,
        conversation_id="documents-1",
        conversation_type="user",
        display_name="My Documents",
        source_type="my_documents",
        enabled=False,
        enabled_explicit=None,
    )
    db.add_all([explicit_stranger, my_documents])
    db.commit()
    db.query(ZaloSource).filter(ZaloSource.id.in_([legacy_friend.id, my_documents.id])).update(
        {ZaloSource.enabled_explicit: None}, synchronize_session=False
    )
    db.commit()
    db.expire_all()

    version = apply_intake_consent(db, account.id)
    db.refresh(account)
    db.refresh(legacy_friend)
    db.refresh(explicit_stranger)
    db.refresh(my_documents)

    assert version == account.policy_version == 1
    assert account.intake_consented_at is not None
    assert (legacy_friend.enabled, legacy_friend.enabled_explicit) == (True, False)
    assert (my_documents.enabled, my_documents.enabled_explicit) == (True, False)
    assert (explicit_stranger.enabled, explicit_stranger.enabled_explicit) == (True, True)
    assert source_ready(legacy_friend) is False

    assert ack_policy(db, account.id, version) == version
    db.refresh(account)
    db.refresh(legacy_friend)
    assert account.policy_acked_version == version
    assert (legacy_friend.acked_enabled, legacy_friend.policy_acked_version) == (True, version)
    assert source_ready(legacy_friend) is True


def test_source_policy_is_explicit_pending_until_the_matching_ack(db):
    account = _account(db)
    source = _source(db, account)
    source.source_type = "friend"
    source.enabled_explicit = False
    source.acked_enabled = True
    source.policy_version = source.policy_acked_version = account.policy_version = account.policy_acked_version = 1
    db.commit()

    version = set_source_policy(db, source.id, False)
    db.refresh(account)
    db.refresh(source)

    assert version == account.policy_version == source.policy_version == 2
    assert source.enabled_explicit is True
    assert source.enabled is False
    assert source.acked_enabled is True
    assert source_ready(source) is False
    with pytest.raises(InboxValidationError):
        ack_policy(db, account.id, 1)
    with pytest.raises(InboxValidationError):
        ack_policy(db, account.id, 3)
    assert ack_policy(db, account.id, 2) == 2
    db.refresh(source)
    assert (source.acked_enabled, source.policy_acked_version, source_ready(source)) == (False, 2, True)


def test_source_policy_two_toggles_restage_the_complete_snapshot_before_ack(db):
    account = _account(db)
    source_a = _source(db, account, "source-a")
    source_a.source_type = "friend"
    source_b = ZaloSource(
        id="source-b",
        connector_account_id=account.id,
        conversation_id="source-b",
        conversation_type="group",
        display_name="Nguồn B",
        source_type="group",
        enabled=True,
        enabled_explicit=False,
    )
    db.add(source_b)
    db.commit()

    assert ack_policy(db, account.id, apply_intake_consent(db, account.id)) == 1
    assert set_source_policy(db, source_a.id, False) == 2
    assert set_source_policy(db, source_b.id, False) == 3
    db.refresh(account)
    db.refresh(source_a)
    db.refresh(source_b)

    assert (source_a.policy_version, source_b.policy_version) == (account.policy_version, account.policy_version)
    with pytest.raises(InboxValidationError):
        ack_policy(db, account.id, 2)
    assert ack_policy(db, account.id, 3) == 3
    db.refresh(source_a)
    db.refresh(source_b)
    assert (source_a.acked_enabled, source_a.policy_acked_version, source_ready(source_a)) == (False, 3, True)
    assert (source_b.acked_enabled, source_b.policy_acked_version, source_ready(source_b)) == (False, 3, True)


def test_concurrent_source_toggles_use_distinct_atomic_versions_and_current_snapshot_is_ackable(tmp_path):
    db_path = tmp_path / "concurrent-policy.sqlite"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})
    database.enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    setup = factory()
    try:
        account = _account(setup)
        source_a = _source(setup, account, "concurrent-a")
        source_b = ZaloSource(
            id="concurrent-source-b",
            connector_account_id=account.id,
            conversation_id="concurrent-b",
            conversation_type="user",
            display_name="Nguồn B",
            enabled=True,
            source_type="friend",
        )
        setup.add(source_b)
        setup.commit()
        source_ids = (source_a.id, source_b.id)
    finally:
        setup.close()

    barrier = threading.Barrier(2)
    versions = []

    def toggle(source_id):
        session = factory()
        try:
            barrier.wait()
            versions.append(set_source_policy(session, source_id, False))
        finally:
            session.close()

    threads = [threading.Thread(target=toggle, args=(source_id,)) for source_id in source_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    verify = factory()
    try:
        account = verify.query(ZaloConnectorAccount).one()
        assert sorted(versions) == [1, 2]
        assert account.policy_version == 2
        assert ack_policy(verify, account.id, account.policy_version) == 2
        assert all(source_ready(source) for source in verify.query(ZaloSource).all())
    finally:
        verify.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_concurrent_source_refreshes_use_distinct_atomic_request_versions(tmp_path):
    db_path = tmp_path / "concurrent-source-sync.sqlite"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})
    database.enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    setup = factory()
    try:
        account_id = _account(setup).id
    finally:
        setup.close()

    barrier = threading.Barrier(2)
    versions = []

    def refresh():
        session = factory()
        try:
            barrier.wait()
            versions.append(request_source_sync(session, account_id))
        finally:
            session.close()

    threads = [threading.Thread(target=refresh) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    verify = factory()
    try:
        assert sorted(versions) == [1, 2]
        assert verify.query(ZaloConnectorAccount).one().source_sync_request_version == 2
    finally:
        verify.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_source_policy_pending_fails_closed_for_media_until_policy_ack(db, tmp_path):
    account = _account(db)
    account.intake_consented_at = datetime(2026, 8, 4, 2, tzinfo=UTC)
    source = _source(db, account)
    source.source_type = "friend"
    source.enabled_explicit = True
    source.enabled = True
    source.acked_enabled = True
    source.policy_version = source.policy_acked_version = account.policy_version = account.policy_acked_version = 1
    db.commit()
    object_path = tmp_path / account.id / "pending.png"
    object_path.parent.mkdir()
    _png(object_path)
    payload = {
        "schema_version": 1,
        "event_type": "media",
        "connector_account_id": account.id,
        "conversation_id": source.conversation_id,
        "conversation_type": "user",
        "source_display_name": source.display_name,
        "msg_id": "pending-media",
        "sent_at": "2026-08-04T03:00:00Z",
        "attachment_index": 0,
        "media_object_key": f"{account.id}/pending.png",
        "mime_type": "image/png",
        "size_bytes": object_path.stat().st_size,
    }
    set_source_policy(db, source.id, True)
    assert ingest_webhook_event(db, payload, storage_root=tmp_path) == {"ignored": True}
    assert ack_policy(db, account.id, 2) == 2
    assert ingest_webhook_event(db, payload, storage_root=tmp_path).source_id == source.id


def test_media_before_consent_is_ignored_even_for_legacy_enabled_source(db, tmp_path):
    account = _account(db)
    source = _source(db, account)
    object_path = tmp_path / account.id / "before-consent.png"
    object_path.parent.mkdir()
    _png(object_path)
    assert ingest_webhook_event(
        db,
        {
            "schema_version": 1,
            "event_type": "media",
            "connector_account_id": account.id,
            "conversation_id": source.conversation_id,
            "conversation_type": "user",
            "source_display_name": source.display_name,
            "msg_id": "before-consent",
            "sent_at": "2026-08-04T03:00:00Z",
            "attachment_index": 0,
            "media_object_key": f"{account.id}/before-consent.png",
            "mime_type": "image/png",
            "size_bytes": object_path.stat().st_size,
        },
        storage_root=tmp_path,
    ) == {"ignored": True}
    assert db.query(ZaloMedia).count() == 0


def test_discovery_reclassifies_default_source_but_preserves_explicit_choice(db):
    account = _account(db)
    apply_intake_consent(db, account.id)
    payload = {
        "schema_version": 1,
        "event_type": "discovery",
        "connector_account_id": account.id,
        "conversation_id": "thread-discovery",
        "conversation_type": "user",
        "source_display_name": "Nguồn discovery",
        "source_type": "stranger",
        "last_activity_at": "2026-08-04T03:00:00Z",
    }
    source = ingest_webhook_event(db, payload, storage_root=".")
    assert (source.source_type, source.enabled, source.enabled_explicit) == ("stranger", False, False)

    source.enabled_explicit = True
    source.enabled = False
    db.commit()
    reclassified = ingest_webhook_event(db, {**payload, "source_type": "friend"}, storage_root=".")
    assert (reclassified.source_type, reclassified.enabled, reclassified.enabled_explicit) == ("friend", False, True)

    with pytest.raises(InboxValidationError, match="source_type"):
        ingest_webhook_event(db, {**payload, "conversation_id": "bad", "source_type": "unknown"}, storage_root=".")
    with pytest.raises(InboxValidationError, match="Timestamp"):
        ingest_webhook_event(
            db,
            {**payload, "conversation_id": "bad-activity", "last_activity_at": "not-a-timestamp"},
            storage_root=".",
        )


def test_discovery_after_current_ack_bumps_once_and_exact_ack_activates_source(db):
    account = _account(db)
    assert ack_policy(db, account.id, apply_intake_consent(db, account.id)) == 1
    payload = {
        "schema_version": 1,
        "event_type": "discovery",
        "connector_account_id": account.id,
        "conversation_id": "new-friend",
        "conversation_type": "user",
        "source_display_name": "Bạn mới",
        "source_type": "friend",
    }

    source = ingest_webhook_event(db, payload, storage_root=".")
    db.refresh(account)
    assert (account.policy_version, account.policy_acked_version) == (2, 1)
    assert (source.enabled, source.enabled_explicit, source.policy_version, source_ready(source)) == (True, False, 2, False)

    ingest_webhook_event(db, {**payload, "source_display_name": "Bạn mới đổi tên"}, storage_root=".")
    db.refresh(account)
    assert account.policy_version == 2

    assert ack_policy(db, account.id, 2) == 2
    db.refresh(source)
    assert source_ready(source) is True


def test_default_reclassification_after_current_ack_bumps_once_and_preserves_explicit_choice(db):
    account = _account(db)
    assert ack_policy(db, account.id, apply_intake_consent(db, account.id)) == 1
    payload = {
        "schema_version": 1,
        "event_type": "discovery",
        "connector_account_id": account.id,
        "conversation_id": "reclassified-source",
        "conversation_type": "user",
        "source_display_name": "Nguồn lạ",
        "source_type": "stranger",
    }
    source = ingest_webhook_event(db, payload, storage_root=".")
    assert ack_policy(db, account.id, 2) == 2

    source = ingest_webhook_event(db, {**payload, "source_type": "friend"}, storage_root=".")
    db.refresh(account)
    assert (account.policy_version, account.policy_acked_version) == (3, 2)
    assert (source.enabled, source.enabled_explicit, source.policy_version, source_ready(source)) == (True, False, 3, False)
    assert ack_policy(db, account.id, 3) == 3

    assert set_source_policy(db, source.id, False) == 4
    assert ack_policy(db, account.id, 4) == 4
    source = ingest_webhook_event(db, {**payload, "source_type": "stranger"}, storage_root=".")
    db.refresh(account)
    assert (account.policy_version, source.enabled, source.enabled_explicit, source_ready(source)) == (4, False, True, True)


def test_source_sync_ack_rejects_stale_future_and_wrong_account_but_replays_exactly(db):
    account = _account(db)
    assert request_source_sync(db, account.id) == 1
    with pytest.raises(InboxValidationError):
        ack_source_sync(db, account.id, 0)
    with pytest.raises(InboxValidationError):
        ack_source_sync(db, account.id, 2)
    with pytest.raises(InboxValidationError):
        ack_source_sync(db, "wrong-account", 1)
    assert ack_source_sync(db, account.id, 1) == 1
    assert ack_source_sync(db, account.id, 1) == 1


def test_source_refresh_ack_and_connector_gap_are_idempotent(db):
    account = _account(db)
    first_request = request_source_sync(db, account.id)
    second_request = request_source_sync(db, account.id)
    assert (first_request, second_request, account.source_sync_request_version) == (1, 2, 2)

    now = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)
    apply_connector_report(account, "connected", 1, now, qr_login_success=True, bound_zalo_id="owner")
    apply_connector_report(account, "disconnected", 1, now + timedelta(seconds=1))
    first_gap = account.gap_started_at
    apply_connector_report(account, "connected", 1, now + timedelta(seconds=2))
    apply_connector_report(account, "disconnected", 2, now + timedelta(seconds=3))
    assert account.gap_started_at == first_gap == now + timedelta(seconds=1)


def test_listener_generation_replacement_marks_gap_once_when_receiving(db):
    account = _account(db)
    now = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)
    assert apply_connector_report(account, "connected", 1, now, qr_login_success=True, bound_zalo_id="owner") is True
    assert apply_connector_report(account, "connected", 2, now + timedelta(seconds=1)) is True
    assert account.gap_started_at == now + timedelta(seconds=1)
    assert apply_connector_report(account, "connected", 2, now + timedelta(seconds=2)) is True
    assert account.gap_started_at == now + timedelta(seconds=1)


def test_zalo_message_text_rejects_duplicate_message_identity(db):
    from models import ZaloMessageText

    account = _account(db)
    source = _source(db, account)
    values = dict(
        connector_account_id=account.id,
        source_id=source.id,
        conversation_id=source.conversation_id,
        msg_id="text-1",
        sender_id="sender-1",
        sent_at=datetime(2026, 8, 4, 3, 0, tzinfo=UTC),
        received_at=datetime(2026, 8, 4, 3, 1, tzinfo=UTC),
        raw_text="Nội dung kiểm thử",
        payload_digest="a" * 64,
    )
    db.add(ZaloMessageText(id="text-row-1", **values))
    db.commit()
    db.add(ZaloMessageText(id="text-row-2", **values))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_zalo_data_sync_model_persists_frozen_json(db):
    from models import ZaloDataSyncRun

    account = _account(db)
    source_ids = ["source-1", "source-2"]
    counters = {"received": 2, "persisted": 1}
    run = ZaloDataSyncRun(
        id="sync-1",
        connector_account_id=account.id,
        status="running",
        cutoff_at=datetime(2026, 8, 4, 3, 0, tzinfo=UTC),
        deadline_at=datetime(2026, 8, 4, 3, 5, tzinfo=UTC),
        source_ids_json=source_ids,
        counters_json=counters,
        started_at=datetime(2026, 8, 4, 3, 0, tzinfo=UTC),
    )
    db.add(run)
    db.commit()
    source_ids.append("source-3")
    counters["received"] = 9
    db.expire_all()

    persisted = db.query(ZaloDataSyncRun).filter_by(id=run.id).one()
    assert persisted.source_ids_json == ["source-1", "source-2"]
    assert persisted.counters_json == {"received": 2, "persisted": 1}

    db.add(
        ZaloDataSyncRun(
            id="sync-2",
            connector_account_id=account.id,
            status="running",
            cutoff_at=run.cutoff_at,
            deadline_at=run.deadline_at,
            source_ids_json=[],
            counters_json={},
            started_at=run.started_at,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


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
    source.source_type = "friend"
    source.enabled_explicit = None
    db.commit()
    assert ack_policy(db, account.id, apply_intake_consent(db, account.id)) == 1
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
