# One-Click Launch (Windows)

For internal team usage, this repo supports true one-click launch from Windows:

1. auto start/restart app on VPS
2. wait until app is ready
3. auto open browser to the app URL

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
     - `VPS_APP_SCHEME` (default `http`)
     - `VPS_APP_PORT` (default `8000`)
     - `VPS_APP_PATH` (default `/`)
     - `VPS_REPO_DIR` (default `~/notary_v2`)

`ssh_credentials.env` is ignored by git by default.

## 2) One click launch

Double-click:

- `connect_vps.bat`

Or run:

```bat
connect_vps.bat
```

On first run, script auto-downloads `plink.exe` to `deploy/vps/bin/`.
No manual SSH typing is needed.

## 3) Notes

- This flow uses password auth for convenience.
- When moving to stricter security, switch to SSH keys and disable password login.

## 4) If you want clone-and-click with zero setup

If your internal process accepts storing password in repo temporarily:

1. Remove this line from `.gitignore`:
   - `deploy/vps/ssh_credentials.env`
2. Commit `deploy/vps/ssh_credentials.env`.

Then new machines can clone and directly double-click `connect_vps.bat`.
