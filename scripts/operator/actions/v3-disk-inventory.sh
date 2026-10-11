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
# -I -B on both interpreters, and -I is the load-bearing one.
#
# -I is ISOLATED mode (it implies -P -s -E). Without it CPython prepends the current
# working directory to sys.path -- verified: sys.path[0] is '' for a program on stdin --
# and the operator workflow runs `cd /opt/ed-finder && bash -s`, escalating to root via
# `sudo -n bash -s` on the non-root path. So a top-level platform.py in that checkout
# would be imported and EXECUTED AS ROOT during the version probe below, before any
# host validation runs, and the main program has the same exposure for every import it
# makes. -B does not address this at all; it only disables bytecode writes, which
# matters for the receipt's read-only claim (importing a module whose cache is missing
# or stale would otherwise write .pyc files as root).
#
# The program imports only the standard library and reads no PYTHON* environment
# variables, so -I's -s and -E cost nothing here.
if ! "$PYTHON_BIN" -I -B -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 14) else 1)'; then
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-disk-inventory","status":"stopped","failures":["python314_required"],"read_only":true,"direct_db_access_performed":false,"db_writes_performed":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false}'
    exit 1
fi

exec "$PYTHON_BIN" -I -B - <<'PY'
from __future__ import annotations

import contextlib
import heapq
import json
import selectors
import math
import os
import signal
import subprocess
import sys
import threading
import time
from typing import Any

EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"
STATEMENT_TIMEOUT_MS = 20000
PROCESS_TIMEOUT_SECONDS = 30
# A hard wall clock for the WHOLE action, from process start.
#
# The per-phase budgets were each bounded but their SUM was not, and the sum is what
# the operator workflow kills: the walk's 1,200 s plus the closing phase's 660 s plus
# up to 31 read-only queries at the 30 s subprocess cap is about 40 minutes on its own,
# against a 40-minute job that also does checkout, Python setup and SSH. So the action
# could be killed before emitting the structured receipt -- the exact outcome every
# budget in this file exists to prevent, reached by a route none of them measured.
#
# Raising the job timeout is not the fix: the `execute` job is shared by every
# allowlisted operation and its 40 minutes is sized for the 35-minute calibration
# probe. Instead this action promises to finish inside its own share, and every
# subprocess and scan is measured against that one deadline, so the scans shorten when
# the queries are slow instead of the two phases overrunning together.
ACTION_BUDGET_SECONDS = 1_800
# Held back from the SCAN budget for the queries and receipt that follow the scans --
# the same principle as the closing reserve, one level up. Without it the scans would
# consume the whole action budget and the closing SQL would have nothing left.
POST_SCAN_SQL_RESERVE_SECONDS = 240
# Fixed at import, so every later measurement shares one origin rather than each
# phase starting its own clock -- which is how the sum escaped being bounded.
ACTION_DEADLINE = time.monotonic() + ACTION_BUDGET_SECONDS
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
# The relation cap does not bound the index inventory: PostgreSQL documents no limit on
# indexes per table, so without this one relation could make the receipt, and the memory
# used to parse it, arbitrarily large.
# The largest relations by total size. One extra row is fetched so truncation is
# reported rather than silent -- every other bounded list in this action does
# that, and this was the one that did not.
RELATION_INVENTORY_LIMIT = 80
INDEX_INVENTORY_LIMIT = 200
# Characters kept from each pg_get_indexdef(). The row cap bounds rows, not bytes, and
# an expression or partial index can hold an arbitrarily large literal or predicate.
# Enough to read a normal definition whole; the full length is reported alongside.
INDEX_DEFINITION_LIMIT = 2_000
# pg_stat_user_tables has one row per user table, so the dead-tuple inventory needs its
# own bound. Ranked by ESTIMATED DEAD BYTES across every table rather than drawn from
# the largest relations: the table holding the most reclaimable dead space need not be
# among the largest by total size.
DEAD_TUPLE_INVENTORY_LIMIT = 100
# Derived generation manifests cannot be deleted, so the attribution queries return one
# row per historical generation and grow without bound as generations accumulate. The
# statement timeout caps execution, not rows or the serialized receipt.
GENERATION_ATTRIBUTION_LIMIT = 50
# pg_database has one row per database and nothing caps it, so the row list is bounded
# for the receipt. The TOTALS that accounted_bytes depends on are computed in SQL across
# every database, so the bound changes what is displayed and never what is accounted.
DATABASE_INVENTORY_LIMIT = 50
# Non-default tablespaces make this action refuse to present a partition at all, so
# the refusal only needs a count. The enumeration is a bounded sample naming what was
# found, because an operator has to know which assumption broke.
TABLESPACE_INVENTORY_LIMIT = 50
# pg_replication_slots lists every slot that exists and max_replication_slots is
# operator configuration, so the row count is not something this action bounds. The
# counts come from an aggregate; the sample is ordered so that the slots actually
# pinning WAL are the ones kept, never the alphabetically first.
REPLICATION_SLOT_INVENTORY_LIMIT = 50
# Every directory scan shares one wall-clock budget. Individually bounded calls are not
# enough: the operator workflow kills the job at 40 minutes, and four fixed scans plus
# eight drill-down steps at the 300 s per-call limit would be 60 minutes, so a valid but
# slow production inventory could be killed before it emitted any receipt at all. With a
# shared budget the walk stops early and records why, which is a usable receipt.
#
# The depth-0 scan of pg_wal gets the NORMAL per-call allowance.
#
# It had 60 s on the reasoning that max_wal_size bounds the directory. That premise is
# false: PostgreSQL documents max_wal_size as a SOFT limit, and max_slot_wal_keep_size
# defaults to -1, which lets a replication slot retain WAL without limit. A lagging
# slot or a failing archive_command is exactly the condition that makes pg_wal huge --
# and exactly when this inventory is wanted -- so a short timeout would stop the
# mandatory reconciliation in the one case it needs to report on.
WAL_DIRECTORY_SCAN_SECONDS = DIRECTORY_USAGE_TIMEOUT_SECONDS
# Held back from the budget for the closing reconciliation, so the walk can never consume
# the budget the reconciliation needs and take the whole section down with it. One
# allowance per closing scan, and the closing phase makes THREE: the PGDATA re-read, the
# depth-1 breakdown of `base` that keeps the base remainder in one metric, and the
# depth-0 re-measure of pg_wal beside the pg_ls_waldir() read. Reserving fewer would
# leave a later scan running against whatever the earlier ones left over, which is a
# different way of failing the scan the reserve exists to protect.
RECONCILE_RESERVE_SECONDS = (
    2 * DIRECTORY_USAGE_TIMEOUT_SECONDS + WAL_DIRECTORY_SCAN_SECONDS
)
# Note on the arithmetic: three full allowances is 900 s, which exceeds what the
# action deadline leaves for scans (1,800 - 240 = 1,560 against a 1,200 s walk). That
# is handled rather than hoped about -- ScanBudget.remaining() takes the minimum of
# this budget and the action deadline, so the WALK shortens to fit instead of the
# closing phase being cut off. Adding the overall deadline first is what made raising
# this reserve safe.
# The budget is the WALK's allowance PLUS the reserve, not a total the reserve is carved
# out of. ScanBudget.remaining() subtracts the reserve from this number for every
# pre-closing caller, so defining it as a fixed total meant that raising the reserve
# silently cut the walk: doubling the reserve took the walk from 1,200 s to 900 s, which
# is enough for the mandatory PGDATA detail scan to raise
# directory_scan_budget_exhausted before the drill-down starts a single step. Stating it
# as a sum keeps the two independent, and keeps the arithmetic in this comment true:
# worst case is 1,200 s of walking plus 600 s of closing = 30 minutes, inside the
# workflow's 40-minute kill.
DIRECTORY_SCAN_WALK_SECONDS = 1_200
DIRECTORY_SCAN_BUDGET_SECONDS = DIRECTORY_SCAN_WALK_SECONDS + RECONCILE_RESERVE_SECONDS
# A drill-down step starting with barely any budget beyond the reserve would time out
# and fail the section. Below this, stop and record the exhaustion instead.
DRILL_DOWN_MIN_CALL_SECONDS = 30
# The largest children kept from each drill-down listing. The walk follows the largest
# and reports ten, so this bounds memory without changing any decision it makes.
DRILL_DOWN_CHILD_LIMIT = 200
# Records kept from any other scan. The whole-filesystem scan at depth 2 is also
# unbounded in output -- /tmp or a home directory can have very high fan-out -- so it
# is capped the same way rather than trusting the depth to keep it small.
DU_DEFAULT_KEEP = 4000
# PGDATA children whose bytes are genuinely already inside accounted_bytes, and only
# those. `base` is the per-database storage that pg_database_size sums, and pg_wal is
# wal_bytes; the temp-directory query measures `base/pgsql_tmp`, which is inside `base`
# and so needs no entry of its own. The cluster-level statistics directories `pg_stat`
# and `pg_stat_tmp` are NOT covered by any of those figures, so filtering them here
# would delete their bytes from every candidate while leaving them inside
# unaccounted_bytes -- the summary would then claim a figure it could not locate.
# Everything not listed (global, pg_xact, pg_multixact, pg_stat, pg_stat_tmp, log,
# replication-slot state) stays visible as an inside-PGDATA candidate.
ACCOUNTED_PGDATA_CHILDREN = frozenset({"base", "pg_wal", "pg_xlog"})
# `pg_ls_waldir()` lists the top-level ORDINARY FILES of pg_wal and documents that it
# excludes directories, so wal_bytes does not cover pg_wal/archive_status or
# PostgreSQL 18's pg_wal/summaries. Excluding the whole pg_wal child would therefore
# drop those bytes from every candidate while leaving them inside unaccounted_bytes.
# The difference between pg_wal's measured size and wal_bytes is reported as its own
# inside-PGDATA candidate.
WAL_CHILD_NAMES = ("pg_wal", "pg_xlog")
# `df` reports filesystem space; `du` estimates space used by files. The difference is
# real -- filesystem metadata, and blocks held by deleted-but-open files -- and is
# reported rather than hidden, with a flag when it is too large to ignore. Reserved
# blocks are deliberately NOT listed as a cause: they explain df's size minus
# (used + available), because they stay FREE while being unavailable to ordinary users,
# so they never appear in `used` and cannot contribute to used-minus-du. Naming them
# here would send an operator to tune the reserved-block percentage, which cannot close
# this residual.
DF_DU_RESIDUAL_SIGNIFICANT_PPM = 20_000  # 2 % of used bytes
MOUNT_INSPECT_FORMAT = "{{range .Mounts}}{{.Source}}\t{{.Destination}}\n{{end}}"


def action_remaining() -> float:
    """Seconds left of the action's own wall-clock promise."""
    return ACTION_DEADLINE - time.monotonic()


def run(
    argv: list[str], *, timeout: int = PROCESS_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    # Every subprocess is measured against the action deadline as well as its own
    # timeout, so no single call can carry the action past the point where it can still
    # emit a receipt. RuntimeError, not SystemExit: each section catches it, records the
    # reason, and the structured receipt is still printed at the end.
    left = action_remaining()
    if left <= 0:
        raise RuntimeError("action_deadline_exceeded")
    timeout = max(1, min(timeout, math.ceil(left)))
    try:
        # errors="surrogateescape", not the strict TextIOWrapper default: a path may
        # contain any byte except NUL and /, so a sequence invalid in the host locale
        # is legal on Unix and reachable in a user directory or an extracted archive.
        # Strict decoding raises UnicodeDecodeError here, which nothing catches, and
        # the privileged action exits with a traceback instead of its structured
        # stopped receipt. Surrogate escapes round-trip, so such a path is still
        # reported -- it is a directory someone may need to look at.
        return subprocess.run(
            argv,
            text=True,
            errors="surrogateescape",
            capture_output=True,
            timeout=timeout,
            check=False,
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


def df_used_bytes(path: str) -> int:
    """The filesystem's used bytes, from the same read-only path as the volume section."""
    return df_values(["df", "-B1", "--output=used", path], ("used_bytes",))["used_bytes"]


def parse_du(stdout: str) -> list[dict[str, Any]]:
    """Parse NUL-delimited `du --null` records.

    Splitting on newlines breaks on a directory whose NAME contains one: the record
    fragments, the fragment without a tab raises directory_usage_output_invalid, and the
    governed inventory stops even though the scan succeeded. The whole-filesystem scan
    covers operator-uncontrolled paths -- a user's home directory, an extracted
    archive -- so this is reachable without anything being wrong. GNU du provides
    --null for exactly this, and a path cannot contain NUL.
    """
    rows: list[dict[str, Any]] = []
    for record in stdout.split("\0"):
        if not record.strip():
            continue
        parts = record.split("\t", 1)
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
    own total minus the totals of the reported descendants that have no NEARER reported
    ancestor; the deepest reported rows keep their full total because nothing below them
    was measured separately. The exclusive sizes sum to the scanned root's total exactly
    once.

    Nearest reported ancestor, not immediate parent. The reported set comes out of a
    bounded top-k, so it is not ancestor-closed: the cap can retain a child while
    dropping its parent -- two equal-sized rows either side of the cutoff, with the
    tie-break keeping the child. Subtracting only when the immediate parent survived
    then left that child's bytes counted twice, once as its own row and again inside
    whichever ancestor the cap did keep, inflating the candidate total and breaking the
    closure after a scan that succeeded. Attributing to the nearest surviving ancestor
    keeps the partition exact whatever the cap drops.
    """
    totals = {row["path"].rstrip("/") or "/": row["bytes"] for row in rows}
    child_bytes: dict[str, int] = {}
    for path, size in totals.items():
        if path == "/":
            continue
        ancestor = path
        while ancestor != "/":
            ancestor = ancestor.rsplit("/", 1)[0] or "/"
            if ancestor in totals:
                child_bytes[ancestor] = child_bytes.get(ancestor, 0) + size
                break
    return {path: size - child_bytes.get(path, 0) for path, size in totals.items()}


def mount_atime_policy(path: str) -> dict[str, Any]:
    """The access-time policy of the filesystem holding `path`.

    `du` reads every directory it traverses, and under the kernel's DEFAULT
    `relatime` that read updates the directory's access time whenever the stored
    atime predates mtime/ctime or is over 24 hours old; under `strictatime` it
    updates on every access. So a receipt claiming the action modifies nothing is
    only true when the filesystem is mounted `noatime` or `nodiratime`. That is a
    property of the host, not of this code, so it is MEASURED and reported rather
    than assumed in either direction.

    Read straight from /proc/mounts: reading a virtual file writes nothing, and it
    avoids depending on findmnt being installed. Longest matching mount point wins,
    because a nested mount governs the paths below it.
    """
    try:
        with open("/proc/mounts", encoding="utf-8", errors="surrogateescape") as handle:
            lines = handle.read().splitlines()
    except OSError as exc:
        return {"available": False, "reason": f"proc_mounts_unreadable:{exc.errno}"}
    target = path.rstrip("/") or "/"
    best: tuple[int, str, str] | None = None
    for line in lines:
        fields = line.split()
        if len(fields) < 4:
            continue
        # /proc/mounts octal-escapes spaces, tabs, newlines and backslashes.
        point = (
            fields[1]
            .replace("\\040", " ")
            .replace("\\011", "\t")
            .replace("\\012", "\n")
            .replace("\\134", "\\")
        )
        stripped = point.rstrip("/") or "/"
        if stripped == "/" or target == stripped or target.startswith(f"{stripped}/"):
            if best is None or len(stripped) > best[0]:
                best = (len(stripped), point, fields[3])
    if best is None:
        return {"available": False, "reason": "mount_point_not_found"}
    options = [item for item in best[2].split(",") if item]
    # nodiratime is sufficient on its own here: du's writes would be to DIRECTORY
    # atimes, and that option suppresses exactly those.
    suppressed = "noatime" in options or "nodiratime" in options
    if "strictatime" in options:
        policy = "strictatime"
    elif "noatime" in options:
        policy = "noatime"
    elif "nodiratime" in options:
        policy = "nodiratime"
    else:
        # The kernel default when none is specified.
        policy = "relatime"
    return {
        "available": True,
        "mount_point": best[1],
        "options": options,
        "atime_policy": policy,
        "directory_atime_writes_suppressed": suppressed,
    }


def same_device_aliases(root: str) -> dict[str, Any]:
    """Mount points under `root` that are aliases of the same underlying directory.

    `du -x` skips directories on a DIFFERENT filesystem, which is all GNU documents it
    as doing -- so it is no protection against a bind mount whose target is on the
    same device as its source. The walk then traverses the same underlying files
    through both paths and the candidate partition can list those bytes twice, while
    `df` counts them once. The resulting negative df/du residual offsets the duplicate,
    so the closure can still come out true: a double count that the receipt's own
    self-check cannot see.

    Detected by identity rather than by guessing at mount flags: two paths that are
    aliases of one directory have the same `st_dev` AND the same `st_ino`, which is
    exactly what "the same directory" means to the kernel. /proc/mounts supplies the
    candidate paths; `stat` decides.
    """
    try:
        with open("/proc/mounts", encoding="utf-8", errors="surrogateescape") as handle:
            lines = handle.read().splitlines()
    except OSError as exc:
        return {"available": False, "reason": f"proc_mounts_unreadable:{exc.errno}"}
    base = root.rstrip("/")
    points: list[str] = []
    for line in lines:
        fields = line.split()
        if len(fields) < 2:
            continue
        point = (
            fields[1]
            .replace("\\040", " ")
            .replace("\\011", "\t")
            .replace("\\012", "\n")
            .replace("\\134", "\\")
        )
        stripped = point.rstrip("/")
        if base in ("", "/") or stripped == base or stripped.startswith(f"{base}/"):
            points.append(point)
    identities: dict[tuple[int, int], list[str]] = {}
    for point in points:
        probe = run(["stat", "-c", "%d %i", point])
        if probe.returncode != 0:
            continue
        parts = probe.stdout.split()
        if len(parts) != 2:
            continue
        dev = as_int(parts[0])
        ino = as_int(parts[1])
        if dev is None or ino is None:
            continue
        identities.setdefault((dev, ino), []).append(point)
    aliases = [sorted(paths) for paths in identities.values() if len(paths) > 1]
    return {
        "available": True,
        "mount_points_under_root": len(points),
        "alias_sets": sorted(aliases),
        "aliases_present": bool(aliases),
    }


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


def postgres_mounts() -> list[tuple[str, str]]:
    """Every mount the container has, as (source, destination).

    All of them, not just the data one. A second mount at or below PGDATA -- a
    separate volume or bind for pg_wal, say -- is invisible from the host side:
    `stat` and `du` on the host see the mount point's UNDERLYING directory inside the
    PGDATA volume, which is typically empty and on PGDATA's own device, so neither a
    path test nor a device test can detect it. Only the container's mount list can.
    """
    result = run(["docker", "inspect", "-f", MOUNT_INSPECT_FORMAT, POSTGRES_CONTAINER])
    if result.returncode != 0:
        raise RuntimeError("postgres_mount_inspection_failed")
    mounts: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise RuntimeError("postgres_mount_output_invalid")
        mounts.append((parts[0], parts[1]))
    return mounts


def postgres_mount(
    mounts: list[tuple[str, str]], container_pgdata: str
) -> tuple[str, str]:
    """The DEEPEST mount whose destination contains the server's data directory.

    Deepest, not a name heuristic. Choosing by destination name
    (`/var/lib/postgresql/data`, else anything under `/var/lib/postgresql`) could
    select an OUTER mount while another mount covered an ancestor of PGDATA beneath
    it -- `/var/lib/postgresql/18` when PGDATA is `/var/lib/postgresql/18/docker`,
    say. host_pgdata() would then map PGDATA into the outer source's hidden
    underlying tree, and if a stale directory happened to exist there, the path and
    device checks would both pass while every scan measured the wrong filesystem.
    The deepest covering mount is the one that actually provides those bytes, so
    selecting it makes an intervening mount impossible rather than merely detectable.
    """
    best: tuple[int, str, str] | None = None
    for source, destination in mounts:
        target = destination.rstrip("/") or "/"
        if container_pgdata == target or container_pgdata.startswith(f"{target}/"):
            if best is None or len(target) > best[0]:
                best = (len(target), source, destination)
    if best is None:
        # No mount provides PGDATA, so its bytes live in the container's own writable
        # layer rather than on a volume. Nothing on the inspected volume is the data
        # directory, and every subtraction below would be wrong.
        raise RuntimeError("postgres_data_mount_unresolved")
    return best[1], best[2]


def container_data_directory(db_user: str, db_name: str) -> str:
    """Ask the server where its data directory is.

    Read BEFORE the mount is chosen, because the mount has to be selected by which
    one contains this path.
    """
    rows = psql("SELECT current_setting('data_directory')", db_user, db_name)
    if len(rows) != 1 or len(rows[0]) != 1 or not rows[0][0].startswith("/"):
        raise RuntimeError("postgres_data_directory_unresolved")
    return rows[0][0].rstrip("/")


def host_pgdata(
    mount_source: str, mount_destination: str, container_pgdata: str
) -> tuple[str, str]:
    """Translate the server's own `data_directory` into a host path.

    The mount destination is not PGDATA. The official PostgreSQL 18 image places
    PGDATA at /var/lib/postgresql/18/docker while the volume is commonly mounted at
    /var/lib/postgresql, so scanning the mount root at depth 1 reports only the `18`
    parent and never the base/pg_wal/log breakdown this action is supposed to show.

    Pure mapping: the data directory is read by container_data_directory() and the
    mount is chosen by postgres_mount() as the deepest one containing it, so by the
    time this runs the only remaining work is the prefix substitution.
    """
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
    killed before emitting any receipt. A partial receipt that says where it stopped
    beats no receipt at all.

    The budget **owns its reserve** rather than taking it as an argument at each call
    site. Passing it per call meant forgetting it at four of them, which silently
    unreserved the reserve: the closing reconciliation scan is mandatory, so any earlier
    scan allowed to spend its time takes the whole section down. Here every call is
    held back from the reserve by default, and only `begin_closing_scan()` opens it --
    once before each of the two closing scans the reserve exists for.
    """

    def __init__(self, seconds: int, reserve_seconds: int) -> None:
        self.total_seconds = seconds
        self.reserve_seconds = reserve_seconds
        self._reserved = True
        self._deadline = time.monotonic() + seconds

    def begin_closing_scan(
        self, seconds: int = DIRECTORY_USAGE_TIMEOUT_SECONDS
    ) -> None:
        """Give the next closing scan its own allowance.

        Called once before EACH closing scan, not once for the phase. The reserve has
        to be an allowance rather than a slice of an advancing deadline: between the
        walk and the closing phase, the database, WAL, relation, index, attribution and
        tablespace queries run without touching the budget at all, while the wall clock
        keeps moving, so a single deadline set at the start of the phase could be
        consumed by time the scan never asked for.

        The same argument applies BETWEEN the two closing scans. The PGDATA re-read can
        take nearly its whole allowance, and the closing WAL query and the base
        classification run after it; against one phase deadline the `base` scan would
        then start with less than a per-call allowance and could time out on a walk it
        would have finished. Its failure is treated as an optional unavailable
        breakdown, so the action would still report success while silently dropping the
        base attribution it exists to produce -- the quietest possible way to lose a
        finding.

        The reserve stays two full allowances, so the pre-closing walk is still held
        back by everything the closing phase can need.
        """
        self._reserved = False
        self._deadline = time.monotonic() + seconds

    def reserve(self) -> float:
        return self.reserve_seconds if self._reserved else 0.0

    def remaining(self) -> float:
        """Time left that the caller may actually use, reserve already deducted.

        Bounded by the ACTION deadline as well as this budget's own, minus the share
        held back for the queries and receipt that follow the scans. Without that the
        scans could spend the action's whole wall clock and the closing SQL would be
        cut off by the workflow kill rather than by anything this file controls.
        """
        own = self._deadline - time.monotonic() - self.reserve()
        overall = action_remaining() - POST_SCAN_SQL_RESERVE_SECONDS
        return min(own, overall)

    def call_timeout(self) -> int:
        left = self.remaining()
        if left <= 0:
            raise RuntimeError("directory_scan_budget_exhausted")
        return max(1, min(DIRECTORY_USAGE_TIMEOUT_SECONDS, math.ceil(left)))


# `du` exits nonzero when any file it enumerated has gone before it could be examined.
# On a live 1.3 TB cluster that is ordinary behaviour, not a fault: PostgreSQL recycles
# WAL segments and removes temporary files and relations continuously, and these scans
# run for minutes. Treating it as a hard failure would make the inventory fail from
# normal database activity. A vanished file is also, by definition, no longer using
# space, so the totals for everything else remain correct and usable.
DU_VANISHED_MARKERS = ("No such file or directory",)
DU_ATTEMPTS = 3
tolerated_churn: list[dict[str, Any]] = []


DU_READ_CHUNK = 65536
# How long a single poll waits before re-checking the deadline. Short enough that a
# quiet `du` cannot push past its timeout, long enough not to spin.
DU_POLL_SECONDS = 1.0
# `du` can emit one diagnostic per vanished or unreadable path, so stderr needs the
# same bound stdout has. Only the first diagnostic and the count are reported.
DU_STDERR_LIMIT = 1 << 20


def du_stream(
    argv: list[str],
    budget: ScanBudget,
    error: str,
    *,
    keep: int,
    expect_path: str | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Run one `du` and keep only its largest `keep` records.

    The output is read INCREMENTALLY and reduced to a bounded top-k as it arrives,
    rather than captured whole and sorted. That is not an optimisation; each
    alternative fails in its own way:

    * Capturing the whole stream leaves memory unbounded however tightly the step
      count and timeout are drawn -- a high-fan-out directory (/tmp, a home
      directory, a layer store) kills the production action without its receipt.
    * A `du | sort | head` pipeline bounds memory but spills `sort`'s temporary files
      to $TMPDIR, which this action promises it never does
      (`filesystem_writes_performed: false`).
    * A nested `bash -c` pipeline returns `head`'s status, not `du`'s, because the new
      shell does not inherit `pipefail` -- so a vanished file, a permission error or
      an I/O failure reads as success and bypasses both the churn handling and the
      fail-closed error.
    * `subprocess` kills only the immediate child on timeout, so a pipeline's `du`
      keeps walking after the step gave up, spending the shared budget and loading
      production.

    One `du`, read in chunks, in a session of its own so a timeout kills the group.
    The caller also receives the count and byte total of the records that did NOT
    survive the cap, because the drill-down's arithmetic needs the complete sum even
    when it only sees the largest few.
    """

    def absorb(
        record: str,
        kept: list[tuple[int, str]],
        omitted: list[int],
    ) -> None:
        parts = record.split("\t", 1)
        if len(parts) != 2:
            raise RuntimeError("directory_usage_output_invalid")
        size = required_int(parts[0], "directory_usage_output_invalid")
        item = (size, parts[1])
        if len(kept) < keep:
            heapq.heappush(kept, item)
            return
        if item > kept[0]:
            dropped = heapq.heapreplace(kept, item)
            omitted[0] += 1
            omitted[1] += dropped[0]
        else:
            omitted[0] += 1
            omitted[1] += size

    reason = "exit_unknown"
    churned: tuple[tuple[list[dict[str, Any]], int, int], dict[str, Any]] | None = None
    target = expect_path.rstrip("/") if expect_path else None
    for attempt in range(1, DU_ATTEMPTS + 1):
        timeout = budget.call_timeout()
        stderr_chunks: list[str] = []
        kept: list[tuple[int, str]] = []
        omitted = [0, 0]
        timed_out = False
        try:
            # BINARY pipes. The deadline has to be enforced between reads, and a text
            # wrapper's read() blocks until its request is satisfied or EOF -- so a `du`
            # that goes quiet traversing a large subtree, or emits less than one chunk
            # and stalls, would never return control to the deadline check and both the
            # per-call and the shared budget would be decoration. Raw descriptors can be
            # polled with a timeout; the bytes are decoded per chunk instead.
            process = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            raise RuntimeError(f"{error}:{type(exc).__name__}") from exc

        stderr_bytes = 0

        def drain(stream: Any = process.stderr) -> None:
            # Bounded. `du` can emit one diagnostic per vanished or unreadable path, so
            # on a churn-heavy PostgreSQL or Docker tree stderr is as unbounded as
            # stdout was; only the first DU_STDERR_LIMIT bytes are needed, because the
            # decision is "are all of these vanished-file messages" and the receipt
            # records the first diagnostic and a count.
            nonlocal stderr_bytes
            with contextlib.suppress(Exception):
                while True:
                    block = stream.read(DU_READ_CHUNK)
                    if not block:
                        break
                    if stderr_bytes < DU_STDERR_LIMIT:
                        stderr_chunks.append(
                            block[: DU_STDERR_LIMIT - stderr_bytes].decode(
                                "utf-8", "surrogateescape"
                            )
                        )
                    stderr_bytes += len(block)

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        carry = b""
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                if not selector.select(timeout=min(remaining, DU_POLL_SECONDS)):
                    continue
                block = process.stdout.read1(DU_READ_CHUNK)
                if not block:
                    break
                carry += block
                # Split on NUL in BYTES, so a multi-byte character spanning a chunk
                # boundary is never decoded in halves.
                parts = carry.split(b"\0")
                carry = parts.pop()
                for raw in parts:
                    record = raw.decode("utf-8", "surrogateescape")
                    if record.strip():
                        absorb(record, kept, omitted)
            if not timed_out and carry.strip():
                absorb(carry.decode("utf-8", "surrogateescape"), kept, omitted)
        finally:
            with contextlib.suppress(Exception):
                selector.close()
            if timed_out:
                with contextlib.suppress(OSError, ProcessLookupError):
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            with contextlib.suppress(Exception):
                process.stdout.close()
            returncode = process.wait()
            reader.join(timeout=5)
            with contextlib.suppress(Exception):
                process.stderr.close()

        if timed_out:
            reason = "timeout"
            churned = None
            break

        rows = [
            {"path": path, "bytes": size}
            for size, path in sorted(kept, key=lambda item: (-item[0], item[1]))
        ]
        if returncode == 0:
            return rows, omitted[0], omitted[1]
        stderr_text = "".join(stderr_chunks)
        stderr_lines = [line for line in stderr_text.splitlines() if line.strip()]
        stderr_truncated = stderr_bytes > DU_STDERR_LIMIT
        detail = stderr_text.strip().splitlines()
        reason = detail[-1][:240] if detail else f"exit_{returncode}"
        # Truncated diagnostics cannot establish "every message is a vanished file":
        # the part not captured could hold a permission error. Fail closed instead of
        # concluding tolerance from a partial read -- bounding stderr must not become a
        # way to lose the evidence that decides whether tolerating is safe.
        # ENDSWITH, not `in`. GNU du writes "du: cannot access 'PATH': REASON", so the
        # reason is the terminal text and the PATH is operator-uncontrolled -- this scan
        # covers the whole filesystem, including /tmp and home directories. A file
        # literally named "No such file or directory" would make a `Permission denied`
        # line on it match as harmless churn, and the action would then accept an
        # incomplete scan and report success. The tolerance has to key on the error
        # du reported, not on text appearing anywhere in the line.
        vanished_only = (
            bool(stderr_lines)
            and not stderr_truncated
            and all(
                any(
                    line.rstrip().endswith(marker)
                    for marker in DU_VANISHED_MARKERS
                )
                for line in stderr_lines
            )
        )
        if not vanished_only:
            churned = None
            break
        if target is not None and not any(
            (row["path"].rstrip("/") or "/") == (target or "/") for row in rows
        ):
            churned = None
            break
        churned = (
            (rows, omitted[0], omitted[1]),
            {
                "scan": error,
                "attempts": attempt,
                "vanished_paths": len(stderr_lines),
                "diagnostics_truncated": stderr_truncated,
                "first_diagnostic": stderr_lines[0][:240],
            },
        )
        if budget.remaining() < DRILL_DOWN_MIN_CALL_SECONDS:
            break
    if churned is not None:
        payload, record = churned
        record["accepted_possibly_undercounting"] = True
        tolerated_churn.append(record)
        return payload
    raise RuntimeError(f"{error}:{reason}")


def du_rows(
    argv: list[str], budget: ScanBudget, error: str, *, expect_path: str | None = None
) -> list[dict[str, Any]]:
    rows, _, _ = du_stream(
        argv, budget, error, keep=DU_DEFAULT_KEEP, expect_path=expect_path
    )
    return rows


def du_total(path: str, budget: ScanBudget) -> int:
    rows, _, _ = du_stream(
        ["du", "--null", "-x", "-B1", "--max-depth=0", path],
        budget,
        "directory_total_failed",
        keep=1,
        expect_path=path,
    )
    total = next(
        (row["bytes"] for row in rows if row["path"].rstrip("/") == path.rstrip("/")),
        None,
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
    stopped_before_first_step = False
    current = root.rstrip("/") or "/"
    for _ in range(max_steps):
        if budget.remaining() < DRILL_DOWN_MIN_CALL_SECONDS:
            if chain:
                chain[-1]["stop_reason"] = "scan_budget_exhausted"
            else:
                # Nothing was inspected at all. Without a section-level reason the
                # receipt would report success with an unexplained empty chain, which
                # reads as "nothing to find" rather than "never looked".
                stopped_before_first_step = True
            break
        # Bounded in OUTPUT as well as in steps and time. A high-fan-out directory --
        # overlay2 with thousands of layers, a backup tree -- emits one record per
        # immediate child, and capturing the whole stream leaves memory unbounded
        # however tightly the step cap and timeout are drawn. du_stream reduces it to
        # the largest DRILL_DOWN_CHILD_LIMIT children as it arrives, which is all the
        # walk uses (it follows the largest and reports ten), and returns the count and
        # byte total of the rest so the arithmetic below stays correct.
        rows, omitted_children, omitted_child_bytes = du_stream(
            ["du", "--null", "-x", "-B1", "--max-depth=1", current],
            budget,
            "drill_down_failed",
            keep=DRILL_DOWN_CHILD_LIMIT,
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
        # The cap's omitted children must be added back, or their bytes would be
        # attributed to this directory's own files -- producing a false
        # `directory_owns_more_directly_than_any_child` stop and preventing descent
        # into a genuinely large child.
        own_file_bytes = here_total - child_total - omitted_child_bytes
        step: dict[str, Any] = {
            "directory": here,
            "own_file_bytes": own_file_bytes,
            "children_omitted_by_cap": omitted_children,
            "children_omitted_bytes": omitted_child_bytes,
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
    if stopped_before_first_step:
        chain.append(
            {
                "directory": current,
                "own_file_bytes": None,
                "children": [],
                "followed": None,
                "stop_reason": "scan_budget_exhausted_before_first_step",
            }
        )
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
    # What that claim covers, stated rather than left to be assumed. The action itself
    # creates, modifies and deletes nothing -- but the shell that runs it spools the
    # embedded program to an unlinked temporary file before the interpreter starts:
    # bash uses a pipe for a here-document only while it fits the pipe buffer, and this
    # program is larger, so stdin resolves to /tmp/sh-thd.* (deleted). Measured, not
    # assumed: a 126 KB here-document under bash 5.2.21 gives
    # `stdin -> /tmp/sh-thd.XXXXXX (deleted)` where a 62-byte one gives `pipe:[...]`.
    #
    # It cannot be removed in this delivery model. The operator control plane pipes one
    # self-contained script to `bash -s` over SSH, so there is no file on the host to
    # exec and no second file to read the program from. Splitting the program across
    # several sub-pipe-buffer here-documents would avoid the spool, at the cost of
    # arbitrary chunk boundaries through the middle of a program that operators have to
    # read and reviewers have to audit -- a worse trade for a deleted file that holds
    # this program's own text, no host data, and nothing after the interpreter starts.
    #
    # So it is reported instead of being quietly covered by an unqualified false.
    "filesystem_writes_scope": (
        "This action creates, modifies and deletes no file and no file content. Two "
        "side effects it cannot avoid are reported rather than covered by that claim. "
        "(1) The shell spools the embedded program to an unlinked temporary file "
        "before the interpreter starts, because the control plane pipes one "
        "self-contained script over SSH and a here-document above the pipe-buffer "
        "size is spooled rather than piped; that file holds the program text, not "
        "host data, and does not outlive the shell. (2) `du` reads every directory it "
        "traverses, and under the kernel's default `relatime` -- or `strictatime` -- "
        "the kernel updates those directories' ACCESS TIMES as a result. That is a "
        "metadata write caused by reading, so it cannot be avoided while measuring at "
        "all, and whether it happens is a property of the host's mount options rather "
        "than of this action: inventory.volume.atime reports the measured policy and "
        "directory_atime_writes_suppressed is true only under noatime or nodiratime. "
        "No file content, size, name or ownership is changed either way."
    ),
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

scan_budget = ScanBudget(DIRECTORY_SCAN_BUDGET_SECONDS, RECONCILE_RESERVE_SECONDS)
mount_source: str | None = None
# The container's full mount list, read in the volume section and used by the WAL
# section to detect a mount nested at or below PGDATA. Module scope for the same reason
# as the others: a failed volume section must not reach a later one as a NameError,
# which is not RuntimeError and would escape the section handler.
container_mounts: list[tuple[str, str]] = []
mount_destination: str | None = None
# Assigned inside the directory-usage section, but read by the drill-down section that
# follows it. Without this, a failed `df --output=target` leaves the name undefined and
# the later guard raises NameError -- which is not RuntimeError, so it escapes the
# section handler and the action dies with a traceback where the structured fail-closed
# receipt belongs.
usage_root: str | None = None
# Same reason as usage_root: assigned in the directory-usage section and read by the
# WAL section, so it must exist even when that section fails. A NameError here is not
# RuntimeError and would escape the section handler as a traceback.
pgdata_container: str | None = None
usage_full: list[dict[str, Any]] | None = None
postgres_data_directory_bytes: int | None = None
pgdata_children_all: list[dict[str, Any]] | None = None
pgdata_host: str | None = None
pgdata_before: int | None = None
# The data-directory size measured immediately AFTER the root walk, so it describes the
# same state as `usage_full`. Read by the summary, which subtracts it from the ancestor
# that contains the data directory; module scope for the same reason as the others --
# a NameError here is not RuntimeError and would escape the section handler.
pgdata_after: int | None = None
tolerance: int = 0
# Same reason again: the database totals are computed in the `databases` section and
# read by the summary. Previously the summary re-derived them by iterating
# inventory["databases"], which on a failed section is a failure DICT -- iterating it
# yields its key strings and raises TypeError, escaping the section handler.
operating_database_bytes: int | None = None
other_databases_bytes: int | None = None
# The opening database total, kept so the closing re-read can be reported as a bracket
# rather than silently replacing it.
database_total_bytes: int | None = None
# The CLOSING database and temp totals, read in the reconciliation section and used by
# the summary so accounted_bytes is genuinely a closing figure. Module scope for the
# same reason as the others.
operating_database_bytes_at_close: int | None = None
database_total_bytes_at_close: int | None = None
temp_bytes_at_close: int | None = None
# The live database OID directory names, read in the `databases` section and used by
# the base breakdown in the reconciliation section. None means "not established",
# which suppresses the breakdown rather than guessing from a partial set.
live_database_oids: dict[str, str] | None = None
base_breakdown: dict[str, Any] | None = None
try:
    container_mounts = postgres_mounts()
    # Data directory first, then the mount that contains it. The reverse order let a
    # name heuristic pick an outer mount while a deeper one actually provided PGDATA.
    container_pgdata_path = container_data_directory(db_user, db_name)
    mount_source, mount_destination = postgres_mount(
        container_mounts, container_pgdata_path
    )
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
        # Measured, because it decides whether this action's own reads write anything.
        # See mount_atime_policy(): under the kernel default `relatime` a du traversal
        # updates directory access times, so "modifies nothing" is a claim about the
        # host's mount options and not about this code.
        "atime": mount_atime_policy(mount_source),
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
        mount_source, mount_destination, container_pgdata_path
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
    # The PGDATA bracket cannot see changes in SIBLING paths, and the root scan can run
    # for minutes: a backup, a Docker layer or a log rotating during it would leave the
    # early `df` reading and the `du` total describing different filesystem states, and
    # the whole difference would be silently relabelled as filesystem overhead. So the
    # filesystem's used bytes are read either side of the root scan too.
    volume_used_before = df_used_bytes(mount_source)
    pgdata_before = du_total(pgdata_host, scan_budget)
    # Fail closed on a failed scan: without this evidence the receipt cannot answer
    # its own question, so it must not be presented as a complete inventory.
    # Same-device bind aliases, EXCLUDED from the walk rather than left to be counted
    # twice. `-x` only skips other filesystems, so a bind whose target shares the
    # source's device is traversed through both paths; `df` counts those blocks once
    # while the candidate partition lists them twice, and the resulting negative
    # residual offsets the duplicate so the closure can still read true.
    #
    # One path per alias set is kept -- the first in sorted order, so the choice is
    # deterministic -- and the rest are excluded. Excluding rather than refusing,
    # because a host-side bind under the scanned root is a legitimate configuration
    # and refusing would make the action unusable on it; the alias sets are reported
    # so the omission is visible.
    alias_report = same_device_aliases(usage_root)
    inventory["directory_scan_same_device_aliases"] = alias_report
    alias_excludes: list[str] = []
    if alias_report.get("available"):
        for paths in alias_report.get("alias_sets", []):
            alias_excludes.extend(paths[1:])
    usage_full = du_rows(
        [
            "du",
            "--null",
            "-x",
            "-B1",
            *(f"--exclude={path}" for path in alias_excludes),
            "--max-depth=2",
            usage_root,
        ],
        scan_budget,
        "directory_usage_failed",
        expect_path=usage_root,
    )
    # IMMEDIATELY after the root scan, before the PGDATA re-read. This is the reading
    # the df/du residual is paired with, and `pgdata_after` is another full walk of a
    # 1.3 TB directory -- minutes. Taken after it, the reading described a filesystem
    # state minutes newer than `usage_full`, so every byte written or freed during that
    # second walk was charged to filesystem metadata and deleted-but-open files. That
    # defeated the point of pairing the residual with its own window: the pairing has
    # to be in time, not merely in name.
    volume_used_after = df_used_bytes(mount_source)
    pgdata_after = du_total(pgdata_host, scan_budget)
    volume_drift = abs(volume_used_after - volume_used_before)
    volume_tolerance = max(
        DIRECTORY_DRIFT_FLOOR_BYTES,
        volume_used_before * DIRECTORY_DRIFT_FRACTION_PPM // 1_000_000,
    )
    inventory["volume_used_bracket"] = {
        "bytes_before_filesystem_scan": volume_used_before,
        "bytes_after_filesystem_scan": volume_used_after,
        "drift_bytes": volume_used_after - volume_used_before,
        "tolerance_bytes": volume_tolerance,
        "reconciled": volume_drift <= volume_tolerance,
    }
    if volume_drift > volume_tolerance:
        raise RuntimeError(
            f"volume_changed_during_scan:drift_{volume_drift}_over_{volume_tolerance}"
        )
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
except RuntimeError as exc:
    section_failed(failures, inventory, "volume_directory_usage", exc)

try:
    # The PGDATA depth-1 scan gets its own section too. It was the last scan still
    # sharing the root scan's handler, so a timeout or an unreadable directory here
    # replaced the already-stored host-level evidence with an error object -- discarding
    # exactly the scan an operator would need in order to investigate this failure.
    if pgdata_host is None or postgres_data_directory_bytes is None:
        raise RuntimeError("postgres_data_directory_unresolved")
    data_usage = du_rows(
        ["du", "--null", "-x", "-B1", "--max-depth=1", pgdata_host],
        scan_budget,
        "postgres_data_directory_usage_failed",
        expect_path=pgdata_host,
    )
    # The COMPLETE child list is kept for accounting and only the receipt view is
    # truncated. Truncating before accounting would roll the discarded children into
    # `postgres_data_directory_bytes - sum(children)` and report them as files directly
    # in PGDATA -- so a large omitted directory would hide behind a synthetic
    # root-files figure, which is the opposite of what this action is for.
    pgdata_children_all = sorted(
        (row for row in data_usage if row["path"].rstrip("/") != pgdata_host),
        key=lambda item: (-item["bytes"], item["path"]),
    )
    inventory["postgres_data_directory_usage"] = {
        "path": pgdata_host,
        "bytes": postgres_data_directory_bytes,
        "child_count": len(pgdata_children_all),
        "children": pgdata_children_all[:40],
    }

except RuntimeError as exc:
    section_failed(failures, inventory, "postgres_data_directory_usage", exc)

try:
    # The drill-down runs in a section of its own. It used to share the one above, so a
    # timeout or an unreadable directory partway down the walk replaced the
    # already-recorded host-level scan with an error object -- discarding the very
    # evidence the shared-budget design exists to preserve.
    if usage_full is None or usage_root is None or pgdata_host is None:
        raise RuntimeError("volume_directory_usage_unavailable")
    if postgres_data_directory_bytes is None:
        raise RuntimeError("postgres_data_directory_usage_unavailable")
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
    )
    # Record the evidence before anything that can fail. A later failure must not erase
    # a scan that succeeded.
    inventory["non_database_drill_down"] = {
        "floor_bytes": drill_floor,
        "floor_ppm_of_used": DRILL_DOWN_FLOOR_PPM,
        "max_steps": DRILL_DOWN_MAX_STEPS,
        "scan_budget_seconds": scan_budget.total_seconds,
        "action_budget_seconds": ACTION_BUDGET_SECONDS,
        "post_scan_sql_reserve_seconds": POST_SCAN_SQL_RESERVE_SECONDS,
        "action_seconds_remaining_after_walk": round(action_remaining(), 1),
        "reconcile_reserve_seconds": scan_budget.reserve_seconds,
        "chain": chain,
    }
except RuntimeError as exc:
    section_failed(failures, inventory, "non_database_drill_down", exc)

try:
    # The totals are computed in SQL over EVERY database, so accounted_bytes stays
    # correct no matter how many exist, and the row list below is a bounded display
    # of the largest. Summing a bounded list in Python would instead understate
    # accounted_bytes, which inflates unaccounted_bytes -- the figure an operator
    # reads as reclaimable.
    #
    # `current_database()` rather than an interpolated name: psql is already
    # connected to the operating database, so this cannot disagree with the
    # connection, and it needs no quoting or case handling. `next(... == db_name)`
    # previously raised StopIteration -- not RuntimeError -- on any mismatch, which
    # escaped the section's own fail-closed handler.
    database_total_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT count(*)::bigint::text AS database_count, "
        "coalesce(sum(pg_database_size(oid)),0)::bigint::text AS total_bytes, "
        "coalesce(sum(CASE WHEN datname=current_database() "
        "THEN pg_database_size(oid) ELSE 0 END),0)::bigint::text "
        "AS operating_bytes FROM pg_database) q",
        db_user,
        db_name,
    )
    if len(database_total_rows) != 1:
        raise RuntimeError("database_total_output_invalid")
    database_count = required_int(
        database_total_rows[0].get("database_count"), "database_total_output_invalid"
    )
    database_total_bytes = required_int(
        database_total_rows[0].get("total_bytes"), "database_total_output_invalid"
    )
    operating_database_bytes = required_int(
        database_total_rows[0].get("operating_bytes"), "database_total_output_invalid"
    )
    # An operating database of zero bytes is not a small database; it means the
    # totals row describes something other than what this code believes it does.
    if operating_database_bytes <= 0:
        raise RuntimeError("operating_database_size_invalid")
    other_databases_bytes = database_total_bytes - operating_database_bytes
    if other_databases_bytes < 0:
        raise RuntimeError("database_total_output_invalid")
    # Bounded, deterministic, and ordered so the row that matters most is never the
    # one dropped. One extra row detects truncation.
    #
    # The OPERATING database sorts first, ahead of size. It is the subject of the whole
    # receipt, and size order alone would drop its detailed row on a cluster with more
    # than DATABASE_INVENTORY_LIMIT larger databases -- leaving a receipt that reports
    # an operating-database total in the summary with no corresponding entry in the
    # list it is supposed to be drawn from. Same reasoning as the published generation
    # in generation_attribution: a bound may drop rows, but never the one row the
    # reader came for.
    database_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT datname, pg_database_size(oid)::bigint AS size_bytes, "
        "datistemplate, datallowconn, "
        "(datname=current_database()) AS operating FROM pg_database "
        "ORDER BY (datname=current_database()) DESC, "
        "pg_database_size(oid) DESC, datname "
        f"LIMIT {DATABASE_INVENTORY_LIMIT + 1}) q",
        db_user,
        db_name,
    )
    inventory["databases"] = database_rows[:DATABASE_INVENTORY_LIMIT]
    # The row list is what the summary's operating figure is read against, so its
    # presence is asserted rather than assumed.
    if not any(row.get("operating") is True for row in inventory["databases"]):
        raise RuntimeError("operating_database_row_missing")
    inventory["database_count"] = database_count
    inventory["database_total_bytes"] = database_total_bytes
    inventory["database_inventory_limit"] = DATABASE_INVENTORY_LIMIT
    inventory["database_inventory_truncated"] = (
        len(database_rows) > DATABASE_INVENTORY_LIMIT
    )
    # The live OID directory NAMES under base/. Needed to tell a live database
    # directory from an orphaned one in the SAME metric `du` reports -- see the base
    # breakdown in the reconciliation section. Bounded like everything else; when the
    # set is incomplete the breakdown is skipped rather than computed from a partial
    # set, because a live database missing from the set would be reported as orphaned
    # storage, which is the worst possible error for this receipt to make.
    oid_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT oid::text AS oid, datname FROM pg_database ORDER BY oid "
        f"LIMIT {DATABASE_INVENTORY_LIMIT + 1}) q",
        db_user,
        db_name,
    )
    if len(oid_rows) > DATABASE_INVENTORY_LIMIT or len(oid_rows) != database_count:
        live_database_oids = None
    else:
        live_database_oids = {}
        for row in oid_rows:
            oid = row.get("oid")
            datname = row.get("datname")
            if not isinstance(oid, str) or not oid.isdigit():
                raise RuntimeError("database_oid_output_invalid")
            if not isinstance(datname, str) or not datname:
                raise RuntimeError("database_oid_output_invalid")
            live_database_oids[oid] = datname
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
    # Count first, then a bounded sample -- same rule as pg_database and
    # pg_tablespace. pg_replication_slots lists every slot that exists, and
    # max_replication_slots can be set high, so the row count is operator
    # configuration rather than anything this action controls.
    #
    # The ORDER follows PostgreSQL's documented wal_status semantics, which are the
    # opposite of the intuitive reading: `extended` means "max_wal_size is exceeded but
    # the files are still retained", so it is the state that actually causes unexpected
    # WAL on disk; `reserved` retains WAL within max_wal_size; `unreserved` means the
    # slot "no longer retains the required WAL files"; `lost` means the slot "is no
    # longer usable". Ordering by lost/unreserved first -- as this did -- filled the
    # sample with the slots that have ALREADY stopped holding WAL and could drop the
    # ones responsible for it, while the receipt claimed the sample was ordered by WAL
    # held. extended, then reserved, then furthest behind by restart_lsn.
    slot_count_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT count(*)::bigint::text AS slots, "
        "count(*) FILTER (WHERE NOT active)::bigint::text AS inactive_slots, "
        "count(*) FILTER (WHERE wal_status IN ('reserved','extended'))"
        "::bigint::text AS wal_retaining_slots, "
        "count(*) FILTER (WHERE wal_status = 'extended')"
        "::bigint::text AS wal_beyond_max_wal_size_slots, "
        "count(*) FILTER (WHERE wal_status = 'lost')"
        "::bigint::text AS lost_slots FROM pg_replication_slots) q",
        db_user,
        db_name,
    )
    if len(slot_count_rows) != 1:
        raise RuntimeError("replication_slot_count_output_invalid")
    slot_count = required_int(
        slot_count_rows[0].get("slots"), "replication_slot_count_output_invalid"
    )
    inactive_slot_count = required_int(
        slot_count_rows[0].get("inactive_slots"),
        "replication_slot_count_output_invalid",
    )
    # Slots RETAINING WAL, not slots that have stopped. The previous counter filtered
    # on ('unreserved','lost'), which is precisely the set that no longer retains it,
    # and reported the result as the WAL-pinning count.
    wal_retaining_slot_count = required_int(
        slot_count_rows[0].get("wal_retaining_slots"),
        "replication_slot_count_output_invalid",
    )
    wal_beyond_max_slot_count = required_int(
        slot_count_rows[0].get("wal_beyond_max_wal_size_slots"),
        "replication_slot_count_output_invalid",
    )
    lost_slot_count = required_int(
        slot_count_rows[0].get("lost_slots"),
        "replication_slot_count_output_invalid",
    )
    slots = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT slot_name, active, wal_status, safe_wal_size, "
        "restart_lsn::text AS restart_lsn FROM pg_replication_slots "
        # QUALIFIED, because an unqualified name in ORDER BY resolves to the OUTPUT
        # column first -- and `restart_lsn::text AS restart_lsn` makes that output a
        # text column. The sort was therefore lexicographic over hex LSNs, where
        # '10/...' precedes the OLDER 'F/...', so the bounded sample could fill with
        # newer slots and omit the one retaining the most WAL: the exact row the
        # ordering exists to keep. A qualified reference is unambiguously the input
        # column, so it sorts as pg_lsn.
        "ORDER BY (wal_status = 'extended') DESC, (wal_status = 'reserved') DESC, "
        "pg_replication_slots.restart_lsn ASC NULLS LAST, slot_name "
        f"LIMIT {REPLICATION_SLOT_INVENTORY_LIMIT}) q",
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
    # Resolve where the WAL directory actually is. `pg_wal` is commonly a real
    # directory inside PGDATA, but initdb --waldir or a later symlink can put it
    # elsewhere, and `du` does not dereference symlinks -- so the accounting has to know
    # rather than assume. Resolved on the host through the same read-only path.
    wal_container = f"{pgdata_container.rstrip('/')}/pg_wal" if pgdata_container else None
    wal_inside = None
    wal_resolved = None
    wal_device = None
    pgdata_device = None
    wal_same_filesystem = None
    # Mounts NESTED at or below PGDATA, from the container's own mount list. Neither
    # the path test nor the device test can see these: a volume or bind attached at
    # pg_wal's canonical destination hides a directory that still exists in the PGDATA
    # volume, and from the host `stat` and `du` inspect THAT underlying directory --
    # typically empty and on PGDATA's own device. So the device check I added for this
    # reports "same filesystem", `du -x` walks the empty placeholder, and
    # pg_ls_waldir()'s bytes are subtracted from a footprint that never contained them.
    # The mount list is the only place the nesting is visible.
    #
    # The mount PROVIDING PGDATA is excluded: that one is the footprint being measured,
    # not something hidden inside it.
    nested_mounts = []
    if pgdata_container is not None:
        pgdata_prefix = pgdata_container.rstrip("/")
        for source, destination in container_mounts:
            target = destination.rstrip("/")
            if target == mount_destination.rstrip("/"):
                continue
            if target == pgdata_prefix or target.startswith(f"{pgdata_prefix}/"):
                nested_mounts.append({"source": source, "destination": destination})
    if pgdata_host is not None:
        probe = run(["readlink", "-f", f"{pgdata_host.rstrip('/')}/pg_wal"])
        if probe.returncode == 0:
            wal_resolved = probe.stdout.strip() or None
        # Path identity is NOT enough. A separate Docker volume or bind mount attached
        # directly at pg_wal's canonical destination is not a symlink, so `readlink -f`
        # returns exactly the expected pathname and the path test says "inside". But
        # the PGDATA walk uses `du -x`, which does not cross filesystem boundaries, so
        # that WAL's bytes are not in the PGDATA total -- while the summary still
        # subtracts pg_ls_waldir()'s figure from this volume. The result is a
        # successful receipt whose partition is invalid, and nothing in the path check
        # can see it.
        #
        # Device identity can. `stat -c %d` is the same st_dev the kernel gives `du
        # -x` to decide whether to descend, so this tests exactly the property the
        # arithmetic depends on -- rather than enumerating mount kinds and hoping the
        # list is complete.
        for target, slot in (
            (f"{pgdata_host.rstrip('/')}/pg_wal", "wal"),
            (pgdata_host.rstrip("/"), "pgdata"),
        ):
            stat_probe = run(["stat", "-c", "%d", target])
            if stat_probe.returncode == 0:
                value = as_int(stat_probe.stdout.strip())
                if slot == "wal":
                    wal_device = value
                else:
                    pgdata_device = value
        if wal_device is not None and pgdata_device is not None:
            wal_same_filesystem = wal_device == pgdata_device
        if wal_resolved:
            wal_inside = (
                wal_resolved == f"{pgdata_host.rstrip('/')}/pg_wal"
                and wal_same_filesystem is True
                and not nested_mounts
            )
    inventory["wal"] = {
        **wal_rows[0],
        "settings": settings_rows[0],
        "replication_slots": slots,
        "replication_slot_count": slot_count,
        "inactive_replication_slot_count": inactive_slot_count,
        # wal_status in ('reserved','extended'): the slots that still retain WAL.
        "wal_retaining_replication_slot_count": wal_retaining_slot_count,
        # wal_status = 'extended': retaining WAL BEYOND max_wal_size, which is the
        # state that puts unexpected WAL on the volume.
        "wal_beyond_max_wal_size_replication_slot_count": wal_beyond_max_slot_count,
        # Counted even though such slots no longer retain WAL, because a lost slot
        # means WAL was already removed from under it -- a broken replica, not a
        # space finding, and the receipt should not make the operator infer it from
        # the sample.
        "lost_replication_slot_count": lost_slot_count,
        "replication_slot_limit": REPLICATION_SLOT_INVENTORY_LIMIT,
        "replication_slot_sample_order": "wal_retained_then_oldest_restart_lsn",
        "replication_slots_truncated": slot_count > REPLICATION_SLOT_INVENTORY_LIMIT,
        "prepared_transactions": prepared_rows[0]["prepared_transactions"],
        "container_directory": wal_container,
        "resolved_host_directory": wal_resolved,
        # Reported so an operator can see WHICH test decided it. A path that matches
        # with a different device is the case a path test alone calls "inside".
        "host_device": wal_device,
        "data_directory_device": pgdata_device,
        "same_filesystem_as_data_directory": wal_same_filesystem,
        # Named, so an operator can see WHAT is nested rather than only that the
        # partition was refused. Listed whether or not it is pg_wal: any mount inside
        # PGDATA breaks the single-footprint assumption this arithmetic rests on.
        "nested_container_mounts": nested_mounts,
        "directory_inside_pgdata": wal_inside,
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

try:
    # The one inventory left without a truncation flag. Unlike the index and
    # dead-tuple lists an operator could not tell an exhaustive result from a
    # partial one, so a database whose space is spread across many medium
    # relations looked as though it had no further relation-level consumers --
    # a silent omission in the section that answers "what is big".
    relation_rows = psql_json(
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
        "ORDER BY pg_total_relation_size(c.oid) DESC, n.nspname, c.relname "
        f"LIMIT {RELATION_INVENTORY_LIMIT + 1}) q",
        db_user,
        db_name,
    )
    inventory["relations"] = relation_rows[:RELATION_INVENTORY_LIMIT]
    inventory["relation_inventory_limit"] = RELATION_INVENTORY_LIMIT
    inventory["relation_inventory_truncated"] = (
        len(relation_rows) > RELATION_INVENTORY_LIMIT
    )
except RuntimeError as exc:
    section_failed(failures, inventory, "relations", exc)

try:
    # Ranked over EVERY user index, then capped -- not drawn from the largest relations.
    # Restricting to the top 20 relations first made the bound mean something other
    # than it said: the 21st relation can be mostly one very large index while the
    # first 20 are larger only because of heap data, so that index was absent and
    # indexes_truncated still reported false. In a receipt whose purpose is finding
    # reclaimable space, a large index invisible with no indication it was skipped is
    # the worst shape of omission. Ranking globally and capping afterwards makes
    # indexes_truncated describe the actual index population.
    inventory["indexes"] = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT n.nspname AS schema, c.relname AS \"table\", "
        "i.relname AS index_name, pg_relation_size(i.oid)::bigint AS index_bytes, "
        "x.indisunique AS is_unique, x.indisprimary AS is_primary, "
        "s.idx_scan::bigint AS idx_scan, "
        # BOUNDED. The row cap bounds rows, not bytes: an expression or partial index
        # can carry an arbitrarily large literal or predicate, and pg_get_indexdef()
        # returns the whole thing. That text is then buffered by run(), materialized
        # again by psql_json(), and serialized once more into the receipt, so a single
        # large definition can exhaust the client or the workflow log before any
        # structured receipt is emitted -- the same failure the row caps exist to
        # prevent, reached through column width instead of row count. Kept rather than
        # dropped, because the definition is how an operator tells a redundant index
        # from a needed one, and the original length says when it was cut.
        f"left(pg_get_indexdef(i.oid), {INDEX_DEFINITION_LIMIT}) AS definition, "
        "length(pg_get_indexdef(i.oid))::bigint AS definition_length, "
        f"(length(pg_get_indexdef(i.oid)) > {INDEX_DEFINITION_LIMIT}) "
        "AS definition_truncated "
        "FROM pg_index x JOIN pg_class i ON i.oid=x.indexrelid "
        "JOIN pg_class c ON c.oid=x.indrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "LEFT JOIN pg_stat_user_indexes s ON s.indexrelid=i.oid "
        "WHERE c.relkind IN ('r','p','m') "
        "AND n.nspname NOT IN ('pg_catalog','information_schema') "
        "AND n.nspname NOT LIKE 'pg_toast%' "
        "ORDER BY pg_relation_size(i.oid) DESC, n.nspname, c.relname, i.relname "
        # Indexes are unlimited in PostgreSQL, so this needs its own bound. One extra
        # row detects truncation, and the largest come first, so a cut loses the least
        # interesting rows rather than an arbitrary slice.
        f"LIMIT {INDEX_INVENTORY_LIMIT + 1}) q",
        db_user,
        db_name,
    )
    inventory["indexes_truncated"] = len(inventory["indexes"]) > INDEX_INVENTORY_LIMIT
    inventory["indexes"] = inventory["indexes"][:INDEX_INVENTORY_LIMIT]
    inventory["index_inventory_limit"] = INDEX_INVENTORY_LIMIT
    inventory["index_inventory_scope"] = "all_user_indexes_ranked_by_size"
    inventory["indexes_limit"] = INDEX_INVENTORY_LIMIT
    if inventory["indexes_truncated"]:
        inventory["indexes"] = inventory["indexes"][:INDEX_INVENTORY_LIMIT]
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
    # Ranked over EVERY user table by ESTIMATED DEAD BYTES, then capped. Not drawn from
    # the largest relations, and not ordered by relation size: dead tuples are
    # reclaimable space, and the table holding the most of it need not be among the
    # largest by total size -- a moderate table that is mostly dead outranks a huge one
    # that is almost all live. Drawing from the top 20 by size made that table
    # invisible, with no truncation flag to say anything had been left out, which is
    # the same defect as ranking indexes within the largest relations.
    #
    # Dead BYTES rather than dead tuple count, because the count says nothing about
    # width: a million tiny dead rows reclaim less than a thousand wide ones. It is an
    # estimate -- planner statistics times a size, named as such in the output -- and
    # numeric throughout, so no intermediate can overflow.
    dead_tuple_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT s.schemaname AS schema, s.relname AS name, "
        "s.n_live_tup::bigint AS n_live_tup, s.n_dead_tup::bigint AS n_dead_tup, "
        "s.last_vacuum::text AS last_vacuum, "
        "s.last_autovacuum::text AS last_autovacuum, "
        "s.last_analyze::text AS last_analyze, "
        "pg_total_relation_size(s.relid)::bigint AS total_bytes, "
        "round(s.n_dead_tup::numeric / "
        "NULLIF(s.n_live_tup + s.n_dead_tup,0),4) AS estimated_dead_fraction, "
        "(pg_table_size(s.relid)::numeric * s.n_dead_tup "
        "/ NULLIF(s.n_live_tup + s.n_dead_tup,0))::bigint "
        "AS estimated_dead_bytes "
        "FROM pg_stat_user_tables s "
        "ORDER BY (pg_table_size(s.relid)::numeric * s.n_dead_tup "
        "/ NULLIF(s.n_live_tup + s.n_dead_tup,0)) DESC NULLS LAST, "
        "s.schemaname, s.relname "
        f"LIMIT {DEAD_TUPLE_INVENTORY_LIMIT + 1}) q",
        db_user,
        db_name,
    )
    inventory["dead_tuples"] = dead_tuple_rows[:DEAD_TUPLE_INVENTORY_LIMIT]
    inventory["dead_tuple_inventory_limit"] = DEAD_TUPLE_INVENTORY_LIMIT
    inventory["dead_tuple_inventory_truncated"] = (
        len(dead_tuple_rows) > DEAD_TUPLE_INVENTORY_LIMIT
    )
    inventory["dead_tuple_inventory_scope"] = (
        "all_user_tables_ranked_by_estimated_dead_bytes"
    )
except RuntimeError as exc:
    section_failed(failures, inventory, "dead_tuples", exc)

try:
    ratings_attribution_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT g.generation_key, (p.derived_generation_id IS NOT NULL) AS published, "
        "count(*)::bigint::text AS chunks, "
        "sum(c.systems)::bigint::text AS systems, "
        "sum(c.physical_bodies)::bigint::text AS physical_bodies, "
        "sum(c.eligible_opportunities)::bigint::text AS eligible_opportunities "
        "FROM v3_derived.build_chunk c "
        "JOIN v3_meta.derived_generation g "
        "ON g.derived_generation_id=c.derived_generation_id "
        "LEFT JOIN v3_meta.current_derived_generation p "
        "ON p.singleton AND p.derived_generation_id=g.derived_generation_id "
        "GROUP BY g.generation_key, (p.derived_generation_id IS NOT NULL) "
        # The published generation sorts FIRST, so the bound can never drop the
        # one generation whose bytes an operator must not reclaim. Lexicographic
        # order alone would: generation keys carry no chronology, so the live
        # generation can sort anywhere, including past the limit.
        "ORDER BY (p.derived_generation_id IS NOT NULL) DESC, g.generation_key "
        # Bounded: generation manifests are never deleted, so this grows
        # without limit as generations accumulate. One extra row detects
        # truncation, and the ordering is deterministic so the same rows are
        # kept on every run.
        f"LIMIT {GENERATION_ATTRIBUTION_LIMIT + 1}) q",
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
            "SELECT g.generation_key, "
            "(p.derived_generation_id IS NOT NULL) AS published, "
            "count(*)::bigint::text AS chunks, "
            "sum(c.systems)::bigint::text AS systems "
            "FROM v3_derived.search_build_chunk c "
            "JOIN v3_meta.derived_generation g "
            "ON g.derived_generation_id=c.derived_generation_id "
            "LEFT JOIN v3_meta.current_derived_generation p "
            "ON p.singleton AND p.derived_generation_id=g.derived_generation_id "
            "GROUP BY g.generation_key, (p.derived_generation_id IS NOT NULL) "
            # The published generation sorts first; see the ratings query above.
            "ORDER BY (p.derived_generation_id IS NOT NULL) DESC, g.generation_key "
        # Bounded: generation manifests are never deleted, so this grows
        # without limit as generations accumulate. One extra row detects
        # truncation, and the ordering is deterministic so the same rows are
        # kept on every run.
        f"LIMIT {GENERATION_ATTRIBUTION_LIMIT + 1}) q",
            db_user,
            db_name,
        )
        if search_receipts_present
        else None
    )
    archetype_attribution_rows = (
        psql_json(
            "SELECT row_to_json(q)::text FROM ("
            "SELECT g.generation_key, "
            "(p.derived_generation_id IS NOT NULL) AS published, "
            "count(*)::bigint::text AS chunks, "
            "sum(c.systems)::bigint::text AS systems "
            "FROM v3_derived.archetype_build_chunk c "
            "JOIN v3_meta.derived_generation g "
            "ON g.derived_generation_id=c.derived_generation_id "
            "LEFT JOIN v3_meta.current_derived_generation p "
            "ON p.singleton AND p.derived_generation_id=g.derived_generation_id "
            "GROUP BY g.generation_key, (p.derived_generation_id IS NOT NULL) "
            # The published generation sorts first; see the ratings query above.
            "ORDER BY (p.derived_generation_id IS NOT NULL) DESC, g.generation_key "
        # Bounded: generation manifests are never deleted, so this grows
        # without limit as generations accumulate. One extra row detects
        # truncation, and the ordering is deterministic so the same rows are
        # kept on every run.
        f"LIMIT {GENERATION_ATTRIBUTION_LIMIT + 1}) q",
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
    published_keys: set[str] = set()
    # Per PRODUCT, because the products have different histories: a generation kept by
    # one product's query can fall beyond another's row cap, and then its absence from
    # that product means the cap cut it off, not that it is empty. Reporting zero made
    # a superseded
    # generation look as though it held none of a product's data -- which is exactly
    # the judgement someone deciding what to reclaim would act on.
    product_truncated: dict[str, bool] = {}
    for product, rows in attribution_rows.items():
        if rows is None:
            continue
        product_truncated[product] = len(rows) > GENERATION_ATTRIBUTION_LIMIT
        product_rows: dict[str, tuple[int, int]] = {}
        for row in rows:
            generation_key = row.get("generation_key")
            if not isinstance(generation_key, str) or not generation_key:
                raise RuntimeError("chunk_receipt_output_invalid")
            published = row.get("published")
            if not isinstance(published, bool):
                raise RuntimeError("chunk_receipt_output_invalid")
            if published:
                published_keys.add(generation_key)
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
            # null, not 0, when this product's own query was truncated and did not
            # mention this generation: "we did not look that far" and "there is
            # nothing there" are different facts, and only one of them is a licence
            # to reclaim.
            unknown = values is None and product_truncated.get(product, False)
            generation_attribution[f"{product}_chunks"] = (
                None
                if rows is None or unknown
                else values[0]
                if values is not None
                else 0
            )
            generation_attribution[f"{product}_systems"] = (
                None
                if rows is None or unknown
                else values[1]
                if values is not None
                else 0
            )
        ratings_counts = ratings_body_counts.get(generation_key)
        # Same rule for the ratings body counts.
        ratings_unknown = ratings_counts is None and product_truncated.get(
            "ratings", False
        )
        generation_attribution["ratings_physical_bodies"] = (
            None
            if ratings_unknown
            else ratings_counts[0]
            if ratings_counts is not None
            else 0
        )
        generation_attribution["ratings_eligible_opportunities"] = (
            None
            if ratings_unknown
            else ratings_counts[1]
            if ratings_counts is not None
            else 0
        )
        rows_by_generation[generation_key] = generation_attribution
    truncated = len(rows_by_generation) > GENERATION_ATTRIBUTION_LIMIT
    if len(published_keys) > 1:
        # v3_meta.current_derived_generation is a singleton, so two published keys
        # means the join or the output is not what this code believes it is.
        raise RuntimeError("chunk_receipt_published_generation_ambiguous")
    published_key = next(iter(published_keys), None)
    # Keep the published generation even when the bound would cut it. The SQL
    # already sorts it first, but the per-product queries are unioned here and
    # re-sorted into a stable key order for the receipt, which would reintroduce
    # exactly the lexicographic drop the SQL ordering prevents.
    ordered = sorted(rows_by_generation.items())
    kept = ordered[:GENERATION_ATTRIBUTION_LIMIT]
    if published_key is not None and published_key not in dict(kept):
        kept = sorted(
            kept[: GENERATION_ATTRIBUTION_LIMIT - 1]
            + [(published_key, rows_by_generation[published_key])]
        )
    inventory["generation_attribution"] = dict(kept)
    inventory["generation_attribution_limit"] = GENERATION_ATTRIBUTION_LIMIT
    inventory["generation_attribution_truncated"] = truncated
    inventory["generation_attribution_published_generation"] = published_key
    # A published generation with no chunk receipts at all cannot be retained,
    # and an operator reading this receipt must be able to tell that case from a
    # retention failure.
    inventory["generation_attribution_published_generation_retained"] = (
        published_key is not None
        and published_key in inventory["generation_attribution"]
    )
except RuntimeError as exc:
    section_failed(failures, inventory, "generation_attribution", exc)

try:
    # pg_database_size includes a database's files across ALL tablespaces, while
    # volume_used_bytes and the `-x` directory scan cover only the filesystem holding
    # PGDATA. A tablespace on another device would therefore be subtracted from this
    # volume despite consuming none of it; one elsewhere on the same device would be
    # counted twice -- once inside accounted_bytes and again as an outside candidate.
    # This action's arithmetic assumes single-filesystem storage, so rather than ship an
    # untested multi-filesystem accounting model it ENUMERATES non-default tablespaces
    # and refuses to present a partition when any exists, naming what it found. The
    # enumeration is also the evidence that none exists, which is the expected case and
    # was previously only assumed.
    # The DECISION needs only a count, so it is taken from an aggregate that cannot
    # grow with the number of tablespaces, and the enumeration below is a bounded
    # sample for the operator. Buffering a row per tablespace -- each costing a
    # pg_tablespace_size walk -- would let the safety path itself be what fails to
    # produce the structured stopped receipt, which is the one outcome a fail-closed
    # guard must not have.
    tablespace_count_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT count(*)::bigint::text AS non_default_count FROM pg_tablespace "
        "WHERE spcname NOT IN ('pg_default','pg_global')) q",
        db_user,
        db_name,
    )
    if len(tablespace_count_rows) != 1:
        raise RuntimeError("tablespace_count_output_invalid")
    non_default_tablespace_count = required_int(
        tablespace_count_rows[0].get("non_default_count"),
        "tablespace_count_output_invalid",
    )
    tablespaces = (
        psql_json(
            "SELECT row_to_json(q)::text FROM ("
            "SELECT spcname, pg_tablespace_location(oid) AS location, "
            "pg_tablespace_size(oid)::bigint AS size_bytes FROM pg_tablespace "
            "WHERE spcname NOT IN ('pg_default','pg_global') "
            "ORDER BY spcname "
            f"LIMIT {TABLESPACE_INVENTORY_LIMIT}) q",
            db_user,
            db_name,
        )
        if non_default_tablespace_count > 0
        else []
    )
    inventory["tablespaces"] = {
        "non_default": tablespaces,
        "non_default_count": non_default_tablespace_count,
        "non_default_limit": TABLESPACE_INVENTORY_LIMIT,
        "non_default_truncated": (
            non_default_tablespace_count > TABLESPACE_INVENTORY_LIMIT
        ),
        # From the COUNT, not from the bounded list: a truncated list is still a
        # cluster with tablespaces, and reading validity off the sample would make a
        # large enough cluster look single-filesystem.
        "single_filesystem_accounting_valid": non_default_tablespace_count == 0,
    }
except RuntimeError as exc:
    section_failed(failures, inventory, "tablespaces", exc)

try:
    # CLOSE THE MEASUREMENT WINDOW. This runs last, after every input the summary uses
    # -- the directory scans, the drill-down, and the database, WAL and
    # temporary-directory queries -- because all of them are inputs to one piece of
    # arithmetic and must describe one state. Closing it earlier (as it first did, right
    # after the drill-down) left every accounted-size query outside the window, so a
    # concurrent derived build or WAL change could make accounted_bytes describe a later
    # state than the directory totals and produce a wrong, or even negative,
    # unaccounted_bytes while the receipt reported success.
    #
    # It is also a section of its own, so failing to reconcile cannot overwrite the
    # scans above. The earlier bracket proved
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
    scan_budget.begin_closing_scan()
    # ONE scan for both the closing total and the breakdown. Two consecutive full
    # PGDATA walks can observe different states on a live cluster, which made
    # postgres_data_directory_bytes and pgdata_children_all mutually inconsistent --
    # able to drive the root-file remainder negative or misattribute bytes, with the
    # reconciliation validating only the earlier of the two. They also shared one
    # 300 s reserve, so two otherwise-valid walks could each take more than half of it
    # and the second would time out. The depth-1 scan reports the root's own total as a
    # row, so one walk gives both figures from one state.
    # Re-read the PGDATA breakdown and use the closing figures for the summary.
    # Accepting drift within tolerance is right -- a live database always moves -- but
    # it meant the inside-PGDATA candidates were computed from the OPENING total and
    # children while the database, WAL and filesystem figures came from the closing
    # state. On this cluster 0.5 % is several GiB, so the candidates could differ from
    # unaccounted_bytes by the whole accepted drift in a receipt reporting success.
    # Tolerating movement has to mean measuring every part of the arithmetic on the
    # same side of it.
    # du_stream, not du_rows: the omitted count and bytes are needed here for exactly
    # the reason the drill-down needs them. PGDATA with more than DU_DEFAULT_KEEP
    # immediate children -- many orphaned directories, which is precisely what this
    # inventory exists to find -- would otherwise have the dropped children's bytes
    # land in the root-file remainder and be reported as files directly in PGDATA.
    closing_usage, pgdata_children_omitted, pgdata_children_omitted_bytes = du_stream(
        ["du", "--null", "-x", "-B1", "--max-depth=1", pgdata_host],
        scan_budget,
        "postgres_data_directory_usage_failed",
        keep=DU_DEFAULT_KEEP,
        expect_path=pgdata_host,
    )
    pgdata_final = next(
        (
            row["bytes"]
            for row in closing_usage
            if row["path"].rstrip("/") == pgdata_host
        ),
        None,
    )
    if pgdata_final is None:
        raise RuntimeError("postgres_data_directory_usage_total_missing")
    postgres_data_directory_bytes = pgdata_final
    # The WAL figure has to come from the same state as the directory breakdown. It was
    # the earlier SQL value, so ordinary top-level WAL growth between the two -- within
    # the accepted drift -- was being labelled "subdirectories and files pg_ls_waldir
    # does not list", which is both wrong and points at the opposite conclusion from
    # the truth: normal WAL reported as unexpected storage.
    closing_wal = psql_json(
        "SELECT row_to_json(q)::text FROM (SELECT "
        "coalesce(sum(size),0)::bigint AS bytes FROM pg_ls_waldir()) q",
        db_user,
        db_name,
    )
    if not closing_wal or "bytes" not in closing_wal[0]:
        raise RuntimeError("wal_bytes_not_reconciled")
    wal_bytes_at_close = closing_wal[0]["bytes"]
    inventory["wal"]["bytes_at_window_close"] = wal_bytes_at_close
    # Measure pg_wal AGAIN, beside the SQL read. The closing walk visited pg_wal at
    # some earlier point in its own traversal, so WAL recycled in between makes the
    # walk's figure the LARGER one -- and the difference then came out positive and was
    # emitted as an "unlisted subdirectories and files" candidate. That is
    # already-removed ordinary WAL presented as reclaimable storage, and because the
    # smaller SQL value also feeds accounted_bytes the closure stayed true while it
    # happened. Only the negative sign took the drift path, so the shrink case the
    # adjacent comment acknowledged was the one still landing in candidates.
    #
    # pg_wal is bounded by max_wal_size plus wal_keep_size, so a depth-0 scan of it is
    # cheap -- it needs its own allowance rather than a share of another scan's, for
    # the same reason every other closing scan does.
    wal_host_dir = f"{pgdata_host.rstrip('/')}/pg_wal"
    scan_budget.begin_closing_scan(WAL_DIRECTORY_SCAN_SECONDS)
    wal_dir_bytes_at_sql = du_total(wal_host_dir, scan_budget)
    # BRACKETED: a second pg_ls_waldir() read after the scan. One read before it was
    # not enough -- that only moved the asymmetry, because WAL generated DURING the
    # scan (up to 60 s) makes the directory figure exceed the earlier SQL total, and
    # the difference was again emitted as unlisted/reclaimable WAL when it is ordinary
    # top-level WAL. With a read either side, the listed figure at the scan's own
    # instant is known to lie between them.
    reclosing_wal = psql_json(
        "SELECT row_to_json(q)::text FROM (SELECT "
        "coalesce(sum(size),0)::bigint AS bytes FROM pg_ls_waldir()) q",
        db_user,
        db_name,
    )
    if not reclosing_wal or "bytes" not in reclosing_wal[0]:
        raise RuntimeError("wal_bytes_not_reconciled")
    wal_bytes_after_scan = reclosing_wal[0]["bytes"]
    # NOT a bracket, because WAL is not monotonic. Taking max(before, after) assumed
    # the scan-time value lies between the endpoints, and it need not: WAL can grow
    # during the scan and be recycled before the second read, so the directory figure
    # can exceed BOTH totals and the excess ordinary WAL is emitted as reclaimable
    # again. That makes this the fourth round on one quantity -- closing figure, then
    # measure beside the read, then bracket -- each fix attacked by the next, because
    # the error is not in any implementation but in asserting an exact classification
    # over a quantity that cannot be pinned to one instant.
    #
    # So: classify only when the two reads AGREE, which is the one case where the
    # scan can be paired to a single WAL snapshot. Otherwise emit no pg_wal candidate
    # at all and record why. Refusing is stable under this line of attack in a way
    # that a fifth correction term would not be -- there is no window left to point
    # at -- and an unexplained figure is the honest outcome where a classified one
    # would be a guess presented as a finding.
    wal_snapshot_stable = wal_bytes_at_close == wal_bytes_after_scan
    wal_listed_for_candidate = wal_bytes_after_scan
    # accounted_bytes uses the figure taken after every scan, so it is genuinely the
    # closing one.
    wal_bytes_at_close = wal_bytes_after_scan
    inventory["wal"]["bytes_at_window_close"] = wal_bytes_at_close
    inventory["wal"]["directory_bytes_beside_sql_read"] = wal_dir_bytes_at_sql
    inventory["wal"]["listed_bytes_before_directory_scan"] = closing_wal[0]["bytes"]
    inventory["wal"]["listed_bytes_after_directory_scan"] = wal_bytes_after_scan
    inventory["wal"]["listed_bytes_for_candidate"] = (
        wal_listed_for_candidate if wal_snapshot_stable else None
    )
    inventory["wal"]["directory_paired_to_one_snapshot"] = wal_snapshot_stable
    inventory["wal"]["listed_bytes_scan_bracket_width"] = abs(
        wal_bytes_after_scan - closing_wal[0]["bytes"]
    )
    pgdata_children_all = sorted(
        (row for row in closing_usage if row["path"].rstrip("/") != pgdata_host),
        key=lambda item: (-item["bytes"], item["path"]),
    )
    inventory["postgres_data_directory_usage"] = {
        "path": pgdata_host,
        "bytes": postgres_data_directory_bytes,
        "child_count": len(pgdata_children_all) + pgdata_children_omitted,
        "children_omitted_by_cap": pgdata_children_omitted,
        "children_omitted_bytes": pgdata_children_omitted_bytes,
        "children": pgdata_children_all[:40],
        "measured_at": "window_close",
    }
    # Break `base` down in `du`'s OWN metric. The base remainder was previously
    # base's `du` bytes minus the `pg_database_size` totals, which compares two
    # DIFFERENT measurements: GNU du reports allocated filesystem blocks, while
    # pg_database_size sums each entry's st_size. On a cluster of this size the
    # per-file block rounding and the directories' own allocation add up to a
    # persistently positive difference, so a perfectly healthy base/ produced an
    # "orphaned storage" candidate out of arithmetic noise -- in the one receipt whose
    # entire purpose is to say what is reclaimable.
    #
    # One extra depth-1 scan of base costs a second traversal of the bulk of PGDATA,
    # which is why the reserve covers two calls. It buys more than metric agreement:
    # an unreferenced OID directory is reported BY PATH instead of disappearing into
    # an anonymous remainder, which is the difference between a finding an operator
    # can act on and a number they cannot explain.
    # A temp-directory probe taken BESIDE the base scan, because the base cap guard
    # below has to decide existence from an observation adjacent to the scan it
    # guards -- not from the opening query (base/pgsql_tmp created in between left it
    # None and the guard permitted a breakdown whose cap had dropped a directory
    # accounted_bytes now subtracts) and not from the final read either, which comes
    # after this scan. The figure accounted_bytes uses is read separately at the very
    # end; this one answers only "does it exist".
    temp_probe_rows = psql_json(
        "SELECT row_to_json(q)::text FROM (SELECT CASE WHEN "
        "COALESCE((pg_stat_file('base/pgsql_tmp',true)).isdir,false) THEN "
        "(SELECT sum(size)::bigint FROM pg_ls_tmpdir()) "
        "ELSE NULL::bigint END AS temp_directory_bytes) q",
        db_user,
        db_name,
    )
    if len(temp_probe_rows) != 1:
        raise RuntimeError("temp_probe_output_invalid")
    temp_directory_exists_at_close = (
        temp_probe_rows[0].get("temp_directory_bytes") is not None
    )
    inventory["temp_directory_beside_base_scan"] = {
        "exists": temp_directory_exists_at_close,
        "bytes": temp_probe_rows[0].get("temp_directory_bytes"),
    }
    base_row = next(
        (
            row
            for row in pgdata_children_all
            if row["path"].rstrip("/").rsplit("/", 1)[-1] == "base"
        ),
        None,
    )
    if base_row is None:
        # REQUIRED, exactly as pg_wal is. A data directory always has a base/, so its
        # absence from the retained children means the size-based cap took it -- and
        # then the omitted-children aggregate reports ALL live database storage as an
        # unaccounted candidate while accounted_bytes already subtracts those
        # databases. Marking the optional breakdown unavailable made the closure flag
        # null, so the operation would still report success with the entire database
        # sitting in the candidate list as reclaimable space. That is the largest
        # possible version of this error, so it fails closed instead.
        raise RuntimeError("base_directory_not_observed_in_data_directory")
    elif live_database_oids is None:
        # Deliberately not computed from an incomplete OID set: a live database whose
        # OID was missing would be reported as orphaned storage.
        base_breakdown = {"available": False, "reason": "live_database_oids_unbounded"}
    else:
        # Its OWN full allowance. The PGDATA re-read above can take nearly all of one,
        # and the closing WAL query and this classification run after it, so against a
        # single phase deadline this scan could start with almost nothing left and time
        # out on a walk it would have finished -- and because its failure is an
        # optional unavailable breakdown, the action would still report success while
        # silently dropping the base attribution it exists to produce.
        scan_budget.begin_closing_scan()
        base_path = base_row["path"].rstrip("/")
        # Its own failure boundary. This scan refines ONE candidate; the PGDATA
        # re-read, the WAL close and the df close around it are what the summary
        # cannot do without. Letting a denied or timed-out base scan raise would take
        # the whole reconciliation -- and so the whole summary -- down over an optional
        # refinement, which is the opposite of what the unavailable path is for.
        try:
            base_usage, base_omitted, base_omitted_bytes = du_stream(
                ["du", "--null", "-x", "-B1", "--max-depth=1", base_path],
                scan_budget,
                "base_directory_usage_failed",
                keep=DU_DEFAULT_KEEP,
                expect_path=base_path,
            )
        except RuntimeError as base_exc:
            base_breakdown = {"available": False, "reason": str(base_exc)[:240]}
        else:
            # base's OWN root total, from this scan. Using the total measured by the
            # earlier PGDATA walk would mix two snapshots: base's children here against
            # base's size from minutes ago. A shrink in between then appeared as
            # reclaimable "files directly in base/", and growth drove other_bytes
            # negative and left the partition false in a receipt reporting success.
            base_total = next(
                (
                    row["bytes"]
                    for row in base_usage
                    if row["path"].rstrip("/") == base_path
                ),
                None,
            )
            # The temp directory, probed again AFTER the scan. One probe before it
            # was not enough: a pgsql_tmp created while the up-to-300-second base
            # walk ran, and then dropped by the row cap, left the pre-scan boolean
            # false while the closing query counts its bytes in accounted_bytes --
            # so the omitted aggregate presents live temp bytes as a candidate and
            # the negative metric-difference term can keep the closure true. Same
            # principle as the OID set below and as pg_wal: a quantity that cannot
            # be pinned to one snapshot is not classified.
            temp_after_rows = psql_json(
                "SELECT row_to_json(q)::text FROM (SELECT CASE WHEN "
                "COALESCE((pg_stat_file('base/pgsql_tmp',true)).isdir,false) THEN "
                "(SELECT sum(size)::bigint FROM pg_ls_tmpdir()) "
                "ELSE NULL::bigint END AS temp_directory_bytes) q",
                db_user,
                db_name,
            )
            if len(temp_after_rows) != 1:
                raise RuntimeError("temp_probe_output_invalid")
            temp_exists_after_scan = (
                temp_after_rows[0].get("temp_directory_bytes") is not None
            )
            # Re-read the OID set around the scan and require it UNCHANGED. A database
            # created between the earlier query and this scan has a live base/<oid>
            # directory that the stale set does not contain, so it would be emitted as
            # "not a live database directory" -- naming a live database's storage as a
            # reclaim candidate, which is the most dangerous output this receipt could
            # produce. Within the reconciliation tolerance the growth alone would not
            # have been noticed. A dropped database is the same error reversed: its
            # directory may still exist while the set no longer lists it.
            oid_rows_after = psql_json(
                "SELECT row_to_json(q)::text FROM ("
                "SELECT oid::text AS oid, datname FROM pg_database ORDER BY oid "
                f"LIMIT {DATABASE_INVENTORY_LIMIT + 1}) q",
                db_user,
                db_name,
            )
            oids_after = {
                row.get("oid")
                for row in oid_rows_after
                if isinstance(row.get("oid"), str)
            }
            if base_total is None:
                base_breakdown = {
                    "available": False,
                    "reason": "base_directory_total_missing",
                }
            elif oids_after != set(live_database_oids):
                base_breakdown = {
                    "available": False,
                    "reason": "live_database_oids_changed_during_base_scan",
                }
            elif abs(base_total - base_row["bytes"]) > tolerance:
                # The breakdown's figures and the PGDATA walk's base child must agree,
                # because the candidate partition subtracts base as an accounted child
                # measured by THAT walk and adds these figures back. Beyond the
                # tolerance they describe different directories, so the difference is
                # refused rather than quietly shifting the partition.
                base_breakdown = {
                    "available": False,
                    "reason": "base_directory_changed_during_scan",
                    "bytes_at_pgdata_scan": base_row["bytes"],
                    "bytes_at_base_scan": base_total,
                    "tolerance_bytes": tolerance,
                }
            else:
                live_bytes = 0
                temp_dir_bytes = 0
                observed_oids: set[str] = set()
                unreferenced: list[dict[str, Any]] = []
                for row in base_usage:
                    if row["path"].rstrip("/") == base_path:
                        continue
                    name = row["path"].rstrip("/").rsplit("/", 1)[-1]
                    if name in live_database_oids:
                        live_bytes += row["bytes"]
                        observed_oids.add(name)
                    elif name == "pgsql_tmp":
                        temp_dir_bytes += row["bytes"]
                    else:
                        unreferenced.append(row)
                # Whatever base's total exceeds its measured entries by: files sitting
                # directly in base/. Its own figure rather than folded into the
                # unreferenced total, because "a stray file in base/" and "a directory
                # that is not a live database" are different findings calling for
                # different actions. Entries the row cap dropped are their own figure
                # again, for the same reason, and both are emitted as candidates --
                # subtracting the omitted aggregate without adding it back deleted
                # those bytes from the partition entirely.
                other_bytes = (
                    base_total
                    - live_bytes
                    - temp_dir_bytes
                    - sum(row["bytes"] for row in unreferenced)
                    - base_omitted_bytes
                )
                # base/pgsql_tmp has to survive the cap for the same reason the live
                # OID directories do: its bytes are already inside accounted_bytes via
                # pg_ls_tmpdir(), so if the SIZE-based cap drops it, the live temporary
                # directory is presented among the unaccounted candidates while still
                # being subtracted as accounted -- and the negative metric-difference
                # term that follows can leave the closure flag true. Only required when
                # the directory actually exists: pg_ls_tmpdir()'s wrapper returns NULL
                # when base/pgsql_tmp is not a directory, and a cluster that has never
                # spilled to disk legitimately has none.
                # The CLOSING observation, not the opening one. base/pgsql_tmp
                # created after the opening temp query but before the closing one
                # left this reading None, so the guard permitted a breakdown whose
                # cap had dropped a directory whose bytes accounted_bytes now
                # subtracts -- and the negative metric difference could offset them
                # and leave the closure true. The existence test and the figure that
                # is subtracted have to come from the same observation.
                temp_directory_exists = temp_directory_exists_at_close
                temp_directory_observed = any(
                    row["path"].rstrip("/").rsplit("/", 1)[-1] == "pgsql_tmp"
                    for row in base_usage
                )
                if observed_oids != set(live_database_oids):
                    # A live database directory the SIZE-based row cap dropped is not in
                    # live_database_directory_bytes, so its bytes land in the
                    # omitted-entry candidate while accounted_bytes still subtracts that
                    # database's full pg_database_size. The resulting negative metric
                    # difference can even keep the closure flag true while accounted
                    # live storage sits among the candidate bytes -- presented, in a
                    # receipt about reclaiming space, as space to reclaim. A breakdown
                    # that did not observe every live database cannot classify base/,
                    # so it is refused, naming which OIDs were missed.
                    base_breakdown = {
                        "available": False,
                        "reason": "live_database_directories_not_all_observed",
                        "live_database_count": len(live_database_oids),
                        "observed_live_database_count": len(observed_oids),
                        "unobserved_live_database_oids": sorted(
                            set(live_database_oids) - observed_oids
                        )[:40],
                        "entries_omitted_by_cap": base_omitted,
                    }
                elif temp_directory_exists != temp_exists_after_scan:
                    base_breakdown = {
                        "available": False,
                        "reason": "temporary_directory_changed_during_base_scan",
                        "exists_before_scan": temp_directory_exists,
                        "exists_after_scan": temp_exists_after_scan,
                    }
                elif (
                    temp_directory_exists or temp_exists_after_scan
                ) and not temp_directory_observed:
                    base_breakdown = {
                        "available": False,
                        "reason": "temporary_directory_not_observed",
                        "entries_omitted_by_cap": base_omitted,
                    }
                else:
                    base_breakdown = {
                        "available": True,
                        "path": base_path,
                        "bytes": base_total,
                        "bytes_at_pgdata_scan": base_row["bytes"],
                        "live_database_directory_bytes": live_bytes,
                        "temporary_directory_bytes": temp_dir_bytes,
                        "unreferenced_directory_bytes": sum(
                            row["bytes"] for row in unreferenced
                        ),
                        "unreferenced_entries": sorted(
                            unreferenced, key=lambda item: (-item["bytes"], item["path"])
                        )[:40],
                        "unreferenced_entry_count": len(unreferenced),
                        "other_bytes": other_bytes,
                        "entries_omitted_by_cap": base_omitted,
                        "entries_omitted_bytes": base_omitted_bytes,
                        "metric": "du_allocated_blocks",
                        "live_database_count": len(live_database_oids),
                    }
    inventory["postgres_base_directory_breakdown"] = base_breakdown
    # Re-read the filesystem too. The PGDATA bracket closes over the database, but a
    # sibling consumer -- a backup, a Docker layer, a host log -- can change during the
    # drill-down and the SQL inventory, and only a fresh `df` can see that. Closing on
    # the reading taken right after the root scan would leave unaccounted_bytes and the
    # df/du residual stale while the receipt reported success.
    # Re-read the DATABASE and TEMP totals here too. accounted_bytes is described as a
    # closing figure, and the WAL and PGDATA figures are, but these two came from the
    # SQL phase -- so a database growing or shrinking in between (freely, within the
    # multi-GiB PGDATA tolerance) landed in database_size_metric_difference_bytes,
    # which is documented as a du-versus-st_size difference and nothing else. That put
    # temporal drift inside a term labelled metrological, and left the headline
    # unaccounted figure wrong by the database change while the closure still held.
    #
    # Cheap to fix properly: two aggregates, no row lists. The opening values are kept
    # as a bracket so the movement is visible rather than merely corrected.
    closing_database_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT coalesce(sum(pg_database_size(oid)),0)::bigint::text AS total_bytes, "
        "coalesce(sum(CASE WHEN datname=current_database() "
        "THEN pg_database_size(oid) ELSE 0 END),0)::bigint::text "
        "AS operating_bytes FROM pg_database) q",
        db_user,
        db_name,
    )
    if len(closing_database_rows) != 1:
        raise RuntimeError("closing_database_total_output_invalid")
    operating_database_bytes_at_close = required_int(
        closing_database_rows[0].get("operating_bytes"),
        "closing_database_total_output_invalid",
    )
    database_total_bytes_at_close = required_int(
        closing_database_rows[0].get("total_bytes"),
        "closing_database_total_output_invalid",
    )
    closing_temp_rows = psql_json(
        "SELECT row_to_json(q)::text FROM (SELECT CASE WHEN "
        "COALESCE((pg_stat_file('base/pgsql_tmp',true)).isdir,false) THEN "
        "(SELECT sum(size)::bigint FROM pg_ls_tmpdir()) "
        "ELSE NULL::bigint END AS temp_directory_bytes) q",
        db_user,
        db_name,
    )
    if len(closing_temp_rows) != 1:
        raise RuntimeError("closing_temp_output_invalid")
    temp_bytes_at_close = closing_temp_rows[0].get("temp_directory_bytes") or 0
    # Recheck the TABLESPACE set here too, beside the closing database totals it
    # qualifies. A non-default tablespace created after the opening count left
    # single_filesystem_accounting_valid true while pg_database_size had begun
    # including bytes outside the selected filesystem -- bytes then subtracted from
    # volume_used, with the resulting negative base metric difference able to keep the
    # closure true. A successful receipt that understates unaccounted space is the one
    # shape of error this whole section exists to rule out, so the assumption is
    # re-measured at the moment the figures that depend on it are taken.
    closing_tablespace_rows = psql_json(
        "SELECT row_to_json(q)::text FROM ("
        "SELECT count(*)::bigint::text AS non_default_count FROM pg_tablespace "
        "WHERE spcname NOT IN ('pg_default','pg_global')) q",
        db_user,
        db_name,
    )
    if len(closing_tablespace_rows) != 1:
        raise RuntimeError("closing_tablespace_count_output_invalid")
    non_default_tablespace_count_at_close = required_int(
        closing_tablespace_rows[0].get("non_default_count"),
        "closing_tablespace_count_output_invalid",
    )
    inventory["tablespaces_at_window_close"] = {
        "non_default_count": non_default_tablespace_count_at_close,
        "single_filesystem_accounting_valid": (
            non_default_tablespace_count_at_close == 0
        ),
        "measured_at": "window_close",
    }
    inventory["databases_at_window_close"] = {
        "operating_database_bytes": operating_database_bytes_at_close,
        "database_total_bytes": database_total_bytes_at_close,
        "temp_directory_bytes": temp_bytes_at_close,
        "operating_database_drift_bytes": (
            operating_database_bytes_at_close - (operating_database_bytes or 0)
        ),
        "database_total_drift_bytes": (
            database_total_bytes_at_close - (database_total_bytes or 0)
        ),
        "measured_at": "window_close",
    }
    volume_used_final = df_used_bytes(mount_source)
    opening = inventory.get("volume_used_bracket")
    if not isinstance(opening, dict) or "bytes_before_filesystem_scan" not in opening:
        raise RuntimeError("volume_used_bracket_unavailable")
    window_drift = abs(volume_used_final - opening["bytes_before_filesystem_scan"])
    window_tolerance = opening["tolerance_bytes"]
    opening["bytes_after_window"] = volume_used_final
    opening["window_drift_bytes"] = (
        volume_used_final - opening["bytes_before_filesystem_scan"]
    )
    opening["reconciled"] = window_drift <= window_tolerance
    if window_drift > window_tolerance:
        raise RuntimeError(
            f"volume_changed_during_window:drift_{window_drift}_over_{window_tolerance}"
        )
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
    tablespace_section = inventory.get("tablespaces")
    # section_failed leaves an error object here, which IS a dict, so a missing validity
    # flag used to be read as "tablespaces found" -- telling the operator that
    # tablespaces exist when they were never successfully inspected. Those are different
    # facts needing different responses, so the flag must be present and boolean.
    if not isinstance(tablespace_section, dict) or not isinstance(
        tablespace_section.get("single_filesystem_accounting_valid"), bool
    ):
        raise RuntimeError("tablespaces_unavailable")
    # BOTH observations have to hold. The opening one proves none existed when the
    # scans began; the closing one proves none appeared while they ran, which is when
    # pg_database_size would have started including bytes outside this filesystem.
    closing_tablespaces = inventory.get("tablespaces_at_window_close")
    if not isinstance(closing_tablespaces, dict) or not isinstance(
        closing_tablespaces.get("single_filesystem_accounting_valid"), bool
    ):
        raise RuntimeError("closing_tablespaces_unavailable")
    if not tablespace_section["single_filesystem_accounting_valid"] or not (
        closing_tablespaces["single_filesystem_accounting_valid"]
    ):
        # Named, not swallowed: the receipt lists the tablespaces so the operator knows
        # exactly which assumption broke and what would have to be measured.
        raise RuntimeError("tablespaces_present_single_filesystem_accounting_invalid")
    # The RECONCILED readings, not the opening `df` from the volume section: that one is
    # taken before the scans and is never validated against anything, so a summary
    # figure derived from it could be stale while the receipt reported success.
    # Recording a bracket and then not using it would have been the appearance of
    # rigour without the substance. Which reconciled reading depends on the figure:
    # unaccounted_bytes uses the CLOSING one below, because the database and WAL totals
    # it subtracts are closing totals; the df/du residual uses
    # bytes_after_filesystem_scan, because it is paired with a du scan from that moment.
    # Both are reported, so a reader can see which window each figure describes.
    used_bracket = inventory.get("volume_used_bracket")
    if not isinstance(used_bracket, dict) or used_bracket.get("reconciled") is not True:
        raise RuntimeError("volume_used_not_reconciled")
    # The CLOSING reading, validated across the whole window. The post-root-scan value
    # is only validated against the opening one, so a sibling growing or shrinking by
    # up to the tolerance during the drill-down or the SQL phase would leave every
    # figure derived from it stale in a receipt that reported success. Collecting the
    # closing reading and then not using it would be the same mistake as recording a
    # bracket and ignoring it.
    if "bytes_after_window" not in used_bracket:
        raise RuntimeError("volume_used_window_not_closed")
    volume_used = used_bracket["bytes_after_window"]
    # The CLOSING database totals, for the same reason the PGDATA and WAL figures are
    # the closing ones: accounted_bytes claims to describe one state. Taken from the
    # SQL phase, any database movement in between was absorbed by
    # database_size_metric_difference_bytes -- a term documented as a du-versus-st_size
    # difference and nothing else -- so temporal drift hid inside a metrological term
    # and the headline unaccounted figure was wrong by the database change.
    if (
        operating_database_bytes_at_close is None
        or database_total_bytes_at_close is None
        or temp_bytes_at_close is None
    ):
        raise RuntimeError("closing_database_sizes_unavailable")
    operating_database_bytes = operating_database_bytes_at_close
    other_databases_bytes = database_total_bytes_at_close - operating_database_bytes
    if other_databases_bytes < 0:
        raise RuntimeError("closing_database_total_output_invalid")
    # The CLOSING WAL figure, for the same reason the PGDATA total is the closing one:
    # every input to this arithmetic has to describe one state. Collecting
    # bytes_at_window_close and then leaving accounted_bytes on the opening value put
    # the candidate partition and the figure it explains on different sides of the
    # accepted drift.
    wal_bytes = (
        inventory["wal"].get("bytes_at_window_close")
        if isinstance(inventory.get("wal"), dict)
        else None
    )
    if wal_bytes is None:
        raise RuntimeError("wal_bytes_not_reconciled")
    temp_bytes = temp_bytes_at_close
    accounted_bytes = (
        operating_database_bytes + other_databases_bytes + wal_bytes + temp_bytes
    )
    if usage_full is None:
        raise RuntimeError("volume_directory_usage_unavailable")
    if postgres_data_directory_bytes is None:
        raise RuntimeError("postgres_data_directory_usage_unavailable")
    # `pg_wal` can live elsewhere (initdb --waldir, or a symlink), and `du` does not
    # dereference symlinks, so a same-filesystem target would appear as an OUTSIDE
    # candidate while its bytes were also subtracted here, and an external-filesystem
    # target would be subtracted from a volume it does not occupy. This action's
    # arithmetic assumes the WAL directory is inside PGDATA, so -- as with
    # tablespaces -- it verifies that rather than assuming it, and refuses to present a
    # partition when it is not, naming what it found instead of shipping untested
    # multi-location accounting.
    wal_location = inventory.get("wal", {})
    if isinstance(wal_location, dict) and wal_location.get("directory_inside_pgdata") is not True:
        raise RuntimeError("wal_directory_outside_pgdata")
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
    # The SCAN-SIDE data-directory size, not the closing one. `usage_full` contains the
    # data directory's footprint as it was during the root walk, so subtracting the
    # closing figure from that ancestor charges the intervening database churn to a
    # SIBLING path: a shrink inflated an outside candidate such as /var/lib by the
    # removed database bytes, and growth suppressed it and could drive it negative.
    # post_scan_volume_drift_bytes does not undo that -- it is a volume-level term and
    # says nothing about which path the bytes were attributed to -- so the receipt could
    # report success, and a true closure, while presenting database churn as reclaimable
    # outside storage. That is the single most misleading row this action could emit.
    #
    # pgdata_after is the measurement taken immediately after the root walk, so it is
    # the one that describes the same state as `usage_full`. The difference against the
    # closing figure the inside candidates use is carried as a signed closure term,
    # because the two sides of the partition are now deliberately measured at different
    # moments and the identity has to say so.
    if pgdata_after is None or pgdata_before is None:
        raise RuntimeError("postgres_data_directory_scan_side_size_unavailable")
    # The LARGER of the bracket, because `pgdata_after` is not a measurement of PGDATA
    # at the moment the root walk visited it -- it is a separate full traversal started
    # only once the whole walk had finished. The footprint actually inside `usage_full`
    # lies somewhere in the bracket, and the two errors are not symmetric:
    #
    #   subtract too LITTLE -> the ancestor is inflated by database bytes, and the
    #                          receipt points at a sibling directory as reclaimable
    #                          space that is really the live database;
    #   subtract too MUCH   -> the ancestor is understated, under-reporting genuine
    #                          sibling space.
    #
    # Only the first can tell an operator to delete the database's bytes from
    # somewhere else, so the conservative choice is the maximum. The bracket's width is
    # reported as the honest size of what cannot be resolved.
    pgdata_scan_side = max(pgdata_before, pgdata_after)
    if data_dir not in exclusive and strict_ancestors:
        container = max(strict_ancestors, key=len)
        exclusive[container] -= pgdata_scan_side
    # MEASUREMENT UNCERTAINTY, not signed corrections.
    #
    # Every figure here is a measurement taken at a different moment from the one it is
    # compared with, and on a live multi-terabyte filesystem nothing holds still: the
    # database writes, WAL is created and recycled, `df` is one instant while `du` is a
    # minutes-long walk. The receipt used to assert that the candidate list summed
    # EXACTLY to the unaccounted figure and defend that claim with a growing set of
    # signed correction terms -- one per way the two sides could disagree. That claim
    # was never needed to answer the question this action exists for ("what large
    # things on this volume are not the database"), and it is not achievable: each
    # correction created another pair of measurements to disagree about.
    #
    # The same bracket widths make a better error bar than they made corrections. Each
    # one is recorded here with the reason it exists, summed into
    # measurement_uncertainty_bytes, and the receipt states the shortfall against that
    # width instead of claiming to balance. The safety property is kept where it
    # matters: a shortfall LARGER than the uncertainty means the list genuinely fails
    # to explain the figure -- a big directory missing -- and that still fails closed.
    uncertainty_terms: list[dict[str, Any]] = []

    def uncertain(term: str, bytes_: int, path: str | None = None) -> None:
        """Record a measurement width. Magnitude only: a width has no direction."""
        if bytes_:
            entry: dict[str, Any] = {"term": term, "bytes": abs(bytes_)}
            if path is not None:
                entry["path"] = path
            uncertainty_terms.append(entry)
    # The last positive-only drop on a computed difference, and the same hazard as the
    # remainders: the ancestor holding the data directory has `pgdata_after` subtracted
    # from it, and that figure is measured at a different instant than `usage_full`, so
    # PGDATA growing in between can drive the ancestor's exclusive size negative -- by
    # up to the bracket tolerance, which is 1 GiB. Silently dropping it put that much
    # outside the partition in a receipt whose closure flag would then be false.
    #
    # A negative cannot be a candidate, so it is carried as a named signed term. Zero
    # is still dropped: a directory of no bytes is not a finding.
    outside = []
    for path, size in exclusive.items():
        if path == data_dir or path.startswith(f"{data_dir}/"):
            continue
        if size > 0:
            outside.append(
                {
                    "path": path,
                    "exclusive_bytes": size,
                    "inside_data_directory": False,
                }
            )
        elif size < 0:
            uncertain("outside_directory_negative_remainder", size, path)
    # Subtracting the whole data directory removes more than accounted_bytes covers.
    # accounted_bytes is the databases (base/), WAL (pg_wal) and the temp directories;
    # PGDATA also holds `global`, `pg_xact`, `pg_multixact`, replication-slot state and
    # often relative log files. Dropping those with the rest of the data directory left
    # them inside unaccounted_bytes but absent from every candidate, so the candidate
    # list could not reconcile or locate the value it claimed to explain. They are
    # therefore kept as candidates in their own right, flagged so nobody mistakes them
    # for ordinary directories: some of them must never be deleted.
    # The complete list, not the truncated receipt view: see the note where it is built.
    if pgdata_children_all is None:
        raise RuntimeError("postgres_data_directory_usage_unavailable")
    pgdata_children = pgdata_children_all
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
    # Every remainder in this section is a measured total minus figures measured by a
    # DIFFERENT instrument or at a DIFFERENT moment, so each one can come out negative:
    # WAL recycled between the directory walk and pg_ls_waldir(), base/ changing between
    # the two walks, children the row cap dropped. A negative cannot be a candidate --
    # there is no negative storage to reclaim -- but silently dropping it is what broke
    # the closure, repeatedly and in a receipt reporting success. So it becomes a NAMED
    # SIGNED TERM in the identity instead. This is one helper rather than a filter at
    # each site because the same `if x > 0` mistake has now been found at five of
    # them; a shared route makes the next remainder correct by construction. The
    # outside rows above take the same route inline, because they append to `outside`
    # rather than `inside` and so cannot share the helper's body.

    def remainder(path: str, value: int, *, term: str) -> None:
        if value > 0:
            inside.append(
                {
                    "path": path,
                    "exclusive_bytes": value,
                    "inside_data_directory": True,
                }
            )
        elif value < 0:
            uncertain(term, value, path)
    # PGDATA also holds files directly at its root -- PG_VERSION, postgresql.conf,
    # postmaster.pid, and anything anyone has ever left there. The depth-1 root total
    # includes them, but iterating only the child directories drops them, while the
    # outside partition has already subtracted the whole PGDATA total. They would sit
    # inside unaccounted_bytes and appear in no candidate at all -- and an unexpected
    # large file directly under PGDATA is exactly the kind of thing this action exists
    # to surface, so it is the worst possible row to lose.
    # pg_wal is excluded as accounted, but wal_bytes comes from pg_ls_waldir(), which
    # lists only pg_wal's top-level ordinary files and documents that it excludes
    # directories. pg_wal/archive_status and PostgreSQL 18's pg_wal/summaries are
    # therefore inside neither figure, so the difference becomes its own candidate.
    # wal_bytes is pg_ls_waldir()'s figure for the LIVE WAL directory, which on
    # PostgreSQL 18 is pg_wal. Subtracting it from pg_xlog as well would treat a stale
    # pg_xlog as though it had been measured: smaller than the live WAL it would vanish
    # from the candidates entirely, larger and only its excess would show -- and an
    # unexpected directory full of old WAL is exactly the reclaimable space this action
    # is looking for. So pg_wal gets the subtraction and pg_xlog is reported whole.
    # The BRACKETED figure for the candidate -- the larger end of the two reads either
    # side of the pg_wal scan -- not the closing one. The candidate is a difference
    # against a du measurement taken between those reads, so pairing it with a figure
    # from outside the bracket reintroduces exactly the invented candidate the bracket
    # exists to prevent. accounted_bytes still uses the closing figure.
    wal_for_subtraction = wal_bytes
    if isinstance(inventory.get("wal"), dict):
        paired = inventory["wal"].get("listed_bytes_for_candidate")
        if paired is not None:
            wal_for_subtraction = paired
    wal_snapshot_stable = (
        inventory["wal"].get("directory_paired_to_one_snapshot", False)
        if isinstance(inventory.get("wal"), dict)
        else False
    )
    for name, subtract in (("pg_wal", wal_for_subtraction), ("pg_xlog", 0)):
        wal_child = next(
            (
                row
                for row in pgdata_children
                if row["path"].rstrip("/").rsplit("/", 1)[-1] == name
            ),
            None,
        )
        # For pg_wal, the candidate is computed from the measurement taken BESIDE the
        # SQL read, and the walk-to-SQL movement becomes a signed term. Both figures
        # are du measurements of the same directory at two instants, so their
        # difference is temporal by construction and belongs nowhere near a reclaim
        # candidate -- in either direction.
        walk_figure = wal_child["bytes"] if wal_child is not None else None
        if name == "pg_wal" and wal_child is not None:
            wal_child = dict(wal_child, bytes=wal_dir_bytes_at_sql)
        if wal_child is None:
            # pg_wal is REQUIRED, pg_xlog is not. The subtraction of wal_bytes happens
            # only here, so a pg_wal that the size-based child cap dropped would skip
            # it while the omitted-children aggregate still reports those bytes as an
            # unaccounted candidate -- live, already-accounted WAL presented as a
            # reclaim candidate, with the closure flag false and the receipt still
            # reporting success. The data directory always has a WAL directory, so its
            # absence from the retained children means the cap took it, which is a
            # partition this action cannot honestly present.
            #
            # pg_xlog genuinely does not exist on a PostgreSQL 18 cluster, and its
            # absence means only that there is no stale pre-10 directory to report.
            if name == "pg_wal":
                raise RuntimeError("wal_directory_not_observed_in_data_directory")
            continue
        # When pg_wal could not be paired to one snapshot, the whole difference is
        # unresolvable rather than unlisted content: it goes to the closure as a
        # signed term and NO candidate is emitted. The pg_xlog arm is unaffected --
        # it subtracts nothing, so there is no second measurement to pair with.
        if name == "pg_wal" and not wal_snapshot_stable:
            unresolvable = wal_child["bytes"] - subtract
            if unresolvable:
                uncertain("pg_wal_unpairable_to_one_snapshot", unresolvable, wal_child["path"])
            continue
        wal_unlisted = wal_child["bytes"] - subtract
        label = (
            "subdirectories and files pg_ls_waldir does not list"
            if subtract
            else "not the live WAL directory on PostgreSQL 18; unexpected storage"
        )
        # Still signed, for the residue: pg_wal's du figure and pg_ls_waldir()'s sum
        # are now taken at essentially the same instant, but they remain two different
        # instruments, so a small difference either way is possible and is temporal
        # rather than storage.
        remainder(
            f"{wal_child['path']} ({label})",
            wal_unlisted,
            term=f"{name}_measurement_drift",
        )
        # The walk-to-SQL movement, as its own signed term. The inside candidates now
        # describe pg_wal as it was beside the SQL read, while the PGDATA total they
        # partition came from the walk, so the difference has to be named or the
        # closure is out by it.
        if walk_figure is not None and walk_figure != wal_child["bytes"]:
            uncertain(f"{name}_walk_to_sql_drift", walk_figure - wal_child["bytes"], wal_child["path"])
    # `base` is excluded as accounted, but pg_database_size scans base/<database OID>
    # rather than the whole directory, and the temp figure covers base/pgsql_tmp's
    # ordinary files. Anything else under base -- an orphaned OID directory from a
    # dropped database, a stray file -- is inside neither figure, so excluding the whole
    # child would remove it from every candidate while leaving it in unaccounted_bytes.
    # Orphaned storage under base is exactly the reclaimable space this action looks
    # for, so it is reported as its own candidates.
    #
    # From the SAME-METRIC breakdown, never from base's `du` bytes minus the
    # `pg_database_size` totals: du measures allocated blocks and pg_database_size sums
    # st_size, so that subtraction turned ordinary block rounding across tens of
    # thousands of relation files into a standing "orphaned storage" candidate. When
    # the breakdown is unavailable, NO base candidate is emitted and the reason is
    # recorded -- an unexplained gap in the partition is honest, a fabricated reclaim
    # target is not.
    base_breakdown_used = isinstance(base_breakdown, dict) and base_breakdown.get(
        "available"
    )
    # Where the metric difference goes now that it is no longer a false candidate. The
    # candidates measure base in `du`'s allocated blocks; accounted_bytes subtracts
    # pg_database_size's and pg_ls_tmpdir's st_size sums for the same storage. The
    # difference is real and is neither reclaimable nor unaccounted -- it is two tools
    # measuring one thing differently -- so it is named as its own term and the
    # partition closes against it explicitly. Left unnamed it would simply be a
    # partition that does not add up in a receipt claiming that it does.
    metric_difference = None
    if base_breakdown_used:
        assert isinstance(base_breakdown, dict)
        metric_difference = (
            base_breakdown["live_database_directory_bytes"]
            + base_breakdown["temporary_directory_bytes"]
        ) - (operating_database_bytes + other_databases_bytes + temp_bytes)
        # The accepted base drift, as a signed term. The add-backs below are measured by
        # the BASE walk while the outer partition removed base as an accounted child
        # measured by the PGDATA walk, so any nonzero drift -- including drift well
        # inside the tolerance that is deliberately accepted -- shifts the candidate
        # total by exactly that amount and made the closure false in an otherwise
        # correct receipt. Requiring equality instead would fail the inventory on
        # ordinary database activity, which is what the tolerance exists to prevent, so
        # the drift is carried rather than refused.
        base_drift = base_breakdown["bytes_at_pgdata_scan"] - base_breakdown["bytes"]
        if base_drift:
            uncertain("base_directory_scan_drift", base_drift, base_breakdown["path"])
        # Named individually: "base/16401 is not a live database" is actionable in a
        # way that a lump remainder never is.
        # A NUMERIC name cannot be proven unreferenced by catalog reads at all.
        # A database being created copies its new base/<oid> tree as part of that
        # statement,
        # and concurrent transactions cannot see the uncommitted pg_database row --
        # so both OID reads can legitimately miss a directory that is about to be a
        # live database. Calling that "not a live database directory" in a receipt
        # someone reclaims from is the worst error this action can make, and no
        # number of extra catalog reads fixes it: the row is invisible until the
        # copy finishes.
        #
        # Its BYTES still belong in the partition -- they are real and unaccounted --
        # so the row is emitted with the classification stated honestly instead of
        # being suppressed or asserted. A non-numeric stray is different: nothing in
        # PostgreSQL creates one under base/, so it is reportable as unreferenced.
        for row in base_breakdown["unreferenced_entries"]:
            name = row["path"].rstrip("/").rsplit("/", 1)[-1]
            numeric = name.isdigit()
            inside.append(
                {
                    "path": (
                        f"{row['path']} (numeric name not in the live database set; "
                        "may be a database still being created -- not proven "
                        "reclaimable)"
                        if numeric
                        else f"{row['path']} (not a live database directory)"
                    ),
                    "exclusive_bytes": row["bytes"],
                    "inside_data_directory": True,
                    "proven_unreferenced": not numeric,
                }
            )
        tail = base_breakdown["unreferenced_directory_bytes"] - sum(
            row["bytes"] for row in base_breakdown["unreferenced_entries"]
        )
        remainder(
            (
                f"{base_breakdown['path']} (further entries that are not live "
                "database directories)"
            ),
            tail,
            term="base_unreferenced_tail",
        )
        remainder(
            f"{base_breakdown['path']} (files directly in this directory)",
            base_breakdown["other_bytes"],
            term="base_direct_files",
        )
        # Entries the row cap dropped get their own aggregate candidate. other_bytes
        # subtracts them so they are not mislabelled as files sitting directly in
        # base/, but subtracting without adding back deleted them from the partition
        # outright -- and with at most DATABASE_INVENTORY_LIMIT live databases, a base/
        # with thousands of entries is overwhelmingly the unexpected directories this
        # inventory exists to find. Losing exactly those bytes is the worst possible
        # place for a silent gap.
        if base_breakdown["entries_omitted_bytes"] > 0:
            inside.append(
                {
                    "path": (
                        f"{base_breakdown['path']} "
                        f"({base_breakdown['entries_omitted_by_cap']} further entries "
                        "the row cap dropped; paths not retained)"
                    ),
                    "exclusive_bytes": base_breakdown["entries_omitted_bytes"],
                    "inside_data_directory": True,
                }
            )
    pgdata_root_files = (
        postgres_data_directory_bytes
        - sum(row["bytes"] for row in pgdata_children)
        - pgdata_children_omitted_bytes
    )
    remainder(
        f"{data_dir} (files directly in this directory)",
        pgdata_root_files,
        term="postgres_data_directory_direct_files",
    )
    # And the PGDATA children the row cap dropped, for the same reason as base/'s. The
    # subtraction above stops them being reported as files directly in the data
    # directory, but the outside partition has already removed the whole PGDATA total,
    # so without a candidate of their own those bytes left the partition altogether --
    # a successful receipt whose candidates did not add up to the figure it reported.
    if pgdata_children_omitted_bytes > 0:
        inside.append(
            {
                "path": (
                    f"{data_dir} ({pgdata_children_omitted} further children the row "
                    "cap dropped; paths not retained)"
                ),
                "exclusive_bytes": pgdata_children_omitted_bytes,
                "inside_data_directory": True,
            }
        )
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
    # Pair du with the df reading taken IMMEDIATELY AFTER the same scan, not with the
    # closing one. Subtracting a scan total from a df reading minutes of SQL later makes
    # every byte written or freed in between look like filesystem metadata or a
    # deleted-but-open file -- which is precisely the category this figure exists to
    # measure, so the contamination is indistinguishable from the signal. The drift
    # between the two df readings is already reconciled against a tolerance, so it is
    # small; but "small" is measured against the volume, while this residual can be
    # smaller still, so a tolerable drift can be a large fraction of it. Both readings
    # are reported so an operator can see which window each figure describes;
    # unaccounted_bytes keeps the closing reading, because the database and WAL figures
    # it subtracts are themselves closing figures.
    volume_used_at_scan = used_bracket.get("bytes_after_filesystem_scan")
    if not isinstance(volume_used_at_scan, int):
        raise RuntimeError("volume_used_at_scan_unavailable")
    residual = volume_used_at_scan - du_root_bytes
    # How much the volume moved WHILE the root walk was running: the width of the
    # window `du_root_bytes` was measured across, and therefore the residual's error
    # bar. Both ends come from the volume bracket, which already reconciled them
    # against the tolerance.
    opening_used = used_bracket.get("bytes_before_filesystem_scan")
    if not isinstance(opening_used, int):
        raise RuntimeError("volume_used_opening_unavailable")
    intra_scan_drift = abs(volume_used_at_scan - opening_used)
    non_database_directory_bytes = sum(
        item["exclusive_bytes"] for item in candidates if not item["inside_data_directory"]
    )
    unaccounted_inside_data_directory_bytes = sum(
        item["exclusive_bytes"] for item in candidates if item["inside_data_directory"]
    )
    # THE THREE TERMS THAT ARE NOT RECLAIMABLE SPACE.
    #
    # The candidates are `du` measurements from the scan window. unaccounted_bytes is a
    # closing `df` reading minus accounted totals read during the SQL phase. Those are
    # three different instants, and no amount of care makes them one: `df`, `du` and six
    # SQL queries cannot be read atomically on a live multi-terabyte cluster. Within the
    # accepted drift the receipt used to present the candidates as a partition of
    # unaccounted_bytes anyway, so up to the whole tolerance -- several GiB here -- could
    # be hidden inside a candidate, or quietly missing from one, in a receipt reporting
    # success.
    #
    # So each difference is named instead, and the identity the summary asserts is
    # stated with them included. All three are temporal or metrological artefacts, NOT
    # storage anyone can free:
    #   post_scan_volume_drift_bytes -- sibling consumers moving between the root scan
    #     and the close; already bounded by the reconciliation tolerance, now visible
    #     rather than absorbed.
    #   database_size_metric_difference_bytes -- du's allocated blocks against
    #     pg_database_size's and pg_ls_tmpdir's st_size for the same files.
    #   filesystem_minus_directory_scan_bytes -- df against du, for the whole volume.
    post_scan_volume_drift = volume_used - volume_used_at_scan
    unaccounted_at_scan = volume_used_at_scan - accounted_bytes
    # The two sides of the partition are now deliberately measured at different moments:
    # the outside candidates subtract the data directory as it was during the root walk,
    # and the inside candidates partition its size at window close. The difference is a
    # signed term, like every other difference between two measurements of the same
    # storage -- and naming it here is what lets the outside rows stay attributed to the
    # right paths instead of absorbing database churn.
    pgdata_span = postgres_data_directory_bytes - pgdata_scan_side
    if pgdata_span:
        uncertain("postgres_data_directory_scan_to_close_drift", -pgdata_span, data_dir)
    # The remaining widths, which the signed-term model never counted because they were
    # not corrections to anything -- they are simply how precisely each figure is known.
    uncertain("volume_used_across_window", post_scan_volume_drift)
    uncertain("postgres_data_directory_bracket", pgdata_after - pgdata_before)
    uncertain("filesystem_minus_directory_scan", residual)
    if metric_difference is not None:
        uncertain("database_size_du_versus_st_size", metric_difference)
    wal_bracket = inventory.get("wal", {})
    if isinstance(wal_bracket, dict):
        uncertain(
            "wal_listed_bracket", wal_bracket.get("listed_bytes_scan_bracket_width") or 0
        )
    databases_closing = inventory.get("databases_at_window_close", {})
    if isinstance(databases_closing, dict):
        uncertain(
            "database_total_across_window",
            databases_closing.get("database_total_drift_bytes") or 0,
        )
    measurement_uncertainty = sum(item["bytes"] for item in uncertainty_terms)
    candidate_total = (
        non_database_directory_bytes + unaccounted_inside_data_directory_bytes
    )
    # How much of the unaccounted figure the candidate list does not explain, against
    # how precisely the two sides are known. This replaces an exact identity: the
    # question that matters is "does the list account for the figure, to within what
    # these measurements can resolve", not "do the numbers balance to the byte" -- which
    # they cannot on a live filesystem and never needed to.
    candidate_shortfall = unaccounted_at_scan - candidate_total
    # Whether the list is even eligible for that comparison. An unavailable base
    # breakdown means base/ contributes NO candidate rows at all, so the shortfall then
    # contains a gap this action put there knowingly -- and a known gap cannot be told
    # apart from the unknown one the comparison exists to detect. The verdict is
    # therefore null rather than false: "not asserted", not "disproved". The shortfall
    # and the uncertainty are still reported, because they are still the best available
    # description of what was measured.
    candidate_list_complete = bool(base_breakdown_used)
    accounted_within_uncertainty = (
        abs(candidate_shortfall) <= measurement_uncertainty
        if candidate_list_complete
        else None
    )
    inventory["summary"] = {
        "volume_used_bytes": volume_used,
        "operating_database_bytes": operating_database_bytes,
        "other_databases_bytes": other_databases_bytes,
        "wal_bytes": wal_bytes,
        "accounted_bytes": accounted_bytes,
        "unaccounted_bytes": volume_used - accounted_bytes,
        # The figure the candidates actually partition: same window as the scans they
        # come from. unaccounted_bytes stays, because it is the one an operator asking
        # "how much of this volume is not the database right now" wants.
        "unaccounted_bytes_at_directory_scan": unaccounted_at_scan,
        "post_scan_volume_drift_bytes": post_scan_volume_drift,
        "database_size_metric_difference_bytes": metric_difference,
        "candidate_total_bytes": candidate_total,
        # Each one is a signed difference between two measurements of the same storage,
        # taken by different instruments or at different moments. They are part of the
        # identity, not commentary on it, and none of them is reclaimable space.
        "measurement_uncertainty_terms": uncertainty_terms,
        "measurement_uncertainty_bytes": measurement_uncertainty,
        # Stated, not implied. When the breakdown is unavailable the metric difference
        # is unknown, so the closure cannot be asserted -- and saying so is the point.
        #
        # The df/du residual is part of the identity, not an aside. Every candidate is
        # a `du` measurement, so they sum towards du_root_bytes, while
        # unaccounted_bytes_at_directory_scan starts from a `df` reading; the gap
        # between those two is exactly `residual`. Asserting the closure without it
        # made the flag false on ANY real filesystem -- df and du always differ by
        # metadata and deleted-but-open blocks -- so a perfectly exact inventory would
        # have reported that its own candidates did not partition the figure they
        # explain. It passed only in a fixture where df and du agree, which is the one
        # place the error could not be seen.
        "candidate_shortfall_bytes": candidate_shortfall,
        "candidate_list_complete": candidate_list_complete,
        "candidates_account_for_unaccounted_within_uncertainty": (
            accounted_within_uncertainty
        ),
        "postgres_data_directory_bytes": postgres_data_directory_bytes,
        # Which figure the outside candidates were actually built against, and how wide
        # the unresolvable part is. The root walk visits the data directory at an
        # unknown instant inside itself, so the footprint in usage_full is only known
        # to lie within the bracket; this is its width, and the conservative end is
        # what was used. Reported because an operator comparing an outside candidate
        # against a reclaim decision needs to know its error bar, not just its value.
        "postgres_data_directory_bytes_used_for_outside_rows": pgdata_scan_side,
        "postgres_data_directory_within_walk_uncertainty_bytes": abs(
            pgdata_after - pgdata_before
        ),
        "non_database_directory_bytes": non_database_directory_bytes,
        "unaccounted_inside_data_directory_bytes": unaccounted_inside_data_directory_bytes,
        "directory_scan_root_bytes": du_root_bytes,
        "volume_used_bytes_at_directory_scan": volume_used_at_scan,
        "filesystem_minus_directory_scan_bytes": residual,
        # The residual's own error bar. `df` is a single instant but `du` is a
        # traversal, so a sibling consumer changing WHILE the root walk runs leaves
        # du_root_bytes holding that directory's earlier or partly-observed size. The
        # before/after volume bracket permits that drift (deliberately -- refusing on
        # any movement would fail every run on a live host) but does not remove it
        # from the residual, so ordinary directory growth could be labelled filesystem
        # metadata or blocks held by deleted-but-open files. Those are the two things
        # an operator chases when this figure is flagged, and neither would be there.
        #
        # So the bracket width is reported as the residual's uncertainty, and
        # significance now requires the residual to exceed BOTH the proportional
        # threshold and the amount the filesystem is known to have moved. A residual
        # smaller than its own error bar is not evidence of anything.
        "filesystem_minus_directory_scan_uncertainty_bytes": intra_scan_drift,
        "filesystem_minus_directory_scan_is_significant": (
            abs(residual)
            > volume_used_at_scan * DF_DU_RESIDUAL_SIGNIFICANT_PPM // 1_000_000
            and abs(residual) > intra_scan_drift
        ),
        "largest_unaccounted_directories": candidates[:10],
        # The totals above sum the COMPLETE candidate list, so hiding the tail without
        # saying so leaves an operator unable to reconcile the figure the method claims
        # to partition -- and a normal PGDATA has enough unaccounted cluster
        # directories to make that likely rather than exceptional.
        "candidate_count": len(candidates),
        "candidates_omitted": max(0, len(candidates) - 10),
        "candidates_omitted_bytes": sum(
            item["exclusive_bytes"] for item in candidates[10:]
        ),
        "method": (
            "accounted_bytes = operating_database_bytes + other_databases_bytes + "
            "wal_bytes + current PostgreSQL temporary-directory bytes; "
            "unaccounted_bytes = volume_used_bytes - accounted_bytes. "
            "largest_unaccounted_directories is a non-overlapping partition: each row "
            "reports its own total minus the totals of its scanned children, the "
            "measured PostgreSQL data-directory size is subtracted from the deepest "
            "scanned directory that contains it, and the data directory itself is "
            "excluded. Directories UNDER it are not all excluded: only the accounted "
            "ones are, so those an accounted figure does not cover (global, pg_xact, "
            "pg_multixact, pg_stat, pg_stat_tmp, pg_xlog, replication-slot state, "
            "pg_wal's unlisted subdirectories, base/ entries that are not live "
            "database directories, relative log files, and files at the data "
            "directory's own root) appear as rows flagged inside_data_directory. No "
            "row counts the database twice, and no row counts another row's bytes. "
            "Rows outside the data directory sum to non_database_directory_bytes; rows "
            "inside it sum to unaccounted_inside_data_directory_bytes. Some of the "
            "latter must never be deleted -- they are listed so the summary can locate "
            "every byte it reports as unaccounted, not as reclaim suggestions. "
            "The base/ rows come from postgres_base_directory_breakdown, a depth-1 du "
            "scan that identifies live database directories by OID, so each entry that "
            "is NOT a live database is named by path. They are NOT base/'s du total "
            "minus the pg_database_size totals: du measures allocated filesystem "
            "blocks and pg_database_size sums each entry's st_size, so that subtraction "
            "reported ordinary per-file block rounding as orphaned storage. That "
            "difference is database_size_metric_difference_bytes, which is two tools "
            "measuring the same files differently and is not reclaimable. When the "
            "breakdown is unavailable (reason recorded there) no base/ row is emitted. "
            "THIS RECEIPT DOES NOT CLAIM THE CANDIDATES BALANCE EXACTLY, and it is "
            "worth saying why, because an exact claim would look stronger. Every figure "
            "here is measured at a different moment from the one it is compared with: "
            "df is a single instant, du is a walk lasting minutes, and the SQL queries "
            "fall between them, while the database writes and WAL is created and "
            "recycled throughout. There is no instant at which all of these could be "
            "read together, so an exact identity could only ever be defended by adding "
            "one correction term per way the measurements can disagree -- and each such "
            "term is another pair of readings to disagree about. The question this "
            "action exists to answer does not need it: an operator deciding what to "
            "reclaim needs to know which large things on the volume are not the "
            "database, and how precisely that is known. "
            "So candidate_shortfall_bytes is unaccounted_bytes_at_directory_scan minus "
            "candidate_total_bytes -- how much of the figure the listed directories do "
            "not explain -- and measurement_uncertainty_bytes is the summed width of "
            "every window involved, itemised in measurement_uncertainty_terms: the "
            "volume's movement across the window and across the root scan, the PGDATA "
            "and base/ and WAL brackets, the database total's movement, df against du "
            "(filesystem_minus_directory_scan_bytes), and du's allocated blocks against "
            "pg_database_size's st_size sums (database_size_metric_difference_bytes). "
            "candidates_account_for_unaccounted_within_uncertainty is whether the "
            "shortfall fits inside that width. None of those terms is storage anyone "
            "can free; they are how precisely the two sides are known. "
            "A shortfall LARGER than the uncertainty is a different matter and fails "
            "the operation: it means the listed directories genuinely do not explain "
            "the figure, which is what a large directory missing from the scan looks "
            "like. "
            "That comparison is only made when candidate_list_complete is true. An "
            "unavailable base breakdown removes base/'s rows from the list entirely, so "
            "the shortfall then contains a gap this action left knowingly, and a known "
            "gap cannot be told apart from the unknown one the check is for. The "
            "verdict is null in that case -- not asserted, not disproved -- while the "
            "shortfall and uncertainty are still reported. "
            "The du scan covers the whole "
            "filesystem that holds the data directory, not only the PostgreSQL volume "
            "subdirectory. filesystem_minus_directory_scan_bytes is "
            "volume_used_bytes_at_directory_scan minus directory_scan_root_bytes -- the "
            "df reading taken immediately after that same scan, NOT volume_used_bytes, "
            "which is the closing reading that unaccounted_bytes uses because the "
            "database and WAL figures it subtracts are also closing figures. Pairing "
            "the scan with the closing reading would charge every byte written or freed "
            "by the intervening SQL to this residual, which is the same category the "
            "residual measures and so could not be told apart from it. "
            "df reports filesystem space and du "
            "estimates space used by files, so this gap is filesystem metadata and "
            "blocks held by deleted-but-open files -- but only beyond "
            "filesystem_minus_directory_scan_uncertainty_bytes, which is how much the "
            "volume moved while the root walk was running. df is one instant and du "
            "is a traversal, so a sibling changing during the walk leaves its earlier "
            "or partly-observed size in directory_scan_root_bytes; a residual no "
            "larger than that width is ordinary movement rather than metadata or a "
            "deleted-but-open file, and is not flagged. "
            "Reserved blocks are NOT a cause: "
            "they explain size minus (used + available) because they remain free while "
            "being unavailable to ordinary users, so they never enter `used`; changing "
            "the reserved-block percentage cannot close this residual. The gap is not "
            "directory usage and cannot be reclaimed by deleting a directory. "
            "non_database_drill_down names the directory that owns the non-database "
            "usage, which a single bounded-depth scan from the root cannot do: GNU du "
            "shows directories at most N levels below the scanned root, so a depth-2 "
            "scan from / emits /var/lib but never /var/lib/docker"
        ),
    }
    # A FALSE closure is a failure, not a field. The whole point of computing the
    # identity is that the receipt's own method claims the candidates partition
    # unaccounted_bytes_at_directory_scan; when they provably do not -- a race, or a
    # measurement discrepancy this action does not model -- recording the verdict and
    # still reporting `success` hands an operator a complete-looking inventory whose
    # arithmetic it has already disproved. That is the one receipt that must not look
    # authoritative, because the next step taken from it deletes something.
    #
    # Recorded directly rather than raised, because section_failed replaces the
    # section's whole value with an error object -- which would delete the summary
    # that is the only evidence of what failed to close. The gap, the candidates and
    # The safety property, kept where it earns its place: a shortfall LARGER than the
    # measurement uncertainty is not a rounding artefact -- it means the candidate list
    # genuinely fails to explain the figure, which is what a big directory missing from
    # the scan looks like. That still fails closed, and every term stays in the receipt
    # for diagnosis; only the status changes. A shortfall within the uncertainty is
    # reported and no longer treated as an error, because it never was one. `None` is
    # left alone -- the candidate list is knowingly incomplete, so there is nothing to
    # disprove.
    if accounted_within_uncertainty is False:
        failures.append(
            "candidates_do_not_account_for_unaccounted:"
            f"shortfall_{candidate_shortfall}_uncertainty_{measurement_uncertainty}"
        )
except (KeyError, StopIteration, TypeError, RuntimeError) as exc:
    section_failed(failures, inventory, "summary", RuntimeError(str(exc)))

# Reported at the very end, after every scan including the closing reconciliation.
# Snapshotting it inside a section captured only the scans that had run by then, so a
# degraded closing measurement could be reported as a clean, reconciled success.
receipt["tolerated_file_churn"] = list(tolerated_churn)
receipt["directory_scans_degraded"] = any(
    entry.get("accepted_possibly_undercounting") for entry in tolerated_churn
)
receipt["failures"] = sorted(set(failures))
receipt["status"] = "success" if not failures else "stopped"
print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
sys.exit(0 if not failures else 1)
PY
