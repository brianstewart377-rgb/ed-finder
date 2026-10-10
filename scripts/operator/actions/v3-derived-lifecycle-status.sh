#!/usr/bin/env bash
# Reports the read-only worker, migration, and generation lifecycle evidence for
# roadmap step 0 of the Finder rollout; it does not change services or data.
set -euo pipefail

if command -v python3.14 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.14)"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-derived-lifecycle-status","status":"stopped","failures":["python3_unavailable"],"read_only":true,"direct_db_access_performed":false,"db_writes_performed":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false}'
    exit 1
fi
if ! "$PYTHON_BIN" -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 14) else 1)'; then
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-derived-lifecycle-status","status":"stopped","failures":["python314_required"],"read_only":true,"direct_db_access_performed":false,"db_writes_performed":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false}'
    exit 1
fi

exec "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"
STATEMENT_TIMEOUT_MS = 20000
PROCESS_TIMEOUT_SECONDS = 30

WORKER_CONTAINERS = (
    "edfinder-ratings-v4-prod-p4",
    "edfinder-ratings-v4-prod-p4-opt1",
    "edfinder-ratings-v4-prod-p4-parallel-v1",
    "edfinder-v3-system-search-p4-opt1",
)
FINDER_MIGRATIONS = (
    "010_v3_system_search_body_type_counts.sql",
    "011_v3_system_archetype.sql",
    "013_v3_system_search_parallel.sql",
    "014_v3_watchlist.sql",
)
WORKER_INSPECT_FORMAT = (
    "{{.State.Status}}\t{{.State.Running}}\t{{.State.ExitCode}}\t{{.State.FinishedAt}}"
)


def run(
    argv: list[str], *, timeout: int = PROCESS_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv, text=True, capture_output=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 125, "", type(exc).__name__)


def resolve_database_identity() -> tuple[str, str]:
    """Read only the non-secret role and database names from the DB container."""
    result = run(
        [
            "docker",
            "exec",
            POSTGRES_CONTAINER,
            "sh",
            "-lc",
            'printf "%s\\t%s\\n" "$POSTGRES_USER" "${POSTGRES_DB:-$POSTGRES_USER}"',
        ]
    )
    if result.returncode != 0:
        raise RuntimeError("postgres_runtime_identity_command_failed")
    parts = result.stdout.rstrip("\n").split("\t")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise RuntimeError("postgres_runtime_identity_missing")
    return parts[0], parts[1]


def psql(
    sql: str,
    db_user: str,
    db_name: str,
    *,
    timeout: int = PROCESS_TIMEOUT_SECONDS,
) -> list[list[str]]:
    # Every statement is hard-coded here. The transaction is an independent
    # safety boundary on top of the operator workflow.
    wrapped = (
        "BEGIN READ ONLY; "
        f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms'; "
        + sql.rstrip().rstrip(";")
        + "; COMMIT;"
    )
    result = run(
        [
            "docker",
            "exec",
            POSTGRES_CONTAINER,
            "psql",
            "-X",
            "-qAt",
            "-F",
            "\t",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            db_user,
            "-d",
            db_name,
            "-c",
            wrapped,
        ],
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = detail[-1][:240] if detail else f"exit_{result.returncode}"
        raise RuntimeError(suffix)
    rows: list[list[str]] = []
    for line in result.stdout.splitlines():
        if line.strip():
            rows.append(line.split("\t"))
    return rows


def as_int(value: str | None) -> int | None:
    if value in (None, "", "\\N"):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def as_optional(value: str | None) -> str | None:
    if value in (None, "", "\\N"):
        return None
    return value


def inspect_worker(name: str) -> dict[str, Any]:
    result = run(["docker", "inspect", "-f", WORKER_INSPECT_FORMAT, name])
    if result.returncode != 0:
        return {
            "name": name,
            "exists": False,
            "running": False,
            "status": None,
            "exit_code": None,
            "finished_at": None,
        }
    parts = result.stdout.rstrip("\n").split("\t")
    if len(parts) != 4:
        return {
            "name": name,
            "exists": True,
            "running": None,
            "status": None,
            "exit_code": None,
            "finished_at": None,
        }
    running_value = parts[1].lower()
    running = True if running_value == "true" else False if running_value == "false" else None
    return {
        "name": name,
        "exists": True,
        "running": running,
        "status": as_optional(parts[0]),
        "exit_code": as_int(parts[2]),
        "finished_at": as_optional(parts[3]),
    }


receipt: dict[str, Any] = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "v3-derived-lifecycle-status",
    "status": "stopped",
    "read_only": True,
    "direct_db_access_performed": False,
    "db_writes_performed": False,
    "env_files_read": False,
    "private_keys_read": False,
    "service_changes_performed": False,
    "filesystem_writes_performed": False,
    "database_identity_source": "running_container_role_and_database_names_only",
    "query_policy": {
        "transaction": "READ ONLY",
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
    },
}
failures: list[str] = []

short_result = run(["hostname", "-s"])
fqdn_result = run(["hostname", "-f"])
host = short_result.stdout.strip()
fqdn = fqdn_result.stdout.strip()
receipt["host"] = {"short": host, "fqdn": fqdn}
if (
    short_result.returncode != 0
    or host != EXPECTED_HOST
    or fqdn_result.returncode != 0
    or fqdn != EXPECTED_FQDN
):
    failures.append("unexpected_host_identity")
if run(["pwd", "-P"]).stdout.strip() != "/opt/ed-finder":
    failures.append("unexpected_working_directory")
if failures:
    receipt["failures"] = sorted(set(failures))
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    sys.exit(1)

container = run(["docker", "inspect", "-f", "{{.State.Running}}", POSTGRES_CONTAINER])
if container.returncode != 0 or container.stdout.strip() != "true":
    failures.append("postgres_container_unavailable")
    receipt["failures"] = sorted(set(failures))
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    sys.exit(1)

workers = [inspect_worker(name) for name in WORKER_CONTAINERS]
all_named_workers_stopped = not any(worker["running"] is True for worker in workers)
receipt["workers"] = workers
receipt["all_named_workers_stopped"] = all_named_workers_stopped

try:
    db_user, db_name = resolve_database_identity()
except RuntimeError as exc:
    failures.append("postgres_runtime_identity_unavailable")
    receipt["query_error"] = str(exc)
    receipt["failures"] = sorted(set(failures))
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    sys.exit(1)

receipt["direct_db_access_performed"] = True
receipt["postgres"] = {
    "container": POSTGRES_CONTAINER,
    "database_user": db_user,
    "database_name": db_name,
}
current_pointers_recorded = False

try:
    postgres_rows = psql(
        "SELECT current_user, current_database(), current_setting('server_version'), "
        "current_setting('server_version_num')",
        db_user,
        db_name,
    )
    if postgres_rows:
        receipt["postgres"].update(
            {
                "reported_user": postgres_rows[0][0],
                "reported_database": postgres_rows[0][1],
                "server_version": postgres_rows[0][2],
                "server_version_num": as_int(postgres_rows[0][3]),
            }
        )

    migration_rows = psql(
        "SELECT migration_name, encode(migration_sha256,'hex'), applied_at::text "
        "FROM v3_meta.schema_migration ORDER BY applied_at, migration_name",
        db_user,
        db_name,
    )
    receipt["schema_migrations"] = [
        {
            "migration_name": row[0],
            "migration_sha256_hex": row[1],
            "applied_at": row[2],
        }
        for row in migration_rows
    ]
    applied_migrations = {row[0] for row in migration_rows}
    receipt["finder_migrations_applied"] = {
        name: name in applied_migrations for name in FINDER_MIGRATIONS
    }

    canonical_pointer_rows = psql(
        "SELECT g.generation_id::text, g.generation_key, g.relation_schema, "
        "g.lifecycle_state, p.publication_sequence::text, p.published_at::text "
        "FROM v3_meta.current_canonical_generation p "
        "JOIN v3_meta.canonical_generation g ON g.generation_id=p.generation_id "
        "WHERE p.singleton",
        db_user,
        db_name,
    )
    receipt["canonical"] = (
        {
            "generation_id": canonical_pointer_rows[0][0],
            "generation_key": canonical_pointer_rows[0][1],
            "relation_schema": canonical_pointer_rows[0][2],
            "lifecycle_state": canonical_pointer_rows[0][3],
            "publication_sequence": as_int(canonical_pointer_rows[0][4]),
            "published_at": canonical_pointer_rows[0][5],
        }
        if canonical_pointer_rows
        else None
    )

    canonical_rows = psql(
        "SELECT generation_id::text, generation_key, lifecycle_state, created_at::text, "
        "published_at::text, retired_at::text, failed_at::text, "
        "LEFT(failure_reason,240) FROM v3_meta.canonical_generation ORDER BY created_at",
        db_user,
        db_name,
    )
    receipt["canonical_generations"] = [
        {
            "generation_id": row[0],
            "generation_key": row[1],
            "lifecycle_state": row[2],
            "created_at": row[3],
            "published_at": as_optional(row[4]),
            "retired_at": as_optional(row[5]),
            "failed_at": as_optional(row[6]),
            "failure_reason": as_optional(row[7]),
        }
        for row in canonical_rows
    ]

    derived_pointer_rows = psql(
        "SELECT g.derived_generation_id::text, g.generation_key, g.lifecycle_state, "
        "g.canonical_generation_id::text, p.publication_sequence::text, "
        "p.published_at::text FROM v3_meta.current_derived_generation p "
        "JOIN v3_meta.derived_generation g "
        "ON g.derived_generation_id=p.derived_generation_id WHERE p.singleton",
        db_user,
        db_name,
    )
    receipt["derived"] = (
        {
            "derived_generation_id": derived_pointer_rows[0][0],
            "generation_key": derived_pointer_rows[0][1],
            "lifecycle_state": derived_pointer_rows[0][2],
            "canonical_generation_id": derived_pointer_rows[0][3],
            "publication_sequence": as_int(derived_pointer_rows[0][4]),
            "published_at": derived_pointer_rows[0][5],
        }
        if derived_pointer_rows
        else None
    )

    derived_rows = psql(
        "SELECT derived_generation_id::text, generation_key, "
        "canonical_generation_id::text, canonical_publication_sequence::text, "
        "mechanics_version, scorer_version, adapter_version, lifecycle_state, "
        "expected_systems::text, expected_bodies::text, created_at::text, "
        "validated_at::text, published_at::text, failed_at::text, LEFT(failure,240) "
        "FROM v3_meta.derived_generation ORDER BY created_at",
        db_user,
        db_name,
    )
    receipt["derived_generations"] = [
        {
            "derived_generation_id": row[0],
            "generation_key": row[1],
            "canonical_generation_id": row[2],
            "canonical_publication_sequence": as_int(row[3]),
            "mechanics_version": row[4],
            "scorer_version": row[5],
            "adapter_version": row[6],
            "lifecycle_state": row[7],
            "expected_systems": as_int(row[8]),
            "expected_bodies": as_int(row[9]),
            "created_at": row[10],
            "validated_at": as_optional(row[11]),
            "published_at": as_optional(row[12]),
            "failed_at": as_optional(row[13]),
            "failure": as_optional(row[14]),
        }
        for row in derived_rows
    ]

    product_present_rows = psql(
        "SELECT to_regclass('v3_meta.derived_product')::text",
        db_user,
        db_name,
    )
    product_table_present = bool(product_present_rows and product_present_rows[0][0])
    receipt["derived_product_table_present"] = product_table_present
    if product_table_present:
        product_rows = psql(
            "SELECT p.derived_generation_id::text, g.generation_key, p.product_code, "
            "p.product_version, p.lifecycle_state, p.expected_rows::text, "
            "p.created_at::text, p.validated_at::text, p.failed_at::text, "
            "LEFT(p.failure,240), "
            "CASE WHEN p.validation_sha256 IS NULL THEN NULL "
            "ELSE encode(p.validation_sha256,'hex') END "
            "FROM v3_meta.derived_product p JOIN v3_meta.derived_generation g "
            "ON g.derived_generation_id=p.derived_generation_id "
            "ORDER BY g.created_at, p.product_code",
            db_user,
            db_name,
        )
        receipt["derived_products"] = [
            {
                "derived_generation_id": row[0],
                "generation_key": row[1],
                "product_code": row[2],
                "product_version": row[3],
                "lifecycle_state": row[4],
                "expected_rows": as_int(row[5]),
                "created_at": row[6],
                "validated_at": as_optional(row[7]),
                "failed_at": as_optional(row[8]),
                "failure": as_optional(row[9]),
                "validation_sha256_hex": as_optional(row[10]),
            }
            for row in product_rows
        ]
    else:
        receipt["derived_products"] = None

    spatial_present_rows = psql(
        "SELECT to_regclass('v3_spatial.current_spatial_generation')::text",
        db_user,
        db_name,
    )
    spatial_present = bool(spatial_present_rows and spatial_present_rows[0][0])
    if not spatial_present:
        receipt["spatial"] = {"present": False}
    else:
        spatial_pointer_rows = psql(
            "SELECT g.spatial_generation_id::text, g.canonical_generation_id::text, "
            "g.pyramid_version, g.lifecycle_state, p.publication_sequence::text, "
            "p.published_at::text FROM v3_spatial.current_spatial_generation p "
            "JOIN v3_spatial.spatial_generation g "
            "ON g.spatial_generation_id=p.spatial_generation_id WHERE p.singleton",
            db_user,
            db_name,
        )
        spatial_pointer = (
            {
                "spatial_generation_id": spatial_pointer_rows[0][0],
                "canonical_generation_id": spatial_pointer_rows[0][1],
                "pyramid_version": spatial_pointer_rows[0][2],
                "lifecycle_state": spatial_pointer_rows[0][3],
                "publication_sequence": as_int(spatial_pointer_rows[0][4]),
                "published_at": spatial_pointer_rows[0][5],
            }
            if spatial_pointer_rows
            else None
        )
        spatial_rows = psql(
            "SELECT spatial_generation_id::text, canonical_generation_id::text, "
            "pyramid_version, lifecycle_state, expected_systems::text, created_at::text, "
            "validated_at::text, published_at::text, failed_at::text, LEFT(failure,240) "
            "FROM v3_spatial.spatial_generation ORDER BY created_at",
            db_user,
            db_name,
        )
        receipt["spatial"] = {
            "present": True,
            "current": spatial_pointer,
            "spatial_generations": [
                {
                    "spatial_generation_id": row[0],
                    "canonical_generation_id": row[1],
                    "pyramid_version": row[2],
                    "lifecycle_state": row[3],
                    "expected_systems": as_int(row[4]),
                    "created_at": row[5],
                    "validated_at": as_optional(row[6]),
                    "published_at": as_optional(row[7]),
                    "failed_at": as_optional(row[8]),
                    "failure": as_optional(row[9]),
                }
                for row in spatial_rows
            ],
        }

    current_pointers_recorded = True
    finder_products = {"system_search": None, "system_archetype": None}
    if receipt["derived"] is not None and receipt["derived_products"] is not None:
        current_id = receipt["derived"]["derived_generation_id"]
        for product in receipt["derived_products"]:
            code = product["product_code"]
            if product["derived_generation_id"] == current_id and code in finder_products:
                finder_products[code] = product["lifecycle_state"]
    receipt["finder_products_on_published_generation"] = finder_products
except RuntimeError as exc:
    failures.append("read_only_query_failed")
    receipt["query_error"] = str(exc)[:240]

receipt["migration_apply_preconditions"] = {
    "all_named_workers_stopped": all_named_workers_stopped,
    "current_pointers_recorded": current_pointers_recorded,
    "ready_for_governed_plan": all_named_workers_stopped and current_pointers_recorded,
}
receipt["failures"] = sorted(set(failures))
receipt["status"] = "success" if not failures else "stopped"
print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
sys.exit(0 if not failures else 1)
PY
