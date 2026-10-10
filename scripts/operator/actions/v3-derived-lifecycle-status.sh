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
MOUNT_INSPECT_FORMAT = (
    "{{range .Mounts}}{{.Source}}\t{{.Destination}}\n{{end}}"
)
FOOTPRINT_RELATIONS = (
    "system_rating_vector",
    "body_mechanics",
    "economy_opportunity",
    "system_search",
    "system_archetype",
    "system_archetype_summary",
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


def psql_json(
    sql: str,
    db_user: str,
    db_name: str,
    *,
    timeout: int = PROCESS_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    rows = psql(sql, db_user, db_name, timeout=timeout)
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if len(row) != 1:
            raise RuntimeError("json_query_output_invalid")
        try:
            value = json.loads(row[0])
        except json.JSONDecodeError as exc:
            raise RuntimeError("json_query_output_invalid") from exc
        if not isinstance(value, dict):
            raise RuntimeError("json_query_output_invalid")
        parsed.append(value)
    return parsed


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


def required_int(value: str | None, error: str) -> int:
    number = as_int(value)
    if number is None:
        raise RuntimeError(error)
    return number


def df_values(argv: list[str], columns: tuple[str, ...]) -> dict[str, Any]:
    result = run(argv)
    if result.returncode != 0:
        raise RuntimeError("disk_usage_command_failed")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        raise RuntimeError("disk_usage_output_missing")
    values = lines[-1].split()
    if len(values) != len(columns):
        raise RuntimeError("disk_usage_output_invalid")
    parsed: dict[str, Any] = {}
    for column, value in zip(columns, values, strict=True):
        if column.endswith("_bytes"):
            parsed[column] = required_int(value, "disk_usage_output_invalid")
        else:
            parsed[column] = value
    return parsed


def inspect_worker(name: str) -> dict[str, Any]:
    result = run(["docker", "inspect", "-f", WORKER_INSPECT_FORMAT, name])
    if result.returncode != 0:
        stderr = result.stderr or ""
        if "No such object" not in stderr and "No such container" not in stderr:
            detail = stderr.strip().splitlines()
            inspect_error = detail[-1][:240] if detail else f"exit_{result.returncode}"
            return {
                "name": name,
                "exists": None,
                "running": None,
                "status": None,
                "exit_code": None,
                "finished_at": None,
                "inspect_error": inspect_error,
            }
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
unknown_worker_state = any(worker["running"] is None for worker in workers)
all_named_workers_stopped = all(
    worker["exists"] is False or worker["running"] is False for worker in workers
)
if unknown_worker_state:
    failures.append("worker_state_unknown")
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

    migration_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT migration_name, encode(migration_sha256,'hex') AS migration_sha256_hex, "
        "applied_at::text AS applied_at FROM v3_meta.schema_migration "
        "ORDER BY applied_at, migration_name) q",
        db_user,
        db_name,
    )
    receipt["schema_migrations"] = migration_rows
    applied_migrations = {row["migration_name"] for row in migration_rows}
    receipt["finder_migrations_applied"] = {
        name: name in applied_migrations for name in FINDER_MIGRATIONS
    }

    canonical_pointer_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT g.generation_id::text AS generation_id, g.generation_key, "
        "g.relation_schema, g.lifecycle_state, "
        "p.publication_sequence::text AS publication_sequence, "
        "p.published_at::text AS published_at "
        "FROM v3_meta.current_canonical_generation p "
        "JOIN v3_meta.canonical_generation g ON g.generation_id=p.generation_id "
        "WHERE p.singleton) q",
        db_user,
        db_name,
    )
    receipt["canonical"] = (
        {
            **canonical_pointer_rows[0],
            "publication_sequence": as_int(
                canonical_pointer_rows[0]["publication_sequence"]
            ),
        }
        if canonical_pointer_rows
        else None
    )

    canonical_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT generation_id::text AS generation_id, generation_key, lifecycle_state, "
        "created_at::text AS created_at, published_at::text AS published_at, "
        "retired_at::text AS retired_at, failed_at::text AS failed_at, "
        "LEFT(failure_reason,240) AS failure_reason "
        "FROM v3_meta.canonical_generation ORDER BY created_at) q",
        db_user,
        db_name,
    )
    receipt["canonical_generations"] = canonical_rows

    derived_pointer_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT g.derived_generation_id::text AS derived_generation_id, "
        "g.generation_key, g.lifecycle_state, "
        "g.canonical_generation_id::text AS canonical_generation_id, "
        "p.publication_sequence::text AS publication_sequence, "
        "p.published_at::text AS published_at FROM v3_meta.current_derived_generation p "
        "JOIN v3_meta.derived_generation g "
        "ON g.derived_generation_id=p.derived_generation_id WHERE p.singleton) q",
        db_user,
        db_name,
    )
    receipt["derived"] = (
        {
            **derived_pointer_rows[0],
            "publication_sequence": as_int(
                derived_pointer_rows[0]["publication_sequence"]
            ),
        }
        if derived_pointer_rows
        else None
    )

    derived_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT derived_generation_id::text AS derived_generation_id, generation_key, "
        "canonical_generation_id::text AS canonical_generation_id, "
        "canonical_publication_sequence::text AS canonical_publication_sequence, "
        "mechanics_version, scorer_version, adapter_version, lifecycle_state, "
        "expected_systems::text AS expected_systems, "
        "expected_bodies::text AS expected_bodies, created_at::text AS created_at, "
        "validated_at::text AS validated_at, published_at::text AS published_at, "
        "failed_at::text AS failed_at, LEFT(failure,240) AS failure "
        "FROM v3_meta.derived_generation ORDER BY created_at) q",
        db_user,
        db_name,
    )
    receipt["derived_generations"] = [
        {
            **row,
            "canonical_publication_sequence": as_int(
                row["canonical_publication_sequence"]
            ),
            "expected_systems": as_int(row["expected_systems"]),
            "expected_bodies": as_int(row["expected_bodies"]),
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
        product_rows = psql_json(
            "SELECT row_to_json(q)::text FROM ("
            "SELECT p.derived_generation_id::text AS derived_generation_id, "
            "g.generation_key, p.product_code, "
            "p.product_version, p.lifecycle_state, p.expected_rows::text, "
            "p.created_at::text AS created_at, p.validated_at::text AS validated_at, "
            "p.failed_at::text AS failed_at, LEFT(p.failure,240) AS failure, "
            "CASE WHEN p.validation_sha256 IS NULL THEN NULL "
            "ELSE encode(p.validation_sha256,'hex') END AS validation_sha256_hex "
            "FROM v3_meta.derived_product p JOIN v3_meta.derived_generation g "
            "ON g.derived_generation_id=p.derived_generation_id "
            "ORDER BY g.created_at, p.product_code) q",
            db_user,
            db_name,
        )
        receipt["derived_products"] = [
            {
                **row,
                "expected_rows": as_int(row["expected_rows"]),
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
        spatial_pointer_rows = psql_json(
            "SELECT row_to_json(q)::text FROM ("
            "SELECT g.spatial_generation_id::text AS spatial_generation_id, "
            "g.canonical_generation_id::text AS canonical_generation_id, "
            "g.pyramid_version, g.lifecycle_state, "
            "p.publication_sequence::text AS publication_sequence, "
            "p.published_at::text AS published_at "
            "FROM v3_spatial.current_spatial_generation p "
            "JOIN v3_spatial.spatial_generation g "
            "ON g.spatial_generation_id=p.spatial_generation_id WHERE p.singleton) q",
            db_user,
            db_name,
        )
        spatial_pointer = (
            {
                **spatial_pointer_rows[0],
                "publication_sequence": as_int(
                    spatial_pointer_rows[0]["publication_sequence"]
                ),
            }
            if spatial_pointer_rows
            else None
        )
        spatial_rows = psql_json(
            "SELECT row_to_json(q)::text FROM ("
            "SELECT spatial_generation_id::text AS spatial_generation_id, "
            "canonical_generation_id::text AS canonical_generation_id, "
            "pyramid_version, lifecycle_state, expected_systems::text, created_at::text, "
            "validated_at::text AS validated_at, published_at::text AS published_at, "
            "failed_at::text AS failed_at, LEFT(failure,240) AS failure "
            "FROM v3_spatial.spatial_generation ORDER BY created_at) q",
            db_user,
            db_name,
        )
        receipt["spatial"] = {
            "present": True,
            "current": spatial_pointer,
            "spatial_generations": [
                {
                    **row,
                    "expected_systems": as_int(row["expected_systems"]),
                }
                for row in spatial_rows
            ],
        }

    current_pointers_recorded = (
        receipt["canonical"] is not None
        and receipt["derived"] is not None
        and (not spatial_present or receipt["spatial"]["current"] is not None)
    )
    if not current_pointers_recorded:
        failures.append("current_pointer_missing")
    finder_products = {"system_search": None, "system_archetype": None}
    if receipt["derived"] is not None and receipt["derived_products"] is not None:
        current_id = receipt["derived"]["derived_generation_id"]
        for product in receipt["derived_products"]:
            code = product["product_code"]
            if product["derived_generation_id"] == current_id and code in finder_products:
                finder_products[code] = product["lifecycle_state"]
    receipt["finder_products_on_published_generation"] = finder_products

    database_size_rows = psql(
        "SELECT pg_database_size(current_database())::text",
        db_user,
        db_name,
    )
    if len(database_size_rows) != 1 or len(database_size_rows[0]) != 1:
        raise RuntimeError("database_size_output_invalid")
    footprint: dict[str, Any] = {
        "database_size_bytes": required_int(
            database_size_rows[0][0], "database_size_output_invalid"
        )
    }

    relation_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT n.nspname AS schema, c.relname AS name, "
        "GREATEST(c.reltuples,0)::bigint::text AS estimated_rows, "
        "s.n_live_tup::text AS n_live_tup, "
        "pg_table_size(c.oid)::text AS table_bytes, "
        "pg_indexes_size(c.oid)::text AS index_bytes, "
        "pg_total_relation_size(c.oid)::text AS total_bytes "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid "
        "WHERE c.relkind IN ('r','p') AND "
        "(n.nspname IN ('v3_derived','v3_spatial','v3_meta') "
        "OR left(n.nspname,7)='v3_gen_') "
        "ORDER BY pg_total_relation_size(c.oid) DESC, n.nspname, c.relname) q",
        db_user,
        db_name,
    )
    relations: list[dict[str, Any]] = []
    relation_totals: dict[tuple[str, str], int] = {}
    for row in relation_rows:
        relation = {
            **row,
            "estimated_rows": required_int(
                row.get("estimated_rows"), "relation_size_output_invalid"
            ),
            "n_live_tup": as_int(row.get("n_live_tup")),
            "table_bytes": required_int(
                row.get("table_bytes"), "relation_size_output_invalid"
            ),
            "index_bytes": required_int(
                row.get("index_bytes"), "relation_size_output_invalid"
            ),
            "total_bytes": required_int(
                row.get("total_bytes"), "relation_size_output_invalid"
            ),
        }
        if not relation.get("schema") or not relation.get("name"):
            raise RuntimeError("relation_size_output_invalid")
        relations.append(relation)
        relation_totals[(relation["schema"], relation["name"])] = relation[
            "total_bytes"
        ]
    footprint["relations"] = relations

    index_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT tn.nspname AS schema, t.relname AS name, i.relname AS index_name, "
        "pg_relation_size(i.oid)::text AS index_bytes FROM pg_index x "
        "JOIN pg_class t ON t.oid=x.indrelid "
        "JOIN pg_namespace tn ON tn.oid=t.relnamespace "
        "JOIN pg_class i ON i.oid=x.indexrelid "
        "WHERE tn.nspname='v3_derived' AND t.relname IN "
        "('system_search','system_archetype','system_archetype_summary',"
        "'system_rating_vector','body_mechanics','economy_opportunity') "
        "ORDER BY t.relname, i.relname) q",
        db_user,
        db_name,
    )
    indexes_of_interest: list[dict[str, Any]] = []
    for row in index_rows:
        indexes_of_interest.append(
            {
                **row,
                "index_bytes": required_int(
                    row.get("index_bytes"), "index_size_output_invalid"
                ),
            }
        )
    footprint["indexes_of_interest"] = indexes_of_interest

    ratings_attribution_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT g.generation_key, count(*)::bigint::text AS chunks, "
        "sum(c.systems)::bigint::text AS systems FROM v3_derived.build_chunk c "
        "JOIN v3_meta.derived_generation g "
        "ON g.derived_generation_id=c.derived_generation_id "
        "GROUP BY g.generation_key ORDER BY g.generation_key) q",
        db_user,
        db_name,
    )
    receipt_table_rows = psql(
        "SELECT to_regclass('v3_derived.search_build_chunk')::text, "
        "to_regclass('v3_derived.archetype_build_chunk')::text",
        db_user,
        db_name,
    )
    if not receipt_table_rows:
        # psql renders two NULLs as a tab-only row, which psql() intentionally
        # drops along with other empty output.
        search_receipts_present = False
        archetype_receipts_present = False
    elif len(receipt_table_rows) != 1 or len(receipt_table_rows[0]) != 2:
        raise RuntimeError("chunk_receipt_presence_output_invalid")
    else:
        search_receipts_present = as_optional(receipt_table_rows[0][0]) is not None
        archetype_receipts_present = as_optional(receipt_table_rows[0][1]) is not None
    search_attribution_rows = (
        psql_json(
            "SELECT row_to_json(q)::text FROM ("
            "SELECT g.generation_key, count(*)::bigint::text AS chunks, "
            "sum(c.systems)::bigint::text AS systems "
            "FROM v3_derived.search_build_chunk c "
            "JOIN v3_meta.derived_generation g "
            "ON g.derived_generation_id=c.derived_generation_id "
            "GROUP BY g.generation_key ORDER BY g.generation_key) q",
            db_user,
            db_name,
        )
        if search_receipts_present
        else None
    )
    archetype_attribution_rows = (
        psql_json(
            "SELECT row_to_json(q)::text FROM ("
            "SELECT g.generation_key, count(*)::bigint::text AS chunks, "
            "sum(c.systems)::bigint::text AS systems "
            "FROM v3_derived.archetype_build_chunk c "
            "JOIN v3_meta.derived_generation g "
            "ON g.derived_generation_id=c.derived_generation_id "
            "GROUP BY g.generation_key ORDER BY g.generation_key) q",
            db_user,
            db_name,
        )
        if archetype_receipts_present
        else None
    )
    attribution_rows = {
        "ratings": ratings_attribution_rows,
        "search": search_attribution_rows,
        "archetype": archetype_attribution_rows,
    }
    attribution: dict[str, dict[str, tuple[int, int]]] = {}
    generation_keys: set[str] = set()
    for product, rows in attribution_rows.items():
        if rows is None:
            continue
        product_rows: dict[str, tuple[int, int]] = {}
        for row in rows:
            generation_key = row.get("generation_key")
            if not isinstance(generation_key, str) or not generation_key:
                raise RuntimeError("chunk_receipt_output_invalid")
            product_rows[generation_key] = (
                required_int(row.get("chunks"), "chunk_receipt_output_invalid"),
                required_int(row.get("systems"), "chunk_receipt_output_invalid"),
            )
            generation_keys.add(generation_key)
        attribution[product] = product_rows
    rows_by_generation: dict[str, dict[str, int | None]] = {}
    for generation_key in sorted(generation_keys):
        generation_attribution: dict[str, int | None] = {}
        for product in ("ratings", "search", "archetype"):
            rows = attribution_rows[product]
            values = attribution.get(product, {}).get(generation_key)
            generation_attribution[f"{product}_chunks"] = (
                None if rows is None else values[0] if values is not None else 0
            )
            generation_attribution[f"{product}_systems"] = (
                None if rows is None else values[1] if values is not None else 0
            )
        rows_by_generation[generation_key] = generation_attribution
    footprint["rows_by_generation"] = rows_by_generation

    mount_result = run(
        ["docker", "inspect", "-f", MOUNT_INSPECT_FORMAT, POSTGRES_CONTAINER]
    )
    if mount_result.returncode != 0:
        raise RuntimeError("postgres_mount_inspection_failed")
    postgres_mount: tuple[str, str] | None = None
    fallback_mount: tuple[str, str] | None = None
    for line in mount_result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise RuntimeError("postgres_mount_output_invalid")
        source, destination = parts
        if destination == "/var/lib/postgresql/data":
            postgres_mount = (source, destination)
            break
        if destination.startswith("/var/lib/postgresql") and fallback_mount is None:
            fallback_mount = (source, destination)
    postgres_mount = postgres_mount or fallback_mount
    if postgres_mount is None:
        footprint["host_disk"] = {"mount_found": False}
    else:
        source, destination = postgres_mount
        host_disk = df_values(
            [
                "df",
                "-B1",
                "--output=source,fstype,size,used,avail",
                source,
            ],
            (
                "filesystem",
                "filesystem_type",
                "size_bytes",
                "used_bytes",
                "avail_bytes",
            ),
        )
        footprint["host_disk"] = {
            "mount_source": source,
            "mount_destination": destination,
            "filesystem": host_disk["filesystem"],
            "size_bytes": host_disk["size_bytes"],
            "used_bytes": host_disk["used_bytes"],
            "avail_bytes": host_disk["avail_bytes"],
        }
    footprint["root_filesystem"] = df_values(
        ["df", "-B1", "--output=size,used,avail", "/"],
        ("size_bytes", "used_bytes", "avail_bytes"),
    )

    product_for_relation = {
        "system_rating_vector": "ratings",
        "body_mechanics": "ratings",
        "economy_opportunity": "ratings",
        "system_search": "search",
        "system_archetype": "archetype",
        "system_archetype_summary": "archetype",
    }
    expected_systems_by_generation = {
        generation["generation_key"]: generation["expected_systems"]
        for generation in receipt["derived_generations"]
    }
    measured_footprint_attribution: dict[str, Any] = {
        "note": (
            "proportional attribution by chunk-receipt system counts; "
            "partial generations are flagged"
        )
    }
    for relation_name in FOOTPRINT_RELATIONS:
        total_bytes = relation_totals.get(("v3_derived", relation_name))
        product = product_for_relation[relation_name]
        product_attribution = attribution.get(product, {})
        total_systems = sum(systems for _, systems in product_attribution.values())
        generation_attribution: dict[str, dict[str, Any]] = {}
        for generation_key, (_, systems) in sorted(product_attribution.items()):
            expected_systems = expected_systems_by_generation.get(generation_key)
            generation_attribution[generation_key] = {
                "attributed_bytes": (
                    (total_bytes * systems + total_systems // 2) // total_systems
                    if total_bytes is not None and total_systems > 0
                    else None
                ),
                "share": systems / total_systems if total_systems > 0 else None,
                "generation_complete": (
                    expected_systems is not None and systems == expected_systems
                ),
            }
        measured_footprint_attribution[relation_name] = {
            "table_total_bytes": total_bytes,
            "receipt_product": product,
            "generations": generation_attribution,
        }
    footprint["measured_footprint_attribution"] = measured_footprint_attribution
    footprint["planned_relations_not_measurable_here"] = [
        "v3_derived.system_search (post-010 row width)",
        "v3_derived.system_archetype",
        "v3_derived.system_archetype_summary",
    ]
    footprint["planned_relations_not_measurable_here_note"] = (
        "size these on a disposable PostgreSQL 18 sample and extrapolate; see "
        "docs/operations/v3-finder-production-rollout-state.md"
    )
    receipt["footprint"] = footprint
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
