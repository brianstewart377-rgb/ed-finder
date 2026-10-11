#!/usr/bin/env bash
# Reports a read-only inventory of the production PostgreSQL data volume.
set -euo pipefail

if command -v python3.14 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.14)"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-disk-inventory","status":"stopped","failures":["python3_unavailable"],"read_only":true,"direct_db_access_performed":false,"db_writes_performed":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false}'
    exit 1
fi
if ! "$PYTHON_BIN" -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 14) else 1)'; then
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-disk-inventory","status":"stopped","failures":["python314_required"],"read_only":true,"direct_db_access_performed":false,"db_writes_performed":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false}'
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
DIRECTORY_USAGE_TIMEOUT_SECONDS = 300
MOUNT_INSPECT_FORMAT = "{{range .Mounts}}{{.Source}}\t{{.Destination}}\n{{end}}"


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


def parse_du(stdout: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            raise RuntimeError("directory_usage_output_invalid")
        rows.append(
            {
                "path": parts[1],
                "bytes": required_int(parts[0], "directory_usage_output_invalid"),
            }
        )
    return rows


def exclusive_usage(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Turn nested `du` totals into a non-overlapping partition.

    `du --max-depth=N` reports a cumulative total for every directory at depth <= N,
    so `/var`, `/var/lib` and `/var/lib/docker` all count the same bytes. Ranking those
    rows directly makes the ancestors of the largest subtree the top answers, which says
    nothing about where the bytes are. Each reported directory's exclusive size is its
    own total minus the totals of its reported children; the deepest reported rows keep
    their full total because nothing below them was measured separately. The exclusive
    sizes sum to the scanned root's total exactly once.
    """
    totals = {row["path"].rstrip("/") or "/": row["bytes"] for row in rows}
    child_bytes: dict[str, int] = {}
    for path, size in totals.items():
        if path == "/":
            continue
        parent = path.rsplit("/", 1)[0] or "/"
        if parent in totals:
            child_bytes[parent] = child_bytes.get(parent, 0) + size
    return {path: size - child_bytes.get(path, 0) for path, size in totals.items()}


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


def postgres_mount() -> tuple[str, str]:
    result = run(["docker", "inspect", "-f", MOUNT_INSPECT_FORMAT, POSTGRES_CONTAINER])
    if result.returncode != 0:
        raise RuntimeError("postgres_mount_inspection_failed")
    exact: tuple[str, str] | None = None
    fallback: tuple[str, str] | None = None
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise RuntimeError("postgres_mount_output_invalid")
        source, destination = parts
        if destination == "/var/lib/postgresql/data":
            exact = (source, destination)
            break
        if destination.startswith("/var/lib/postgresql") and fallback is None:
            fallback = (source, destination)
    mount = exact or fallback
    if mount is None:
        raise RuntimeError("postgres_data_mount_unresolved")
    return mount


def section_failed(
    failures: list[str], inventory: dict[str, Any], section: str, exc: RuntimeError
) -> None:
    failures.append("read_only_query_failed")
    inventory[section] = {f"{section}_failed": str(exc)[:240]}


receipt: dict[str, Any] = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "v3-disk-inventory",
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
inventory: dict[str, Any] = {}
receipt["inventory"] = inventory

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

mount_source: str | None = None
usage_full: list[dict[str, Any]] | None = None
postgres_data_directory_bytes: int | None = None
try:
    mount_source, mount_destination = postgres_mount()
    disk = df_values(
        ["df", "-B1", "--output=source,fstype,size,used,avail", mount_source],
        ("filesystem", "filesystem_type", "size_bytes", "used_bytes", "avail_bytes"),
    )
    inventory["volume"] = {
        "mount_source": mount_source,
        "mount_destination": mount_destination,
        "filesystem": disk["filesystem"],
        "size_bytes": disk["size_bytes"],
        "used_bytes": disk["used_bytes"],
        "avail_bytes": disk["avail_bytes"],
    }
except RuntimeError as exc:
    section_failed(failures, inventory, "volume", exc)

try:
    inventory["root_filesystem"] = df_values(
        ["df", "-B1", "--output=size,used,avail", "/"],
        ("size_bytes", "used_bytes", "avail_bytes"),
    )
except RuntimeError as exc:
    section_failed(failures, inventory, "root_filesystem", exc)

try:
    if mount_source is None:
        raise RuntimeError("postgres_data_mount_unresolved")
    # `df` measures the whole filesystem, so `du` must scan the whole filesystem too.
    # The PostgreSQL data directory is a Docker volume subdirectory of the same
    # device, so scanning only that subdirectory would hide every sibling consumer
    # (Docker layers, logs, backups) — exactly the unaccounted usage this action
    # exists to locate. Resolve the mount point and scan from there, staying on the
    # one filesystem with `-x`.
    target_result = run(["df", "--output=target", mount_source])
    if target_result.returncode != 0:
        raise RuntimeError("directory_usage_mount_point_unresolved")
    target_lines = [line.strip() for line in target_result.stdout.splitlines() if line.strip()]
    if len(target_lines) < 2 or not target_lines[1].startswith("/"):
        raise RuntimeError("directory_usage_mount_point_unresolved")
    usage_root = target_lines[1]
    inventory["volume_directory_usage_root"] = usage_root
    usage_result = run(
        ["du", "-x", "-B1", "--max-depth=2", usage_root],
        timeout=DIRECTORY_USAGE_TIMEOUT_SECONDS,
    )
    if usage_result.returncode != 0:
        detail = (usage_result.stderr or usage_result.stdout).strip().splitlines()
        reason = detail[-1][:240] if detail else f"exit_{usage_result.returncode}"
        # Fail closed: without this evidence the receipt cannot answer its own
        # question, so it must not be presented as a complete inventory.
        raise RuntimeError(f"directory_usage_failed:{reason}")
    else:
        usage_full = parse_du(usage_result.stdout)
        inventory["volume_directory_usage"] = sorted(
            usage_full, key=lambda item: (-item["bytes"], item["path"])
        )[:40]
except RuntimeError as exc:
    section_failed(failures, inventory, "volume_directory_usage", exc)

try:
    if mount_source is None:
        raise RuntimeError("postgres_data_mount_unresolved")
    # The accounted PostgreSQL bytes have to be subtracted from the filesystem scan
    # above, and the only figure that is consistent with that scan is the data
    # directory's own on-disk size — not the sum of `pg_database_size`, which counts
    # logical relation bytes and would leave a residue in the partition. Depth 1 also
    # answers the operator's question directly by splitting base/ from pg_wal and logs.
    data_usage_result = run(
        ["du", "-x", "-B1", "--max-depth=1", mount_source.rstrip("/")],
        timeout=DIRECTORY_USAGE_TIMEOUT_SECONDS,
    )
    if data_usage_result.returncode != 0:
        detail = (data_usage_result.stderr or data_usage_result.stdout).strip().splitlines()
        reason = detail[-1][:240] if detail else f"exit_{data_usage_result.returncode}"
        raise RuntimeError(f"postgres_data_directory_usage_failed:{reason}")
    data_usage = parse_du(data_usage_result.stdout)
    data_dir_key = mount_source.rstrip("/")
    total_row = next((row for row in data_usage if row["path"] == data_dir_key), None)
    if total_row is None:
        raise RuntimeError("postgres_data_directory_usage_total_missing")
    postgres_data_directory_bytes = total_row["bytes"]
    inventory["postgres_data_directory_usage"] = {
        "path": data_dir_key,
        "bytes": postgres_data_directory_bytes,
        "children": sorted(
            (row for row in data_usage if row["path"] != data_dir_key),
            key=lambda item: (-item["bytes"], item["path"]),
        )[:40],
    }
except RuntimeError as exc:
    section_failed(failures, inventory, "postgres_data_directory_usage", exc)

try:
    inventory["databases"] = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT datname, pg_database_size(datname)::bigint AS size_bytes, "
        "datistemplate, datallowconn FROM pg_database "
        "ORDER BY pg_database_size(datname) DESC, datname) q",
        db_user,
        db_name,
    )
except RuntimeError as exc:
    section_failed(failures, inventory, "databases", exc)

try:
    wal_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT count(*)::bigint AS segments, sum(size)::bigint AS bytes "
        "FROM pg_ls_waldir()) q",
        db_user,
        db_name,
    )
    settings_rows = psql_json(
        "SELECT row_to_json(q)::text FROM (SELECT "
        "current_setting('max_wal_size') AS max_wal_size, "
        "current_setting('min_wal_size') AS min_wal_size, "
        "current_setting('wal_keep_size') AS wal_keep_size, "
        "current_setting('archive_mode') AS archive_mode) q",
        db_user,
        db_name,
    )
    slots = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT slot_name, active, wal_status, safe_wal_size, "
        "restart_lsn::text AS restart_lsn FROM pg_replication_slots "
        "ORDER BY slot_name) q",
        db_user,
        db_name,
    )
    prepared_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT count(*)::bigint AS prepared_transactions FROM pg_prepared_xacts) q",
        db_user,
        db_name,
    )
    if len(wal_rows) != 1 or len(settings_rows) != 1 or len(prepared_rows) != 1:
        raise RuntimeError("wal_query_output_invalid")
    inventory["wal"] = {
        **wal_rows[0],
        "settings": settings_rows[0],
        "replication_slots": slots,
        "prepared_transactions": prepared_rows[0]["prepared_transactions"],
    }
except RuntimeError as exc:
    section_failed(failures, inventory, "wal", exc)

try:
    tmp_rows = psql_json(
        "SELECT row_to_json(q)::text FROM (SELECT CASE WHEN "
        "COALESCE((pg_stat_file('base/pgsql_tmp',true)).isdir,false) THEN "
        "(SELECT sum(size)::bigint FROM pg_ls_tmpdir()) "
        "ELSE NULL::bigint END AS temp_directory_bytes) q",
        db_user,
        db_name,
    )
    stats_rows = psql_json(
        "SELECT row_to_json(q)::text FROM (SELECT "
        "sum(temp_bytes)::bigint AS temp_bytes, "
        "sum(temp_files)::bigint AS temp_files FROM pg_stat_database) q",
        db_user,
        db_name,
    )
    log_rows = psql_json(
        "SELECT row_to_json(q)::text FROM (SELECT "
        "current_setting('log_directory') AS log_directory, "
        "current_setting('logging_collector') AS logging_collector) q",
        db_user,
        db_name,
    )
    if len(tmp_rows) != 1 or len(stats_rows) != 1 or len(log_rows) != 1:
        raise RuntimeError("temp_and_logs_query_output_invalid")
    inventory["temp_and_logs"] = {**tmp_rows[0], **stats_rows[0], **log_rows[0]}
except RuntimeError as exc:
    section_failed(failures, inventory, "temp_and_logs", exc)

largest_relations_sql = (
    "SELECT c.oid, n.nspname, c.relname FROM pg_class c "
    "JOIN pg_namespace n ON n.oid=c.relnamespace "
    "WHERE c.relkind IN ('r','p','m') "
    "AND n.nspname NOT IN ('pg_catalog','information_schema') "
    "AND n.nspname NOT LIKE 'pg_toast%' "
    "ORDER BY pg_total_relation_size(c.oid) DESC, n.nspname, c.relname LIMIT 20"
)

try:
    inventory["relations"] = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT n.nspname AS schema, c.relname AS name, c.relkind::text AS relkind, "
        "GREATEST(c.reltuples,0)::bigint AS estimated_rows, "
        "pg_table_size(c.oid)::bigint AS table_bytes, "
        "pg_relation_size(c.oid)::bigint AS heap_bytes, "
        "pg_indexes_size(c.oid)::bigint AS index_bytes, "
        # pg_table_size already includes TOAST, and pg_total_relation_size is
        # table + indexes, so subtracting both always yields zero. Read the TOAST
        # footprint from the relation's own toast relation instead.
        "(CASE WHEN c.reltoastrelid <> 0 "
        "THEN pg_total_relation_size(c.reltoastrelid) ELSE 0 END)::bigint AS toast_bytes, "
        "pg_total_relation_size(c.oid)::bigint AS total_bytes "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relkind IN ('r','p','m') "
        "AND n.nspname NOT IN ('pg_catalog','information_schema') "
        "AND n.nspname NOT LIKE 'pg_toast%' "
        "ORDER BY pg_total_relation_size(c.oid) DESC, n.nspname, c.relname LIMIT 80) q",
        db_user,
        db_name,
    )
except RuntimeError as exc:
    section_failed(failures, inventory, "relations", exc)

try:
    inventory["indexes"] = psql_json(
        "SELECT row_to_json(q)::text FROM (WITH largest AS ("
        + largest_relations_sql
        + ") SELECT largest.nspname AS schema, largest.relname AS \"table\", "
        "i.relname AS index_name, pg_relation_size(i.oid)::bigint AS index_bytes, "
        "x.indisunique AS is_unique, x.indisprimary AS is_primary, "
        "s.idx_scan::bigint AS idx_scan, pg_get_indexdef(i.oid) AS definition "
        "FROM largest JOIN pg_index x ON x.indrelid=largest.oid "
        "JOIN pg_class i ON i.oid=x.indexrelid "
        "LEFT JOIN pg_stat_user_indexes s ON s.indexrelid=i.oid "
        "ORDER BY pg_relation_size(i.oid) DESC, largest.nspname, "
        "largest.relname, i.relname) q",
        db_user,
        db_name,
    )
except RuntimeError as exc:
    section_failed(failures, inventory, "indexes", exc)

try:
    # idx_scan is cumulative since the statistics were last reset, so a receipt
    # that reports scan counts without the window invites reading a recently
    # reset counter as "never used". Report the window alongside it.
    stats_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT stats_reset::text AS stats_reset, "
        "(now() - COALESCE(stats_reset, now()))::text AS window_age, "
        "(stats_reset IS NULL) AS stats_never_reset "
        "FROM pg_stat_database WHERE datname = current_database()) q",
        db_user,
        db_name,
    )
    inventory["index_statistics_window"] = stats_rows[0] if stats_rows else {
        "stats_reset": None,
        "stats_never_reset": None,
    }
except RuntimeError as exc:
    section_failed(failures, inventory, "index_statistics_window", exc)

try:
    inventory["dead_tuples"] = psql_json(
        "SELECT row_to_json(q)::text FROM (WITH largest AS ("
        + largest_relations_sql
        + ") SELECT largest.nspname AS schema, largest.relname AS name, "
        "s.n_live_tup::bigint AS n_live_tup, s.n_dead_tup::bigint AS n_dead_tup, "
        "s.last_vacuum::text AS last_vacuum, "
        "s.last_autovacuum::text AS last_autovacuum, "
        "s.last_analyze::text AS last_analyze, "
        "round(s.n_dead_tup::numeric / "
        "NULLIF(s.n_live_tup + s.n_dead_tup,0),4) AS estimated_dead_fraction "
        "FROM largest JOIN pg_stat_user_tables s ON s.relid=largest.oid "
        "ORDER BY pg_total_relation_size(largest.oid) DESC, "
        "largest.nspname, largest.relname) q",
        db_user,
        db_name,
    )
except RuntimeError as exc:
    section_failed(failures, inventory, "dead_tuples", exc)

try:
    ratings_attribution_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT g.generation_key, count(*)::bigint::text AS chunks, "
        "sum(c.systems)::bigint::text AS systems, "
        "sum(c.physical_bodies)::bigint::text AS physical_bodies, "
        "sum(c.eligible_opportunities)::bigint::text AS eligible_opportunities "
        "FROM v3_derived.build_chunk c "
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
        archetype_receipts_present = (
            as_optional(receipt_table_rows[0][1]) is not None
        )
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
    ratings_body_counts: dict[str, tuple[int, int]] = {}
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
            if product == "ratings":
                ratings_body_counts[generation_key] = (
                    required_int(
                        row.get("physical_bodies"), "chunk_receipt_output_invalid"
                    ),
                    required_int(
                        row.get("eligible_opportunities"),
                        "chunk_receipt_output_invalid",
                    ),
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
        ratings_counts = ratings_body_counts.get(generation_key)
        generation_attribution["ratings_physical_bodies"] = (
            ratings_counts[0] if ratings_counts is not None else 0
        )
        generation_attribution["ratings_eligible_opportunities"] = (
            ratings_counts[1] if ratings_counts is not None else 0
        )
        rows_by_generation[generation_key] = generation_attribution
    inventory["generation_attribution"] = rows_by_generation
except RuntimeError as exc:
    section_failed(failures, inventory, "generation_attribution", exc)

try:
    volume_used = inventory["volume"]["used_bytes"]
    database_rows = inventory["databases"]
    operating_database_bytes = next(
        row["size_bytes"] for row in database_rows if row["datname"] == db_name
    )
    other_databases_bytes = sum(
        row["size_bytes"] for row in database_rows if row["datname"] != db_name
    )
    wal_bytes = inventory["wal"]["bytes"] or 0
    temp_bytes = inventory["temp_and_logs"]["temp_directory_bytes"] or 0
    accounted_bytes = (
        operating_database_bytes + other_databases_bytes + wal_bytes + temp_bytes
    )
    if usage_full is None:
        raise RuntimeError("volume_directory_usage_unavailable")
    if postgres_data_directory_bytes is None:
        raise RuntimeError("postgres_data_directory_usage_unavailable")
    data_dir = mount_source.rstrip("/")
    exclusive = exclusive_usage(usage_full)
    # The PostgreSQL data directory is deeper than the filesystem scan's depth on this
    # layout, so its bytes sit inside the exclusive remainder of its deepest reported
    # ancestor (for example /var/lib when the volume is under /var/lib/docker). Subtract
    # the measured data-directory size there, so the database is counted once — as the
    # database — and never again as an ancestor directory. If the data directory is
    # itself a reported row, the exclusive arithmetic has already removed it from its
    # parent and the row is dropped below, so no subtraction is needed.
    strict_ancestors = [
        path
        for path in exclusive
        if path != data_dir and data_dir.startswith("/" if path == "/" else f"{path}/")
    ]
    if data_dir not in exclusive and strict_ancestors:
        container = max(strict_ancestors, key=len)
        exclusive[container] -= postgres_data_directory_bytes
    candidates = sorted(
        (
            {"path": path, "exclusive_bytes": size}
            for path, size in exclusive.items()
            if path != data_dir
            and not path.startswith(f"{data_dir}/")
            and size > 0
        ),
        key=lambda item: (-item["exclusive_bytes"], item["path"]),
    )
    inventory["summary"] = {
        "volume_used_bytes": volume_used,
        "operating_database_bytes": operating_database_bytes,
        "other_databases_bytes": other_databases_bytes,
        "wal_bytes": wal_bytes,
        "accounted_bytes": accounted_bytes,
        "unaccounted_bytes": volume_used - accounted_bytes,
        "postgres_data_directory_bytes": postgres_data_directory_bytes,
        "non_database_directory_bytes": sum(
            item["exclusive_bytes"] for item in candidates
        ),
        "largest_unaccounted_directories": candidates[:10],
        "method": (
            "accounted_bytes = operating_database_bytes + other_databases_bytes + "
            "wal_bytes + current PostgreSQL temporary-directory bytes; "
            "unaccounted_bytes = volume_used_bytes - accounted_bytes. "
            "largest_unaccounted_directories is a non-overlapping partition: each row "
            "reports its own total minus the totals of its scanned children, the "
            "measured PostgreSQL data-directory size is subtracted from the deepest "
            "scanned directory that contains it, and the data directory and everything "
            "under it are excluded. No row therefore counts the database, and no row "
            "counts another row's bytes. The du scan covers the whole filesystem that "
            "holds the data directory, not only the PostgreSQL volume subdirectory"
        ),
    }
except (KeyError, StopIteration, TypeError, RuntimeError) as exc:
    section_failed(failures, inventory, "summary", RuntimeError(str(exc)))

receipt["failures"] = sorted(set(failures))
receipt["status"] = "success" if not failures else "stopped"
print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
sys.exit(0 if not failures else 1)
PY
