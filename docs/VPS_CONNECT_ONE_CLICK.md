# One-Click SSH (Windows)

For internal team usage, this repo supports one-click VPS SSH access from Windows.

## 1) Setup once

1. Copy:
   - `deploy/vps/ssh_credentials.example`
   - to `deploy/vps/ssh_credentials.env`
2. Fill real values in `deploy/vps/ssh_credentials.env`:
   - `VPS_HOST`
   - `VPS_PORT`
   - `VPS_USER`
   - `VPS_PASSWORD`

`ssh_credentials.env` is ignored by git by default.

## 2) One click connect

Double-click:

- `connect_vps.bat`

Or run:

```bat
connect_vps.bat
```

On first run, script auto-downloads `plink.exe` to `deploy/vps/bin/`.

## 3) Notes

- This flow uses password auth for convenience.
- When moving to stricter security, switch to SSH keys and disable password login.

## 4) If you want clone-and-click with zero setup

If your internal process accepts storing password in repo temporarily:

1. Remove this line from `.gitignore`:
   - `deploy/vps/ssh_credentials.env`
2. Commit `deploy/vps/ssh_credentials.env`.

Then new machines can clone and directly double-click `connect_vps.bat`.
