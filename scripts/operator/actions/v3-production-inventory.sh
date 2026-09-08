#!/usr/bin/env bash
set -euo pipefail

# Read-only production inventory is deliberately allowed to use the host's
# already-present Python 3 standard library. Do not install CPython 3.14 merely
# to run this status/preflight path.
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' '{"schema_version":"ed-finder/v3-production-inventory/v1","operation":"v3-production-inventory","status":"stopped","read_only":true,"direct_db_access_performed":false,"db_writes_performed":false,"migrations_performed":false,"application_data_writes_performed":false,"env_files_read":false,"container_environment_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false,"failures":["python3_unavailable"]}'
    exit 78
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$(command -v python3)" -I -S "$SCRIPT_DIR/../v3_production_inventory.py"
