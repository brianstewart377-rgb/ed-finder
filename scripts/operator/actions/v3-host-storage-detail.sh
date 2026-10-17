#!/usr/bin/env bash
# Read-only host storage evidence. No database connections or filesystem changes.
set -euo pipefail
if command -v python3.14 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.14)"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-host-storage-detail","status":"stopped","failures":["python3_unavailable"],"read_only":true,"direct_db_access_performed":false,"db_writes_performed":false,"filesystem_writes_performed":false}'
    exit 1
fi
# Use -c rather than a large here-document: bash may spool heredocs to disk.
# Isolated stdlib imports cannot load worktree code or write bytecode.
# The outer ceiling also covers interpreter startup; Python reserves receipt time.
exec timeout --signal=KILL 600 "$PYTHON_BIN" -I -B -c 'from __future__ import annotations

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
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
receipt = {
    "schema_version": "ed-finder/operator-operation-result/v1",
    "operation": "v3-host-storage-detail",
    "read_only": True,
    "direct_db_access_performed": False,
    "db_writes_performed": False,
    "filesystem_writes_performed": False,
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
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True
        )
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
            # Also stop descendants if a timeout/output cap interrupted the command.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
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


def mount_guard():
    # du reads directories, so relatime/strictatime would violate the no-write
    # promise. Refuse rather than remounting or silently claiming no metadata writes.
    # Hold a pollable mount descriptor across every scan; even a reverted remount
    # invalidates the opening observation.
    monitor = open("/proc/self/mounts", "rb")
    try:
        mounts = []
        for line in monitor.read().decode().splitlines():
            source, path, filesystem, options, *_ = line.split()
            mounts.append((unescape_mount(path), set(options.split(","))))
        covering = [
            m
            for m in mounts
            if "/var/lib" == m[0] or "/var/lib".startswith(m[0].rstrip("/") + "/")
        ]
        if not covering:
            raise RuntimeError("var_lib_mount_unresolved")
        # Last entry at a stacked mount is the visible one, as in mountinfo order.
        visible = {}
        for path, options in mounts:
            visible[path] = options
        root = max(covering, key=lambda m: len(m[0]))[0]
        scanned = {root: visible[root]}
        scanned.update({p: o for p, o in visible.items() if p.startswith("/var/lib/")})
        unsafe = [
            p
            for p, opts in scanned.items()
            if not opts.intersection({"noatime", "nodiratime", "ro"})
        ]
        receipt["directory_atime_guard"] = {
            "checked_mounts": sorted(scanned),
            "unsafe_mounts": sorted(unsafe),
        }
        if unsafe:
            raise RuntimeError("directory_atime_writes_not_suppressed")
        poller = select.poll()
        poller.register(monitor, select.POLLPRI | select.POLLERR)
        return monitor, poller
    except BaseException:
        monitor.close()
        raise


def system_df():
    rows = json_lines(DOCKER + ["system", "df", "--format", "{{json .}}"])
    if {r["Type"] for r in rows} != {
        "Images",
        "Containers",
        "Local Volumes",
        "Build Cache",
    } or len(rows) != 4:
        raise ValueError("docker_totals_incomplete")
    return [
        {
            "type": r["Type"],
            "total_count": int(r["TotalCount"]),
            "active": int(r["Active"]),
            "size": r["Size"],
            "size_bytes": size_bytes(r["Size"]),
            "reclaimable": r["Reclaimable"],
            "reclaimable_bytes": size_bytes(r["Reclaimable"]),
        }
        for r in rows
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


def volume_inventory(containers):
    detail = json.loads(run(DOCKER + ["system", "df", "-v", "--format", "{{json .}}"]))
    sizes = {}
    for volume in detail["Volumes"]:
        try:
            sizes[volume["Name"]] = (volume["Size"], size_bytes(volume["Size"]))
        except ValueError:
            sizes[volume["Name"]] = (volume["Size"], None)
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
                {"name": c["name"], "state": c["state"]}
                for c in containers
                if any(
                    m.get("Type") == "volume" and m.get("Name") == actual
                    for m in c["mounts"]
                )
            ]
            if containers is not None
            else None
        )
        value = sizes.get(actual)
        if value is None or value[1] is None:
            # No fallback filesystem traversal, especially for the production volume.
            receipt["failures"].append("volume_size_unavailable:" + actual)
        result.append(
            {
                "name": actual,
                "labels": labels or {},
                "mountpoint": mountpoint,
                "size_bytes": value[1] if value else None,
                "size": value[0] if value else None,
                "size_source": "docker_system_df_verbose",
                "in_use": bool(users) if users is not None else None,
                "containers": users,
            }
        )
    return sorted(result, key=lambda v: (-(v["size_bytes"] or 0), v["name"]))


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
    command = ["du", "--null", "-sx" if total else "-x", "-B1"]
    if not total:
        command.append("--max-depth=2")
    command.extend(["--exclude=" + PGDATA_PATH, "--", path])
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
        section("docker_system_df", system_df)
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
