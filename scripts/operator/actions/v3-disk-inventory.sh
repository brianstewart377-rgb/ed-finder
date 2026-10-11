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
# -B on both interpreters. Every receipt states filesystem_writes_performed: false
# unconditionally, and this action runs as root; without -B, importing `platform` or any
# stdlib module whose bytecode cache is missing or stale writes .pyc files under the
# runtime's directories. Small, but a read-only claim has to be true to be worth making.
if ! "$PYTHON_BIN" -B -c 'import platform, sys; raise SystemExit(0 if platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 14) else 1)'; then
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-disk-inventory","status":"stopped","failures":["python314_required"],"read_only":true,"direct_db_access_performed":false,"db_writes_performed":false,"env_files_read":false,"private_keys_read":false,"service_changes_performed":false,"filesystem_writes_performed":false}'
    exit 1
fi

exec "$PYTHON_BIN" -B - <<'PY'
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
INDEX_INVENTORY_LIMIT = 200
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
# Held back from the budget for the closing reconciliation, so the walk can never consume
# the budget the reconciliation needs and take the whole section down with it. TWO full
# per-call allowances, because the closing phase makes two scans: the PGDATA re-read and
# the depth-1 breakdown of `base` that keeps the base remainder in one metric. Reserving
# one would leave the second running against whatever the first left over, which is a
# different way of failing the scan the reserve exists to protect.
RECONCILE_RESERVE_SECONDS = 2 * DIRECTORY_USAGE_TIMEOUT_SECONDS
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


def run(
    argv: list[str], *, timeout: int = PROCESS_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
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
    killed before emitting any receipt. A partial receipt that says where it stopped
    beats no receipt at all.

    The budget **owns its reserve** rather than taking it as an argument at each call
    site. Passing it per call meant forgetting it at four of them, which silently
    unreserved the reserve: the closing reconciliation scan is mandatory, so any earlier
    scan allowed to spend its time takes the whole section down. Here every call is
    held back from the reserve by default and only `release_reserve()` opens it, for the
    one scan the reserve exists for.
    """

    def __init__(self, seconds: int, reserve_seconds: int) -> None:
        self.total_seconds = seconds
        self.reserve_seconds = reserve_seconds
        self._reserved = True
        self._deadline = time.monotonic() + seconds

    def release_reserve(self) -> None:
        """Open the reserve, for the closing reconciliation scan only.

        This also RESTARTS the reserve's clock. The reserve has to be an allowance
        rather than a slice of an advancing deadline: between the scans and this call,
        the database, WAL, relation, index, attribution and tablespace queries run
        without touching the budget at all, while the wall clock keeps moving. Those
        sections could therefore consume the supposedly protected 300 s and the closing
        scan would raise directory_scan_budget_exhausted immediately -- the one scan the
        reserve exists for, denied by time it never asked for.
        """
        self._reserved = False
        self._deadline = time.monotonic() + self.reserve_seconds

    def reserve(self) -> float:
        return self.reserve_seconds if self._reserved else 0.0

    def remaining(self) -> float:
        """Time left that the caller may actually use, reserve already deducted."""
        return self._deadline - time.monotonic() - self.reserve()

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
        pending = ""
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
        vanished_only = (
            bool(stderr_lines)
            and not stderr_truncated
            and all(
                any(marker in line for marker in DU_VANISHED_MARKERS)
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
tolerance: int = 0
# Same reason again: the database totals are computed in the `databases` section and
# read by the summary. Previously the summary re-derived them by iterating
# inventory["databases"], which on a failed section is a failure DICT -- iterating it
# yields its key strings and raises TypeError, escaping the section handler.
operating_database_bytes: int | None = None
other_databases_bytes: int | None = None
# The live database OID directory names, read in the `databases` section and used by
# the base breakdown in the reconciliation section. None means "not established",
# which suppresses the breakdown rather than guessing from a partial set.
live_database_oids: dict[str, str] | None = None
base_breakdown: dict[str, Any] | None = None
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
    # The PGDATA bracket cannot see changes in SIBLING paths, and the root scan can run
    # for minutes: a backup, a Docker layer or a log rotating during it would leave the
    # early `df` reading and the `du` total describing different filesystem states, and
    # the whole difference would be silently relabelled as filesystem overhead. So the
    # filesystem's used bytes are read either side of the root scan too.
    volume_used_before = df_used_bytes(mount_source)
    pgdata_before = du_total(pgdata_host, scan_budget)
    # Fail closed on a failed scan: without this evidence the receipt cannot answer
    # its own question, so it must not be presented as a complete inventory.
    usage_full = du_rows(
        ["du", "--null", "-x", "-B1", "--max-depth=2", usage_root],
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
        "ORDER BY (wal_status = 'extended') DESC, (wal_status = 'reserved') DESC, "
        "restart_lsn ASC NULLS LAST, slot_name "
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
    if pgdata_host is not None:
        probe = run(["readlink", "-f", f"{pgdata_host.rstrip('/')}/pg_wal"])
        if probe.returncode == 0:
            wal_resolved = probe.stdout.strip() or None
        if wal_resolved:
            wal_inside = wal_resolved == f"{pgdata_host.rstrip('/')}/pg_wal"
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
        "s.idx_scan::bigint AS idx_scan, pg_get_indexdef(i.oid) AS definition "
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
    for product, rows in attribution_rows.items():
        if rows is None:
            continue
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
    scan_budget.release_reserve()
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
    base_row = next(
        (
            row
            for row in pgdata_children_all
            if row["path"].rstrip("/").rsplit("/", 1)[-1] == "base"
        ),
        None,
    )
    if base_row is None:
        base_breakdown = {"available": False, "reason": "base_child_not_measured"}
    elif live_database_oids is None:
        # Deliberately not computed from an incomplete OID set: a live database whose
        # OID was missing would be reported as orphaned storage.
        base_breakdown = {"available": False, "reason": "live_database_oids_unbounded"}
    elif scan_budget.remaining() < DRILL_DOWN_MIN_CALL_SECONDS:
        base_breakdown = {"available": False, "reason": "scan_budget_exhausted"}
    else:
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
                temp_section = inventory.get("temp_and_logs")
                temp_directory_exists = (
                    isinstance(temp_section, dict)
                    and temp_section.get("temp_directory_bytes") is not None
                )
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
                elif temp_directory_exists and not temp_directory_observed:
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
    if not tablespace_section["single_filesystem_accounting_valid"]:
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
    if operating_database_bytes is None or other_databases_bytes is None:
        raise RuntimeError("database_sizes_unavailable")
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
    temp_bytes = inventory["temp_and_logs"]["temp_directory_bytes"] or 0
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
    # each site because the same `if x > 0` mistake has now been found at four of them;
    # a shared route makes the next remainder correct by construction.
    closure_adjustments: list[dict[str, Any]] = []

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
            closure_adjustments.append(
                {"term": term, "bytes": value, "path": path}
            )
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
    wal_for_subtraction = (
        inventory["wal"].get("bytes_at_window_close", wal_bytes)
        if isinstance(inventory.get("wal"), dict)
        else wal_bytes
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
        if wal_child is None:
            continue
        wal_unlisted = wal_child["bytes"] - subtract
        label = (
            "subdirectories and files pg_ls_waldir does not list"
            if subtract
            else "not the live WAL directory on PostgreSQL 18; unexpected storage"
        )
        # Signed. `du` visits pg_wal during the closing PGDATA walk and
        # pg_ls_waldir() runs after it, so WAL written in between makes this
        # negative. Dropping it then left the closure false; worse, a shrink turned
        # ordinary WAL that had already been recycled into an "unlisted storage"
        # candidate. Neither is reclaimable space, and the signed term says which
        # way the WAL moved.
        remainder(
            f"{wal_child['path']} ({label})",
            wal_unlisted,
            term=f"{name}_measurement_drift",
        )
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
            closure_adjustments.append(
                {
                    "term": "base_directory_scan_drift",
                    "bytes": base_drift,
                    "path": base_breakdown["path"],
                }
            )
        # Named individually: "base/16401 is not a live database" is actionable in a
        # way that a lump remainder never is.
        for row in base_breakdown["unreferenced_entries"]:
            inside.append(
                {
                    "path": f"{row['path']} (not a live database directory)",
                    "exclusive_bytes": row["bytes"],
                    "inside_data_directory": True,
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
    closure_adjustment_bytes = sum(item["bytes"] for item in closure_adjustments)
    candidate_total = (
        non_database_directory_bytes + unaccounted_inside_data_directory_bytes
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
        "closure_adjustments": closure_adjustments,
        "closure_adjustment_bytes": closure_adjustment_bytes,
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
        "candidates_partition_unaccounted_at_scan": (
            None
            if metric_difference is None
            else candidate_total
            + metric_difference
            + residual
            + closure_adjustment_bytes
            == unaccounted_at_scan
        ),
        "postgres_data_directory_bytes": postgres_data_directory_bytes,
        "non_database_directory_bytes": non_database_directory_bytes,
        "unaccounted_inside_data_directory_bytes": unaccounted_inside_data_directory_bytes,
        "directory_scan_root_bytes": du_root_bytes,
        "volume_used_bytes_at_directory_scan": volume_used_at_scan,
        "filesystem_minus_directory_scan_bytes": residual,
        "filesystem_minus_directory_scan_is_significant": (
            abs(residual)
            > volume_used_at_scan * DF_DU_RESIDUAL_SIGNIFICANT_PPM // 1_000_000
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
            "breakdown is unavailable (reason recorded there) no base/ row is emitted "
            "and candidates_partition_unaccounted_at_scan is null, because the closure "
            "cannot then be asserted. "
            "THE CANDIDATES PARTITION unaccounted_bytes_at_directory_scan, NOT "
            "unaccounted_bytes: they are du measurements from the scan window, while "
            "unaccounted_bytes uses the closing df reading. df, du and the SQL queries "
            "cannot be read atomically on a live cluster, so the difference is named "
            "(post_scan_volume_drift_bytes) rather than absorbed into a candidate, "
            "where up to the whole reconciliation tolerance could hide. The identity "
            "the receipt asserts is candidate_total_bytes + "
            "database_size_metric_difference_bytes + "
            "filesystem_minus_directory_scan_bytes + closure_adjustment_bytes == "
            "unaccounted_bytes_at_directory_scan, reported as "
            "candidates_partition_unaccounted_at_scan. The residual belongs in that "
            "identity because every candidate is a du measurement, so they sum towards "
            "directory_scan_root_bytes while the figure they explain starts from a df "
            "reading, and the gap between the two IS the residual. "
            "closure_adjustments lists every other signed difference between two "
            "measurements of the same storage -- WAL recycled between the directory "
            "walk and pg_ls_waldir(), base/ changing between the two walks, a "
            "remainder that came out negative because its operands were measured at "
            "different moments. A negative remainder cannot be a candidate, because "
            "there is no negative storage to reclaim, so it is carried here instead of "
            "being dropped. Nothing in closure_adjustments, and neither "
            "post_scan_volume_drift_bytes nor database_size_metric_difference_bytes, is "
            "storage anyone can free. "
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
            "blocks held by deleted-but-open files. Reserved blocks are NOT a cause: "
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
