#!/usr/bin/env bash
set -euo pipefail

# Read-only authority/preflight may use a compatible already-present CPython
# standard library. Actual mutation retains exact CPython 3.14 and never
# installs it. Every runtime probe is bounded before any Python code is trusted.
operation="authority-gate"
previous=""
for argument in "$@"; do
    if [ "$previous" = "--operation" ]; then operation="$argument"; fi
    case "$argument" in
        --operation=*) operation="${argument#--operation=}" ;;
    esac
    previous="$argument"
done

case "$operation" in
    authority-gate) receipt_operation="production-authority-gate" ;;
    preflight) receipt_operation="production-preflight" ;;
    promote) receipt_operation="production-promotion" ;;
    *)
        printf '%s\n' '{"schema_version":"ed-finder/v3-production-deployment-receipt/v1","operation":"production-authority-gate","status":"stopped","failures":["invalid_requested_operation"],"database_access_performed":false,"database_writes_performed":false,"migrations_performed":false,"application_data_writes_performed":false,"image_pulls_performed":false,"service_changes_performed":false,"edge_recreated":false,"filesystem_writes_performed":false}'
        exit 78
        ;;
esac

stopped_runtime_receipt() {
    failure="$1"
    filesystem_writes=false
    filesystem_scope=""
    if [ "$operation" = preflight ] || [ "$operation" = promote ]; then
        filesystem_writes=true
        filesystem_scope=',"filesystem_write_scope":"ephemeral-operation-bundle-only"'
    fi
    printf '{"schema_version":"ed-finder/v3-production-deployment-receipt/v1","operation":"%s","status":"stopped","target":{"production":true,"hostname":"ed-finder-prod","fqdn":"nb79a3d.mevnode.com"},"failures":["%s"],"database_access_performed":false,"database_writes_performed":false,"migrations_performed":false,"application_data_writes_performed":false,"image_pulls_performed":false,"service_changes_performed":false,"edge_recreated":false,"protected_resources_changed":false,"filesystem_writes_performed":%s,"env_files_read":false,"env_contents_recorded":false,"private_keys_read":false%s}\n' "$receipt_operation" "$failure" "$filesystem_writes" "$filesystem_scope"
}

exact_cpython314() {
    timeout --signal=KILL 10 "$1" -I -S -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 14) else 1)' </dev/null >/dev/null 2>&1
}

compatible_readonly_python() {
    timeout --signal=KILL 10 "$1" -I -S -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info.major == 3 and sys.version_info.minor >= 9 else 1)' </dev/null >/dev/null 2>&1
}

if [ "$operation" = "promote" ]; then
    if ! command -v python3.14 >/dev/null 2>&1; then
        stopped_runtime_receipt "python314_required_for_production_mutation"
        exit 78
    fi
    PYTHON_BIN="$(command -v python3.14)"
    if ! exact_cpython314 "$PYTHON_BIN"; then
        stopped_runtime_receipt "python314_required_for_production_mutation"
        exit 78
    fi
else
    PYTHON_BIN=""
    runtime_candidate_seen=false
    if command -v python3.14 >/dev/null 2>&1; then
        runtime_candidate_seen=true
        candidate="$(command -v python3.14)"
        if exact_cpython314 "$candidate"; then
            PYTHON_BIN="$candidate"
        fi
    fi
    if [ -z "$PYTHON_BIN" ]; then
        if ! command -v python3 >/dev/null 2>&1; then
            if [ "$runtime_candidate_seen" = true ]; then
                stopped_runtime_receipt "python3_unsupported_for_production_readonly"
            else
                stopped_runtime_receipt "python3_unavailable"
            fi
            exit 78
        fi
        candidate="$(command -v python3)"
        if ! compatible_readonly_python "$candidate"; then
            stopped_runtime_receipt "python3_unsupported_for_production_readonly"
            exit 78
        fi
        PYTHON_BIN="$candidate"
    fi
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$PYTHON_BIN" -I -S "$SCRIPT_DIR/../v3_production_deploy.py" "$@"
