#!/usr/bin/env bash
set -euo pipefail

APP_DIR=""
APP_USER=""
APP_HOST="0.0.0.0"
APP_PORT="8000"

log() {
  printf '[systemd-setup] %s\n' "$*"
}

die() {
  printf '[systemd-setup][error] %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage:
  bash deploy/vps/install_systemd.sh --app-dir <path> --app-user <user> [--host 0.0.0.0] [--port 8000]
USAGE
}

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
    return
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    die "Can sudo de tao service trong /etc/systemd/system."
  fi
  sudo "$@"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --app-dir)
        [[ $# -ge 2 ]] || die "Thieu gia tri cho --app-dir"
        APP_DIR="$2"
        shift 2
        ;;
      --app-user)
        [[ $# -ge 2 ]] || die "Thieu gia tri cho --app-user"
        APP_USER="$2"
        shift 2
        ;;
      --host)
        [[ $# -ge 2 ]] || die "Thieu gia tri cho --host"
        APP_HOST="$2"
        shift 2
        ;;
      --port)
        [[ $# -ge 2 ]] || die "Thieu gia tri cho --port"
        APP_PORT="$2"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Tuy chon khong hop le: $1"
        ;;
    esac
  done
}

validate() {
  [[ -n "$APP_DIR" ]] || die "Bat buoc co --app-dir"
  [[ -n "$APP_USER" ]] || die "Bat buoc co --app-user"
  [[ -d "$APP_DIR" ]] || die "APP_DIR khong ton tai: $APP_DIR"
  [[ -x "$APP_DIR/venv/bin/python" ]] || die "Khong tim thay Python venv: $APP_DIR/venv/bin/python"
  id "$APP_USER" >/dev/null 2>&1 || die "User khong ton tai: $APP_USER"
  command -v systemctl >/dev/null 2>&1 || die "Khong tim thay systemctl."
}

install_services() {
  local app_group
  app_group="$(id -gn "$APP_USER")"

  log "Ghi file notary-web.service..."
  run_root tee /etc/systemd/system/notary-web.service >/dev/null <<EOF
[Unit]
Description=Notary FastAPI service
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$app_group
WorkingDirectory=$APP_DIR
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
Environment=LANG=C.UTF-8
Environment=LC_ALL=C.UTF-8
EnvironmentFile=-$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python -m uvicorn main:app --host $APP_HOST --port $APP_PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

  log "Ghi file notary-worker.service..."
  run_root tee /etc/systemd/system/notary-worker.service >/dev/null <<EOF
[Unit]
Description=Notary OCR Celery worker
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$app_group
WorkingDirectory=$APP_DIR
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
Environment=LANG=C.UTF-8
Environment=LC_ALL=C.UTF-8
EnvironmentFile=-$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

  log "Reload + enable services..."
  run_root systemctl daemon-reload
  run_root systemctl enable --now notary-worker.service
  run_root systemctl enable --now notary-web.service
}

main() {
  parse_args "$@"
  validate
  install_services
  log "Done. Kiem tra: systemctl status notary-web notary-worker"
}

main "$@"
