#!/usr/bin/env bash
# Streamed from trusted main; the workflow prepends the shared read-only fence.
set -euo pipefail
if ! command -v python3.14 >/dev/null 2>&1 || ! python3.14 -I -S -c 'import platform,sys; sys.exit(not (platform.python_implementation()=="CPython" and sys.version_info[:2]==(3,14)))'; then
  printf '%s\n' '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-backup-wrapper-install","status":"stopped","failures":["python314_required"],"filesystem_writes_performed":false,"db_writes_performed":false,"service_changes_performed":false,"wrapper_temp_written":false,"wrapper_installed":false,"installed_hash_verified":false,"source_sha256":null,"installed_sha256":null}'
  exit 1
fi
# Read-only host authority checks precede every database probe. No lock or file
# mutation occurs until the shared purge-state fence has also passed.
preflight_failure=''
if [ "$(hostname -s)" != 'ed-finder-prod' ] || [ "$(hostname -f)" != 'nb79a3d.mevnode.com' ]; then
  preflight_failure='target_host_mismatch'
elif [ "$(env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker context inspect default --format '{{.Endpoints.docker.Host}}' 2>/dev/null)" != 'unix:///var/run/docker.sock' ]; then
  preflight_failure='docker_default_endpoint_mismatch'
fi
if [ -n "$preflight_failure" ]; then
  fence_status=78
  fence_report="{\"failures\":[\"$preflight_failure\"]}"
elif declare -F v3_purge_state_check >/dev/null; then
  fence_status=0
  fence_report="$(v3_purge_state_check)" || fence_status=$?
else
  fence_status=78
  fence_report='{"failures":["purge_state_helper_unavailable"]}'
fi
exec python3.14 -I -S - "$fence_status" "$fence_report" "$@" <<'PY'
from __future__ import annotations

import base64
import binascii
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

EXPECTED_HOST = "ed-finder-prod"
EXPECTED_FQDN = "nb79a3d.mevnode.com"
CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"
DESTINATION = Path("/opt/ed-finder-v3-runtime/pgbackrest-operation.sh")
SCHEDULE_LOCK = Path("/run/lock/edfinder-v3-pgbackrest-schedule.lock")
INSTALL_SQL = """BEGIN READ ONLY;
SET LOCAL statement_timeout = '20s';
SET LOCAL lock_timeout = '5s';
SELECT json_build_object(
 'migration_applied', EXISTS (SELECT 1 FROM v3_meta.schema_migration
   WHERE migration_name='016_v3_governed_derived_purge.sql'),
 'ledger_exists', to_regclass('v3_meta.derived_generation_purge_event') IS NOT NULL);
COMMIT;
"""


class Refusal(Exception):
    pass


def run(argv: list[str], *, text: str | None = None) -> str:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("DOCKER_", "PG"))}
    if argv[0] == "docker":
        argv = ["docker", "--host", "unix:///var/run/docker.sock", *argv[1:]]
    result = subprocess.run(argv, input=text, text=True, capture_output=True, timeout=30, check=False, env=env)
    if result.returncode:
        # Never copy subprocess stderr into the receipt: no credentials or private paths.
        raise Refusal("host_probe_failed")
    return result.stdout.strip()


def main() -> int:
    receipt = {
        "schema_version": "ed-finder/operator-operation-result/v1",
        "operation": "v3-backup-wrapper-install",
        "status": "stopped",
        "failures": [],
        "target": {"hostname": EXPECTED_HOST, "fqdn": EXPECTED_FQDN},
        "destination": str(DESTINATION),
        "source_sha": None,
        "source_sha256": None,
        "installed_sha256": None,
        "read_only": False,
        "direct_db_access_performed": False,
        "db_writes_performed": False,
        "filesystem_writes_performed": False,
        "wrapper_temp_written": False,
        "wrapper_installed": False,
        "installed_hash_verified": False,
        "service_changes_performed": False,
        "timer_changes_performed": False,
        "unit_changes_performed": False,
        "env_files_read": False,
        "private_keys_read": False,
    }
    temporary: str | None = None
    lock_file = None
    try:
        if len(sys.argv) != 6:
            raise Refusal("invalid_install_arguments")
        fence_status, fence_report, source_sha, expected_hash, encoded_source = sys.argv[1:]
        fence = json.loads(fence_report)
        if not isinstance(fence, dict):
            raise Refusal("purge_state_query_failed")
        receipt["purge_state"] = fence
        if fence_status != "0":
            failures = fence.get("failures")
            receipt["failures"] = failures if isinstance(failures, list) and failures else ["purge_state_refused"]
            raise Refusal("purge_state_refused")
        if not re.fullmatch(r"[0-9a-f]{40}", source_sha) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise Refusal("invalid_committed_source_identity")
        receipt["source_sha"] = source_sha
        receipt["source_sha256"] = expected_hash
        if len(encoded_source) > 100_000:
            raise Refusal("source_size_invalid")
        source = base64.b64decode(encoded_source, validate=True)
        if not source or hashlib.sha256(source).hexdigest() != expected_hash:
            raise Refusal("committed_source_hash_mismatch")
        if os.geteuid() != 0:
            raise Refusal("root_required")
        if run(["hostname", "-s"]) != EXPECTED_HOST or run(["hostname", "-f"]) != EXPECTED_FQDN:
            raise Refusal("target_host_mismatch")
        if run(["docker", "context", "inspect", "default", "--format", "{{.Endpoints.docker.Host}}"]) != "unix:///var/run/docker.sock":
            raise Refusal("docker_default_endpoint_mismatch")
        # Hold the schedule lock until the installed hash has been verified.
        lock_file = SCHEDULE_LOCK.open("a+")
        receipt["filesystem_writes_performed"] = True
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refusal("pgbackrest_schedule_lease_held") from exc
        processes = run(["docker", "top", CONTAINER, "-eo", "pid,args"])
        if any("pgbackrest" in line.lower() and re.search(r"\b(backup|verify)\b", line.lower()) for line in processes.splitlines()):
            raise Refusal("pgbackrest_operation_active")
        receipt["direct_db_access_performed"] = True
        ledger = json.loads(run([
            "docker", "exec", "-i", "-u", "postgres", CONTAINER,
            "psql", "-X", "--no-psqlrc", "--no-password", "--username", "edfinder_v3",
            "--dbname", "edfinder_v3_phase4c_full_20260827_r5", "--set=ON_ERROR_STOP=1",
            "--quiet", "--tuples-only", "--no-align",
        ], text=INSTALL_SQL))
        if not isinstance(ledger, dict):
            raise Refusal("purge_ledger_probe_invalid")
        if ledger.get("migration_applied") is not True:
            raise Refusal("purge_migration_016_not_applied")
        if ledger.get("ledger_exists") is not True:
            raise Refusal("purge_ledger_missing")
        if DESTINATION.parent.resolve() != DESTINATION.parent or not DESTINATION.parent.is_dir() or DESTINATION.is_symlink():
            raise Refusal("destination_path_invalid")
        fd, temporary = tempfile.mkstemp(prefix=".pgbackrest-operation-", dir=DESTINATION.parent)
        receipt["wrapper_temp_written"] = True
        with os.fdopen(fd, "wb") as staged:
            os.fchmod(staged.fileno(), 0o700)
            staged.write(source)
            staged.flush()
            os.fsync(staged.fileno())
        if hashlib.sha256(Path(temporary).read_bytes()).hexdigest() != expected_hash:
            raise Refusal("staged_source_hash_mismatch")
        os.replace(temporary, DESTINATION)
        temporary = None
        receipt["wrapper_installed"] = True
        directory_fd = os.open(DESTINATION.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        installed_hash = hashlib.sha256(DESTINATION.read_bytes()).hexdigest()
        receipt["installed_sha256"] = installed_hash
        if installed_hash != expected_hash or DESTINATION.stat().st_mode & 0o777 != 0o700:
            raise Refusal("installed_source_verification_failed")
        receipt["installed_hash_verified"] = True
        receipt["status"] = "passed"
    except (Refusal, OSError, ValueError, binascii.Error, subprocess.TimeoutExpired) as exc:
        failure = str(exc) if isinstance(exc, Refusal) else "install_probe_or_io_failed"
        if failure not in receipt["failures"]:
            receipt["failures"].append(failure)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
        if lock_file is not None:
            lock_file.close()
        print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] == "passed" else 1


raise SystemExit(main())
PY
