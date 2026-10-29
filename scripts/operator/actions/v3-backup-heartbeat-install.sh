#!/usr/bin/env bash
# Streamed from trusted main. Installs the backup heartbeat script, service and
# timer from committed sources with pinned SHA-256s, enables the timer and runs
# it once. It never reads or records the heartbeat URL beyond validating that
# the owner-created file is a private root file of the expected shape.
set -euo pipefail
if ! command -v python3.14 >/dev/null 2>&1 || ! python3.14 -I -S -c 'import platform,sys; sys.exit(not (platform.python_implementation()=="CPython" and sys.version_info[:2]==(3,14)))'; then
  printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-backup-heartbeat-install","status":"stopped","failures":["python314_required"],"filesystem_writes_performed":false,"db_writes_performed":false,"service_changes_performed":false,"timer_changes_performed":false,"unit_changes_performed":false}'
  exit 1
fi
exec python3.14 -I -S - "$@" <<'PY'
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
URL_FILE = Path("/etc/ed-finder/v3-production/backup-heartbeat.url")
URL_PATTERN = re.compile(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/[A-Za-z0-9._~/-]{1,200}")
SERVICE = "edfinder-v3-backup-heartbeat.service"
TIMER = "edfinder-v3-backup-heartbeat.timer"
# Committed source path -> (installed path, mode). Order is the argument order.
FILES = (
    ("deploy/v3-production/backup/backup-heartbeat.sh",
     Path("/opt/ed-finder-v3-runtime/backup-heartbeat.sh"), 0o700),
    ("deploy/v3-production/backup/" + SERVICE, Path("/etc/systemd/system/" + SERVICE), 0o644),
    ("deploy/v3-production/backup/" + TIMER, Path("/etc/systemd/system/" + TIMER), 0o644),
)
MAX_SOURCE_BYTES = 100_000


class Refusal(Exception):
    pass


def run(argv: list[str], *, timeout: int = 30, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith(("DOCKER_", "PG"))}
    result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False, env=env)
    if check and result.returncode:
        # Never copy subprocess output into the receipt: no credentials or private paths.
        raise Refusal("host_command_failed:" + Path(argv[0]).name)
    return result


def check_url_file(path: Path | None = None) -> None:
    path = URL_FILE if path is None else path
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise Refusal("heartbeat_url_file_missing") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise Refusal("heartbeat_url_file_not_private_root_file")
    if info.st_size > 512 or not URL_PATTERN.fullmatch(path.read_text(encoding="ascii").strip()):
        raise Refusal("heartbeat_url_invalid")


def stage(source: bytes, destination: Path, mode: int) -> None:
    if destination.parent.resolve() != destination.parent or not destination.parent.is_dir() or destination.is_symlink():
        raise Refusal("destination_path_invalid")
    fd, temporary = tempfile.mkstemp(prefix="." + destination.name + "-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as staged:
            os.fchmod(staged.fileno(), mode)
            staged.write(source)
            staged.flush()
            os.fsync(staged.fileno())
        os.replace(temporary, destination)
        temporary = None
        directory_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def main() -> int:
    receipt = {
        "schema_version": "ed-finder/operator-operation-result/v1",
        "operation": "v3-backup-heartbeat-install",
        "status": "stopped",
        "failures": [],
        "target": {"hostname": EXPECTED_HOST, "fqdn": EXPECTED_FQDN},
        "source_sha": None,
        "files": [],
        "heartbeat_url_file_valid": False,
        "files_installed": False,
        "installed_hashes_verified": False,
        "units_reloaded": False,
        "timer_enabled": False,
        "first_run_exit_status": None,
        "read_only": False,
        "direct_db_access_performed": False,
        "db_writes_performed": False,
        "filesystem_writes_performed": False,
        "service_changes_performed": False,
        "timer_changes_performed": False,
        "unit_changes_performed": False,
        "env_files_read": False,
        "private_keys_read": False,
    }
    try:
        arguments = sys.argv[1:]
        if len(arguments) != 1 + 2 * len(FILES):
            raise Refusal("invalid_install_arguments")
        source_sha = arguments[0]
        if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
            raise Refusal("invalid_committed_source_identity")
        receipt["source_sha"] = source_sha
        sources = []
        for index, (relative, destination, mode) in enumerate(FILES):
            expected, encoded = arguments[1 + 2 * index], arguments[2 + 2 * index]
            if not re.fullmatch(r"[0-9a-f]{64}", expected) or len(encoded) > MAX_SOURCE_BYTES:
                raise Refusal("invalid_committed_source_identity")
            payload = base64.b64decode(encoded, validate=True)
            if not payload or hashlib.sha256(payload).hexdigest() != expected:
                raise Refusal("committed_source_hash_mismatch")
            sources.append((payload, destination, mode))
            receipt["files"].append({"source": relative, "destination": str(destination),
                                     "mode": oct(mode), "source_sha256": expected, "installed_sha256": None})
        if os.geteuid() != 0:
            raise Refusal("root_required")
        if run(["hostname", "-s"]).stdout.strip() != EXPECTED_HOST or run(["hostname", "-f"]).stdout.strip() != EXPECTED_FQDN:
            raise Refusal("target_host_mismatch")
        # The owner creates the URL file first, so the timer is never enabled
        # without anything to ping (the content is validated, never recorded).
        check_url_file()
        receipt["heartbeat_url_file_valid"] = True
        receipt["filesystem_writes_performed"] = True
        for payload, destination, mode in sources:
            stage(payload, destination, mode)
        receipt["files_installed"] = True
        receipt["unit_changes_performed"] = True
        for item, (payload, destination, mode) in zip(receipt["files"], sources, strict=True):
            installed = hashlib.sha256(destination.read_bytes()).hexdigest()
            item["installed_sha256"] = installed
            if installed != item["source_sha256"] or destination.stat().st_mode & 0o777 != mode:
                raise Refusal("installed_source_verification_failed")
        receipt["installed_hashes_verified"] = True
        run(["systemctl", "daemon-reload"])
        receipt["units_reloaded"] = True
        run(["systemctl", "enable", "--now", TIMER])
        receipt["timer_changes_performed"] = True
        receipt["timer_enabled"] = run(["systemctl", "is-enabled", TIMER], check=False).stdout.strip() == "enabled"
        if not receipt["timer_enabled"]:
            raise Refusal("timer_not_enabled")
        # A oneshot start waits for the run; its exit status is the first verdict.
        receipt["service_changes_performed"] = True
        run(["systemctl", "start", SERVICE], timeout=360, check=False)
        shown = run(["systemctl", "show", "--property=ExecMainStatus", "--value", SERVICE]).stdout.strip()
        receipt["first_run_exit_status"] = int(shown) if shown.isdigit() else None
        if receipt["first_run_exit_status"] != 0:
            raise Refusal("first_heartbeat_run_not_healthy")
        receipt["status"] = "passed"
    except (Refusal, OSError, ValueError, binascii.Error, subprocess.TimeoutExpired) as exc:
        failure = str(exc) if isinstance(exc, Refusal) else "install_probe_or_io_failed"
        if failure not in receipt["failures"]:
            receipt["failures"].append(failure)
    finally:
        print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] == "passed" else 1


raise SystemExit(main())
PY
