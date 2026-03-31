#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$APP_DIR/.env"

APP_USER="${SUDO_USER:-${USER:-}}"
APP_HOST="0.0.0.0"
APP_PORT="8000"
INSTALL_SYSTEM_PACKAGES="1"
INSTALL_SYSTEMD="1"
DOWNLOAD_OCR_MODEL="1"
INSTALL_LOCAL_OCR_DEPS="1"

APT_PACKAGES=(
  python3
  python3-venv
  python3-pip
  python3-dev
  build-essential
  libgl1
  libglib2.0-0
  libzbar0
  libgomp1
  curl
  ca-certificates
)

log() {
  printf '[vps-install] %s\n' "$*"
}

die() {
  printf '[vps-install][error] %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage:
  bash install_vps.sh [options]

Options:
  --app-user <user>          Linux user that will run services.
  --host <host>              Uvicorn bind host (default: 0.0.0.0).
  --port <port>              Uvicorn bind port (default: 8000).
  --skip-system-packages     Skip apt package installation.
  --without-systemd          Skip systemd service setup.
  --without-ocr-model        Skip OCR model auto download.
  --without-local-ocr-deps   Skip Local OCR Python dependency installation.
  -h, --help                 Show this help.
USAGE
}

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
    return
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    die "Can sudo de cai package/service. Hay chay script bang root hoac cai sudo."
  fi
  sudo "$@"
}

escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[\/&]/\\&/g'
}

set_env_if_empty_or_missing() {
  local key="$1"
  local value="$2"
  local escaped
  escaped="$(escape_sed_replacement "$value")"

  if grep -Eq "^${key}=" "$ENV_FILE"; then
    local current
    current="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d'=' -f2- || true)"
    if [[ -z "${current//[[:space:]]/}" ]]; then
      sed -i "s|^${key}=.*|${key}=${escaped}|" "$ENV_FILE"
    fi
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

set_env_value() {
  local key="$1"
  local value="$2"
  local escaped
  escaped="$(escape_sed_replacement "$value")"

  if grep -Eq "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$ENV_FILE"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
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
      --skip-system-packages)
        INSTALL_SYSTEM_PACKAGES="0"
        shift
        ;;
      --without-systemd)
        INSTALL_SYSTEMD="0"
        shift
        ;;
      --without-ocr-model)
        DOWNLOAD_OCR_MODEL="0"
        shift
        ;;
      --without-local-ocr-deps)
        INSTALL_LOCAL_OCR_DEPS="0"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Tuy chon khong hop le: $1. Dung --help de xem huong dan."
        ;;
    esac
  done
}

install_system_packages() {
  [[ "$INSTALL_SYSTEM_PACKAGES" == "1" ]] || return 0

  command -v apt-get >/dev/null 2>&1 || die "Script hien chi ho tro Ubuntu/Debian (apt-get)."
  log "Cai package he thong..."
  run_root apt-get update -y
  run_root apt-get install -y "${APT_PACKAGES[@]}"
}

setup_python_env() {
  cd "$APP_DIR"

  if [[ ! -d "$APP_DIR/venv" ]]; then
    log "Tao virtualenv..."
    python3 -m venv "$APP_DIR/venv"
  fi

  log "Nang cap pip/setuptools/wheel..."
  "$APP_DIR/venv/bin/python" -m pip install --upgrade pip setuptools wheel

  log "Cai dependencies Python..."
  "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
}

install_local_ocr_python_deps() {
  [[ "$INSTALL_LOCAL_OCR_DEPS" == "1" ]] || return 0
  local req_file="$APP_DIR/requirements-local-ocr.txt"
  if [[ ! -f "$req_file" ]]; then
    die "Khong tim thay $req_file"
  fi
  log "Cai dependencies Local OCR..."
  "$APP_DIR/venv/bin/pip" install -r "$req_file"
}

setup_env_and_dirs() {
  cd "$APP_DIR"

  if [[ ! -f "$ENV_FILE" ]]; then
    log "Tao .env tu .env.example..."
    cp "$APP_DIR/.env.example" "$ENV_FILE"
  fi

  mkdir -p "$APP_DIR/logs" "$APP_DIR/tmp/ocr" "$APP_DIR/models/rapidocr"

  # Ensure queue config exists even when user starts from a custom env file.
  set_env_if_empty_or_missing "CELERY_BROKER_URL" "sqlalchemy+sqlite:///./ocr_jobs.db"
  set_env_if_empty_or_missing "CELERY_RESULT_BACKEND" "db+sqlite:///./ocr_jobs.db"
  set_env_if_empty_or_missing "LOCAL_OCR_TIMING_LOG" "1"
  set_env_if_empty_or_missing "LOCAL_OCR_TIMING_SLOW_MS" "1500"
}

download_default_ocr_model() {
  [[ "$DOWNLOAD_OCR_MODEL" == "1" ]] || return 0

  local model_dir="$APP_DIR/models/rapidocr"
  local vi_model_v4="$model_dir/vi_PP-OCRv4_rec_infer.onnx"
  local vi_model_v3="$model_dir/vi_PP-OCRv3_rec_infer.onnx"
  local vi_keys="$model_dir/vi_dict.txt"
  local latin_model="$model_dir/latin_PP-OCRv3_rec_infer.onnx"
  local latin_keys="$model_dir/latin_dict.txt"
  local rec_model=""
  local rec_keys=""

  if [[ ! -f "$latin_model" ]]; then
    log "Tai OCR rec model mac dinh (latin)..."
    curl -fL "https://huggingface.co/breezedeus/cnocr-ppocr-latin_PP-OCRv3/resolve/main/latin_PP-OCRv3_rec_infer.onnx" -o "$latin_model"
  fi

  if [[ ! -f "$latin_keys" ]]; then
    log "Tai OCR rec dictionary..."
    curl -fL "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/dict/latin_dict.txt" -o "$latin_keys"
  fi

  if [[ -f "$vi_model_v4" ]]; then
    rec_model="$vi_model_v4"
  elif [[ -f "$vi_model_v3" ]]; then
    rec_model="$vi_model_v3"
  else
    rec_model="$latin_model"
  fi

  if [[ "$rec_model" == "$vi_model_v4" || "$rec_model" == "$vi_model_v3" ]]; then
    if [[ -f "$vi_keys" ]]; then
      rec_keys="$vi_keys"
    else
      rec_keys="$latin_keys"
    fi
  else
    rec_keys="$latin_keys"
  fi

  log "Chon OCR rec model: $rec_model"
  set_env_value "LOCAL_OCR_REC_MODEL_PATH" "$rec_model"
  set_env_value "LOCAL_OCR_REC_KEYS_PATH" "$rec_keys"
}

install_systemd_services() {
  [[ "$INSTALL_SYSTEMD" == "1" ]] || return 0

  log "Tao systemd services..."
  bash "$SCRIPT_DIR/install_systemd.sh" \
    --app-dir "$APP_DIR" \
    --app-user "$APP_USER" \
    --host "$APP_HOST" \
    --port "$APP_PORT"
}

print_summary() {
  cat <<EOF

=========================================
VPS setup completed.
=========================================
Project dir : $APP_DIR
Service user: $APP_USER
Host / port : $APP_HOST:$APP_PORT

Next steps:
1) Edit $ENV_FILE and set OPENAI_API_KEY.
EOF

  if [[ "$INSTALL_SYSTEMD" == "1" ]]; then
    cat <<EOF
2) Manage services:
   bash $APP_DIR/deploy/vps/manage_services.sh status
   bash $APP_DIR/deploy/vps/manage_services.sh logs
3) Open firewall port if needed (default 8000).
EOF
  else
    cat <<EOF
2) Start manually (without systemd):
   cd $APP_DIR
   ./venv/bin/python -m celery -A celery_app.celery_app worker --pool=solo --concurrency=1 --loglevel=INFO
   ./venv/bin/python -m uvicorn main:app --host $APP_HOST --port $APP_PORT
EOF
  fi
}

main() {
  parse_args "$@"

  if [[ -z "${APP_USER}" ]]; then
    APP_USER="$(id -un)"
  fi

  id "$APP_USER" >/dev/null 2>&1 || die "User '$APP_USER' khong ton tai tren VPS."
  [[ -f "$APP_DIR/requirements.txt" ]] || die "Khong tim thay requirements.txt trong $APP_DIR"

  install_system_packages
  setup_python_env
  install_local_ocr_python_deps
  setup_env_and_dirs
  download_default_ocr_model
  install_systemd_services
  print_summary
}

main "$@"
