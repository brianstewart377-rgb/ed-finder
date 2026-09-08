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
export V3_PRODUCTION_DEPLOY_SCRIPT="$SCRIPT_DIR/../v3_production_deploy.py"
exec "$PYTHON_BIN" -I -S - "$@" <<'PY'
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.parse

SCRIPT = os.environ["V3_PRODUCTION_DEPLOY_SCRIPT"]
spec = importlib.util.spec_from_file_location("v3_production_deploy", SCRIPT)
if spec is None or spec.loader is None:
    raise SystemExit(78)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

SCHEMA_V2 = "ed-finder/v3-production-schema-identity/v2"
DB_NAME = "edfinder_v3_phase4c_full_20260827_r5"
DB_USER = "edfinder_v3"
APP_DB_HOST = "postgres"
LEDGER_TABLE = "v3_meta.schema_migration"
LEDGER_NAMES = [
    "001_v3_baseline.sql",
    "002_v3_accounts_identity.sql",
    "r1_v3/001_structural_shell.sql",
]
LEDGER_IDENTITY = "sha256:78f2ae409ba78e5b5d3687f6df3dd029079582fc683fda6761659057b3f31693"
IDENTITY_ALGORITHM = "sha256(concat(utf8(migration_name),NUL,raw_sha256,LF) ordered by migration_name)"


def expected_database_identity():
    return {
        "container": deploy.POSTGRES_CONTAINER,
        "database_name": DB_NAME,
        "database_user": DB_USER,
        "application_host": APP_DB_HOST,
        "server_address": "local",
        "server_port": 5432,
    }


def validate_schema_file(path, expected_sha):
    if deploy.sha256_file(path) != expected_sha:
        raise deploy.DeploymentError("production schema identity checksum mismatch")
    value = deploy.load_json(path, "production schema identity")
    if set(value) != {
        "schema_version", "database_identity", "migration_set_identity",
        "native_ledger", "evidence",
    } or value.get("schema_version") != SCHEMA_V2:
        raise deploy.DeploymentError("production native schema identity shape is invalid")
    if value.get("database_identity") != expected_database_identity():
        raise deploy.DeploymentError("production native database identity is invalid")
    if value.get("migration_set_identity") != LEDGER_IDENTITY:
        raise deploy.DeploymentError("production native ledger identity is not the reviewed Phase4C identity")
    native = value.get("native_ledger")
    if native != {
        "table": LEDGER_TABLE,
        "migration_count": len(LEDGER_NAMES),
        "migration_names": LEDGER_NAMES,
        "identity_algorithm": IDENTITY_ALGORITHM,
    }:
        raise deploy.DeploymentError("production native ledger authority is invalid")
    evidence = value.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 512:
        raise deploy.DeploymentError("production native schema identity lacks reviewed evidence")
    if re.search(
        r"(?i)(password|passwd|secret|private[-_ ]?key|access[-_ ]?token|dsn|credential)",
        evidence,
    ) or re.search(r"(?i)[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@", evidence):
        raise deploy.DeploymentError("production schema evidence contains secret-like text")
    return value


def database_identity_from_env(path, *, on_read=None):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise deploy.DeploymentError("unable to read verified production API env snapshot") from exc
    if on_read is not None:
        on_read()
    assignments = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw_value = line.partition("=")
        if separator and key.strip() == "DATABASE_URL":
            assignments.append(raw_value.strip())
    if len(assignments) != 1:
        raise deploy.DeploymentError("production API env must contain exactly one DATABASE_URL")
    value = assignments[0]
    if (
        not value or value[0] in {"'", '"'} or "$" in value or "`" in value
        or any(character.isspace() for character in value)
    ):
        raise deploy.DeploymentError("production DATABASE_URL must be one unquoted literal")
    try:
        parsed = urllib.parse.urlsplit(value)
        database_name = urllib.parse.unquote(parsed.path.removeprefix("/"))
        username = urllib.parse.unquote(parsed.username or "")
        password = parsed.password
        port = parsed.port
    except (ValueError, UnicodeError) as exc:
        raise deploy.DeploymentError("production DATABASE_URL identity is invalid") from exc
    if (
        parsed.scheme not in {"postgresql", "postgres"}
        or username != DB_USER
        or not password
        or parsed.hostname != APP_DB_HOST
        or port not in {None, 5432}
        or database_name != DB_NAME
        or parsed.query
        or parsed.fragment
    ):
        raise deploy.DeploymentError("production DATABASE_URL does not target retained V3 PostgreSQL")
    return expected_database_identity()


def verify_live_schema(schema, env, runner):
    sql = r"""
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10000ms';
SELECT COALESCE(json_agg(
  json_build_object(
    'migration_name', migration_name,
    'migration_sha256', encode(migration_sha256, 'hex')
  ) ORDER BY migration_name
), '[]'::json)::text
FROM v3_meta.schema_migration;
COMMIT;
""".strip()
    result = runner(
        [
            "docker", "exec", deploy.POSTGRES_CONTAINER,
            "psql", "-X", "--no-password", "--tuples-only", "--no-align", "--quiet",
            "--set", "ON_ERROR_STOP=1", "--username", DB_USER, "--dbname", DB_NAME,
            "--command", sql,
        ],
        env=env,
    )
    if len(result.stdout.encode("utf-8")) > deploy.MAX_JSON:
        raise deploy.DeploymentError("production native migration ledger output exceeds size limit")
    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            try:
                rows = json.loads(line)
            except json.JSONDecodeError as exc:
                raise deploy.DeploymentError("production native migration ledger returned invalid JSON") from exc
    if (
        not isinstance(rows, list)
        or len(rows) != len(LEDGER_NAMES)
        or any(
            not isinstance(item, dict)
            or set(item) != {"migration_name", "migration_sha256"}
            or not isinstance(item["migration_name"], str)
            or not re.fullmatch(r"[A-Za-z0-9_./-]+\.sql", item["migration_name"])
            or not re.fullmatch(r"[0-9a-f]{64}", str(item["migration_sha256"]))
            for item in rows
        )
        or [item["migration_name"] for item in rows] != LEDGER_NAMES
    ):
        raise deploy.DeploymentError("production native migration ledger entries are invalid")
    digest = hashlib.sha256()
    for item in rows:
        digest.update(item["migration_name"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(item["migration_sha256"]))
        digest.update(b"\n")
    observed_identity = "sha256:" + digest.hexdigest()
    if observed_identity != schema.get("migration_set_identity") or observed_identity != LEDGER_IDENTITY:
        raise deploy.DeploymentError("production_migration_authority_absent_or_schema_incompatible")


deploy.SCHEMA_IDENTITY_SCHEMA = SCHEMA_V2
deploy.validate_schema_file = validate_schema_file
deploy.database_identity_from_env = database_identity_from_env
deploy.verify_live_schema = verify_live_schema
raise SystemExit(deploy.main(sys.argv[1:]))
PY
