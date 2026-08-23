#!/usr/bin/env bash
set -euo pipefail

target="${1:-}"
shift || true

case "$target" in
  hetzner)
    exec bash scripts/operator/actions/dispatch.sh "$@"
    ;;
  mevspace)
    exec bash scripts/operator/targets/mevspace/dispatch.sh "$@"
    ;;
  *)
    echo "STOP: unsupported operator target: ${target:-<missing>}" >&2
    echo "Allowed targets: hetzner, mevspace" >&2
    exit 1
    ;;
esac
