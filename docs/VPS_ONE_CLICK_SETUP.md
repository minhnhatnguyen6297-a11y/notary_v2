# VPS One-Click Setup

This repo now includes a one-command VPS installer so collaborators can deploy quickly after clone.

## 1) Clone and run one command

```bash
git clone <your-repo-url>
cd notary_v2
bash install_vps.sh
```

What this command does:

1. Installs system packages (Ubuntu/Debian).
2. Creates `venv` and installs Python dependencies.
3. Installs Local OCR Python dependencies (`cv2`, `onnxruntime`, `rapidocr`).
4. Creates `.env` from `.env.example` if missing.
5. Downloads a default local OCR model (`models/rapidocr/*`) if missing.
6. Creates and starts 2 `systemd` services:
   - `notary-web.service`
   - `notary-worker.service`

## 2) Configure API key

Update `OPENAI_API_KEY` in `.env`:

```bash
nano .env
```

Then restart:

```bash
bash deploy/vps/manage_services.sh restart
```

## 3) Service operations

```bash
bash deploy/vps/manage_services.sh status
bash deploy/vps/manage_services.sh logs
bash deploy/vps/manage_services.sh restart
```

App log files:

- `logs/web.log` (FastAPI + OCR API timing)
- `logs/worker.log` (Celery worker + OCR batch timing)

## 4) Optional installer flags

```bash
bash install_vps.sh --app-user ubuntu --host 0.0.0.0 --port 8000
```

Common flags:

- `--skip-system-packages`
- `--without-systemd`
- `--without-ocr-model`

## 5) Expose service publicly

Open firewall for your chosen port (default `8000`), then access:

`http://<vps-public-ip>:8000`
