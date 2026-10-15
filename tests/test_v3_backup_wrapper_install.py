"""Disposable contracts for the ledger-aware backup wrapper and its installer."""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "deploy/v3-production/backup/pgbackrest-operation.sh"
INSTALLER = ROOT / "scripts/operator/actions/v3-backup-wrapper-install.sh"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"


@pytest.mark.parametrize("operation", ["full", "diff", "verify"])
@pytest.mark.parametrize("state", ["live", "dead", "none", "missing", "query_failed"])
def test_wrapper_ledger_guard(tmp_path, operation, state):
    binary = tmp_path / "bin"
    binary.mkdir()
    log = tmp_path / "docker.jsonl"
    docker = binary / "docker"
    docker.write_text(f"#!{sys.executable}\n" + '''import json,os,sys
args=sys.argv[1:]
with open(os.environ['TEST_DOCKER_LOG'],'a') as out: out.write(json.dumps(args)+'\\n')
if args[0]=='inspect': sys.exit(0)
if args[0]=='top': print('PID COMMAND'); sys.exit(0)
if 'psql' in args:
    query=sys.stdin.read()
    assert 'BEGIN READ ONLY' in query and 'v3_meta.purge_open_event' in query
    assert 'a.pid=e.backend_pid AND a.backend_start=e.backend_start' in query
    assert "'FAILED_STOP'" in query
    state=os.environ['TEST_PURGE_STATE']
    if state in ('missing','query_failed'):
        print('relation missing' if state=='missing' else 'query failed',file=sys.stderr)
        sys.exit(1)
    if state=='live': print('purge_id=test event_sequence=7 kind=REWRITE_STARTED relation=system_search backend_pid=123 backend_start=now')
    sys.exit(0)
if 'info' in args: print('[{"status":{"message":"ok"}}]')
''')
    docker.chmod(0o755)
    for name, script in {
        "mountpoint": "exit 0",
        "findmnt": "echo fuse.rclone",
        "nice": 'shift 2; exec "$@"',
        "ionice": 'shift 2; exec "$@"',
    }.items():
        p = binary / name
        p.write_text("#!/bin/sh\n" + script + "\n")
        p.chmod(0o755)
    wrapper = tmp_path / "wrapper.sh"
    wrapper.write_text(WRAPPER.read_text().replace("/run/lock/edfinder-v3-pgbackrest-schedule.lock", str(tmp_path / "schedule.lock")))
    env = {**os.environ, "PATH": f"{binary}:{os.environ['PATH']}", "TEST_DOCKER_LOG": str(log), "TEST_PURGE_STATE": state}
    result = subprocess.run(["bash", str(wrapper), operation], env=env, capture_output=True, text=True, check=False)
    commands = [json.loads(line) for line in log.read_text().splitlines()]
    psql = next(command for command in commands if "psql" in command)
    start = psql.index("psql")
    assert psql[start:start + 8] == ["psql", "-X", "--no-psqlrc", "--no-password", "--username", "edfinder_v3", "--dbname", "edfinder_v3_phase4c_full_20260827_r5"]
    started = [command for command in commands if "--log-level-console=info" in command]
    if state == "live":
        assert result.returncode == 0
        assert "SKIP: live purge backend:" in result.stdout
        assert "event_sequence=7" in result.stdout
        assert not started
    elif state in ("missing", "query_failed"):
        assert result.returncode != 0
        assert not started
        assert "SKIP" not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert len(started) == 1
        assert f"PASS: pgBackRest {operation}" in result.stdout


def installer_namespace():
    source = INSTALLER.read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    source = source.rsplit("\nraise SystemExit(main())", 1)[0]
    namespace = {}
    exec(compile(source, str(INSTALLER), "exec"), namespace)
    return namespace


def install(tmp_path, capsys, *, failure=None, fence=None):
    ns = installer_namespace()
    destination = tmp_path / "runtime" / "pgbackrest-operation.sh"
    destination.parent.mkdir()
    destination.write_text("old wrapper")
    lock = tmp_path / "schedule.lock"
    payload = WRAPPER.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    ns["DESTINATION"] = destination
    ns["SCHEDULE_LOCK"] = lock
    calls = []
    held = lock.open("a+") if failure == "lease" else None
    if held is not None:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def run(argv, *, text=None):
        calls.append((argv, text))
        if argv == ["hostname", "-s"]:
            return "wrong-host" if failure == "host" else "ed-finder-prod"
        if argv == ["hostname", "-f"]:
            return "nb79a3d.mevnode.com"
        if argv == ["docker", "context", "inspect", "default", "--format", "{{.Endpoints.docker.Host}}"]:
            return "tcp://remote:2375" if failure == "context" else "unix:///var/run/docker.sock"
        if "top" in argv:
            return "123 pgbackrest --stanza=edfinder_v3 backup" if failure == "active" else "PID COMMAND"
        if "psql" in argv:
            assert "BEGIN READ ONLY" in text
            assert "016_v3_governed_derived_purge.sql" in text
            if failure == "query":
                raise ns["Refusal"]("host_probe_failed")
            return json.dumps({"migration_applied": failure != "migration", "ledger_exists": failure != "ledger"})
        raise AssertionError(argv)

    ns["run"] = run
    fence = fence or {"status": "clear", "failures": []}
    argv = ["installer", "78" if fence["failures"] else "0", json.dumps(fence), "a" * 40, digest, base64.b64encode(payload).decode()]
    if failure == "source_hash":
        argv[4] = "b" * 64
    real_replace = os.replace
    replacements = []

    def replace(source, target):
        replacements.append((source, target))
        assert Path(source).parent == destination.parent
        assert Path(source).stat().st_mode & 0o777 == 0o700
        assert hashlib.sha256(Path(source).read_bytes()).hexdigest() == digest
        real_replace(source, target)
        if failure == "installed_hash":
            destination.write_text("corrupted")

    try:
        with patch.object(sys, "argv", argv), patch.object(os, "geteuid", return_value=0), patch.object(os, "replace", side_effect=replace):
            status = ns["main"]()
    finally:
        if held is not None:
            held.close()
    receipt = json.loads(capsys.readouterr().out)
    return SimpleNamespace(status=status, receipt=receipt, destination=destination, payload=payload, calls=calls, replacements=replacements)


def test_installer_atomic_verified_install_and_receipt(tmp_path, capsys):
    result = install(tmp_path, capsys)
    assert result.status == 0
    assert result.destination.read_bytes() == result.payload
    assert len(result.replacements) == 1
    receipt = result.receipt
    assert receipt["schema_version"] == "ed-finder/operator-operation-result/v1"
    assert receipt["source_sha"] == "a" * 40
    assert receipt["source_sha256"] == receipt["installed_sha256"] == hashlib.sha256(result.payload).hexdigest()
    for flag in ("filesystem_writes_performed", "wrapper_temp_written", "wrapper_installed", "installed_hash_verified"):
        assert receipt[flag] is True
    for flag in ("db_writes_performed", "service_changes_performed", "timer_changes_performed", "unit_changes_performed", "env_files_read", "private_keys_read"):
        assert receipt[flag] is False
    assert not list(result.destination.parent.glob(".pgbackrest-operation-*"))


@pytest.mark.parametrize(("failure", "code"), [
    ("lease", "pgbackrest_schedule_lease_held"),
    ("active", "pgbackrest_operation_active"),
    ("migration", "purge_migration_016_not_applied"),
    ("ledger", "purge_ledger_missing"),
    ("query", "host_probe_failed"),
    ("host", "target_host_mismatch"),
    ("context", "docker_default_endpoint_mismatch"),
    ("source_hash", "committed_source_hash_mismatch"),
])
def test_installer_refusals_preserve_installed_file(tmp_path, capsys, failure, code):
    result = install(tmp_path, capsys, failure=failure)
    assert result.status == 1
    assert code in result.receipt["failures"]
    assert result.destination.read_text() == "old wrapper"
    assert result.receipt["wrapper_installed"] is False
    assert result.receipt["wrapper_temp_written"] is False
    assert not result.replacements


@pytest.mark.parametrize("kind", ["BATCH_STARTED", "REWRITE_STARTED", "SERVICES_QUIESCED", "WRITER_FENCE_ENABLED", "AUTOVACUUM_DISABLED", "FAILED_STOP", "lease_held", "ledger_missing"])
def test_installer_purge_fence_precedes_host_locks_and_writes(tmp_path, capsys, kind):
    code = "purge_state_" + kind
    result = install(tmp_path, capsys, fence={"failures": [code]})
    assert result.status == 1
    assert code in result.receipt["failures"]
    assert result.receipt["filesystem_writes_performed"] is False
    assert not result.calls
    assert not result.replacements


def test_installer_checks_hash_after_atomic_rename(tmp_path, capsys):
    result = install(tmp_path, capsys, failure="installed_hash")
    assert result.status == 1
    assert result.receipt["wrapper_installed"] is True
    assert result.receipt["installed_hash_verified"] is False
    assert "installed_source_verification_failed" in result.receipt["failures"]


def test_install_workflow_streams_trusted_source_and_keeps_strict_ssh():
    workflow = WORKFLOW.read_text()
    assert "          - v3-backup-wrapper-install\n" in workflow
    assert "            v3-backup-wrapper-install) ;;" in workflow
    step = workflow.split("      - name: Install trusted V3 backup wrapper", 1)[1].split("      - name: Upload", 1)[0]
    assert 'git -C trusted-main rev-parse HEAD' in step
    assert 'git -C trusted-main show "$source_sha:deploy/v3-production/backup/pgbackrest-operation.sh"' in step
    assert 'sha256sum "$source_file"' in step
    assert 'v3-purge-fenced-actions/v3-backup-wrapper-install.sh' in step
    assert "StrictHostKeyChecking=yes" in step
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in step
    assert "ssh-keyscan" not in workflow
    assert 'cat trusted-main/scripts/operator/lib/v3_purge_state.py' in workflow
    assert 'cat trusted-main/scripts/operator/lib/v3-purge-state.sh' in workflow
    assert "systemctl" not in INSTALLER.read_text()


@pytest.mark.parametrize("path", [WRAPPER, INSTALLER])
def test_changed_shell_parses(path):
    subprocess.run(["bash", "-n", str(path)], check=True)


@pytest.mark.parametrize(("host", "endpoint", "fence_called", "code"), [
    ("other-host", "unix:///var/run/docker.sock", False, "target_host_mismatch"),
    ("ed-finder-prod", "tcp://remote:2375", False, "docker_default_endpoint_mismatch"),
    ("ed-finder-prod", "unix:///var/run/docker.sock", True, "purge_host_lease_held"),
])
def test_installer_shell_host_authority_precedes_database_fence(tmp_path, host, endpoint, fence_called, code):
    binary = tmp_path / "bin"
    binary.mkdir()
    hostname = binary / "hostname"
    hostname.write_text(f'#!/bin/sh\nif [ "$1" = -s ]; then echo {host}; else echo nb79a3d.mevnode.com; fi\n')
    hostname.chmod(0o755)
    docker = binary / "docker"
    docker.write_text(f'#!/bin/sh\nprintf "%s\\n" "{endpoint}"\n')
    docker.chmod(0o755)
    marker = tmp_path / "fence-called"
    stream = f'''v3_purge_state_check() {{
        touch '{marker}'
        echo '{{"failures":["purge_host_lease_held"]}}'
        return 78
    }}
''' + INSTALLER.read_text()
    result = subprocess.run(
        ["bash", "-s", "--", "a" * 40, "b" * 64, "YQ=="], input=stream,
        env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}"},
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 1, result.stderr
    receipt = json.loads(result.stdout)
    assert code in receipt["failures"]
    assert marker.exists() == fence_called
    assert receipt["filesystem_writes_performed"] is False
    assert receipt["direct_db_access_performed"] is False


def test_installer_docker_executor_sanitizes_environment_and_pins_local_socket():
    ns = installer_namespace()
    with patch.dict(os.environ, {"DOCKER_CONTEXT": "remote", "DOCKER_HOST": "tcp://remote", "PGPASSWORD": "test-only"}), patch.object(subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="ok")) as called:
        assert ns["run"](["docker", "top", "pinned-container"]) == "ok"
    argv = called.call_args.args[0]
    assert argv == ["docker", "--host", "unix:///var/run/docker.sock", "top", "pinned-container"]
    assert not any(key.startswith(("DOCKER_", "PG")) for key in called.call_args.kwargs["env"])
