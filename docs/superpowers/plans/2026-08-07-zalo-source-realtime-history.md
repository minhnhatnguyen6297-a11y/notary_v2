# Zalo Source, Realtime, and History Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved Zalo source policy, metadata synchronization, realtime text/media intake, and user-triggered seven-day best-effort Data Sync without changing shared OCR behavior.

**Architecture:** Extend the existing SQLite/SQLAlchemy Zalo records with explicit policy state and narrow text/sync-run tables. Reuse the existing signed webhook, connector config polling, durable file outbox, media store, `/api/state` browser polling, and process lifecycle. Deliver source policy/realtime first, then manual history, then UI/integration; keep OCR/output code and its dirty shared files outside every implementation commit.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, SQLite startup migrations, Pydantic, Jinja2, browser JavaScript, Node.js 20 built-in test runner, `zca-js==2.1.2`, pytest.

## Global Constraints

- Source of truth: `docs/platform/zalo-document-inbox/spec.md` at approval commit `954b4d7`.
- Preserve `docs/platform/document-intake/spec.md`, `routers/ocr_ai.py`, and `tests/test_ocr_ai.py`; do not stage, modify, revert, or use them to make this goal green.
- Friends/groups default `BẬT` after persisted consent; strangers default `TẮT`; explicit user choice wins future refresh/reclassification.
- `My Documents` is a separate default-`BẬT` source, but realtime support remains behind controlled-account verification and history remains excluded until a separately approved live spike.
- Source Sync updates metadata only; full reconciliation is every 60 minutes, never every 15 seconds.
- Realtime receives upstream events continuously; source policy gates persistence/download after receipt.
- Data Sync starts only from the user action, runs once per account at a time, snapshots ACKed enabled source IDs plus cutoff, issues exactly one User and one Group history request, applies the local seven-day filter, and never claims completeness.
- Production logs must not contain raw chat text, Zalo raw identifiers, original filenames, remote attachment URLs, session/cookie data, or document contents.
- Deployment must provide `ZALO_INBOX_TEXT_QUOTA_BYTES`, `ZALO_INBOX_TEXT_RETENTION_HOURS`, and `ZALO_DATA_SYNC_TIMEOUT_SECONDS`; all must be positive and fail closed when missing/invalid.
- Use `venv/Scripts/python.exe`, not system Python 3.14.
- Focused verification and full-project verification must be reported separately.
- User approved shared SQLite FK enforcement on 2026-08-07: every app connection uses `PRAGMA foreign_keys=ON`; startup runs `PRAGMA foreign_key_check` and stops on violations. Do not add cascade or repair callers without separate evidence/approval.
- Baseline note: `tests/test_zalo_inbox.py` currently has two date-fixture failures because fixed August 2026 batches are now expired; repair those fixtures only inside the Zalo test task. API-only baseline is 12 passed; UI baseline is 5 passed; connector baseline is 22 passed.

---

## File Ownership Map

- `models.py`: Zalo persistence entities and uniqueness constraints only.
- `database.py`: additive/idempotent SQLite migration for Zalo tables and columns.
- `services/zalo_inbox.py`: source policy, webhook component ingestion, text retention, and Data Sync state transitions; do not change OCR/output functions.
- `routers/zalo_inbox.py`: request/response models and HTTP endpoints; keep managed-process lifecycle intact.
- `zalo_connector/src/core.mjs`: signed backend client, message normalization, component events, durable queue primitives.
- `zalo_connector/src/connector.mjs`: source discovery triggers, policy refresh/ACK, listener routing, My Documents classification, and manual history orchestration.
- `frontend/templates/zalo_inbox.html` and `frontend/static/js/zalo_inbox.js`: consent/source/Data Sync UI using existing `/api/state` polling.
- `tests/test_zalo_inbox.py`, `tests/test_zalo_inbox_api.py`, `tests/zalo_inbox_ui_static.test.mjs`, `zalo_connector/test/*.test.mjs`: focused regression coverage.
- `verify.ps1`: change only if a newly added Zalo file is not recognized by `Test-ZaloInboxRelevantChange`; do not change its OCR scope.

---

### Task 1: Persist source policy, text components, gaps, and Data Sync runs

**Files:**
- Modify: `models.py:186-260`
- Modify: `database.py:90-99`
- Modify: `verify.ps1:86-105`
- Test: `tests/test_zalo_inbox.py`

**Interfaces:**
- Produces `ZaloConnectorAccount.intake_consented_at`, `policy_version`, `policy_acked_version`, `source_sync_request_version`, `source_sync_acked_version`, `gap_started_at`, and `text_storage_full`.
- Produces `ZaloSource.source_type`, nullable tri-state `enabled_explicit`, `acked_enabled`, `policy_version`, `policy_acked_version`, and `last_activity_at`. Migration leaves legacy rows `enabled_explicit=NULL`; newly discovered default-derived rows use `False`; only a user toggle writes `True`.
- Produces `ZaloMessageText` with unique `(connector_account_id, conversation_id, msg_id)` and fields `sender_id`, `sent_at`, `received_at`, `raw_text`, `payload_digest`.
- Produces `ZaloDataSyncRun` with `status`, `cutoff_at`, `deadline_at`, `source_ids_json`, `counters_json`, `error_message`, `started_at`, and `completed_at`; migration creates partial unique index `uq_zalo_data_sync_running_account ON zalo_data_sync_runs(connector_account_id) WHERE status='running'`.
- Consumers: Tasks 2–6 import these models directly; no JSON policy blob is allowed as a second source of truth.

- [ ] **Step 1: Add failing model and migration tests**

Add tests that create the schema twice and assert additive migration is idempotent, legacy `enabled` rows remain untouched before re-consent, duplicate text keys violate the database uniqueness contract, and Data Sync rows persist frozen source/counter JSON without mutation.

```python
def test_zalo_policy_migration_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "legacy.db")
    database.migrate_zalo_schema()
    database.migrate_zalo_schema()
    columns = _columns(tmp_path / "legacy.db", "zalo_sources")
    assert {"source_type", "enabled_explicit", "acked_enabled", "policy_version", "policy_acked_version", "last_activity_at"} <= columns
    assert _scalar(tmp_path / "legacy.db", "SELECT enabled_explicit FROM zalo_sources LIMIT 1") is None
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `venv/Scripts/python.exe -m pytest tests/test_zalo_inbox.py -k "policy_migration or message_text or data_sync_model" -q`

Expected: FAIL because the columns/models do not exist.

- [ ] **Step 3: Add the minimum SQLAlchemy entities and SQLite migration**

Use scalar columns and database constraints. Define local test helpers `_columns(db_path, table)` and `_scalar(db_path, sql)` using `sqlite3`. Extend `migrate_zalo_schema()` with `_ensure_table_columns()`, `CREATE TABLE IF NOT EXISTS`, and the partial unique index; do not rebuild or reinterpret legacy source rows during startup.

```python
class ZaloMessageText(Base):
    __tablename__ = "zalo_message_texts"
    __table_args__ = (UniqueConstraint("connector_account_id", "conversation_id", "msg_id", name="uq_zalo_message_text"),)

class ZaloDataSyncRun(Base):
    __tablename__ = "zalo_data_sync_runs"
```

- [ ] **Step 4: Run focused tests and migration smoke**

Run:

```bash
venv/Scripts/python.exe -m pytest tests/test_zalo_inbox.py -k "policy_migration or message_text or data_sync_model" -q
venv/Scripts/python.exe -c "import database; database.migrate_zalo_schema(); database.migrate_zalo_schema()"
```

Expected: PASS. The second migration invocation makes no change and raises no error.

- [ ] **Step 5: Add `database.py` to the Zalo verifier trigger**

Modify `verify.ps1:92-100` so `Test-ZaloInboxRelevantChange` includes `database.py`; run `verify.bat` and record any pre-existing OCR failure separately.

- [ ] **Step 6: Enforce declared foreign keys at the shared connection boundary**

Enable `PRAGMA foreign_keys=ON` for every SQLAlchemy connection and run `PRAGMA foreign_key_check` before normal startup. Add behavioral orphan-insert tests for new Zalo tables plus a valid inheritance-FK smoke on temporary databases. If existing callers fail because they write/delete in the wrong order, stop and report the caller; do not add cascade or broaden the fix.

- [ ] **Step 7: Review and commit Task 1**

Review gate: Terra writer, Sol reviewer. Stage only `models.py`, `database.py`, and the Task 1 test hunks.

```bash
git add models.py database.py tests/test_zalo_inbox.py verify.ps1
git commit -m "feat(zalo): persist source policy and sync state"
```

### Task 2: Implement consent, source defaults, policy ACK, refresh requests, and ordering

**Files:**
- Modify: `services/zalo_inbox.py:284-394` only for source/message ingestion helpers; do not touch OCR/output functions below the batch boundary.
- Modify: `routers/zalo_inbox.py:242-499`
- Test: `tests/test_zalo_inbox.py`
- Test: `tests/test_zalo_inbox_api.py`

**Interfaces:**
- Produces `apply_intake_consent(db, account_id) -> ZaloConnectorAccount`.
- Produces `set_source_policy(db, source_id, enabled) -> ZaloSource`.
- Produces `ack_policy(db, account_id, policy_version) -> ZaloConnectorAccount`; only an exact current version atomically copies every staged desired state into ACK-active state.
- Produces `request_source_sync(db, account_id) -> int` returning the requested version.
- HTTP: `POST /api/connectors/{account_id}/consent`, `PATCH /api/sources/{source_id}`, `POST /api/connectors/{account_id}/sources/refresh`.
- Connector config response: `{policy_version, source_sync_request_version, sources:[{conversation_id, source_type, desired_enabled, acked_enabled, policy_version}], protected_media_object_keys}`.
- Webhook accepts `policy_ack={schema_version:1,event_type:"policy_ack",connector_account_id,policy_version}` and `source_sync_ack={schema_version:1,event_type:"source_sync_ack",connector_account_id,source_sync_request_version}`. Stale/future/wrong-account versions are rejected; exact replay is idempotent.

- [ ] **Step 1: Add failing policy and source-order tests**

Cover re-consent migration, defaults by `source_type`, explicit-choice preservation after stranger→friend reclassification, policy-version increment, fail-closed pending state, stale ACK rejection, source ordering, and listener-gap transitions for disconnect/reconnect/stopped/generation replacement.

```python
def test_reconsent_applies_new_defaults_once_and_preserves_later_explicit_choice(db):
    account = _account(db)
    friend = _source(db, account, source_type="friend", enabled=False)
    stranger = _source(db, account, source_type="stranger", enabled=True)
    apply_intake_consent(db, account.id)
    assert friend.enabled is True and stranger.enabled is False
    set_source_policy(db, friend.id, False)
    apply_intake_consent(db, account.id)
    assert friend.enabled is False and friend.enabled_explicit is True
```

API tests must assert `/api/state` returns `consent_required`, `policy_pending`, `source_type`, `last_activity_at`, and activity-desc/alphabet ordering with strangers in a separate group field.

- [ ] **Step 2: Run focused policy tests and confirm RED**

Run: `venv/Scripts/python.exe -m pytest tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py -k "consent or source_policy or policy_ack or source_order or source_refresh" -q`

Expected: FAIL on missing models/functions/routes.

- [ ] **Step 3: Implement source policy as one versioned contract**

`apply_intake_consent()` applies new defaults only to rows where `enabled_explicit IS NULL`, converts those rows to default-derived `False`, sets the consent timestamp, increments `policy_version`, and leaves rows already `False` or `True` untouched. `set_source_policy()` writes `enabled_explicit=True`, increments the account/source policy version, and leaves `acked_enabled`/`policy_acked_version` unchanged until exact connector ACK.

```python
def source_ready(source: ZaloSource) -> bool:
    return (
        source.policy_acked_version == source.policy_version
        and source.acked_enabled is not None
    )
```

Do not infer ACK from elapsed time or the 15-second config poll.

- [ ] **Step 4: Extend signed webhook/config/state routes**

Accept source discovery with explicit `source_type` and `last_activity_at`. Reject invalid types. An exact `policy_ack` transaction atomically copies desired enabled values to `acked_enabled`, advances account/source ACK versions, and returns success only after commit. `/api/state` must expose pending state without raw conversation IDs or text.

Extend `apply_connector_report()` so a transition from continuously receiving to disconnected, stopped, or a replacement listener generation sets `gap_started_at` once using backend receipt time. Reconnect does not clear or overwrite an existing gap marker; heartbeat repeats are idempotent. Data Sync completion also never clears it.

- [ ] **Step 5: Run backend policy tests**

Run: `venv/Scripts/python.exe -m pytest tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py -k "consent or source_policy or policy_ack or source_order or source_refresh" -q`

Expected: PASS.

- [ ] **Step 6: Review and commit Task 2**

Review gate: Terra writer, Sol reviewer. Confirm no OCR function diff.

```bash
git add services/zalo_inbox.py routers/zalo_inbox.py tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py
git commit -m "feat(zalo): add consent and acknowledged source policy"
```

### Task 3: Make connector Source Sync event-driven with versioned policy ACK

**Files:**
- Modify: `zalo_connector/src/core.mjs:10-57`
- Modify: `zalo_connector/src/connector.mjs:15-344`
- Test: `zalo_connector/test/core.test.mjs`
- Test: `zalo_connector/test/connector.test.mjs`

**Interfaces:**
- Extends `WebhookClient` with `ackPolicy(accountId, policyVersion)` and `ackSourceSync(accountId, sourceSyncRequestVersion)`; each sends the exact Task 2 signed event through existing `sendEvent()`.
- Produces `sourceDescriptor({conversationId, sourceType, displayName, lastActivityAt})` normalized discovery events.
- Produces `syncSources({api, accountId, client, send2meId}) -> Map<string, SourceDescriptor>`.
- Consumes Task 2 config fields and ACK event contracts.
- Keeps `configPollMs=15000`; adds `sourceReconcileMs=3600000`.

- [ ] **Step 1: Add failing connector policy/source-sync tests**

Cover:

```javascript
test('config policy is fail-closed until connector ACKs the exact version', async () => {
  const previous = new Set(['unchanged-source', 'changed-source']);
  const runtime = await refreshRuntimeState({accountId: 'a', client, store, activeEnabledIds: previous});
  assert.equal(runtime.policyVersion, 7);
  assert.deepEqual(sentEvents.at(-1), {
    schema_version: 1,
    event_type: 'policy_ack',
    connector_account_id: 'a',
    policy_version: 7,
  });
  assert.deepEqual([...runtime.enabledIds], ['unchanged-source', 'new-source']);
});
```

Also test that pending changed sources are removed from the effective set before ACK, ACK failure retains only unchanged previously-active sources, friends/groups defaults are metadata only, `My Documents` descriptor uses `api.getContext().loginInfo.send2me_id`, friend/group listener events request immediate reconciliation, manual refresh emits exact `source_sync_ack`, stale refresh versions are ignored, and the periodic timer is 3,600,000 ms rather than 15,000 ms.

- [ ] **Step 2: Run connector tests and confirm RED**

Run: `npm --prefix zalo_connector test`

Expected: FAIL on missing policy/source-sync interfaces.

- [ ] **Step 3: Implement versioned policy refresh and ACK**

`refreshRuntimeState()` computes `pendingChangedIds` where desired state/version differs from ACK-active state. Before sending ACK, atomically set `effectiveEnabledIds = previousActiveEnabledIds - pendingChangedIds`, so every changed source is fail-closed while unchanged sources continue realtime. Stage the complete desired enabled set, send `policy_ack`, wait for HTTP success, and only then atomically replace the effective set with the staged set. ACK/config failure retains the fail-closed effective set (unchanged previously-active sources only) and backend continues exposing `Đang áp dụng`; never reactivate a pending changed source or partially apply the staged set.

- [ ] **Step 4: Implement Source Sync triggers**

Call full `syncSources()` after login/session restore, listener `connected`, friend/group change events, every 60 minutes, and when `source_sync_request_version` advances. After all discovery events succeed, call `ackSourceSync(accountId, requestedVersion)` and advance the connector's local acknowledged version only after HTTP success. Unknown-message targeted resolution belongs to Task 4, not this full scan.

- [ ] **Step 5: Run connector tests and syntax check**

```bash
npm --prefix zalo_connector test
npm --prefix zalo_connector run check
```

Expected: PASS; no Zalo source scan occurs on the 15-second config timer.

- [ ] **Step 6: Review and commit Task 3**

Review gate: Sol writer, fresh-context Sol reviewer because listener lifecycle and ACK ordering are loss-sensitive.

```bash
git add zalo_connector/src/core.mjs zalo_connector/src/connector.mjs zalo_connector/test/core.test.mjs zalo_connector/test/connector.test.mjs
git commit -m "feat(zalo): synchronize sources and acknowledge policy"
```

### Task 4: Ingest realtime text, dynamic sources, and verified My Documents events

**Files:**
- Modify: `services/zalo_inbox.py:284-394`
- Modify: `zalo_connector/src/core.mjs:59-111`
- Modify: `zalo_connector/src/connector.mjs:38-344`
- Test: `tests/test_zalo_inbox.py`
- Test: `tests/test_zalo_inbox_api.py`
- Test: `zalo_connector/test/core.test.mjs`
- Test: `zalo_connector/test/connector.test.mjs`

**Interfaces:**
- Produces internal download descriptor `{message metadata, raw_text, attachments:[{attachment_index,mime_type,download_url,original_filename}]}` and, only after downloads finish, published webhook envelope `{schema_version:1,event_type:"message",connector_account_id,conversation_id,conversation_type,source_type,source_display_name,msg_id,sender_id,sent_at,raw_text:null|string,attachments:[{attachment_index,mime_type,media_object_key,size_bytes}]}`; component keys follow R-024.
- Produces a durable `message-assembly` record keyed by `(account_id, conversation_id, msg_id)` that references per-attachment download-queue records. The assembly is published once all supported downloads reach success/failure terminal state; crash/restart resumes it without overwriting sibling attachments.
- Produces `resolveUnknownSource(api, message, send2meId) -> {status:"resolved",source}|{status:"confirmed_stranger",source}|{status:"retryable_failure",error_code}`. Network errors, malformed/empty responses, and upstream failures are never reclassified as strangers.
- Produces `ingest_message_envelope(db, payload, storage_root) -> {text_id, media_ids, ignored}` inside `services/zalo_inbox.py`.
- Webhook ACK shape is `{ack:true, components:{text:"imported|duplicate|ignored|absent", media:[{attachment_index,status:"imported|duplicate|ignored"}]}}`; Task 6 uses these statuses for counters.
- `createZaloClient()` enables self listening, while message filtering accepts self events only when `threadId == send2me_id`.
- Consumes Task 2 ACKed source policy; pending/disabled/stranger sources remain fail-closed for content.

- [ ] **Step 1: Add failing message-component and source-resolution tests**

Backend tests:

```python
def test_message_with_text_and_two_attachments_is_component_idempotent(db, tmp_path):
    first = ingest_webhook_event(db, envelope, storage_root=tmp_path)
    replay = ingest_webhook_event(db, envelope, storage_root=tmp_path)
    assert first == replay
    assert db.query(ZaloMessageText).count() == 1
    assert db.query(ZaloMedia).count() == 2
```

Cover payload conflict per component, crash between two attachment downloads, sibling attachment keys not overwriting each other, `last_activity_at` updates for every received message, pending/disabled source content ignored, confirmed stranger metadata-only, unknown lookup timeout/error/inconclusive retained in a bounded retry queue, and text quota pressure not blocking media. Add sentinel-based backend and connector log-capture tests for success, validation failure, download failure, and lookup failure; assert logs omit raw text, sender/conversation IDs, source display name, original filename, remote URL, object key, and upstream error message while retaining only opaque IDs/status/sanitized error codes. This log rule does not remove display names from the public source UI.

Connector tests cover plain text, mixed text+media, multiple attachments, unsupported media, friend/group lookup, confirmed stranger (`getUserInfo().changed_profiles[id].isFr === 0`), timeout/error/inconclusive lookup retry, outgoing self-message rejection, and exact `send2me_id` acceptance.

- [ ] **Step 2: Run focused backend and connector tests; confirm RED**

```bash
venv/Scripts/python.exe -m pytest tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py -k "message or text or activity or stranger or my_documents" -q
npm --prefix zalo_connector test
```

Expected: FAIL because only single media events are supported today.

- [ ] **Step 3: Normalize message components without logging content**

Replace `attachmentEvents()` with a pure normalizer returning the internal descriptor. Keep remote URLs/original filenames only in per-attachment durable download records. Build one durable assembly after downloads, strip those fields, insert `media_object_key`/`size_bytes`, then enqueue one published envelope under the message key. Never enqueue separate attachments under the same message-level outbox ID.

- [ ] **Step 4: Implement dynamic source resolution and My Documents gate**

Use `getUserInfo()` for unknown user threads and `getGroupInfo()` for unknown group threads. Only a valid response that explicitly proves non-friend creates `stranger` metadata and discards content. A timeout, network/upstream error, missing profile, or malformed/inconclusive response writes the original event to the existing durable queue and retries at most three times with bounded backoff; after the third failure, report a sanitized technical failure and retain no content. Obtain `send2me_id` from `api.getContext().loginInfo.send2me_id`; never classify all `message.isSelf` as My Documents.

- [ ] **Step 5: Implement transactional backend component ingestion**

Validate the whole envelope first. Persist each eligible component idempotently and commit once; a conflicting component must reject without overwriting prior data. Run text-retention cleanup independently from media quota. Do not expose `raw_text`, sender ID, conversation ID, digest, object key, or remote URL through `/api/state`.

- [ ] **Step 6: Run focused tests and syntax checks**

```bash
venv/Scripts/python.exe -m pytest tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py -k "message or text or activity or stranger or my_documents" -q
npm --prefix zalo_connector test
npm --prefix zalo_connector run check
```

Expected: PASS.

- [ ] **Step 7: Review and commit Task 4**

Review gate: Sol writer, fresh-context Sol reviewer. My Documents remains marked `verification_required` in public state until Task 9 controlled-account evidence succeeds and the user confirms it; do not claim production readiness from unit tests or UI rendering.

```bash
git add services/zalo_inbox.py tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py zalo_connector/src/core.mjs zalo_connector/src/connector.mjs zalo_connector/test/core.test.mjs zalo_connector/test/connector.test.mjs
git commit -m "feat(zalo): ingest realtime text and dynamic sources"
```

### Task 5: Add backend-owned manual Data Sync lifecycle

**Files:**
- Modify: `services/zalo_inbox.py` only in new Data Sync helpers above the batch-processing functions.
- Modify: `routers/zalo_inbox.py:242-499`
- Test: `tests/test_zalo_inbox.py`
- Test: `tests/test_zalo_inbox_api.py`

**Interfaces:**
- Produces `start_data_sync(db, account_id, now=None) -> ZaloDataSyncRun`.
- Produces `apply_data_sync_report(db, payload) -> ZaloDataSyncRun`.
- HTTP: `POST /api/connectors/{account_id}/data-sync` returns `{run_id, status}`.
- Dedicated connector-only signed HTTP endpoint `GET /api/connectors/{account_id}/commands/next` uses the existing timestamp + HMAC-of-empty-body contract and returns `204` or one command. Connector polls this endpoint every 1 second independently from the 15-second policy/config poll; browser never calls it.

```json
{
  "command_type": "data_sync",
  "run_id": "opaque-uuid",
  "cutoff_at": "2026-08-07T10:00:00Z",
  "deadline_at": "2026-08-07T10:05:00Z",
  "source_ids": ["thread-a", "group-b"]
}
```

- Signed webhook accepts `data_sync_progress`, `data_sync_complete`, and `data_sync_failed` with `{run_id,counters:{received,duplicates,imported_text,imported_media,media_download_failures}}`. All five values start at zero, are non-negative integers, never decrease, and terminal replay must match the persisted terminal counters. Failure adds a sanitized `error_code`, never raw upstream text.
- `/api/state` exposes only the latest run's public status, cutoff, counters, sanitized error, and timestamps.

- [ ] **Step 1: Add failing lifecycle/API tests**

Cover consent/connected/policy-ACK gates, no enabled source empty state, two concurrent start transactions where exactly one succeeds and the other receives conflict from the partial unique index, ACKed-enabled snapshot, `My Documents` exclusion, fixed cutoff/deadline, command endpoint authentication/account binding, stale/wrong-account report rejection, exact counter keys and monotonic non-negative integers, timeout-to-error, partial ACK preservation, safe rerun, and toggle-after-start not changing `source_ids_json`.

```python
def test_data_sync_snapshots_only_acked_enabled_sources(db):
    run = start_data_sync(db, account.id, now=cutoff)
    assert run.cutoff_at == cutoff
    assert run.source_ids_json == [acked_friend.conversation_id]
    assert run.status == "running"
```

- [ ] **Step 2: Run Data Sync backend tests and confirm RED**

Run: `venv/Scripts/python.exe -m pytest tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py -k "data_sync" -q`

Expected: FAIL because the lifecycle and endpoint do not exist.

- [ ] **Step 3: Implement the minimal state machine**

Allowed statuses are `running`, `completed_best_effort`, and `error`. `start_data_sync()` queries only sources where desired and ACKed policy are both enabled/current, excludes `my_documents`, freezes sorted conversation IDs, cutoff, zeroed counters, and `deadline_at = now + ZALO_DATA_SYNC_TIMEOUT_SECONDS`. Insert and commit under the partial unique index; translate its concurrent-insert integrity error to `409`. Reject if any policy is pending. Do not add cancel, resume, queue, or run history management UI.

- [ ] **Step 4: Publish the active command through the dedicated signed endpoint**

Return the command only while the run is active and before `deadline_at`; otherwise atomically persist `error` before returning `204`. This endpoint and its one-second connector poll are independent from policy/config propagation. A connector restart may receive and safely re-run the same `run_id`; backend component idempotency prevents duplicates.

- [ ] **Step 5: Accept progress/terminal reports idempotently**

A replay of the same terminal report returns the existing run. A report for a different account/run or a counter regression is rejected. Completion never clears `gap_started_at` or claims completeness.

- [ ] **Step 6: Run focused tests**

Run: `venv/Scripts/python.exe -m pytest tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py -k "data_sync" -q`

Expected: PASS.

- [ ] **Step 7: Review and commit Task 5**

Review gate: Sol writer, fresh-context Sol reviewer because account binding, frozen policy, and idempotency are data-loss boundaries.

```bash
git add services/zalo_inbox.py routers/zalo_inbox.py tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py
git commit -m "feat(zalo): add manual data sync lifecycle"
```

### Task 6: Execute best-effort history through the realtime listener

**Files:**
- Modify: `zalo_connector/src/core.mjs:10-57`
- Modify: `zalo_connector/src/connector.mjs:78-344`
- Test: `zalo_connector/test/core.test.mjs`
- Test: `zalo_connector/test/connector.test.mjs`

**Interfaces:**
- Extends `WebhookClient` with signed `getNextCommand(accountId)` calling the Task 5 connector-only endpoint; start a dedicated one-second command timer separate from the 15-second config timer.
- Produces `runDataSync({api, command, accountId, sourceNames, store, outbox, downloadQueue, client, now})`; `command.deadline_at` is the authoritative timer deadline.
- Calls exactly `api.listener.requestOldMessages(ThreadType.User)` and `api.listener.requestOldMessages(ThreadType.Group)` once per run attempt.
- Correlates the two `old_messages(messages, type)` callbacks to the sole active `run_id`; same-type overlap is impossible because only one run is active.
- Emits signed progress and exactly one terminal event for each run attempt.

- [ ] **Step 1: Add failing history-run tests**

Cover exact request cardinality, duplicate delivery of the same `run_id` while active, User/Group callback correlation, local `sent_at >= cutoff_at - 7 days && sent_at <= cutoff_at`, source snapshot filtering, `My Documents` exclusion, supported text/media only, same component idempotency keys as realtime, realtime priority, expired URL failure count, deadline timeout, listener disconnect, stale terminal report after backend timeout, rerun safety, and no history request when the command endpoint returns `204`.

```javascript
test('manual Data Sync makes exactly one User and one Group request', async () => {
  await runDataSync(fixture);
  assert.deepEqual(requests, [ThreadType.User, ThreadType.Group]);
});
```

- [ ] **Step 2: Run connector tests and confirm RED**

Run: `npm --prefix zalo_connector test`

Expected: FAIL because Data Sync orchestration is missing.

- [ ] **Step 3: Add signed client report helpers**

Use `WebhookClient.sendEvent()` for progress/terminal reports and the exact five-counter schema from Task 5. Use existing HMAC credentials for `getNextCommand()`. Do not add another secret, broker, browser call, or config-command field.

- [ ] **Step 4: Implement a single history-run controller**

Reject a command whose deadline is expired. Register one `old_messages` handler before issuing requests and bind it to the sole active `run_id`; duplicate delivery of that same active run is ignored. Start a timer for `deadline_at`. Serialize history work behind realtime work in small bounded chunks, but allow newly received realtime events to enter ahead of the next history chunk. Remove handlers/timers and clear active run state on every terminal path. A stale terminal response from backend is treated as acknowledged cleanup, not retried forever.

- [ ] **Step 5: Normalize old messages through the Task 4 envelope path**

Reuse the same source classifier, local filter, component keys, durable download queue, and outbox. Count:

- `received`: source-snapshot + seven-day eligible messages;
- `duplicates`: sum of `duplicate` component statuses in the Task 4 webhook ACK;
- `imported_text`: newly ACKed text components;
- `imported_media`: newly ACKed media components;
- `media_download_failures`: eligible attachment downloads that fail.

Never create placeholders for failed downloads and never include My Documents history before the approved spike.

- [ ] **Step 6: Run connector tests and checks**

```bash
npm --prefix zalo_connector test
npm --prefix zalo_connector run check
```

Expected: PASS; normal startup/reconnect does not call `requestOldMessages`.

- [ ] **Step 7: Review and commit Task 6**

Review gate: Sol writer, fresh-context Sol reviewer. Inspect listener handler cleanup and durable boundaries explicitly.

```bash
git add zalo_connector/src/core.mjs zalo_connector/src/connector.mjs zalo_connector/test/core.test.mjs zalo_connector/test/connector.test.mjs
git commit -m "feat(zalo): run manual best-effort history sync"
```

### Task 7: Render consent, source policy, refresh, gaps, and Data Sync progress

**Files:**
- Modify: `frontend/templates/zalo_inbox.html:6-153`
- Modify: `frontend/static/js/zalo_inbox.js:1-366`
- Test: `tests/zalo_inbox_ui_static.test.mjs`
- Test: `tests/test_zalo_inbox_api.py`

**Interfaces:**
- Consumes only public `/api/state` fields from Tasks 2 and 5.
- Uses `POST /api/connectors/{account_id}/consent`, `POST /api/connectors/{account_id}/sources/refresh`, `PATCH /api/sources/{source_id}`, and `POST /api/connectors/{account_id}/data-sync`.
- Does not receive or render raw chat text, sender IDs, conversation IDs, object keys, or history payloads.

- [ ] **Step 1: Add failing UI contract tests**

Add static and API assertions for:

```javascript
test('data sync is disabled until consent, connection, and policy ACK are ready', () => {
  assert.match(source, /consent_required/);
  assert.match(source, /policy_pending/);
  assert.match(source, /data-sync/);
});
```

Cover consent/re-consent copy, `Đang áp dụng`, refresh-source progress/error, friends/groups/My Documents section ordered by activity then alphabet, separate stranger section default-off, search by display name, Data Sync three states and counters `received`, `duplicates`, `imported_text`, `imported_media`, `media_download_failures`, best-effort warning, gap timestamp that does not auto-clear, and disabled reasons.

- [ ] **Step 2: Run UI/API tests and confirm RED**

```bash
node --test tests/zalo_inbox_ui_static.test.mjs
venv/Scripts/python.exe -m pytest tests/test_zalo_inbox_api.py -k "state or consent or source or data_sync" -q
```

Expected: FAIL because the markup/rendering/actions are absent.

- [ ] **Step 3: Add minimal source-policy UI**

Keep one settings modal. Add a plain consent panel, search input, `Làm mới nguồn`, and two source sections. A pending toggle is disabled and labeled `Đang áp dụng`; do not optimistically render it as ready. Avoid tags, filters, pagination, or a source-management screen.

- [ ] **Step 4: Add minimal Data Sync UI**

Add one `Đồng bộ dữ liệu` button and one status block. Render `Đang đồng bộ`, `Hoàn tất best-effort`, or `Lỗi`, the exact five Task 5 counter keys, cutoff, sanitized error, and the permanent best-effort/gap warning. Poll through the existing two-second `refreshState()` path; do not add browser WebSocket/SSE.

- [ ] **Step 5: Preserve existing selection/batch behavior**

Source sorting may change only the settings list. Media arriving during batch selection remains append-only and must not reorder cards or clear `selectedMedia`.

- [ ] **Step 6: Run UI and API tests**

```bash
node --test tests/zalo_inbox_ui_static.test.mjs
venv/Scripts/python.exe -m pytest tests/test_zalo_inbox_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Browser QA the local UI with isolated data**

Use an isolated temporary SQLite DB/session override or test app; do not use the user's live Zalo session. Verify consent, ordered sections, pending toggles, refresh, Data Sync progress/error, gap warning, focus refresh, and keyboard-accessible labels/buttons.

- [ ] **Step 8: Review and commit Task 7**

Review gate: Terra writer, Sol reviewer. No visual redesign or OCR UI changes.

```bash
git add frontend/templates/zalo_inbox.html frontend/static/js/zalo_inbox.js tests/zalo_inbox_ui_static.test.mjs tests/test_zalo_inbox_api.py
git commit -m "feat(zalo): add source and history sync controls"
```

### Task 8: Repair Zalo-only baseline fixtures and run integration gates

**Files:**
- Modify: `tests/test_zalo_inbox.py` only for the two expired fixed-time fixtures and new integration cases.
- Modify: `tests/test_zalo_inbox_api.py` for end-to-end source/message/sync coverage.
- Modify: `tests/zalo_inbox_ui_static.test.mjs` if aggregate UI assertions are missing.
- Modify: `zalo_connector/test/*.test.mjs` if aggregate connector assertions are missing.
- Modify: `verify.ps1` only if newly created Zalo files are not covered by `Test-ZaloInboxRelevantChange`.

**Interfaces:**
- Exercises the exact contracts from Tasks 1–7; introduces no production interface.
- Preserves the three dirty OCR files and reports their verifier effect separately.

- [ ] **Step 1: Fix only the stale Zalo test clocks**

Replace hard-coded expired `created_at`/`expires_at` values in `test_end_to_end_outputs_keep_frozen_order_and_provenance` and `test_retry_export_reuses_confirmed_snapshot` with a local `now = datetime.now(UTC)` and `expires_at = now + timedelta(hours=72)`. Do not change production expiry behavior.

- [ ] **Step 2: Add aggregate integration tests**

Cover:

1. onboard → metadata Source Sync → consent → policy pending → policy ACK;
2. unknown friend/group first event retained, stranger metadata-only;
3. mixed text/media envelope duplicate replay;
4. toggle pending fail-closed;
5. manual Data Sync snapshots ACKed IDs/cutoff, reports counters, preserves gap warning, and safely reruns;
6. state serialization contains no secrets/raw text/paths/remote URLs.
7. captured backend/connector logs on success and Data Sync/download/validation failures contain none of the sentinel PII values or raw upstream errors.

- [ ] **Step 3: Run focused Zalo gates**

```bash
venv/Scripts/python.exe -m pytest tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py -q
node --test tests/zalo_inbox_ui_static.test.mjs
npm --prefix zalo_connector test
npm --prefix zalo_connector run check
```

Expected: all focused Zalo checks PASS. Report the Python count, UI count, and connector count separately.

- [ ] **Step 4: Run repository verification without hiding unrelated failures**

Run from the normal Windows shell entrypoint:

```text
verify.bat
```

Expected: Zalo gates pass. If `tests/test_ocr_ai.py` fails because of the pre-existing dirty OCR worktree, report it as an unrelated full-verifier failure; do not edit/stage OCR files under this goal.

- [ ] **Step 5: Verify scope and secrets**

```bash
git diff --check
git status --short
git diff --name-only 954b4d7..HEAD
```

Confirm no `node_modules`, runtime session, QR image, database, raw text fixture, credential, or OCR file entered a goal commit.

- [ ] **Step 6: Final independent review and commit**

Fresh-context Sol reviewer checks spec coverage, component idempotency, migration safety, listener cleanup, API redaction, UI disabled states, and focused/full verification distinction.

```bash
git add tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py tests/zalo_inbox_ui_static.test.mjs zalo_connector/test
# Add verify.ps1 only if its Zalo file allowlist changed.
git commit -m "test(zalo): cover source realtime and history sync"
```

### Task 9: Controlled-account live acceptance

**Files:**
- No production file changes are expected.
- Save no QR, session, raw text, media, database, or credential artifact to Git.

**Interfaces:**
- Uses the normal local launcher and public module UI.
- Human boundary: user performs QR scan/account approval; agent never enters credentials.

- [ ] **Step 1: Verify runtime prerequisites without exposing secrets**

Check required environment variables by presence only, identify the actual process listening on the local port, and confirm no duplicate connector for the same account.

- [ ] **Step 2: Verify consent and source inventory**

After user login, verify friends/groups default on, strangers default off, My Documents listed separately, activity ordering, manual refresh, 60-minute cadence configuration, and policy ACK before readiness.

- [ ] **Step 3: Verify realtime cases**

With user-controlled test conversations, verify friend/group text, one supported image/PDF, stranger metadata-only, new friend/group discovery, listener disconnect/reconnect gap warning, and outbox retry. Do not use private conversations not selected for the test.

- [ ] **Step 4: Verify My Documents realtime gate**

Send one controlled text and one supported attachment to My Documents. Confirm only events with `threadId == send2me_id` are accepted and ordinary outgoing self messages are rejected. If this does not pass, keep My Documents marked unverified; do not broaden the self-message rule.

- [ ] **Step 5: Verify manual seven-day Data Sync**

Press `Đồng bộ dữ liệu`; prove that the request begins only then, reports best-effort counters, excludes strangers/My Documents, does not duplicate realtime items, keeps the gap warning, and does not block a newly arriving realtime event.

- [ ] **Step 6: Close the goal only after user confirmation**

Report machine evidence, focused tests, full-verifier status, unresolved upstream limitations, and the shared OCR gate. The goal remains open until the user confirms live behavior.

---

## Execution Coordination

- Coordinator: Hermes `gpt-5.6-sol` on `custom:cockpit` owns contracts, worktree integration, and final acceptance.
- Task 1 writer: Terra; reviewer: Sol.
- Task 2 writer: Terra; reviewer: Sol.
- Tasks 3, 4, 5, and 6 writers: Sol; each uses a separate fresh-context Sol reviewer.
- Task 7 writer: Terra; reviewer: Sol.
- Task 8 writer: Terra for mechanical fixtures/tests, Sol for aggregate integration/review.
- Luna may run mechanical stale-rule, secret, path, and scope scans only; Luna does not own schema, lifecycle, privacy, or listener logic.
- Parallel execution is allowed only for tasks with disjoint file ownership. Because Tasks 2/4/5 share backend files and Tasks 3/4/6 share connector files, execute those chains sequentially. Task 7 may begin after Task 5 response shapes are frozen and can run in parallel with Task 6 in a separate worktree.
- Every writer commits only its allowlisted files. Coordinator integrates commits sequentially and reruns the task's focused gate after each integration.

## Plan Self-Review Checklist

- [x] Every approved R-032–R-039 and FR-040–FR-048 maps to at least one task and executable test.
- [x] No task modifies the three shared OCR dirty files or silently implements the OCR/output slice.
- [x] No `TBD`, `TODO`, “similar to,” missing signature, or undefined status remains.
- [x] Model names, HTTP routes, event types, status strings, and counter names are identical across producer/consumer tasks.
- [x] Baseline fixture failures and full-verifier OCR failures are reported honestly and separately.
- [x] Live My Documents and best-effort history remain acceptance gates, not unit-test claims.

## Spec Coverage Map

| Approved contract | Implementation tasks | Primary evidence |
|---|---|---|
| R-032 / FR-001 source consent/default/explicit choice | 1, 2, 7 | migration, policy service/API, consent UI tests |
| R-033 / FR-043 Source Sync triggers and ordering | 2, 3, 7 | backend order tests, connector timers/events, UI sections |
| R-034 / FR-002 realtime and unknown sources | 4 | backend component tests + connector message tests |
| R-035 / FR-044 My Documents | 3, 4, 9 | unit classification plus controlled-account verification |
| R-036 / FR-045–047 manual Data Sync | 5, 6, 7, 9 | run state tests, listener history tests, UI and live evidence |
| R-037 / FR-040/042 text research/quota | 1, 4 | text uniqueness, redaction, independent-pressure tests |
| R-038 / FR-041 listener gap | 4, 5, 7, 9 | state/gap persistence and controlled reconnect |
| R-039 / FR-048 polling boundary | 2, 3 | policy ACK and 60-minute reconciliation tests |
