#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3.14 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.14)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  printf 'CPython 3.14 is required\n' >&2
  exit 1
fi
"$PYTHON_BIN" -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 14) else 1)' \
  || { printf 'CPython 3.14 is required\n' >&2; exit 1; }
exec "$PYTHON_BIN" "$SCRIPT_DIR/station_enrichment_guard.py" "$@"
