#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-derived-data-status","status":"stopped","failures":["python3_unavailable"],"read_only":true,"direct_db_access_performed":false,"db_writes_performed":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false}'
    exit 1
fi

exec python3 - <<'PY'
from __future__ import annotations

import json
import socket
import subprocess
import sys
from typing import Any

EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"
DB_USER = "edfinder"
DB_NAME = "edfinder"
STATEMENT_TIMEOUT_MS = 20_000
PROCESS_TIMEOUT_SECONDS = 30

RELATIONS = (
    "systems",
    "bodies",
    "ratings",
    "grid_cells",
    "macro_grid",
    "cluster_summary",
    "system_slot_topology",
    "system_archetype_scores",
    "system_archetype_traits",
    "system_regional_analysis",
    "mv_archetype_rankings",
    "mv_map_regions",
    "mv_map_heatmap_200ly",
    "mv_map_heatmap_500ly",
    "mv_map_heatmap_1000ly",
    "mv_map_timeline_month",
)


def run(argv: list[str], *, timeout: int = PROCESS_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 125, "", type(exc).__name__)


def psql(sql: str, *, timeout: int = PROCESS_TIMEOUT_SECONDS) -> list[list[str]]:
    # Every statement is hard-coded in this file. The explicit READ ONLY
    # transaction is a second safety boundary on top of the operator workflow.
    wrapped = (
        "BEGIN READ ONLY; "
        f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms'; "
        + sql.rstrip().rstrip(";")
        + "; COMMIT;"
    )
    result = run(
        [
            "docker", "exec", POSTGRES_CONTAINER,
            "psql", "-X", "-qAt", "-F", "\t", "-v", "ON_ERROR_STOP=1",
            "-U", DB_USER, "-d", DB_NAME, "-c", wrapped,
        ],
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = detail[-1][:240] if detail else f"exit_{result.returncode}"
        raise RuntimeError(suffix)
    rows: list[list[str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        rows.append(line.split("\t"))
    return rows


def as_int(value: str | None) -> int | None:
    if value in (None, "", "\\N"):
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def as_float(value: str | None) -> float | None:
    if value in (None, "", "\\N"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


receipt: dict[str, Any] = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "v3-derived-data-status",
    "status": "stopped",
    "read_only": True,
    "direct_db_access_performed": False,
    "db_writes_performed": False,
    "env_files_read": False,
    "private_keys_read": False,
    "service_changes_performed": False,
    "filesystem_writes_performed": False,
    "query_policy": {
        "transaction": "READ ONLY",
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        "large_table_strategy": "catalog estimates plus small TABLESAMPLE probes",
    },
}
failures: list[str] = []

host = socket.gethostname().split(".")[0]
fqdn_result = run(["hostname", "-f"])
fqdn = fqdn_result.stdout.strip()
receipt["host"] = {"short": host, "fqdn": fqdn}
if host != EXPECTED_HOST or fqdn_result.returncode != 0 or fqdn != EXPECTED_FQDN:
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

receipt["direct_db_access_performed"] = True

try:
    version_rows = psql(
        "SELECT current_setting('server_version'), current_setting('server_version_num'), "
        "pg_size_pretty(pg_database_size(current_database()))"
    )
    if version_rows:
        receipt["postgres"] = {
            "server_version": version_rows[0][0],
            "server_version_num": as_int(version_rows[0][1]),
            "database_size": version_rows[0][2],
        }

    relation_names = ",".join("'%s'" % name.replace("'", "''") for name in RELATIONS)
    relation_rows = psql(
        "SELECT c.relname, c.relkind, GREATEST(c.reltuples,0)::bigint, "
        "pg_total_relation_size(c.oid)::bigint, "
        "CASE WHEN c.relkind='m' THEN COALESCE(pm.ispopulated,false)::text ELSE '' END "
        "FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "LEFT JOIN pg_matviews pm ON pm.schemaname=n.nspname AND pm.matviewname=c.relname "
        "WHERE n.nspname='public' AND c.relname IN (" + relation_names + ") "
        "ORDER BY c.relname"
    )
    relations: dict[str, Any] = {}
    for row in relation_rows:
        relations[row[0]] = {
            "kind": row[1],
            "estimated_rows": as_int(row[2]),
            "total_bytes": as_int(row[3]),
            "is_populated": None if row[4] == "" else row[4] == "true",
        }
    for name in RELATIONS:
        relations.setdefault(name, {"missing": True})
    receipt["relations"] = relations

    stat_rows = psql(
        "SELECT tablename, attname, null_frac::text, n_distinct::text, "
        "COALESCE(most_common_vals::text,''), COALESCE(most_common_freqs::text,'') "
        "FROM pg_stats WHERE schemaname='public' AND ("
        "(tablename='systems' AND attname IN ('grid_cell_id','macro_grid_id','rating_dirty','cluster_dirty','has_body_data')) OR "
        "(tablename='ratings' AND attname='rating_version') OR "
        "(tablename='system_archetype_scores' AND attname='dirty')) "
        "ORDER BY tablename, attname"
    )
    receipt["planner_statistics"] = [
        {
            "table": row[0],
            "column": row[1],
            "null_frac": as_float(row[2]),
            "n_distinct": as_float(row[3]),
            "most_common_vals": row[4] or None,
            "most_common_freqs": row[5] or None,
        }
        for row in stat_rows
    ]

    # Samples are deliberately tiny and are used only to answer whether the
    # post-import derived columns appear substantially populated. They are not
    # accepted as exact integrity evidence.
    system_sample = psql(
        "SELECT COUNT(*)::bigint, "
        "COUNT(*) FILTER (WHERE grid_cell_id IS NOT NULL)::bigint, "
        "COUNT(*) FILTER (WHERE macro_grid_id IS NOT NULL)::bigint, "
        "COUNT(*) FILTER (WHERE has_body_data)::bigint, "
        "COUNT(*) FILTER (WHERE rating_dirty)::bigint, "
        "COUNT(*) FILTER (WHERE cluster_dirty)::bigint "
        "FROM systems TABLESAMPLE SYSTEM (0.01)"
    )
    if system_sample:
        row = system_sample[0]
        receipt["systems_sample"] = {
            "sample_rows": as_int(row[0]),
            "grid_cell_present": as_int(row[1]),
            "macro_grid_present": as_int(row[2]),
            "has_body_data": as_int(row[3]),
            "rating_dirty": as_int(row[4]),
            "cluster_dirty": as_int(row[5]),
            "sample_percent": 0.01,
        }

    ratings_sample = psql(
        "SELECT COUNT(*)::bigint, "
        "COUNT(*) FILTER (WHERE rating_version='3.4')::bigint, "
        "COUNT(*) FILTER (WHERE rating_version IS NULL)::bigint "
        "FROM ratings TABLESAMPLE SYSTEM (0.05)"
    )
    if ratings_sample:
        row = ratings_sample[0]
        receipt["ratings_sample"] = {
            "sample_rows": as_int(row[0]),
            "rating_version_3_4": as_int(row[1]),
            "rating_version_null": as_int(row[2]),
            "sample_percent": 0.05,
        }

    archetype_sample = psql(
        "SELECT COUNT(*)::bigint, COUNT(*) FILTER (WHERE dirty)::bigint "
        "FROM system_archetype_scores TABLESAMPLE SYSTEM (0.1)"
    ) if not relations.get("system_archetype_scores", {}).get("missing") else []
    if archetype_sample:
        receipt["archetype_sample"] = {
            "sample_rows": as_int(archetype_sample[0][0]),
            "dirty": as_int(archetype_sample[0][1]),
            "sample_percent": 0.1,
        }

    app_meta_rows = psql(
        "SELECT key, value, updated_at::text FROM app_meta "
        "WHERE key IN ('last_nightly_update','nightly_update_started_at_epoch','nightly_update_completed_at_epoch') "
        "ORDER BY key"
    )
    receipt["maintenance_markers"] = [
        {"key": row[0], "value": row[1], "updated_at": row[2]}
        for row in app_meta_rows
    ]

    stats_rows = psql(
        "SELECT relname, last_analyze::text, last_autoanalyze::text, last_vacuum::text, last_autovacuum::text "
        "FROM pg_stat_user_tables WHERE relname IN "
        "('systems','bodies','ratings','cluster_summary','system_archetype_scores','system_regional_analysis') "
        "ORDER BY relname"
    )
    receipt["table_maintenance"] = [
        {
            "table": row[0],
            "last_analyze": row[1] or None,
            "last_autoanalyze": row[2] or None,
            "last_vacuum": row[3] or None,
            "last_autovacuum": row[4] or None,
        }
        for row in stats_rows
    ]
except RuntimeError as exc:
    failures.append("read_only_query_failed")
    receipt["query_error"] = str(exc)

receipt["failures"] = sorted(set(failures))
receipt["status"] = "success" if not failures else "stopped"
print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
sys.exit(0 if not failures else 1)
PY
