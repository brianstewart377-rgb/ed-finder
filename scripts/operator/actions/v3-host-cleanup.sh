#!/usr/bin/env bash
# Sole governed caller: chatgpt-ed-new-ops.yml, manual main dispatch only.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C
if command -v python3.14 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.14)"
else
    PYTHON_BIN="$(command -v python3)"
fi
# timeout owns the entire process group, including du/rm. Even an unresponsive
# Python process or child is killed before 1800 seconds. Python reserves time to
# emit a stopped receipt before this last-resort ceiling.
exec timeout --signal=TERM --kill-after=5s 1790s "$PYTHON_BIN" -I -S -B - "$@" <<'PY'
from __future__ import annotations

import base64
import fcntl
import json
import os
import platform
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

ALLOWLIST = (
    "/data/v3/source-artifacts/spansh/2026-08-24T205426Z",
    "/root/edfinder-v3-benchmark",
    "/root/.bun",
    "/root/.codex",
)
EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
ACTION_DEADLINE = time.monotonic() + 1770
COMMAND_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
PURGE_HOST_LEASE = "/run/lock/edfinder-v3-derived-purge.lock"
_host_lease_fd: int | None = None


def acquire_host_lease() -> int:
    # Keep the same inode locked as the governed purge even if SSH or its
    # runner disappears and GitHub releases the workflow concurrency fence.
    global _host_lease_fd
    descriptor = os.open(PURGE_HOST_LEASE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    acquired = False
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RuntimeError("purge_host_lease_not_regular")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("purge_host_lease_held") from None
        _host_lease_fd = descriptor
        acquired = True
        return descriptor
    finally:
        if not acquired:
            os.close(descriptor)


def release_host_lease() -> None:
    global _host_lease_fd
    if _host_lease_fd is not None:
        os.close(_host_lease_fd)
        _host_lease_fd = None


def remaining() -> float:
    seconds = ACTION_DEADLINE - time.monotonic()
    if seconds <= 0:
        raise RuntimeError("action_deadline_exceeded")
    return seconds


def run(argv: list[str]) -> str:
    result = subprocess.run(
        argv, capture_output=True, text=True, errors="surrogateescape",
        env=COMMAND_ENV, timeout=min(30, remaining()), check=False,
    )
    if result.returncode:
        raise RuntimeError("command_failed:" + argv[0])
    return result.stdout.strip()


def within(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent.rstrip("/") + "/")


def protected_docker_paths() -> tuple[str, ...]:
    # Include unused named volumes, bind mounts of stopped containers, and a
    # non-default Docker root. Inspect only specific fields, never environments
    # or credentials. A failed/incomplete Docker read stops all deletion.
    paths = {"/var/lib/docker"}
    docker_root = json.loads(run(["docker", "--host", "unix:///var/run/docker.sock", "info", "--format", "{{json .DockerRootDir}}"]))
    if not isinstance(docker_root, str) or not docker_root.startswith("/"):
        raise RuntimeError("docker_root_unverified")
    paths.add(os.path.realpath(docker_root))
    volumes = run(["docker", "--host", "unix:///var/run/docker.sock", "volume", "ls", "-q"]).splitlines()
    for volume in volumes:
        mount = json.loads(run(["docker", "--host", "unix:///var/run/docker.sock", "volume", "inspect", "--format", "{{json .Mountpoint}}", volume]))
        if not isinstance(mount, str) or not mount.startswith("/"):
            raise RuntimeError("docker_volume_mountpoint_unverified")
        paths.add(os.path.realpath(mount))
    containers = run(["docker", "--host", "unix:///var/run/docker.sock", "ps", "-aq", "--no-trunc"]).splitlines()
    for container in containers:
        mounts = json.loads(run(["docker", "--host", "unix:///var/run/docker.sock", "inspect", "--format", "{{json .Mounts}}", container]))
        if not isinstance(mounts, list):
            raise RuntimeError("docker_container_mounts_unverified")
        for mount in mounts:
            mount_type = mount.get("Type") if isinstance(mount, dict) else None
            source = mount.get("Source") if isinstance(mount, dict) else None
            # tmpfs and named pipes expose no host filesystem directory. In
            # particular Docker reports an empty Source for --tmpfs mounts.
            if mount_type in ("tmpfs", "npipe"):
                continue
            if not isinstance(source, str) or not source.startswith("/"):
                raise RuntimeError("docker_mount_source_unverified")
            paths.add(os.path.realpath(source))
    return tuple(sorted(paths))


def mount_points() -> tuple[tuple[str, ...], tuple[str, ...]]:
    # ismount alone misses bind mounts on the same device. The kernel's mount
    # table also identifies their source roots, which may be exposed elsewhere
    # even when no mount point lies inside the deletion candidate.
    entries = []
    with open("/proc/self/mountinfo", encoding="utf-8", errors="surrogateescape") as mounts:
        for line in mounts:
            fields = line.split()
            if (
                len(fields) < 10 or "-" not in fields[6:]
                or not re.fullmatch(r"[0-9]+:[0-9]+", fields[2])
                or not fields[4].startswith("/")
            ):
                raise RuntimeError("mount_table_unverified")
            root = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), fields[3])
            point = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), fields[4])
            entries.append((fields[2], root, point))
    root_mounts = [entry for entry in entries if entry[2] == "/"]
    # A stacked "/" shows the later entry, as mountinfo lists mounts in order.
    if not root_mounts or not root_mounts[-1][1].startswith("/"):
        raise RuntimeError("root_mount_unverified")
    root_device = root_mounts[-1][0]
    # Namespace mounts such as Docker network namespaces report a pseudo root
    # like net:[4026532...] on their own nsfs device; they expose no directory
    # of the root filesystem. A non-path root on the root device would be
    # unexplained, so it still refuses.
    if any(device == root_device and not root.startswith("/") for device, root, _ in entries):
        raise RuntimeError("mount_table_unverified")
    return (
        tuple(point for _, _, point in entries),
        tuple(root for device, root, point in entries
              if device == root_device and point != "/" and root.startswith("/")),
    )


def check_open_files(path: str) -> None:
    # Do not glob. A disappearing process/fd is normal; permission errors or
    # other incomplete observations are refusals. Deleted-but-open files count.
    with os.scandir("/proc") as processes:
        for process in processes:
            remaining()
            if not process.name.isdecimal():
                continue
            try:
                with os.scandir(process.path + "/fd") as descriptors:
                    for descriptor in descriptors:
                        try:
                            target = os.readlink(descriptor.path)
                        except FileNotFoundError:
                            continue
                        if target.endswith(" (deleted)"):
                            target = target[:-10]
                        if within(target, path):
                            raise RuntimeError("open_file_under_path")
            except FileNotFoundError:
                continue


def validate_path(path: str, protected_paths: tuple[str, ...], spansh: bool = False) -> None:
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode):
        raise RuntimeError("not_real_directory")
    if os.path.realpath(path) != path:
        raise RuntimeError("realpath_mismatch")
    parent = os.path.dirname(path)
    while True:
        if stat.S_ISLNK(os.lstat(parent).st_mode):
            raise RuntimeError("symlinked_parent")
        if parent == "/":
            break
        parent = os.path.dirname(parent)
    mounts, bind_sources = mount_points()
    if path in mounts or os.path.ismount(path):
        raise RuntimeError("mount_point")
    if any(within(mount, path) for mount in mounts):
        raise RuntimeError("nested_mount_or_filesystem")
    if any(within(source, path) or within(path, source) for source in bind_sources):
        raise RuntimeError("bind_mount_source")
    root_device = os.lstat("/").st_dev
    if info.st_dev != root_device:
        raise RuntimeError("different_filesystem")
    if info.st_uid != 0:
        raise RuntimeError("non_root_owner")
    # Refuse either direction: deleting a directory inside a Docker mount is
    # just as unsafe as deleting an ancestor containing that mount.
    for protected in ("/var/lib/docker", *protected_paths):
        if within(protected, path) or within(path, protected):
            raise RuntimeError("protected_docker_path")
    # fwalk uses directory descriptors with follow_symlinks=False; links inside
    # the candidate are never traversed. Refuse nested mounts too (including
    # same-device bind mounts), before fwalk descends into them.
    def walk_error(error: OSError) -> None:
        raise error

    for directory, dirs, files, descriptor in os.fwalk(
        path, topdown=True, onerror=walk_error, follow_symlinks=False,
    ):
        remaining()
        if "PG_VERSION" in dirs or "PG_VERSION" in files:
            raise RuntimeError("postgres_data_directory")
        for name in dirs:
            child = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISLNK(child.st_mode):
                continue
            if child.st_dev != root_device or os.path.ismount(os.path.join(directory, name)):
                raise RuntimeError("nested_mount_or_filesystem")
    if spansh:
        check_open_files(path)


def du_bytes(path: str) -> int:
    result = subprocess.run(
        ["du", "-sx", "-B1", "--", path], capture_output=True,
        text=True, env=COMMAND_ENV, timeout=remaining(), check=False,
    )
    if result.returncode:
        raise RuntimeError("du_failed")
    value = int(result.stdout.split("\t", 1)[0])
    if value < 0:
        raise RuntimeError("du_invalid")
    return value


class RemovalError(RuntimeError):
    def __init__(self, reason: str, writes: bool):
        super().__init__(reason)
        self.writes = writes


def remove_tree(path: str) -> bool:
    # GNU rm never follows symlinks. stdbuf disables verbose-output buffering
    # so a timeout does not discard evidence of partial deletion.
    # Verbose output is consumed in bounded
    # chunks, not retained: each output byte proves at least one successful
    # unlink/rmdir, including during a partial deletion or timeout. No output
    # means no removed entry; attempting rm alone is not called a write.
    writes = False
    process = subprocess.Popen(
        ["stdbuf", "-o0", "rm", "-rf", "--one-file-system", "--verbose", "--", path],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=COMMAND_ENV,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                for key, _ in selector.select(timeout=min(1, remaining())):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if chunk:
                        writes = True
                    else:
                        selector.unregister(key.fileobj)
            if process.wait(timeout=remaining()):
                raise RemovalError("rm_failed", writes)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        process.kill()
        process.wait()
        # Drain any buffered proof of removal after killing the subprocess.
        if process.stdout.read(65536):
            writes = True
        raise RemovalError(str(exc), writes) from exc
    finally:
        process.stdout.close()
    return writes


def cleanup_path(path: str, *, protected_paths: tuple[str, ...], spansh: bool = False) -> dict:
    result = {
        "path": path, "outcome": "refused", "bytes_removed_estimate": None,
        "filesystem_writes_performed": False,
    }
    try:
        # lstat distinguishes absent from dangling links, and propagates denied
        # access rather than misreporting it as already absent.
        try:
            os.lstat(path)
        except FileNotFoundError:
            result["outcome"] = "already_absent"
            result["bytes_removed_estimate"] = 0
            return result
        validate_path(path, protected_paths, spansh)
        before = os.lstat(path)
        result["bytes_removed_estimate"] = du_bytes(path)
        # Recheck after potentially slow du, including processes and mounts.
        validate_path(path, protected_docker_paths(), spansh)
        after = os.lstat(path)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise RuntimeError("path_identity_changed")
        result["filesystem_writes_performed"] = remove_tree(path)
        try:
            os.lstat(path)
        except FileNotFoundError:
            result["outcome"] = "removed"
        else:
            raise RuntimeError("path_still_present")
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        result["reason"] = str(exc)[:200]
        if isinstance(exc, RemovalError):
            result["filesystem_writes_performed"] = exc.writes
    return result


def root_df() -> dict:
    fields = run(["df", "-B1", "--output=size,used,avail", "/"]).splitlines()
    size, used, available = map(int, fields[-1].split())
    return {"size_bytes": size, "used_bytes": used, "available_bytes": available}


def verify_authority(encoded: str) -> None:
    authority = json.loads(base64.b64decode(encoded, validate=True))
    if not isinstance(authority, dict) or not isinstance(authority.get("target"), dict):
        raise RuntimeError("invalid_target_authority")
    target = authority["target"]
    if (
        authority.get("schema_version") != "ed-finder/v3-production-target-authority/v1"
        or authority.get("status") != "authorized"
        or target.get("hostname") != EXPECTED_HOST
        or target.get("fqdn") != EXPECTED_FQDN
        or target.get("production") is not True
        or run(["hostname", "-s"]) != target["hostname"]
        or run(["hostname", "-f"]) != target["fqdn"]
    ):
        raise RuntimeError("unexpected_host_identity_or_authority")
    if os.geteuid() != 0:
        raise RuntimeError("root_required")


def run_cleanup() -> dict:
    receipt = {
        "schema_version": "ed-finder/operator-operation-result/v1",
        "operation": "v3-host-cleanup", "status": "stopped", "paths": [],
        "filesystem_bytes_reclaimed": None, "root_df_before": None, "root_df_after": None,
        "filesystem_writes_performed": False, "db_writes_performed": False,
        "service_changes_performed": False, "failures": [],
    }
    try:
        acquire_host_lease()
        if platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 14):
            raise RuntimeError("python314_required")
        if len(sys.argv) != 2:
            raise RuntimeError("exactly_one_authority_argument_required")
        verify_authority(sys.argv[1])
        receipt["root_df_before"] = root_df()
        for index, path in enumerate(ALLOWLIST):
            try:
                remaining()
                try:
                    os.lstat(path)
                except FileNotFoundError:
                    receipt["paths"].append({
                        "path": path, "outcome": "already_absent", "bytes_removed_estimate": 0,
                        "filesystem_writes_performed": False,
                    })
                    continue
                # Refresh protection immediately before each candidate; Docker
                # failures must not quietly become an empty protection list.
                protected = protected_docker_paths()
                result = cleanup_path(path, protected_paths=protected, spansh=index == 0)
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                result = {"path": path, "outcome": "refused", "reason": str(exc)[:200],
                          "bytes_removed_estimate": None,
                          "filesystem_writes_performed": False}
            receipt["paths"].append(result)
            receipt["filesystem_writes_performed"] |= result["filesystem_writes_performed"]
        receipt["root_df_after"] = root_df()
        receipt["filesystem_bytes_reclaimed"] = (
            receipt["root_df_after"]["available_bytes"] - receipt["root_df_before"]["available_bytes"]
        )
        receipt["status"] = "success" if all(
            item["outcome"] in ("removed", "already_absent") for item in receipt["paths"]
        ) else "stopped"
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        reason = str(exc)[:200]
        receipt["failures"].append(reason)
        for path in ALLOWLIST[len(receipt["paths"]):]:
            receipt["paths"].append({
                "path": path, "outcome": "refused", "reason": reason,
                "bytes_removed_estimate": None,
                "filesystem_writes_performed": False,
            })
    return receipt


def deadline_signal(_signum: int, _frame: object) -> None:
    raise RuntimeError("action_deadline_exceeded")


if __name__ == "__main__":
    signal.signal(signal.SIGALRM, deadline_signal)
    signal.alarm(1770)
    try:
        receipt = run_cleanup()
        # Complete the receipt within the outer watchdog's reserved twenty seconds.
        signal.alarm(0)
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")), flush=True)
    finally:
        release_host_lease()
    sys.exit(0 if receipt["status"] == "success" else 1)
PY
