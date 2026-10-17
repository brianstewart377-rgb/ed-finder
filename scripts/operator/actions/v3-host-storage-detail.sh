#!/usr/bin/env bash
# Read-only host storage evidence. No database connections or file content writes; directory atime can change.
set -euo pipefail
if command -v python3.14 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.14)"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-host-storage-detail","status":"stopped","failures":["python3_unavailable"],"read_only":true,"direct_db_access_performed":false,"db_writes_performed":false,"content_writes_performed":false,"directory_atime_metadata_writes_possible":false}'
    exit 1
fi
# Use -c rather than a large here-document: bash may spool heredocs to disk.
# Isolated stdlib imports cannot load worktree code or write bytecode.
# The outer ceiling also covers interpreter startup; Python reserves receipt time.
exec timeout --signal=KILL 600 "$PYTHON_BIN" -I -S -B -c 'from __future__ import annotations

import json
import os
import platform
import re
import select
import selectors
import signal
import subprocess
import sys
import time
from decimal import Decimal

EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
PGDATA_VOLUME = "edfinder-v3-phase4c-full-20260827_r5-pgdata"
PGDATA_PATH = "/var/lib/docker/volumes/edfinder-v3-phase4c-full-20260827_r5-pgdata"
ACTION_BUDGET_SECONDS = 590
STARTED = time.monotonic()
DEADLINE = STARTED + ACTION_BUDGET_SECONDS
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MOUNTINFO_PATH = "/proc/self/mountinfo"
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
# Only these non-secret identity labels keep their values. Every other label
# is reduced to a count so labels never carry credentials into the receipt.
VOLUME_LABEL_KEYS = (
    "com.docker.compose.project",
    "com.docker.compose.volume",
    "io.ed-finder.purge-rehearsal",
)
receipt = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "v3-host-storage-detail",
    "read_only": True,
    "direct_db_access_performed": False,
    "db_writes_performed": False,
    "content_writes_performed": False,
    "directory_atime_metadata_writes_possible": False,
    "env_files_read": False,
    "private_keys_read": False,
    "service_changes_performed": False,
    "action_budget_seconds": ACTION_BUDGET_SECONDS,
    "pgdata_du_excluded_path": PGDATA_PATH,
    "measurement_note": "Sequential live observations; sizes can change between sections. Docker human sizes are rounded, not exact byte measurements. In-use means referenced by any container, including stopped containers; it is not cleanup authorization.",
    "failures": [],
}


class DeadlineExceeded(Exception):
    pass


def deadline_signal(signum, frame):
    raise DeadlineExceeded("action_deadline_exceeded")


signal.signal(signal.SIGALRM, deadline_signal)
signal.alarm(ACTION_BUDGET_SECONDS)


def run(argv, *, closing=False):
    # Reserve the final ten seconds for closing df and receipt emission.
    left = DEADLINE - time.monotonic() - (2 if closing else 12)
    if left <= 0:
        raise RuntimeError("action_budget_exhausted")
    end = time.monotonic() + min(left, 180 if argv[0] == "du" else 60)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    proc = None
    try:
        # Stay in the process group of the outer timeout wrapper, so killing
        # the collector at its deadline also kills a running du or docker.
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
            selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("command_timeout:" + argv[0])
                for key, _ in selector.select(min(remaining, 0.2)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        buffers[key.data].extend(chunk)
                        if sum(map(len, buffers.values())) > MAX_OUTPUT_BYTES:
                            raise RuntimeError("command_output_limit:" + argv[0])
            proc.wait(timeout=max(0.001, end - time.monotonic()))
        if proc.returncode:
            # Do not echo raw diagnostics or container metadata into failures.
            raise RuntimeError("command_failed:" + argv[0] + ":" + str(proc.returncode))
        return buffers["stdout"].decode("utf-8", "surrogateescape")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("command_unavailable_or_timed_out:" + argv[0]) from exc
    finally:
        if proc is not None:
            # Stop the command if a timeout or output cap interrupted it.
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
            proc.stderr.close()


def section(name, fn):
    try:
        receipt[name] = fn()
    except (RuntimeError, ValueError, KeyError, TypeError, IndexError, OSError) as exc:
        receipt["failures"].append(name + ":" + str(exc))


def json_lines(command):
    return [json.loads(line) for line in run(command).splitlines() if line.strip()]


def size_bytes(value):
    # Docker CLI sizes use decimal SI units, with optional reclaimable percent.
    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*(B|kB|KB|MB|GB|TB|PB)(?:\s+\([^)]*\))?\s*", str(value)
    )
    if not match:
        raise ValueError("docker_size_invalid")
    power = {"B": 0, "kB": 1, "KB": 1, "MB": 2, "GB": 3, "TB": 4, "PB": 5}[match[2]]
    return int(Decimal(match[1]) * (1000**power))


def df(*, closing=False):
    lines = run(
        ["df", "-B1", "--output=size,used,avail", "/"], closing=closing
    ).splitlines()
    size, used, available = map(int, lines[-1].split())
    return {"size_bytes": size, "used_bytes": used, "available_bytes": available}


def unescape_mount(value):
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), value)


def below(path, root):
    return path.startswith(root.rstrip("/") + "/")


def read_mountinfo():
    # Kernel fields escape spaces, tabs, newlines and backslashes as octal.
    with open(MOUNTINFO_PATH, encoding="utf-8", errors="surrogateescape") as handle:
        entries = []
        for line in handle:
            fields = line.split()
            if len(fields) < 10 or "-" not in fields[6:]:
                raise RuntimeError("mountinfo_invalid")
            entries.append(
                {
                    "device": fields[2],
                    "root": unescape_mount(fields[3]),
                    "point": unescape_mount(fields[4]),
                    "options": set(fields[5].split(",")),
                }
            )
    if not any(e["point"] == "/" for e in entries):
        raise RuntimeError("root_mount_unresolved")
    return entries


def mount_guard():
    # Keep a pollable descriptor across every scan, including reverted remounts.
    monitor = open(MOUNTINFO_PATH, "rb")
    try:
        monitor.read()
        read_mountinfo()
        poller = select.poll()
        poller.register(monitor, select.POLLPRI | select.POLLERR)
        return monitor, poller
    except BaseException:
        monitor.close()
        raise


def excluded_paths():
    # A volume whose users are unknown may belong to another PostgreSQL
    # container, so the /var/lib scan must skip it as well.
    return {PGDATA_PATH} | {
        v["mountpoint"]
        for v in receipt.get("volumes", [])
        if v.get("reason")
        in ("postgres_data_volume_not_scanned", "container_inventory_unavailable")
    }


def scan_guard(path):
    # Check before EVERY du, including per-volume and optional directory totals.
    entries = read_mountinfo()
    exclusions = excluded_paths()
    if path == "/var/lib" or below(path, "/var/lib"):
        # du -x skips mounts of other devices, such as the overlay mounts of
        # running containers and their shm tmpfs, so only mounts of the device
        # that holds /var/lib can be walked twice or lead outside it.
        holders = [
            e
            for e in entries
            if e["point"] in ("/", "/var/lib") or below("/var/lib", e["point"])
        ]
        # Later entries are visible for stacked mounts, so prefer the last one.
        holder = max(reversed(holders), key=lambda e: len(e["point"]))
        scan_device = holder["device"]
        # Mount roots are relative to the filesystem, not to the host tree.
        suffix = "/var/lib"[len(holder["point"].rstrip("/")) :]
        source = (holder["root"].rstrip("/") + suffix) or "/"
        offending = sorted(
            {
                e["point"]
                for e in entries
                if e["point"] not in ("/", "/var/lib")
                and e["device"] == scan_device
                and (
                    (
                        below(e["point"], "/var/lib")
                        and not any(
                            e["point"] == x or below(e["point"], x) for x in exclusions
                        )
                    )
                    or e["root"] == source
                    or below(e["root"], source)
                )
            }
        )
        if offending:
            receipt["var_lib_scan_refused"] = "nested_mount"
            receipt["var_lib_scan_offending_mount_points"] = offending
            raise RuntimeError("nested_mount")
    # Later entries are visible for stacked mounts. Attribute metadata risk only
    # to paths being scanned, never to the excluded PostgreSQL volume.
    visible = {e["point"]: e for e in entries}
    covering = [p for p in visible if path == p or below(path, p)]
    if not covering:
        raise RuntimeError("scan_mount_unresolved")
    top = max(covering, key=len)
    # du -x never enters mounts of other devices, so they cannot gain atimes.
    points = {top} | {
        p
        for p in visible
        if below(p, path)
        and visible[p]["device"] == visible[top]["device"]
        and not any(p == x or below(p, x) for x in exclusions)
    }
    guard = receipt.setdefault(
        "directory_atime_guard",
        {
            "checked_mounts": [],
            "atime_updating_mounts": [],
        },
    )
    unsafe = {
        p
        for p in points
        if not visible[p]["options"].intersection({"noatime", "nodiratime", "ro"})
    }
    guard["checked_mounts"] = sorted(set(guard["checked_mounts"]) | points)
    guard["atime_updating_mounts"] = sorted(
        set(guard["atime_updating_mounts"]) | unsafe
    )
    receipt["directory_atime_metadata_writes_possible"] = bool(
        guard["atime_updating_mounts"]
    )
    receipt["directory_atime_writes_suppressed"] = not receipt[
        "directory_atime_metadata_writes_possible"
    ]


def container_inventory():
    ids = run(
        DOCKER + ["container", "ls", "--all", "--quiet", "--no-trunc"]
    ).splitlines()
    result = []
    # Project only non-secret fields, never read .Config.Env or arbitrary inspect.
    projection = "{{json .Name}}\t{{json .Image}}\t{{json .Config.Image}}\t{{json .Created}}\t{{json .State.Status}}\t{{json .State.Running}}\t{{json .Mounts}}"
    for cid in ids:
        name, image_id, image, created, state, running, mounts = [
            json.loads(x)
            for x in run(DOCKER + ["container", "inspect", "--format", projection, cid])
            .rstrip("\n")
            .split("\t")
        ]
        result.append(
            {
                "name": name.lstrip("/"),
                "image_id": image_id,
                "image": image,
                "created": created,
                "state": state,
                "running": running,
                "mounts": mounts,
            }
        )
    return result


DATABASE_MARKERS = ("postgres", "postgis", "timescale")


def database_container(container):
    # Over-match on purpose: a false match only leaves a volume unmeasured.
    # Compose names such as octopus-postgres-1 and any postgres image count.
    text = (
        str(container.get("name", "")) + " " + str(container.get("image", ""))
    ).lower()
    return any(marker in text for marker in DATABASE_MARKERS)


def volume_inventory(containers):
    names = run(DOCKER + ["volume", "ls", "--quiet"]).splitlines()
    result = []
    if PGDATA_VOLUME not in names:
        receipt["failures"].append("production_pgdata_volume_missing")
    for name in names:
        projection = "{{json .Name}}\t{{json .Labels}}\t{{json .Mountpoint}}"
        actual, labels, mountpoint = [
            json.loads(x)
            for x in run(DOCKER + ["volume", "inspect", "--format", projection, name])
            .rstrip("\n")
            .split("\t")
        ]
        users = (
            [
                {"name": c["name"], "state": c["state"], "database": database_container(c)}
                for c in containers
                if any(
                    m.get("Type") == "volume" and m.get("Name") == actual
                    for m in c["mounts"]
                )
            ]
            if containers is not None
            else None
        )
        postgres = (
            actual == PGDATA_VOLUME
            or mountpoint == PGDATA_PATH
            or below(mountpoint, PGDATA_PATH)
            or any(u["database"] for u in (users or []))
        )
        result.append(
            {
                "name": actual,
                "labels": {
                    k: v for k, v in (labels or {}).items() if k in VOLUME_LABEL_KEYS
                },
                "other_label_count": len(
                    [k for k in (labels or {}) if k not in VOLUME_LABEL_KEYS]
                ),
                "mountpoint": mountpoint,
                "size_bytes": None,
                "measured": False,
                "reason": "postgres_data_volume_not_scanned"
                if postgres
                else "container_inventory_unavailable"
                if containers is None
                else "measurement_pending",
                "in_use": bool(users) if users is not None else None,
                "containers": users,
            }
        )
    return sorted(result, key=lambda v: (-(v["size_bytes"] or 0), v["name"]))


def measure_volumes():
    for volume in receipt.get("volumes", []):
        if volume["reason"] != "measurement_pending":
            continue
        try:
            path = volume["mountpoint"]
            if not path.startswith("/") or os.path.normpath(path) != path:
                raise RuntimeError("volume_mountpoint_invalid")
            volume["size_bytes"] = du(path, total=True)[0]["size_bytes"]
            volume["measured"] = True
            volume["size_source"] = "du_allocated_bytes"
            del volume["reason"]
        except (RuntimeError, ValueError, OSError) as exc:
            volume["reason"] = str(exc)
            receipt["failures"].append("volume_size:" + volume["name"] + ":" + str(exc))
    receipt["volumes"].sort(key=lambda v: (-(v["size_bytes"] or 0), v["name"]))


def image_inventory(containers):
    rows = json_lines(
        DOCKER + ["image", "ls", "--all", "--no-trunc", "--format", "{{json .}}"]
    )
    result = []
    for row in rows:
        result.append(
            {
                "repository_tag": row["Repository"] + ":" + row["Tag"],
                "id": row["ID"],
                "size": row["Size"],
                "size_bytes": size_bytes(row["Size"]),
                "created": row["CreatedAt"],
                "in_use": any(c["image_id"] == row["ID"] for c in containers)
                if containers is not None
                else None,
            }
        )
    return sorted(result, key=lambda i: (-i["size_bytes"], i["repository_tag"]))


def du(path, *, total=False):
    scan_guard(path)
    command = ["du", "--null", "-sx" if total else "-x", "--block-size=1"]
    if not total:
        command.append("--max-depth=2")
    command.extend("--exclude=" + x for x in sorted(excluded_paths()))
    command.extend(["--", path])
    rows = []
    for record in run(command).split("\0"):
        if record:
            size, name = record.split("\t", 1)
            rows.append({"path": name, "size_bytes": int(size)})
    if not rows or not any(r["path"] == path for r in rows):
        raise ValueError("du_root_missing")
    return sorted(rows, key=lambda r: (-r["size_bytes"], r["path"]))


def var_lib():
    rows = du("/var/lib")
    receipt["var_lib_entries_omitted"] = max(0, len(rows) - 40)
    return rows[:40]


def optional_directory(path):
    try:
        os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return {"path": path, "present": False, "size_bytes": None}
    # Never follow a symlink to a secret, external filesystem, or excluded path.
    if os.path.islink(path) or not os.path.isdir(path):
        raise RuntimeError("optional_path_not_directory")
    return {
        "path": path,
        "present": True,
        "size_bytes": du(path, total=True)[0]["size_bytes"],
    }


def main():
    if platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 14):
        raise RuntimeError("python314_required")
    host = run(["hostname", "-s"]).strip()
    fqdn = run(["hostname", "-f"]).strip()
    receipt["host"] = {"short": host, "fqdn": fqdn}
    if host != EXPECTED_HOST or fqdn != EXPECTED_FQDN:
        raise RuntimeError("unexpected_host_identity")
    if run(["pwd", "-P"]).strip() != "/opt/ed-finder":
        raise RuntimeError("unexpected_working_directory")
    section("root_filesystem_before", df)
    monitor, poller = mount_guard()
    try:
        section("containers", container_inventory)
        containers = receipt.pop("containers", None)
        if containers is not None:
            receipt["stopped_containers"] = [
                {k: c[k] for k in ("name", "image", "created", "state")}
                | {"status": c["state"]}
                for c in containers
                if not c["running"]
            ]
        section("volumes", lambda: volume_inventory(containers))
        section("images", lambda: image_inventory(containers))
        pgdata = next(
            (v for v in receipt.get("volumes", []) if v["name"] == PGDATA_VOLUME),
            None,
        )
        if pgdata is None or pgdata["mountpoint"] != PGDATA_PATH + "/_data":
            raise RuntimeError("pgdata_exclusion_mountpoint_unverified")
        measure_volumes()
        section("var_lib_top", var_lib)
        section("pgbackrest", lambda: optional_directory("/var/lib/pgbackrest"))
        section("ed_finder", lambda: optional_directory("/var/lib/ed-finder"))
    finally:
        if poller.poll(0):
            receipt["failures"].append("mount_table_changed_during_scan")
        monitor.close()


try:
    main()
except (
    RuntimeError,
    ValueError,
    KeyError,
    TypeError,
    IndexError,
    OSError,
    DeadlineExceeded,
) as exc:
    receipt["failures"].append(str(exc))
finally:
    # Closing df uses reserved budget and runs even when the mount guard refuses.
    if "host" in receipt and receipt["host"] == {
        "short": EXPECTED_HOST,
        "fqdn": EXPECTED_FQDN,
    }:
        section("root_filesystem_after", lambda: df(closing=True))
    receipt["status"] = "stopped" if receipt["failures"] else "success"
    receipt["elapsed_seconds"] = round(time.monotonic() - STARTED, 3)
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    signal.alarm(0)
sys.exit(1 if receipt["failures"] else 0)
'
