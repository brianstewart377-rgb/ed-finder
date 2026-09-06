#!/usr/bin/env bash
set -euo pipefail

# Contabo is a live-checkpoint environment, not production. This launcher
# rejects any non-CPython-3.14 host before the Python safety boundary runs.
if command -v python3.14 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.14)"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    printf '%s\n' '{"status":"stopped","failures":["python3_unavailable"],"service_changes_performed":false}'
    exit 78
fi
if ! "$PYTHON_BIN" -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 14) else 1)'; then
    printf '%s\n' '{"status":"stopped","failures":["python314_required"],"service_changes_performed":false}'
    exit 78
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$PYTHON_BIN" "$SCRIPT_DIR/../v3_checkpoint_deploy.py" "$@"
