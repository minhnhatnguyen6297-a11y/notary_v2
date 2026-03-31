#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
WEB_SERVICE="notary-web.service"
WORKER_SERVICE="notary-worker.service"

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
    return
  fi
  if command -v sudo >/dev/null 2>&1; then
    sudo "$@"
    return
  fi
  "$@"
}

usage() {
  cat <<'USAGE'
Usage:
  bash deploy/vps/manage_services.sh <action>

Actions:
  start     Start both services
  stop      Stop both services
  restart   Restart both services
  status    Show status for both services
  logs      Follow service logs (Ctrl+C to exit)
USAGE
}

case "$ACTION" in
  start)
    run_root systemctl start "$WORKER_SERVICE" "$WEB_SERVICE"
    run_root systemctl status "$WORKER_SERVICE" "$WEB_SERVICE" --no-pager
    ;;
  stop)
    run_root systemctl stop "$WEB_SERVICE" "$WORKER_SERVICE"
    run_root systemctl status "$WORKER_SERVICE" "$WEB_SERVICE" --no-pager
    ;;
  restart)
    run_root systemctl restart "$WORKER_SERVICE" "$WEB_SERVICE"
    run_root systemctl status "$WORKER_SERVICE" "$WEB_SERVICE" --no-pager
    ;;
  status)
    run_root systemctl status "$WORKER_SERVICE" "$WEB_SERVICE" --no-pager
    ;;
  logs)
    run_root journalctl -u "$WORKER_SERVICE" -u "$WEB_SERVICE" -f --no-pager
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Action khong hop le: $ACTION" >&2
    usage
    exit 1
    ;;
esac
