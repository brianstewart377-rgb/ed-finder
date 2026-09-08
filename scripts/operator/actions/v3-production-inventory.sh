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
export V3_PRODUCTION_INVENTORY_SCRIPT="$SCRIPT_DIR/../v3_production_inventory.py"
exec "$(command -v python3)" -I -S - <<'PY'
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re

SCRIPT = os.environ["V3_PRODUCTION_INVENTORY_SCRIPT"]
spec = importlib.util.spec_from_file_location("v3_production_inventory", SCRIPT)
if spec is None or spec.loader is None:
    raise SystemExit(78)
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)

inventory.DB_USER = "edfinder_v3"
inventory.DB_NAME = "edfinder_v3_phase4c_full_20260827_r5"
inventory.LEDGER_SQL = r"""
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10000ms';
SELECT json_build_object(
  'database_name', current_database(),
  'server_address', COALESCE(inet_server_addr()::text, 'local'),
  'server_port', COALESCE(inet_server_port(), current_setting('port')::int),
  'transaction_read_only', current_setting('transaction_read_only'),
  'migrations', COALESCE((
    SELECT json_agg(
      json_build_object(
        'migration_name', migration_name,
        'migration_sha256', encode(migration_sha256, 'hex')
      ) ORDER BY migration_name
    ) FROM v3_meta.schema_migration
  ), '[]'::json)
)::text;
COMMIT;
""".strip()


def parse_native_ledger(result):
    value = {
        "inspection_succeeded": False,
        "query_read_only": False,
        "database_identity": None,
        "ledger_table": "v3_meta.schema_migration",
        "migration_count": 0,
        "migration_names": [],
        "native_ledger_identity": None,
        "identity_algorithm": "sha256(concat(utf8(migration_name),NUL,raw_sha256,LF) ordered by migration_name)",
    }
    if result.returncode != 0:
        return value
    try:
        observed = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return value
    if not isinstance(observed, dict) or set(observed) != {
        "database_name", "server_address", "server_port",
        "transaction_read_only", "migrations",
    }:
        return value
    entries = observed["migrations"]
    if (
        not isinstance(entries, list)
        or not entries
        or any(
            not isinstance(item, dict)
            or set(item) != {"migration_name", "migration_sha256"}
            or not isinstance(item["migration_name"], str)
            or not 0 < len(item["migration_name"]) <= 160
            or re.fullmatch(r"[A-Za-z0-9_./-]+\.sql", item["migration_name"]) is None
            or re.fullmatch(r"[0-9a-f]{64}", str(item["migration_sha256"])) is None
            for item in entries
        )
    ):
        return value
    if entries != sorted(entries, key=lambda item: item["migration_name"]):
        return value
    names = [item["migration_name"] for item in entries]
    if len(set(names)) != len(names):
        return value
    digest = hashlib.sha256()
    for item in entries:
        digest.update(item["migration_name"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(item["migration_sha256"]))
        digest.update(b"\n")
    value.update(
        inspection_succeeded=True,
        query_read_only=observed["transaction_read_only"] == "on",
        database_identity={
            "database_name": observed["database_name"],
            "server_address": observed["server_address"],
            "server_port": observed["server_port"],
        },
        migration_count=len(entries),
        migration_names=names,
        native_ledger_identity="sha256:" + digest.hexdigest(),
    )
    if not value["query_read_only"]:
        value["inspection_succeeded"] = False
    return value


inventory.parse_ledger = parse_native_ledger

capture = io.StringIO()
with contextlib.redirect_stdout(capture):
    inventory.main()
lines = [line for line in capture.getvalue().splitlines() if line.strip()]
if not lines:
    raise SystemExit(78)
try:
    receipt = json.loads(lines[-1])
except json.JSONDecodeError:
    print(lines[-1])
    raise SystemExit(78)

# The current checkpoint intentionally has an API-only loopback origin and a
# temporary public shell before edge cutover. Accept only that exact observed
# transitional shape; every other HTTP failure remains fail-closed.
failures = set(receipt.get("failures") or [])
http = receipt.get("http") if isinstance(receipt.get("http"), dict) else {}
current = receipt.get("current_release") if isinstance(receipt.get("current_release"), dict) else {}
origin_health_shape = current.get("origin_health") if isinstance(current.get("origin_health"), dict) else {}
origin_root = http.get("origin_root") if isinstance(http.get("origin_root"), dict) else {}
origin_health = http.get("origin_health") if isinstance(http.get("origin_health"), dict) else {}
public_root = http.get("public_root") if isinstance(http.get("public_root"), dict) else {}
public_health = http.get("public_health") if isinstance(http.get("public_health"), dict) else {}

origin_transition = (
    origin_root.get("inspection_succeeded") is True
    and origin_root.get("status_code") == 404
    and origin_health.get("inspection_succeeded") is True
    and origin_health.get("status_code") == 200
    and origin_health_shape.get("status") == "ok"
    and origin_health_shape.get("database") == "connected"
)
public_transition = (
    public_root.get("inspection_succeeded") is True
    and public_root.get("status_code") == 200
    and current.get("public_temporary_shell") is True
    and public_health.get("inspection_succeeded") is True
    and public_health.get("status_code") == 503
)
if origin_transition:
    failures.discard("origin_root_inventory_failed")
if public_transition:
    failures.discard("public_health_inventory_failed")
receipt["transition_policy"] = {
    "api_only_origin_observed": origin_transition,
    "temporary_public_shell_observed": public_transition,
    "accepted_only_for_read_only_inventory_before_cutover": True,
}
receipt["failures"] = sorted(failures)
receipt["status"] = "success" if not failures else "stopped"
print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
raise SystemExit(0 if not failures else 78)
PY
