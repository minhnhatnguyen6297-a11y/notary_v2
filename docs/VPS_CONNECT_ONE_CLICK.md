# One-Click Launch (Windows)

For internal team usage, this repo supports a standard Windows VPS workflow:

1. launch app on VPS
2. open SSH shell when needed
3. stream logs when needed

## 1) Setup once

1. Copy:
  - `deploy/vps/ssh_credentials.example`
   - to `deploy/vps/ssh_credentials.env`
2. Fill real values in `deploy/vps/ssh_credentials.env`:
   - `VPS_HOST`
   - `VPS_PORT`
   - `VPS_USER`
   - `VPS_PASSWORD`
   - `VPS_HOSTKEY` (required for no-prompt mode)
   - optional app fields:
     - `VPS_AUTO_OPEN_BROWSER` (default `1`)
     - `VPS_APP_SCHEME` (default `http`)
     - `VPS_APP_PORT` (default `8000`)
     - `VPS_APP_PATH` (default `/`)
     - `VPS_REPO_DIR` (default `~/notary_v2`)

`ssh_credentials.env` is ignored by git by default.

## 2) Standard entry points

Double-click:

- `launch_vps_app.bat`
- `connect_vps.bat`
- `view_vps_logs.bat` (live logs)

Or run:

```bat
launch_vps_app.bat
```

Behavior:

- `launch_vps_app.bat`: start/restart app on VPS, wait until ready, open browser
- `connect_vps.bat`: open interactive SSH shell and auto-open the configured app URL first
- `view_vps_logs.bat`: stream `logs/web.log` and `logs/worker.log`

On first run, scripts auto-download `plink.exe` to `deploy/vps/bin/`.
No manual SSH typing is needed after config is filled.

By default, interactive SSH uses a clean shell mode (`TERM=dumb`) so Windows console does not show garbled sequences like `[?2004h`.

If you need the VPS default terminal behavior instead, run:

```bat
connect_vps.bat --raw
```

If you want SSH only and do not want the browser to open, set this in `deploy/vps/ssh_credentials.env`:

```env
VPS_AUTO_OPEN_BROWSER=0
```

## 2.1) View logs live

Double-click `view_vps_logs.bat` to stream:

- `logs/web.log`
- `logs/worker.log`

## 3) Notes

- This flow uses password auth for convenience.
- When moving to stricter security, switch to SSH keys and disable password login.

## 4) If you want clone-and-click with zero setup

If your internal process accepts storing password in repo temporarily:

1. Remove this line from `.gitignore`:
   - `deploy/vps/ssh_credentials.env`
2. Commit `deploy/vps/ssh_credentials.env`.

Then new machines can clone and directly use:

- `launch_vps_app.bat`
- `connect_vps.bat`
- `view_vps_logs.bat`

## 5) Recommended policy

- Treat VPS repo `~/notary_v2` as the primary running source of truth.
- Read `docs/VPS_WORKFLOW.md` before starting work on a new machine or in a new chat.
