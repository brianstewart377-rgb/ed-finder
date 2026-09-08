#!/usr/bin/env bash
set -euo pipefail

# Read-only authority/preflight may use the already-present Python 3 standard
# library. Actual mutation retains exact CPython 3.14 and never installs it.
operation="authority-gate"
previous=""
for argument in "$@"; do
    if [ "$previous" = "--operation" ]; then operation="$argument"; fi
    previous="$argument"
done

if [ "$operation" = "promote" ]; then
    if ! command -v python3.14 >/dev/null 2>&1; then
        printf '%s\n' '{"schema_version":"ed-finder/v3-production-deployment-receipt/v1","operation":"production-promotion","status":"stopped","target":{"production":true,"hostname":"ed-finder-prod","fqdn":"nb79a3d.mevnode.com"},"failures":["python314_required_for_production_mutation"],"database_access_performed":false,"database_writes_performed":false,"migrations_performed":false,"application_data_writes_performed":false,"image_pulls_performed":false,"service_changes_performed":false,"edge_recreated":false,"filesystem_writes_performed":false}'
        exit 78
    fi
    PYTHON_BIN="$(command -v python3.14)"
    if ! "$PYTHON_BIN" -I -S -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 14) else 1)'; then
        printf '%s\n' '{"schema_version":"ed-finder/v3-production-deployment-receipt/v1","operation":"production-promotion","status":"stopped","target":{"production":true,"hostname":"ed-finder-prod","fqdn":"nb79a3d.mevnode.com"},"failures":["python314_required_for_production_mutation"],"database_access_performed":false,"database_writes_performed":false,"migrations_performed":false,"application_data_writes_performed":false,"image_pulls_performed":false,"service_changes_performed":false,"edge_recreated":false,"filesystem_writes_performed":false}'
        exit 78
    fi
elif ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' '{"schema_version":"ed-finder/v3-production-deployment-receipt/v1","operation":"production-promotion","status":"stopped","failures":["python3_unavailable"],"database_access_performed":false,"database_writes_performed":false,"migrations_performed":false,"application_data_writes_performed":false,"image_pulls_performed":false,"service_changes_performed":false,"edge_recreated":false,"filesystem_writes_performed":false}'
    exit 78
else
    PYTHON_BIN="$(command -v python3)"
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$PYTHON_BIN" -I -S "$SCRIPT_DIR/../v3_production_deploy.py" "$@"
