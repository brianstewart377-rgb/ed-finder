#!/usr/bin/env bash
set -euo pipefail

operation="authority-gate"
source_sha=""
workflow_run_id=""
previous=""
for argument in "$@"; do
    if [ "$previous" = "--operation" ]; then operation="$argument"; fi
    if [ "$previous" = "--source-sha" ]; then source_sha="$argument"; fi
    if [ "$previous" = "--workflow-run-id" ]; then workflow_run_id="$argument"; fi
    case "$argument" in
        --operation=*) operation="${argument#--operation=}" ;;
        --source-sha=*) source_sha="${argument#--source-sha=}" ;;
        --workflow-run-id=*) workflow_run_id="${argument#--workflow-run-id=}" ;;
    esac
    previous="$argument"
done

stopped_runtime_receipt() {
    local reason="$1" source_value="null" run_value="null"
    [[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] && source_value="\"$source_sha\""
    [[ "$workflow_run_id" =~ ^[1-9][0-9]{0,19}$ ]] && run_value="\"$workflow_run_id\""
    printf '{"schema_version":"ed-finder/v3-production-migration-receipt/v1","operation":"production-migration","status":"stopped","created_at":"%s","source_sha":%s,"workflow_run_id":%s,"target":{"production":true,"hostname":"ed-finder-prod","fqdn":"nb79a3d.mevnode.com"},"desired_ledger_sha256":null,"schema_identity_sha256":null,"schema_identity_before_sha256":null,"schema_identity_after_sha256":null,"schema_identity_updated":false,"prior_release_compatibility_verified":false,"applied_before":[],"pending":[],"applied_now":[],"database_access_performed":false,"database_writes_performed":false,"migrations_performed":false,"service_changes_performed":false,"edge_recreated":false,"protected_resources_changed":false,"failures":["%s"]}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$source_value" "$run_value" "$reason"
}

case "$operation" in
    authority-gate|plan|apply) ;;
    *)
        stopped_runtime_receipt "invalid_requested_operation"
        exit 78
        ;;
esac

exact_cpython314() {
    timeout --signal=KILL 10 "$1" -I -S -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 14) else 1)' </dev/null >/dev/null 2>&1
}

compatible_readonly_python() {
    timeout --signal=KILL 10 "$1" -I -S -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info.major == 3 and sys.version_info.minor >= 9 else 1)' </dev/null >/dev/null 2>&1
}

if [ "$operation" = apply ]; then
    if ! command -v python3.14 >/dev/null 2>&1; then
        stopped_runtime_receipt "python314_required_for_production_migration"
        exit 78
    fi
    PYTHON_BIN="$(command -v python3.14)"
    if ! exact_cpython314 "$PYTHON_BIN"; then
        stopped_runtime_receipt "python314_required_for_production_migration"
        exit 78
    fi
else
    PYTHON_BIN=""
    if command -v python3.14 >/dev/null 2>&1; then
        candidate="$(command -v python3.14)"
        if exact_cpython314 "$candidate"; then PYTHON_BIN="$candidate"; fi
    fi
    if [ -z "$PYTHON_BIN" ] && command -v python3 >/dev/null 2>&1; then
        candidate="$(command -v python3)"
        if compatible_readonly_python "$candidate"; then PYTHON_BIN="$candidate"; fi
    fi
    if [ -z "$PYTHON_BIN" ]; then
        stopped_runtime_receipt "compatible_python_required_for_production_migration_plan"
        exit 78
    fi
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$PYTHON_BIN" -I -S "$SCRIPT_DIR/../v3_production_migrate.py" "$@"
