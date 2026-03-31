#!/usr/bin/env bash
set -euo pipefail

SWAP_FILE="/swapfile"
SWAP_SIZE_GB="4"

log() {
  printf '[swap-setup] %s\n' "$*"
}

die() {
  printf '[swap-setup][error] %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage:
  bash deploy/vps/setup_swap.sh [--swap-file /swapfile] [--size-gb 4]
USAGE
}

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
    return
  fi
  if command -v sudo >/dev/null 2>&1; then
    sudo "$@"
    return
  fi
  die "Can root hoac sudo de tao swap."
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --swap-file)
        [[ $# -ge 2 ]] || die "Thieu gia tri cho --swap-file"
        SWAP_FILE="$2"
        shift 2
        ;;
      --size-gb)
        [[ $# -ge 2 ]] || die "Thieu gia tri cho --size-gb"
        SWAP_SIZE_GB="$2"
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

ensure_swap_file() {
  local size_mb
  size_mb="$((SWAP_SIZE_GB * 1024))"

  if run_root swapon --show=NAME --noheadings | grep -Fxq "$SWAP_FILE"; then
    log "Swap da active: $SWAP_FILE"
    return 0
  fi

  if [[ -f "$SWAP_FILE" ]]; then
    log "Da ton tai $SWAP_FILE, tai su dung..."
  else
    log "Tao swap file ${SWAP_SIZE_GB}GB tai $SWAP_FILE..."
    if run_root fallocate -l "${SWAP_SIZE_GB}G" "$SWAP_FILE" 2>/dev/null; then
      :
    else
      log "fallocate khong ho tro, fallback sang dd..."
      run_root dd if=/dev/zero of="$SWAP_FILE" bs=1M count="$size_mb" status=progress
    fi
  fi

  run_root chmod 600 "$SWAP_FILE"
  if ! run_root blkid "$SWAP_FILE" >/dev/null 2>&1; then
    run_root mkswap "$SWAP_FILE" >/dev/null
  fi
  run_root swapon "$SWAP_FILE"
}

persist_swap() {
  local fstab_line="$SWAP_FILE none swap sw 0 0"
  if ! run_root grep -Fqx "$fstab_line" /etc/fstab; then
    log "Them swap vao /etc/fstab..."
    printf '%s\n' "$fstab_line" | run_root tee -a /etc/fstab >/dev/null
  fi
}

persist_vm_tuning() {
  local sysctl_file="/etc/sysctl.d/99-notary-swap.conf"
  log "Ap dung vm.swappiness=10 va vm.vfs_cache_pressure=50..."
  run_root tee "$sysctl_file" >/dev/null <<'EOF'
vm.swappiness=10
vm.vfs_cache_pressure=50
EOF
  run_root sysctl -p "$sysctl_file" >/dev/null
}

main() {
  parse_args "$@"
  [[ "$SWAP_SIZE_GB" =~ ^[0-9]+$ ]] || die "--size-gb phai la so nguyen duong"
  ensure_swap_file
  persist_swap
  persist_vm_tuning
  log "Trang thai hien tai:"
  run_root swapon --show
  run_root free -h
}

main "$@"
