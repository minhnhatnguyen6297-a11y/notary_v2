from __future__ import annotations

import hashlib
import hmac
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from models import ZaloBatch, ZaloConnectorAccount, ZaloMedia, ZaloSource
from routers import zalo_inbox


def _app(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    monkeypatch.setenv("ZALO_INBOX_BOOTSTRAP_SECRET", "bootstrap-test")
    monkeypatch.setenv("ZALO_INBOX_WEBHOOK_SECRET", "webhook-test")
    monkeypatch.setenv("ZALO_INBOX_STORAGE_ROOT", str(tmp_path / "source"))
    monkeypatch.setenv("ZALO_INBOX_BATCH_ROOT", str(tmp_path / "batches"))
    monkeypatch.setenv("ZALO_INBOX_MAX_FILE_BYTES", str(1024 * 1024))
    monkeypatch.setenv("ZALO_INBOX_MAX_ITEMS", "10")
    monkeypatch.setenv("ZALO_INBOX_MAX_TOTAL_BYTES", str(2 * 1024 * 1024))
    monkeypatch.setenv("ZALO_INBOX_MAX_RENDERED_PIXELS", "10000")

    app = FastAPI()
    app.include_router(zalo_inbox.router)

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[zalo_inbox.get_session_factory] = lambda: factory
    return app, factory


def _signed_post(client, payload):
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = hmac.new(b"webhook-test", timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return client.post(
        "/zalo-inbox/api/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "x-zalo-timestamp": timestamp,
            "x-zalo-signature": signature,
        },
    )


def test_onboard_webhook_batch_pdf_and_safe_serialization(tmp_path, monkeypatch):
    app, factory = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        page = client.get("/zalo-inbox/")
        assert page.status_code == 200
        assert "Hộp tài liệu Zalo" in page.text
        unauthorized = client.post("/zalo-inbox/api/connectors/onboard")
        assert unauthorized.status_code == 403
        onboard = client.post(
            "/zalo-inbox/api/connectors/onboard",
            headers={"x-zalo-bootstrap": "bootstrap-test"},
        )
        assert onboard.status_code == 200
        account_id = onboard.json()["connector_account_id"]
        assert client.post(
            "/zalo-inbox/api/connectors/onboard",
            headers={"x-zalo-bootstrap": "bootstrap-test"},
        ).json()["connector_account_id"] == account_id

        discovery = {
            "schema_version": 1,
            "event_type": "discovery",
            "connector_account_id": account_id,
            "conversation_id": "thread-1",
            "conversation_type": "user",
            "source_display_name": "Khách A",
        }
        assert _signed_post(client, discovery).status_code == 200

        db = factory()
        source = db.query(ZaloSource).one()
        source.enabled = True
        db.commit()
        source_id = source.id
        db.close()

        object_path = tmp_path / "source" / account_id / "doc.png"
        object_path.parent.mkdir(parents=True)
        Image.new("RGB", (20, 10), "white").save(object_path, "PNG")
        media_payload = {
            "schema_version": 1,
            "event_type": "media",
            "connector_account_id": account_id,
            "conversation_id": "thread-1",
            "conversation_type": "user",
            "source_display_name": "Khách A",
            "msg_id": "msg-1",
            "sent_at": "2026-08-04T03:00:00Z",
            "attachment_index": 0,
            "media_object_key": f"{account_id}/doc.png",
            "mime_type": "image/png",
            "size_bytes": object_path.stat().st_size,
        }
        accepted = _signed_post(client, media_payload)
        assert accepted.status_code == 200

        state = client.get("/zalo-inbox/api/state")
        assert state.status_code == 200
        payload = state.json()
        assert payload["sources"][0]["id"] == source_id
        media_id = payload["media"][0]["id"]
        assert "media_object_key" not in json.dumps(payload)
        assert str(tmp_path) not in json.dumps(payload)

        created = client.post("/zalo-inbox/api/batches", json={"media_ids": [media_id]})
        assert created.status_code == 202
        batch_id = created.json()["batch_id"]
        batch = client.get(f"/zalo-inbox/api/batches/{batch_id}")
        assert batch.status_code == 200
        assert batch.json()["status"] == "review"
        assert str(tmp_path) not in batch.text

        config_timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        config_signature = hmac.new(
            b"webhook-test", config_timestamp.encode() + b".", hashlib.sha256
        ).hexdigest()
        connector_config = client.get(
            f"/zalo-inbox/api/connectors/{account_id}/config",
            headers={"x-zalo-timestamp": config_timestamp, "x-zalo-signature": config_signature},
        )
        assert connector_config.status_code == 200
        assert connector_config.json()["sources"] == [{"conversation_id": "thread-1", "enabled": True}]
        assert connector_config.json()["protected_media_object_keys"] == [f"{account_id}/doc.png"]

        db = factory()
        protected_batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).one()
        protected_batch.expires_at = datetime(2026, 8, 4, 2, 59, tzinfo=timezone.utc)
        db.commit()
        db.close()
        config_timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        config_signature = hmac.new(
            b"webhook-test", config_timestamp.encode() + b".", hashlib.sha256
        ).hexdigest()
        expired_config = client.get(
            f"/zalo-inbox/api/connectors/{account_id}/config",
            headers={"x-zalo-timestamp": config_timestamp, "x-zalo-signature": config_signature},
        )
        assert expired_config.json()["protected_media_object_keys"] == []

        db = factory()
        protected_batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).one()
        protected_batch.expires_at = datetime.now(timezone.utc) + timedelta(hours=72)
        db.commit()
        db.close()

        selected = client.post(f"/zalo-inbox/api/batches/{batch_id}/outputs", json={"outputs": ["pdf"]})
        assert selected.status_code == 202
        completed = client.get(f"/zalo-inbox/api/batches/{batch_id}").json()
        assert completed["status"] == "completed"
        assert completed["outputs"]["pdf"]["status"] == "ready"
        assert "path" not in json.dumps(completed)
        state_after_completion = client.get("/zalo-inbox/api/state").json()
        assert state_after_completion["latest_batch"]["unfinished"] is False

        download = client.get(f"/zalo-inbox/api/batches/{batch_id}/download/pdf")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/pdf")

        db = factory()
        expired_batch = db.query(ZaloBatch).filter(ZaloBatch.id == batch_id).one()
        expired_batch.expires_at = datetime(2026, 8, 4, 2, 59, tzinfo=timezone.utc)
        db.commit()
        db.close()
        expired_download = client.get(f"/zalo-inbox/api/batches/{batch_id}/download/pdf")
        assert expired_download.status_code == 404


def test_webhook_rejects_bad_signature_without_writing(tmp_path, monkeypatch):
    app, factory = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        client.post("/zalo-inbox/api/connectors/onboard", headers={"x-zalo-bootstrap": "bootstrap-test"})
        response = client.post(
            "/zalo-inbox/api/webhook",
            json={"schema_version": 1, "event_type": "discovery"},
            headers={
                "x-zalo-timestamp": str(int(datetime.now(timezone.utc).timestamp())),
                "x-zalo-signature": "bad",
            },
        )
        assert response.status_code == 400
    db = factory()
    assert db.query(ZaloMedia).count() == 0
    assert db.query(ZaloSource).count() == 0
    db.close()


def test_start_connector_is_idempotent_and_does_not_expose_secrets(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch)
    monkeypatch.setenv("ZALO_INBOX_BACKEND_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("ZALO_CONNECTOR_QUOTA_BYTES", "1048576")
    monkeypatch.setenv("ZALO_CONNECTOR_RETENTION_HOURS", "72")
    monkeypatch.setenv("UNRELATED_API_KEY", "must-not-reach-connector")
    monkeypatch.setattr(zalo_inbox, "_connector_process", None)
    calls = []

    class Process:
        pid = 1234

        def __init__(self):
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            assert timeout == 3

    def fake_popen(command, **options):
        calls.append((command, options))
        return Process()

    monkeypatch.setattr(zalo_inbox.subprocess, "Popen", fake_popen)
    with TestClient(app) as client:
        first = client.post("/zalo-inbox/api/connectors/start")
        second = client.post("/zalo-inbox/api/connectors/start")

    assert first.status_code == 202
    assert first.json() == {"status": "starting"}
    assert second.status_code == 200
    assert second.json() == {"status": "running"}
    assert len(calls) == 1
    command, options = calls[0]
    assert command == ["node", str(zalo_inbox._connector_entrypoint())]
    assert "bootstrap-test" not in json.dumps(command)
    assert "webhook-test" not in json.dumps(command)
    assert options["env"]["ZALO_INBOX_BOOTSTRAP_SECRET"] == "bootstrap-test"
    assert options["env"]["ZALO_INBOX_WEBHOOK_SECRET"] == "webhook-test"
    assert options["env"]["ZALO_CONNECTOR_PARENT_PID"] == str(os.getpid())
    assert "UNRELATED_API_KEY" not in options["env"]
    assert options["stdout"] is zalo_inbox.subprocess.DEVNULL
    assert options["stderr"] is zalo_inbox.subprocess.DEVNULL
    assert calls[0][1]["env"] is options["env"]
    assert zalo_inbox._connector_process is None


def test_start_connector_fails_closed_when_deployment_config_is_missing(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch)
    monkeypatch.delenv("ZALO_CONNECTOR_QUOTA_BYTES", raising=False)
    monkeypatch.delenv("ZALO_CONNECTOR_RETENTION_HOURS", raising=False)
    monkeypatch.setattr(zalo_inbox, "_connector_process", None)
    with TestClient(app) as client:
        response = client.post("/zalo-inbox/api/connectors/start")
    assert response.status_code == 503
    assert "ZALO_CONNECTOR_QUOTA_BYTES" in response.json()["detail"]


def test_start_connector_rejects_invalid_limits_before_spawning(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch)
    monkeypatch.setenv("ZALO_CONNECTOR_QUOTA_BYTES", "not-a-number")
    monkeypatch.setenv("ZALO_CONNECTOR_RETENTION_HOURS", "72")
    monkeypatch.setattr(zalo_inbox, "_connector_process", None)
    monkeypatch.setattr(
        zalo_inbox.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Popen must not run")),
    )

    with TestClient(app) as client:
        response = client.post("/zalo-inbox/api/connectors/start")

    assert response.status_code == 503
    assert response.json()["detail"] == "ZALO_CONNECTOR_QUOTA_BYTES không hợp lệ"


def test_connector_failure_is_sanitized_and_clears_stale_qr(tmp_path, monkeypatch):
    app, factory = _app(tmp_path, monkeypatch)
    monkeypatch.setenv("ZALO_CONNECTOR_QUOTA_BYTES", "1048576")
    monkeypatch.setenv("ZALO_CONNECTOR_RETENTION_HOURS", "72")
    monkeypatch.setattr(zalo_inbox, "_connector_process", None)

    db = factory()
    db.add(
        ZaloConnectorAccount(
            id="account-failed",
            session_state="usable",
            listener_generation=0,
            qr_image="data:image/png;base64,stale",
            last_seen_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    db.close()

    class FailedProcess:
        pid = 1234

        def __init__(self):
            self.polls = 0

        def poll(self):
            self.polls += 1
            return None if self.polls == 1 else 9

        def terminate(self):
            raise AssertionError("exited process must not be terminated")

    monkeypatch.setattr(zalo_inbox.subprocess, "Popen", lambda *args, **kwargs: FailedProcess())

    with TestClient(app) as client:
        started = client.post("/zalo-inbox/api/connectors/start")
        snapshot = client.get("/zalo-inbox/api/state")

    assert started.status_code == 202
    assert snapshot.status_code == 200
    connector = snapshot.json()["connector"]
    assert connector["state"] == "disconnected"
    assert connector["error"] == "Zalo connector đã dừng. Kiểm tra cấu hình và thử lại."
    assert connector["qr_image"] is None
    assert "exit_code" not in connector
    assert "stderr" not in connector
    assert "secret" not in json.dumps(connector).lower()


def test_connector_immediate_exit_returns_a_sanitized_startup_error(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch)
    monkeypatch.setenv("ZALO_CONNECTOR_QUOTA_BYTES", "1048576")
    monkeypatch.setenv("ZALO_CONNECTOR_RETENTION_HOURS", "72")
    monkeypatch.setattr(zalo_inbox, "_connector_process", None)

    class ExitedProcess:
        pid = 1234

        def poll(self):
            return 7

    monkeypatch.setattr(zalo_inbox.subprocess, "Popen", lambda *args, **kwargs: ExitedProcess())

    with TestClient(app) as client:
        response = client.post("/zalo-inbox/api/connectors/start")

    assert response.status_code == 503
    assert response.json() == {"detail": zalo_inbox.CONNECTOR_STOPPED_MESSAGE}
    assert zalo_inbox._connector_process is None


def test_start_connector_force_restart_replaces_a_running_process(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch)
    monkeypatch.setenv("ZALO_CONNECTOR_QUOTA_BYTES", "1048576")
    monkeypatch.setenv("ZALO_CONNECTOR_RETENTION_HOURS", "72")

    class RunningProcess:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            assert timeout == 3

    old_process = RunningProcess()
    new_process = RunningProcess()
    captured_env = []
    monkeypatch.setattr(zalo_inbox, "_connector_process", old_process)
    monkeypatch.setattr(
        zalo_inbox.subprocess,
        "Popen",
        lambda *args, **kwargs: (captured_env.append(kwargs["env"]) or new_process),
    )

    with TestClient(app) as client:
        response = client.post(
            "/zalo-inbox/api/connectors/start",
            json={"force_restart": True, "force_qr": True},
        )
        assert response.status_code == 202
        assert response.json() == {"status": "starting"}
        assert old_process.terminated is True
        assert zalo_inbox._connector_process is new_process
        assert captured_env[0]["ZALO_CONNECTOR_FORCE_QR"] == "1"
    assert new_process.terminated is True
    assert zalo_inbox._connector_process is None


def test_force_qr_clears_the_previous_qr_before_starting(tmp_path, monkeypatch):
    app, factory = _app(tmp_path, monkeypatch)
    monkeypatch.setenv("ZALO_CONNECTOR_QUOTA_BYTES", "1048576")
    monkeypatch.setenv("ZALO_CONNECTOR_RETENTION_HOURS", "72")
    monkeypatch.setattr(zalo_inbox, "_connector_process", None)

    db = factory()
    db.add(
        ZaloConnectorAccount(
            id="account-stale-qr",
            session_state="login_required",
            listener_generation=0,
            qr_image="data:image/png;base64,stale",
        )
    )
    db.commit()
    db.close()

    class RunningProcess:
        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout):
            pass

    monkeypatch.setattr(zalo_inbox.subprocess, "Popen", lambda *args, **kwargs: RunningProcess())

    with TestClient(app) as client:
        response = client.post("/zalo-inbox/api/connectors/start", json={"force_qr": True})
        snapshot = client.get("/zalo-inbox/api/state")

    assert response.status_code == 202
    assert snapshot.json()["connector"]["qr_image"] is None


def test_opening_state_does_not_public_or_open_stale_qr(tmp_path, monkeypatch):
    app, factory = _app(tmp_path, monkeypatch)
    db = factory()
    db.add(ZaloConnectorAccount(
        id="account-stale-open",
        session_state="login_required",
        listener_generation=0,
        qr_image="data:image/png;base64,stale",
        qr_generated_at=datetime.now(timezone.utc) - timedelta(minutes=3),
        qr_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    ))
    db.commit()
    db.close()

    with TestClient(app) as client:
        connector = client.get("/zalo-inbox/api/state").json()["connector"]

    assert connector["qr_image"] is None


def test_windows_cleanup_is_idempotent_when_the_child_refuses_to_exit(monkeypatch):
    calls = []

    class StubbornProcess:
        def poll(self):
            return None

        def terminate(self):
            calls.append("terminate")

        def kill(self):
            calls.append("kill")

        def wait(self, timeout):
            calls.append(f"wait:{timeout}")
            raise zalo_inbox.subprocess.TimeoutExpired("node", timeout)

    monkeypatch.setattr(zalo_inbox, "_connector_process", StubbornProcess())
    monkeypatch.setattr(zalo_inbox, "_connector_error", "old")

    zalo_inbox._terminate_connector_process()

    assert calls == ["terminate", "wait:3", "kill", "wait:3"]
    assert zalo_inbox._connector_process is None
    assert zalo_inbox._connector_error is None


def test_main_lifespan_stops_the_managed_connector(monkeypatch):
    import main

    stopped = []
    monkeypatch.setattr(main.ocr_local, "warmup_local_ocr", lambda: (True, None))
    monkeypatch.setattr(main.zalo_inbox, "_terminate_connector_process", lambda: stopped.append(True))

    async def exercise():
        async with main.lifespan(main.app):
            pass

    asyncio.run(exercise())
    assert stopped == [True]
