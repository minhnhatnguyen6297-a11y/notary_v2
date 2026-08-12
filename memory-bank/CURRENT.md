# Current handoff

Updated: 2026-08-11
Source machine: MAY3
Tracking branch: `codex/zalo-document-inbox-v2`
Tracking worktree: `D:/notary_v2-worktrees/task-8-integration`
Tracking HEAD before this handoff commit: `5acf510`
Handoff checkpoint: resolve with
`git log -1 --format=%H -- memory-bank/CURRENT.md`.

Always rerun Git/process checks. Do not trust this file as current runtime state.

## Goal

Continue unresolved Zalo Document Inbox and shared OCR work without merging the
module into the primary branch until the user explicitly changes that decision.
Preserve the user's OCR edits and the primary worktree's interrupted cherry-pick.

## Completed and consolidated

The complete Tasks 1–8 implementation is on `codex/zalo-document-inbox-v2`.
The branch is local-only and has not been merged into the primary branch or
pushed.

Linear module commits after base `7b982d2`:

1. `6400d0e` source policy
2. `d5c0b8c` acknowledged versions
3. `7d9e159` source display names
4. `1ac18d4` Source Sync
5. `238349c` realtime intake
6. `5bd136b` manual Data Sync backend
7. `a847dd7` history sync connector
8. `6b1ee44` source/Data Sync UI
9. `57b7115` integrated tests
10. `7ea3e74` text quota/retention setup
11. `5acf510` OCR decision and open acceptance issues

Completed live evidence:

- QR login/account approval and one bound connector process.
- Source discovery, consent defaults, exact policy ACK and manual Source Sync ACK.
- Friend JPEG and group text intake with durable queues empty after ACK.
- Reconnect with persisted gap warning.
- Text quota recovery; media remained available while text config was absent.

Verification baseline:

- Connector: `90/90`.
- UI/setup: `18/18`.
- Focused integrated Python: `97 passed`, one shared OCR failure.
- `verify.bat` with project venv: `135 passed`, the same shared OCR failure.
- Shared failure: `routers.zalo_inbox._output_job` references missing
  `ocr_ai.shape_cached_ocr`.

## Current machine state and safety boundaries

### Primary worktree — do not edit blindly

Path: `D:/notary_v2`
Branch: `codex/inheritance-diagram-v2`
HEAD: `7b982d2`

It is in an interrupted cherry-pick of `d4a2ffd`:

- `CHERRY_PICK_HEAD` is present.
- Conflict: `routers/zalo_inbox.py`.
- Conflict: `tests/test_zalo_inbox_api.py`.
- Conflict markers make `routers/zalo_inbox.py:459` invalid Python.
- Therefore `import main`, Uvicorn and `run.bat` fail before binding port 8000.

Other pre-existing user/shared OCR changes are present in:

- `docs/platform/document-intake/spec.md`
- `routers/ocr_ai.py`
- `tests/test_ocr_ai.py`

Cherry-pick-staged UI files are also present. Do not run reset, checkout, clean,
stash, cherry-pick abort/continue, or conflict resolution until the exact staged,
unstaged and unmerged state has been backed up and the user authorizes the chosen
recovery.

### Module worktree

Path: `D:/notary_v2-worktrees/task-8-integration`
Branch: `codex/zalo-document-inbox-v2`

Expected tracked state after this handoff commit: clean.
Ignored live artifacts may remain:

- `notary.db`
- `runtime/`

They contain controlled acceptance state and must never be committed. The live
server/connector were stopped; port 8000 had no listener. The temporary launcher
and `node_modules` junction were removed.

Primary `.env` was updated locally, without printing values, to add positive
`ZALO_INBOX_TEXT_QUOTA_BYTES` and `ZALO_INBOX_TEXT_RETENTION_HOURS`. `.env` is not
tracked.

## Task 1 — Recover the primary worktree safely

Status: blocked on explicit recovery choice.

Goal: remove the invalid interrupted cherry-pick state without losing the user's
shared OCR edits. Do not merge the Zalo module into this branch.

Prerequisite evidence:

```bash
git -C D:/notary_v2 status --porcelain=v2
git -C D:/notary_v2 diff
git -C D:/notary_v2 diff --cached
git -C D:/notary_v2 ls-files -u
git -C D:/notary_v2 show -s --oneline CHERRY_PICK_HEAD
```

Required procedure:

1. Create a timestamped directory outside every Git worktree, for example
   `D:/notary_v2-handoffs/primary-YYYYMMDD-HHMMSS/`. Do not include `.env`,
   databases, logs, runtime/session directories or credentials.
2. From `D:/notary_v2`, save these exact artifacts:

   ```bash
   git diff --binary -- \
     docs/platform/document-intake/spec.md routers/ocr_ai.py tests/test_ocr_ai.py \
     > D:/notary_v2-handoffs/<stamp>/ocr-unstaged.patch
   cp docs/platform/document-intake/spec.md \
     D:/notary_v2-handoffs/<stamp>/document-intake-spec.worktree.md
   cp routers/ocr_ai.py \
     D:/notary_v2-handoffs/<stamp>/ocr_ai.worktree.py
   cp tests/test_ocr_ai.py \
     D:/notary_v2-handoffs/<stamp>/test_ocr_ai.worktree.py
   git diff --cached --binary > D:/notary_v2-handoffs/<stamp>/index-staged.patch
   git status --porcelain=v2 > D:/notary_v2-handoffs/<stamp>/status-v2.txt
   git rev-parse CHERRY_PICK_HEAD > D:/notary_v2-handoffs/<stamp>/CHERRY_PICK_HEAD.txt
   git ls-files -u > D:/notary_v2-handoffs/<stamp>/unmerged-index.txt
   for f in routers/zalo_inbox.py tests/test_zalo_inbox_api.py; do
     for stage in 1 2 3; do
       git show ":${stage}:${f}" > \
         "D:/notary_v2-handoffs/<stamp>/$(basename "$f").stage-${stage}"
     done
   done
   (cd D:/notary_v2-handoffs/<stamp> && sha256sum \
     ocr-unstaged.patch document-intake-spec.worktree.md \
     ocr_ai.worktree.py test_ocr_ai.worktree.py index-staged.patch \
     status-v2.txt CHERRY_PICK_HEAD.txt unmerged-index.txt \
     zalo_inbox.py.stage-1 zalo_inbox.py.stage-2 zalo_inbox.py.stage-3 \
     test_zalo_inbox_api.py.stage-1 test_zalo_inbox_api.py.stage-2 \
     test_zalo_inbox_api.py.stage-3 > SHA256SUMS)
   ```

   On Windows Git Bash, replace `<stamp>` with the chosen literal directory;
   do not rely on a shell variable that was not exported.
3. Prove every expected artifact is non-empty/readable, run
   `(cd D:/notary_v2-handoffs/<stamp> && sha256sum -c SHA256SUMS)`, and require it
   to pass. Confirm `CHERRY_PICK_HEAD.txt` is exactly
   `d4a2ffd4427024805c26d86b8368cbaa3446b9d7`.
4. Prove the OCR patch is re-applicable without touching the primary worktree:
   create a temporary detached worktree at primary HEAD `7b982d2`, run
   `git apply --check D:/notary_v2-handoffs/<stamp>/ocr-unstaged.patch`, then
   remove only that temporary worktree. If apply-check fails, stop and preserve
   the primary state; the backup is not yet recovery-capable.
5. Separate the user's OCR changes from files introduced by the failed Task 7
   cherry-pick.
6. Ask the user to choose abort versus deliberate conflict resolution. The user
   already directed that the Zalo module remain on its own branch, so abort is
   the likely choice, but this handoff does not authorize it.
7. **Do not run cherry-pick abort/continue before steps 1–4 pass.** After the
   authorized recovery action, prove from the exact primary directory:

   ```bash
   cd D:/notary_v2
   D:/notary_v2/venv/Scripts/python.exe -m py_compile \
     D:/notary_v2/main.py D:/notary_v2/routers/zalo_inbox.py
   git status -sb
   ```

8. Before deleting the backup, restore/apply the OCR patch in an isolated
   checkout and compare the three resulting file hashes with the backed-up
   worktree copies or blobs. Keep the backup until the OCR task is committed.

Stop conditions:

- Any uncertainty about whether a line belongs to the user's OCR work.
- Any need to merge/cherry-pick `codex/zalo-document-inbox-v2` into primary.
- Any destructive Git operation without explicit approval.

## Task 2 — Shared OCR Qwen-only implementation

Status: approved product decision; implementation/review pending.
Dependency: Task 1 must first produce a valid isolated OCR worktree/state.

Normative source: `docs/platform/document-intake/spec.md`.
Decision: active Cloud AI OCR is Qwen-only. Remove all server/client QR decode,
QR rescue/fallback, QR-first routing and QR/source priority. Never restore QR
helpers to fix tests or `shape_cached_ocr`.

Required scope discovery:

- `routers/ocr_ai.py`
- `frontend/templates/cases/form.html`
- `frontend/static/ocr_qr_worker.js`
- `routers/zalo_inbox.py` output job
- `tests/test_ocr_ai.py`
- `tests/test_zalo_inbox_api.py`
- every caller of `shape_cached_ocr`
- Graphify shared-impact query before editing

Before deleting `ocr_qr_worker.js`, prove whether it has any non-AI consumer.
This task removes QR only from active Cloud AI OCR. Zalo connector login QR and
parked `routers/ocr_local.py` QR code are separate scopes and must not be changed
here.

Acceptance:

- 100% OCR items use Qwen active path.
- Existing multipart endpoint and top-level response contract remain compatible.
- No active QR decode/fallback/priority symbols or browser QR preprocessing.
- Zalo output job no longer references a missing API; behavior is covered by a
  shared OCR/Zalo regression.
- Independent spec and quality reviews approve.
- Focused OCR + Zalo tests pass; full verifier status is reported separately.

Do not absorb Local OCR restoration into this task.

## Task 3 — Align parked Local OCR runtime and launcher

Status: open implementation task; requires explicit scope approval.
Dependency: Task 2 contract should be settled first.

Diagnosis already proved:

- `run.bat:138` starts only Uvicorn.
- `run.bat:166` explicitly says the Local OCR worker is not auto-started.
- Commit `b5e0518 build(ocr): remove local OCR startup` intentionally removed
  Celery, broker setup and worker startup because Cloud OCR became supported path.
- `requirements.txt` no longer declares Celery.
- Existing venv still has Celery 5.3.6 and Local OCR packages only because it is
  old; this is not fresh-install evidence.
- `main.py` still imports/registers `ocr_local` and warms Local OCR at startup.
- `/api/ocr/local/submit` and `/submit-batch` still call Celery `.delay()` and can
  leave jobs queued forever without a worker.

Goal: make runtime match the parked Local OCR contract. Preferred direction is
removing/disabling Local OCR warmup/router/queued endpoints, not restarting the
worker. Do not add Celery back to `run.bat` unless the user separately reopens
Local OCR product scope.

Fresh-install acceptance:

1. Create an isolated venv from `requirements.txt` only.
2. `import main` succeeds without Celery or Local OCR optional packages.
3. Uvicorn binds and `GET /` returns 200 without Local OCR warmup.
4. Parked local endpoints are absent or return one explicit non-queued response;
   they must not create durable `queued` jobs.
5. Cloud `/api/ocr/analyze` remains functional and requires no worker.
6. Launcher exposes Uvicorn startup failures instead of hiding them in a separate
   window and declaring readiness after a blind timeout.

Minimum executable diagnostic loop, run from a clean dedicated worktree. Replace
`<local-ocr-task>` once with its literal path; do not run this against the primary
worktree or its database:

```bash
cd D:/notary_v2-worktrees/<local-ocr-task>
test -z "$(git status --porcelain --untracked-files=all)"
test ! -e D:/notary-v2-temp/local-ocr-diagnostic
mkdir -p D:/notary-v2-temp/local-ocr-diagnostic
find . -path './.git' -prune -o -type f -print | sort \
  > D:/notary-v2-temp/local-ocr-diagnostic/files-before.txt
git status --porcelain=v2 --untracked-files=all \
  > D:/notary-v2-temp/local-ocr-diagnostic/git-before.txt
test ! -e D:/notary-v2-temp/fresh-venv
python -m venv D:/notary-v2-temp/fresh-venv
D:/notary-v2-temp/fresh-venv/Scripts/python.exe -m pip install -r requirements.txt
D:/notary-v2-temp/fresh-venv/Scripts/python.exe -c \
  "import main; print('main import OK')"
```

Start Uvicorn with the agent process manager, not shell `&`, so termination is
tracked even when an assertion fails:

```text
terminal(
  command="D:/notary-v2-temp/fresh-venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8768",
  workdir="D:/notary_v2-worktrees/<local-ocr-task>",
  background=true
)
```

After readiness, run these literal failure-producing assertions:

```bash
D:/notary-v2-temp/fresh-venv/Scripts/python.exe -c \
  "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8768/',timeout=10); assert r.status==200"
D:/notary-v2-temp/fresh-venv/Scripts/python.exe -c \
  "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8768/openapi.json',timeout=10)); p=d['paths']; assert '/api/ocr/analyze' in p; assert '/api/ocr/local/submit' not in p; assert '/api/ocr/local/submit-batch' not in p; assert not any(x == '/api/ocr/local/status' or x.startswith('/api/ocr/local/status/') for x in p)"
D:/notary-v2-temp/fresh-venv/Scripts/python.exe -c \
  "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8768/api/ocr/config',timeout=10); assert r.status==200"
```

Do not submit a Local OCR fixture: after this task, parked endpoints are required
to be absent, so OpenAPI absence is the red/green contract and cannot enqueue a
job. In a `finally` path, call `process(action='kill', session_id=<server-id>)`,
then assert shutdown:

```bash
D:/notary-v2-temp/fresh-venv/Scripts/python.exe -c \
  "import socket; s=socket.socket(); s.settimeout(1); assert s.connect_ex(('127.0.0.1',8768)) != 0; s.close()"
find . -path './.git' -prune -o -type f -print | sort \
  > D:/notary-v2-temp/local-ocr-diagnostic/files-after.txt
comm -13 \
  D:/notary-v2-temp/local-ocr-diagnostic/files-before.txt \
  D:/notary-v2-temp/local-ocr-diagnostic/files-after.txt \
  > D:/notary-v2-temp/local-ocr-diagnostic/new-files.txt
git status --porcelain=v2 --untracked-files=all \
  > D:/notary-v2-temp/local-ocr-diagnostic/git-after.txt
test ! -s D:/notary-v2-temp/local-ocr-diagnostic/git-before.txt
test ! -s D:/notary-v2-temp/local-ocr-diagnostic/git-after.txt
```

Review `new-files.txt` explicitly. If non-empty, delete only newly created files
inside this fixed runtime allowlist; any other path is a hard stop:

```bash
while IFS= read -r f; do
  test -n "$f" || continue
  case "$f" in
    ./notary.db|./ocr_jobs.db|./logs/*|./tmp/*|./runtime/*) rm -f -- "$f" ;;
    *) echo "UNEXPECTED ARTIFACT: $f" >&2; exit 1 ;;
  esac
done < D:/notary-v2-temp/local-ocr-diagnostic/new-files.txt
find . -path './.git' -prune -o -type f -print | sort \
  > D:/notary-v2-temp/local-ocr-diagnostic/files-cleaned.txt
cmp \
  D:/notary-v2-temp/local-ocr-diagnostic/files-before.txt \
  D:/notary-v2-temp/local-ocr-diagnostic/files-cleaned.txt
test -z "$(git status --porcelain --untracked-files=all)"
```

Remove empty runtime directories only if they were absent before; otherwise
leave them. Then remove the external temp venv/diagnostics and prove cleanup:

```bash
rm -rf D:/notary-v2-temp/fresh-venv \
  D:/notary-v2-temp/local-ocr-diagnostic
test ! -e D:/notary-v2-temp/fresh-venv
test ! -e D:/notary-v2-temp/local-ocr-diagnostic
test -z "$(git status --porcelain --untracked-files=all)"
```

Focused tests must cover `main` import, route registration, Cloud OCR config,
parked endpoint absence and launcher failure reporting. The old project venv,
`worker.log`, and installed Celery 5.3.6 are explicitly invalid evidence.

Do not use historical `worker.log` as current worker evidence.

## Task 4 — Live verify realtime My Documents

Status: open human acceptance.
Normative issue: `docs/platform/zalo-document-inbox/open-issues.md`,
`ZALO-LIVE-001`.

Use a controlled account and normal module UI. User sends one text and one
supported JPG/JPEG/PNG/PDF to My Documents. Verify only events where
`threadId == session send2me_id` become `my_documents`. Also send one ordinary
outgoing self-message in another thread and prove it is rejected.

Stop condition: never broaden the self-message rule to make the test pass.
My Documents history remains out of scope.

## Task 5 — Controlled manual Data Sync

Status: open human acceptance.
Normative issue: `ZALO-LIVE-002`.

Do not use the prior account with 975 enabled sources. Use a dedicated controlled
account or disable every source outside the approved test set and wait for exact
policy ACK.

Verify:

- no history before the user click;
- exactly one User and one Group history request;
- frozen ACKed source snapshot and seven-day cutoff;
- My Documents and strangers excluded;
- exact five counters and best-effort terminal status;
- safe rerun counts duplicates and does not duplicate records;
- gap warning remains;
- a new realtime event is processed before the history backlog completes.

Do not claim completeness; upstream history is best-effort.

## Task 6 — Optional remaining live matrix

Status: open, non-blocking for keeping the module branch.

- Stranger event creates metadata only; no text/media persistence.
- External friend text and one non-private PDF. Existing live evidence is friend
  JPEG plus group text.
- Controlled outbox retry during a temporary backend interruption.
- DOCX is intentionally unsupported and must not produce placeholders.

## Task 7 — Publish and later clean branches/worktrees

Status: pending user decision.

The tracking branch is local-only. First commit this handoff checkpoint and
verify the branch is clean. If the user authorizes publication:

```bash
git -C D:/notary_v2-worktrees/task-8-integration status -sb
git -C D:/notary_v2-worktrees/task-8-integration log -1 --oneline
git -C D:/notary_v2-worktrees/task-8-integration push -u origin \
  codex/zalo-document-inbox-v2
git -C D:/notary_v2 ls-remote --exit-code --heads origin \
  codex/zalo-document-inbox-v2
git -C D:/notary_v2 merge-base --is-ancestor \
  codex/zalo-document-inbox-v2 origin/codex/zalo-document-inbox-v2
git -C D:/notary_v2 worktree list --porcelain
git -C D:/notary_v2 branch --list 'codex/zalo*'
```

Do not merge it into primary/main. Record the remote commit hash and compare it
to local HEAD before considering the branch externally backed up.

There are currently ten linked task worktrees, including separate Task 3 ACK,
display and Source Sync variants. Cleanup requires explicit user approval for
each named worktree and each named branch after fresh inventory. Remove no
worktree/branch merely because its commit is an ancestor. Cleanup is allowed
only after remote containment or another external backup is verified, and only
from outside the worktree being removed.

## Verification commands on the tracking branch

```bash
cd D:/notary_v2-worktrees/task-8-integration
npm --prefix zalo_connector test
npm --prefix zalo_connector run check
node --test tests/zalo_inbox_ui_static.test.mjs
env -u PYTHONPATH D:/notary_v2/venv/Scripts/python.exe -m pytest \
  tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py -q
git diff --check
git status -sb
```

Expected historical result: connector 90/90, UI/setup 18/18, Python 97 passed
plus one shared OCR failure. Rerun; do not repeat old numbers as fresh evidence.

## Normative references

- `AGENTS.md`
- `docs/platform/document-intake/README.md`
- `docs/platform/document-intake/spec.md`
- `docs/platform/zalo-document-inbox/README.md`
- `docs/platform/zalo-document-inbox/spec.md`
- `docs/platform/zalo-document-inbox/open-issues.md`
- `docs/superpowers/plans/2026-08-07-zalo-source-realtime-history.md`

## Next exact action

Commit this reviewed handoff checkpoint on `codex/zalo-document-inbox-v2` first.
Then start Task 1 read-only evidence capture and recovery-backup validation. Do
not edit the primary worktree or run destructive Git commands until the backup
passes its hash/apply/restore checks and the user chooses the recovery method.
If the primary branch is not needed, Tasks 4–6 can continue independently from
`codex/zalo-document-inbox-v2` using isolated live state.
