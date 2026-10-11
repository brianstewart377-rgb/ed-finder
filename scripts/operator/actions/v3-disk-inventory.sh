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
import math
import subprocess
import sys
import time
from typing import Any

EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"
STATEMENT_TIMEOUT_MS = 20000
PROCESS_TIMEOUT_SECONDS = 30
DIRECTORY_USAGE_TIMEOUT_SECONDS = 300
# The data directory is measured either side of the filesystem scan; a live database
# writes while they run, so a small difference is expected and a large one means the
# two scans describe different states and cannot be subtracted from one another.
DIRECTORY_DRIFT_FLOOR_BYTES = 1 << 30  # 1 GiB
DIRECTORY_DRIFT_FRACTION_PPM = 5_000  # 0.5 %
# Stop drilling once the largest child is under this fraction of the volume's used
# bytes: below it the usage is spread rather than owned, and naming one directory would
# mislead. Expressed as a fraction so it scales with the volume instead of being a
# magic size, and so the floor is a stated property of the volume in the receipt.
DRILL_DOWN_FLOOR_PPM = 2_500  # 0.25 % of used bytes
DRILL_DOWN_MAX_STEPS = 8
# Every directory scan shares one wall-clock budget. Individually bounded calls are not
# enough: the operator workflow kills the job at 40 minutes, and four fixed scans plus
# eight drill-down steps at the 300 s per-call limit would be 60 minutes, so a valid but
# slow production inventory could be killed before it emitted any receipt at all. With a
# shared budget the walk stops early and records why, which is a usable receipt.
DIRECTORY_SCAN_BUDGET_SECONDS = 1_500
# Held back from the budget for the closing reconciliation scan, so the walk can never
# consume the budget the reconciliation needs and take the whole section down with it.
# It is the full per-call allowance, not a smaller round number: reserving less would
# leave the mandatory closing scan running against a shortened timeout, which is a
# different way of failing it.
RECONCILE_RESERVE_SECONDS = DIRECTORY_USAGE_TIMEOUT_SECONDS
# A drill-down step starting with barely any budget beyond the reserve would time out
# and fail the section. Below this, stop and record the exhaustion instead.
DRILL_DOWN_MIN_CALL_SECONDS = 30
# PGDATA children whose bytes are already inside accounted_bytes. Everything else under
# PGDATA (global, pg_xact, pg_multixact, log, replication-slot state) is unaccounted and
# must stay visible as a candidate, or the summary cannot reconcile its own figure.
ACCOUNTED_PGDATA_CHILDREN = frozenset(
    {"base", "pg_wal", "pg_xlog", "pg_stat_tmp", "pg_stat", "pgsql_tmp"}
)
# `df` reports filesystem space; `du` estimates space used by files. The difference is
# real (ext4 metadata, reserved blocks, blocks held by deleted-but-open files) and is
# reported rather than hidden, with a flag when it is too large to ignore.
DF_DU_RESIDUAL_SIGNIFICANT_PPM = 20_000  # 2 % of used bytes
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


def host_pgdata(
    mount_source: str, mount_destination: str, db_user: str, db_name: str
) -> tuple[str, str]:
    """Translate the server's own `data_directory` into a host path.

    The mount destination is not PGDATA. The official PostgreSQL 18 image places
    PGDATA at /var/lib/postgresql/18/docker while the volume is commonly mounted at
    /var/lib/postgresql, so scanning the mount root at depth 1 reports only the `18`
    parent and never the base/pg_wal/log breakdown this action is supposed to show.
    Ask the server where its data directory actually is and map it through the mount.
    """
    rows = psql("SELECT current_setting('data_directory')", db_user, db_name)
    if len(rows) != 1 or len(rows[0]) != 1 or not rows[0][0].startswith("/"):
        raise RuntimeError("postgres_data_directory_unresolved")
    container_pgdata = rows[0][0].rstrip("/")
    destination = mount_destination.rstrip("/")
    source = mount_source.rstrip("/")
    if container_pgdata == destination:
        relative = ""
    elif container_pgdata.startswith(f"{destination}/"):
        relative = container_pgdata[len(destination) + 1 :]
    else:
        # PGDATA is not inside the mount we selected, so nothing on this volume is
        # the data directory and the subtraction below would be wrong. Fail closed
        # rather than subtract a size from the wrong subtree.
        raise RuntimeError("postgres_data_directory_outside_mount")
    return (f"{source}/{relative}" if relative else source), container_pgdata


class ScanBudget:
    """One wall-clock budget shared by every directory scan in this run.

    Bounding each `du` call individually is not enough. The operator workflow kills the
    job at 40 minutes, and four fixed scans plus eight drill-down steps at the 300 s
    per-call limit is 60 minutes, so a valid but slow production inventory could be
    killed before emitting any receipt. Each call is given whichever is smaller, the
    per-call limit or what is left, and the walk stops and records why when the budget
    runs out -- a partial receipt that says where it stopped beats no receipt at all.
    """

    def __init__(self, seconds: int) -> None:
        self.total_seconds = seconds
        self._deadline = time.monotonic() + seconds

    def remaining(self) -> float:
        return self._deadline - time.monotonic()

    def call_timeout(self, reserve_seconds: float = 0.0) -> int:
        # The reserve is subtracted from what this call may use. Returning the whole
        # remaining budget would let one scan spend the reserve it was meant to protect.
        left = self.remaining() - reserve_seconds
        if left <= 0:
            raise RuntimeError("directory_scan_budget_exhausted")
        return max(1, min(DIRECTORY_USAGE_TIMEOUT_SECONDS, math.ceil(left)))


def du_rows(
    argv: list[str], budget: ScanBudget, error: str, *, reserve_seconds: float = 0.0
) -> list[dict[str, Any]]:
    result = run(argv, timeout=budget.call_timeout(reserve_seconds))
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        reason = detail[-1][:240] if detail else f"exit_{result.returncode}"
        raise RuntimeError(f"{error}:{reason}")
    return parse_du(result.stdout)


def du_total(path: str, budget: ScanBudget) -> int:
    rows = du_rows(
        ["du", "-x", "-B1", "--max-depth=0", path], budget, "directory_total_failed"
    )
    total = next(
        (row["bytes"] for row in rows if row["path"].rstrip("/") == path.rstrip("/")), None
    )
    if total is None:
        raise RuntimeError("directory_total_missing")
    return total


def drill_down(
    root: str,
    pgdata: str,
    pgdata_bytes: int,
    *,
    floor_bytes: int,
    max_steps: int,
    budget: ScanBudget,
    reserve_seconds: float = 0.0,
) -> list[dict[str, Any]]:
    """Walk from `root` towards the directory that actually owns the non-database bytes.

    A single `du --max-depth=N` cannot do this. GNU `du` shows directories at most N
    levels below the scanned root, so a depth-2 scan from / can emit /var/lib but never
    /var/lib/docker -- every deeper consumer stays collapsed into one aggregate and the
    owning directory is never named. Scanning deep enough to name it from the root would
    emit a row per Docker layer, which is unbounded in output.

    So descend one level at a time instead: list a directory's children, subtract the
    measured data-directory size from whichever child contains it, and step into the
    largest remaining child -- but only when that child is bigger than what the current
    directory holds directly in its own files. A directory with one huge file and one
    modest subdirectory owns its bytes itself, and descending would name the wrong
    owner, so the walk stops and says so.

    The walk also stops when the largest child falls under the floor (the usage is
    spread, not owned) or when the shared scan budget runs out. Each stop records its
    reason, and the chain is the evidence: where it looked, what it saw, what it chose.
    """
    chain: list[dict[str, Any]] = []
    current = root.rstrip("/") or "/"
    for _ in range(max_steps):
        if budget.remaining() - reserve_seconds < DRILL_DOWN_MIN_CALL_SECONDS:
            if chain:
                chain[-1]["stop_reason"] = "scan_budget_exhausted"
            break
        rows = du_rows(
            ["du", "-x", "-B1", "--max-depth=1", current],
            budget,
            "drill_down_failed",
            reserve_seconds=reserve_seconds,
        )
        here = current
        here_total = next(
            (row["bytes"] for row in rows if (row["path"].rstrip("/") or "/") == here), None
        )
        if here_total is None:
            raise RuntimeError("drill_down_total_missing")
        children = []
        child_total = 0
        for row in rows:
            path = row["path"].rstrip("/") or "/"
            if path == here:
                continue
            child_total += row["bytes"]
            contains_pgdata = path == pgdata or pgdata.startswith(f"{path}/")
            children.append(
                {
                    "path": path,
                    "bytes_excluding_database": row["bytes"]
                    - (pgdata_bytes if contains_pgdata else 0),
                    "contains_database": contains_pgdata,
                }
            )
        children.sort(key=lambda item: (-item["bytes_excluding_database"], item["path"]))
        # What this directory holds directly in its own files, which no child reports.
        own_file_bytes = here_total - child_total
        step: dict[str, Any] = {
            "directory": here,
            "own_file_bytes": own_file_bytes,
            "children": children[:10],
            "followed": None,
            "stop_reason": None,
        }
        candidate = next(
            (
                child
                for child in children
                if child["path"] != pgdata
                and not child["path"].startswith(f"{pgdata}/")
                and child["bytes_excluding_database"] >= floor_bytes
            ),
            None,
        )
        if candidate is None:
            step["stop_reason"] = "no_child_above_floor"
            chain.append(step)
            break
        if own_file_bytes > candidate["bytes_excluding_database"]:
            # Descending here would name a smaller child as the owner of bytes this
            # directory holds itself, in its own files.
            step["stop_reason"] = "directory_owns_more_directly_than_any_child"
            chain.append(step)
            break
        step["followed"] = candidate["path"]
        chain.append(step)
        current = candidate["path"]
    else:
        if chain:
            chain[-1]["stop_reason"] = "step_limit_reached"
    return chain

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

scan_budget = ScanBudget(DIRECTORY_SCAN_BUDGET_SECONDS)
mount_source: str | None = None
mount_destination: str | None = None
usage_full: list[dict[str, Any]] | None = None
postgres_data_directory_bytes: int | None = None
pgdata_host: str | None = None
pgdata_before: int | None = None
tolerance: int = 0
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

    pgdata_host, pgdata_container = host_pgdata(
        mount_source, mount_destination, db_user, db_name
    )
    inventory["postgres_data_directory"] = {
        "container_path": pgdata_container,
        "host_path": pgdata_host,
        "mount_destination": mount_destination,
    }

    # Bracket the data-directory measurement around the filesystem scan. The database
    # is live: it extends relations, recycles WAL and writes logs while these commands
    # run. Subtracting a size measured after the scan from a total measured before it
    # would understate the non-database remainder when the database grew (and the
    # `> 0` filter would then silently drop the row) or invent usage when it shrank --
    # in both cases while the receipt still said `success`. Measuring either side of
    # the scan turns that into a detectable, and refusable, inconsistency.
    pgdata_before = du_total(pgdata_host, scan_budget)
    # Fail closed on a failed scan: without this evidence the receipt cannot answer
    # its own question, so it must not be presented as a complete inventory.
    usage_full = du_rows(
        ["du", "-x", "-B1", "--max-depth=2", usage_root],
        scan_budget,
        "directory_usage_failed",
    )
    pgdata_after = du_total(pgdata_host, scan_budget)
    drift = abs(pgdata_after - pgdata_before)
    tolerance = max(
        DIRECTORY_DRIFT_FLOOR_BYTES, pgdata_before * DIRECTORY_DRIFT_FRACTION_PPM // 1_000_000
    )
    inventory["postgres_data_directory_bracket"] = {
        "bytes_before_filesystem_scan": pgdata_before,
        "bytes_after_filesystem_scan": pgdata_after,
        "drift_bytes": pgdata_after - pgdata_before,
        "tolerance_bytes": tolerance,
    }
    if drift > tolerance:
        # The two scans cannot be reconciled, so the partition below would be fiction.
        raise RuntimeError(f"directory_usage_inconsistent:drift_{drift}_over_{tolerance}")
    # Use the larger reading for the subtraction. If the database grew during the scan,
    # the filesystem total already contains part of that growth; subtracting the larger
    # figure understates the non-database remainder rather than inventing usage that
    # does not exist, which is the safe direction for a reclaim decision.
    postgres_data_directory_bytes = max(pgdata_before, pgdata_after)
    inventory["volume_directory_usage"] = sorted(
        usage_full, key=lambda item: (-item["bytes"], item["path"])
    )[:40]

    data_usage = du_rows(
        ["du", "-x", "-B1", "--max-depth=1", pgdata_host],
        scan_budget,
        "postgres_data_directory_usage_failed",
    )
    inventory["postgres_data_directory_usage"] = {
        "path": pgdata_host,
        "bytes": postgres_data_directory_bytes,
        "children": sorted(
            (row for row in data_usage if row["path"].rstrip("/") != pgdata_host),
            key=lambda item: (-item["bytes"], item["path"]),
        )[:40],
    }

    # Name the directory that owns the non-database usage, which a single bounded-depth
    # scan from the root cannot do (see drill_down).
    # The volume section may have failed after the mount resolved, in which case
    # inventory["volume"] is an error object. Stop this section deliberately instead of
    # raising KeyError out of the `except RuntimeError` below, which would scan for
    # minutes and then die with a traceback where a structured stopped receipt belongs.
    volume_section = inventory.get("volume")
    if not isinstance(volume_section, dict) or "used_bytes" not in volume_section:
        raise RuntimeError("volume_measurement_unavailable")
    drill_floor = max(
        1, volume_section["used_bytes"] * DRILL_DOWN_FLOOR_PPM // 1_000_000
    )
    # The walk stops with the reconciliation scan's budget still unspent, so the
    # closing measurement can always run. Without that reserve, a walk that consumed
    # the whole budget would take the reconciliation down with it and lose both the
    # successful filesystem scan and the chain that recorded why it stopped -- which is
    # precisely the partial evidence the budget exists to preserve.
    chain = drill_down(
        usage_root,
        pgdata_host,
        postgres_data_directory_bytes,
        floor_bytes=drill_floor,
        max_steps=DRILL_DOWN_MAX_STEPS,
        budget=scan_budget,
        reserve_seconds=RECONCILE_RESERVE_SECONDS,
    )
    # Record the evidence before anything that can fail. A later failure must not erase
    # a scan that succeeded.
    inventory["non_database_drill_down"] = {
        "floor_bytes": drill_floor,
        "floor_ppm_of_used": DRILL_DOWN_FLOOR_PPM,
        "max_steps": DRILL_DOWN_MAX_STEPS,
        "scan_budget_seconds": scan_budget.total_seconds,
        "reconcile_reserve_seconds": RECONCILE_RESERVE_SECONDS,
        "chain": chain,
    }
except RuntimeError as exc:
    section_failed(failures, inventory, "volume_directory_usage", exc)

try:
    # Close the bracket around the drill-down as well, in a section of its own so that
    # failing to reconcile cannot overwrite the scans above. The earlier bracket proved
    # the data directory was stable across the filesystem scan, but the walk runs up to
    # eight further scans afterwards and compares current ancestor totals against the
    # one fixed data-directory size. If the database grew in between -- a concurrent
    # derived build, say -- that growth is mislabelled as non-database usage and can
    # send the walk down into the PostgreSQL volume; if it shrank, real sibling usage
    # is hidden. Either way the receipt would still have said `success`.
    if pgdata_host is None or pgdata_before is None:
        raise RuntimeError("postgres_data_directory_unresolved")
    bracket = inventory.get("postgres_data_directory_bracket")
    if not isinstance(bracket, dict):
        raise RuntimeError("postgres_data_directory_bracket_unavailable")
    pgdata_final = du_total(pgdata_host, scan_budget)
    span_drift = abs(pgdata_final - pgdata_before)
    bracket["bytes_after_drill_down"] = pgdata_final
    bracket["span_drift_bytes"] = pgdata_final - pgdata_before
    bracket["span_reconciled"] = span_drift <= tolerance
    inventory["postgres_data_directory_reconciliation"] = {
        "span_drift_bytes": pgdata_final - pgdata_before,
        "tolerance_bytes": tolerance,
        "reconciled": span_drift <= tolerance,
    }
    if span_drift > tolerance:
        raise RuntimeError(
            f"directory_usage_inconsistent:span_drift_{span_drift}_over_{tolerance}"
        )
except RuntimeError as exc:
    section_failed(
        failures, inventory, "postgres_data_directory_reconciliation", exc
    )

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
    # This is the DATABASE-wide reset time, and it is not every index's observation
    # window. PostgreSQL supports resetting a single table or index independently
    # (pg_stat_reset_single_table_counters), which zeroes that index's idx_scan without
    # touching pg_stat_database.stats_reset. Presenting the database figure as the
    # index's window would pair a freshly reset index with a months-old age and make a
    # heavily used index look unused -- and an unused index is exactly what someone
    # hunting for reclaimable space would drop. There is no per-index reset timestamp
    # in PostgreSQL, so the honest reading is that an individual index's window is
    # unknown; the receipt says so rather than implying a precision it does not have.
    window = dict(stats_rows[0]) if stats_rows else {
        "stats_reset": None,
        "stats_never_reset": None,
    }
    window["scope"] = "database"
    window["per_index_window_known"] = False
    window["note"] = (
        "stats_reset is pg_stat_database's database-wide value. A single index or table "
        "may have been reset independently with pg_stat_reset_single_table_counters, "
        "which zeroes idx_scan without changing this timestamp, and PostgreSQL records "
        "no per-index reset time. Treat each index's observation window as unknown: a "
        "zero idx_scan is not evidence that an index is unused, and must not on its own "
        "justify dropping one."
    )
    inventory["index_statistics_window"] = window
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
    reconciliation = inventory.get("postgres_data_directory_reconciliation")
    if not isinstance(reconciliation, dict) or reconciliation.get("reconciled") is not True:
        # Unreconciled measurements must not be presented as a partition.
        raise RuntimeError("postgres_data_directory_not_reconciled")
    if pgdata_host is None:
        raise RuntimeError("postgres_data_directory_unresolved")
    data_dir = pgdata_host
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
    outside = [
        {"path": path, "exclusive_bytes": size, "inside_data_directory": False}
        for path, size in exclusive.items()
        if path != data_dir and not path.startswith(f"{data_dir}/") and size > 0
    ]
    # Subtracting the whole data directory removes more than accounted_bytes covers.
    # accounted_bytes is the databases (base/), WAL (pg_wal) and the temp directories;
    # PGDATA also holds `global`, `pg_xact`, `pg_multixact`, replication-slot state and
    # often relative log files. Dropping those with the rest of the data directory left
    # them inside unaccounted_bytes but absent from every candidate, so the candidate
    # list could not reconcile or locate the value it claimed to explain. They are
    # therefore kept as candidates in their own right, flagged so nobody mistakes them
    # for ordinary directories: some of them must never be deleted.
    pgdata_children = inventory["postgres_data_directory_usage"]["children"]
    inside = [
        {
            "path": row["path"],
            "exclusive_bytes": row["bytes"],
            "inside_data_directory": True,
        }
        for row in pgdata_children
        if row["path"].rstrip("/").rsplit("/", 1)[-1] not in ACCOUNTED_PGDATA_CHILDREN
        and row["bytes"] > 0
    ]
    candidates = sorted(
        outside + inside,
        key=lambda item: (-item["exclusive_bytes"], item["path"]),
    )
    # `du` and `df` measure different things, so the partition closes against the du
    # root total, not against df's used bytes. The gap between them is real on ext4 --
    # filesystem metadata, reserved blocks, and blocks still held by deleted-but-open
    # files (a dropped relation or unlinked WAL segment a backend has open) -- and it
    # can be large enough to matter for a reclaim decision. Report it as its own figure
    # so it cannot be mistaken for directory usage, and flag it when it is significant,
    # because space held by deleted-but-open files is reclaimed by ending the holder,
    # not by deleting anything.
    du_root_bytes = next(
        (
            row["bytes"]
            for row in usage_full
            if (row["path"].rstrip("/") or "/") == (usage_root.rstrip("/") or "/")
        ),
        None,
    )
    if du_root_bytes is None:
        raise RuntimeError("directory_usage_root_total_missing")
    residual = volume_used - du_root_bytes
    non_database_directory_bytes = sum(
        item["exclusive_bytes"] for item in candidates if not item["inside_data_directory"]
    )
    unaccounted_inside_data_directory_bytes = sum(
        item["exclusive_bytes"] for item in candidates if item["inside_data_directory"]
    )
    inventory["summary"] = {
        "volume_used_bytes": volume_used,
        "operating_database_bytes": operating_database_bytes,
        "other_databases_bytes": other_databases_bytes,
        "wal_bytes": wal_bytes,
        "accounted_bytes": accounted_bytes,
        "unaccounted_bytes": volume_used - accounted_bytes,
        "postgres_data_directory_bytes": postgres_data_directory_bytes,
        "non_database_directory_bytes": non_database_directory_bytes,
        "unaccounted_inside_data_directory_bytes": unaccounted_inside_data_directory_bytes,
        "directory_scan_root_bytes": du_root_bytes,
        "filesystem_minus_directory_scan_bytes": residual,
        "filesystem_minus_directory_scan_is_significant": (
            abs(residual) > volume_used * DF_DU_RESIDUAL_SIGNIFICANT_PPM // 1_000_000
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
            "counts another row's bytes. Rows outside the data directory sum to "
            "non_database_directory_bytes; rows inside it are the PostgreSQL "
            "directories that accounted_bytes does not cover (global, pg_xact, "
            "pg_multixact, replication-slot state, relative log files) and are flagged "
            "inside_data_directory, because some of them must never be deleted -- they "
            "are listed so the summary can locate every byte it reports as "
            "unaccounted, not as reclaim suggestions. The du scan covers the whole "
            "filesystem that holds the data directory, not only the PostgreSQL volume "
            "subdirectory. filesystem_minus_directory_scan_bytes is volume_used_bytes "
            "minus directory_scan_root_bytes: df reports filesystem space and du "
            "estimates space used by files, so this gap is filesystem metadata, "
            "reserved blocks and blocks held by deleted-but-open files. It is not "
            "directory usage and cannot be reclaimed by deleting a directory. "
            "non_database_drill_down names the directory that owns the non-database "
            "usage, which a single bounded-depth scan from the root cannot do: GNU du "
            "shows directories at most N levels below the scanned root, so a depth-2 "
            "scan from / emits /var/lib but never /var/lib/docker"
        ),
    }
except (KeyError, StopIteration, TypeError, RuntimeError) as exc:
    section_failed(failures, inventory, "summary", RuntimeError(str(exc)))

receipt["failures"] = sorted(set(failures))
receipt["status"] = "success" if not failures else "stopped"
print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
sys.exit(0 if not failures else 1)
PY
