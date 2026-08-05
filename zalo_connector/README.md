# Zalo receive connector

Receive-only `zca-js` process for the local/trusted-network Zalo Document Inbox.
It never sends Zalo messages. Media is downloaded to the same storage root used by FastAPI, then a signed event is persisted in the local outbox before publication.

## Required configuration

Set these in the process environment (secrets are intentionally not stored in this repository):

- `ZALO_INBOX_BACKEND_URL` — for example `http://127.0.0.1:8000`
- `ZALO_INBOX_BOOTSTRAP_SECRET` — must match the FastAPI process
- `ZALO_INBOX_WEBHOOK_SECRET` — must match the FastAPI process
- `ZALO_INBOX_STORAGE_ROOT` — the exact same shared path used by FastAPI
- `ZALO_CONNECTOR_QUOTA_BYTES` — deployment hard quota; no built-in value
- `ZALO_CONNECTOR_RETENTION_HOURS` — deployment retention; no built-in value
- `ZALO_CONNECTOR_STATE_ROOT` — optional session/outbox location; defaults to `runtime/zalo_connector`

FastAPI batch preflight also requires `ZALO_INBOX_MAX_FILE_BYTES`, `ZALO_INBOX_MAX_ITEMS`, `ZALO_INBOX_MAX_TOTAL_BYTES`, and `ZALO_INBOX_MAX_RENDERED_PIXELS`.

## Run and verify

```sh
npm ci
npm test
npm run check
npm start
```

Normally the user starts this process by choosing `Nguồn nhận` → `Đăng nhập Zalo` inside `/zalo-inbox/`; `npm start` remains the operator/debug path. The first run publishes a browser-safe QR login state and writes the QR image under `ZALO_CONNECTOR_STATE_ROOT`. The backend binds the first successful QR account and rejects a different account until the separate reset/onboard workflow exists.

The in-module launcher supports one local FastAPI worker. For `uvicorn --workers > 1` or a deployed service, run the connector once under an external service manager instead of using the UI launcher.

A real Zalo account is still required to complete the scan/confirmation and smoke-test restored session, source discovery, image/PDF payloads, and CDN downloads; offline tests mock those external boundaries.

Do not expose this module publicly until the platform has authentication/authorization. Opaque account/media/batch IDs are not authorization.
