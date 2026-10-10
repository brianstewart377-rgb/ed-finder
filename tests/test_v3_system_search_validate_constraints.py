from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import textwrap

import pytest


pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ACTION = (
    ROOT
    / "scripts"
    / "operator"
    / "actions"
    / "v3-system-search-validate-constraints.sh"
)
WORKFLOW = ROOT / ".github" / "workflows" / "chatgpt-ed-new-ops.yml"

MIGRATION_SHA = "a042ccd1544d95cf47407a0722497321a544f15c62ac07dc83c914a19d7acbdf"
CONSTRAINTS = (
    "system_search_ammonia_count_check",
    "system_search_bio_signal_total_check",
    "system_search_black_hole_count_check",
    "system_search_elw_count_check",
    "system_search_gas_giant_count_check",
    "system_search_geo_signal_total_check",
    "system_search_hmc_count_check",
    "system_search_icy_count_check",
    "system_search_metal_rich_count_check",
    "system_search_neutron_count_check",
    "system_search_other_star_count_check",
    "system_search_ring_count_check",
    "system_search_rocky_count_check",
    "system_search_rocky_ice_count_check",
    "system_search_terraformable_count_check",
    "system_search_walkable_count_check",
    "system_search_white_dwarf_count_check",
    "system_search_ww_count_check",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _receipt(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    lines = result.stdout.splitlines()
    assert len(lines) == 1, result.stdout
    return json.loads(lines[0])


def _docker_calls(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _make_fake_path(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker-calls.jsonl"

    python314 = fake_bin / "python3.14"
    python314.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            printf '%s\\n' "$*" >> "$TEST_PYTHON_LOG"
            exec "{sys.executable}" "$@"
            """
        ),
        encoding="utf-8",
    )

    hostname = fake_bin / "hostname"
    hostname.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            if [ "${1:-}" = "-f" ]; then
              printf '%s\\n' 'nb79a3d.mevnode.com'
            else
              printf '%s\\n' 'ed-finder-prod'
            fi
            """
        ),
        encoding="utf-8",
    )

    sleep = fake_bin / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    docker = fake_bin / "docker"
    docker.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json
            import os
            from pathlib import Path
            import sys

            constraints = {CONSTRAINTS!r}
            args = sys.argv[1:]
            joined = " ".join(args)
            stdin = ""
            if "run.sql" in joined and "-i" in args:
                stdin = sys.stdin.read()

            log_path = Path(os.environ["TEST_DOCKER_LOG"])
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({{"args": args, "stdin": stdin}}) + "\\n")

            marker = Path(os.environ["TEST_DOCKER_MARKER"])
            if args[:2] == ["context", "show"]:
                print("default")
                raise SystemExit(0)
            if args[:3] == ["context", "inspect", "default"]:
                print('{{"Endpoints":{{"docker":{{"Host":"unix:///var/run/docker.sock"}}}}}}')
                raise SystemExit(0)
            if args and args[0] == "inspect":
                if "State.Running" in joined:
                    print("true")
                else:
                    print("{{}}")
                raise SystemExit(0)

            if "schema_migration" in joined:
                if os.environ.get("FAKE_LEDGER_QUERY_FAIL") == "1":
                    raise SystemExit(1)
                print(os.environ.get("FAKE_LEDGER_SHA", {MIGRATION_SHA!r}))
                raise SystemExit(0)
            if "pg_constraint" in joined:
                unvalidated = set(
                    filter(None, os.environ.get("FAKE_UNVALIDATED", "").split(","))
                )
                for name in constraints:
                    print(f"{{name}}|{{'f' if name in unvalidated else 't'}}")
                raise SystemExit(0)
            if "pg_stat_activity" in joined:
                if os.environ.get("FAKE_ACTIVE") == "1" or marker.exists():
                    print(
                        "991|active|00:00:03|ALTER TABLE v3_derived.system_search "
                        "VALIDATE CONSTRAINT system_search_ww_count_check"
                    )
                raise SystemExit(0)
            if "run.pid" in joined and "-d" not in args:
                if os.environ.get("FAKE_RUNNER_KILL_SUCCEEDS") != "1":
                    raise SystemExit(1)
                runner_cmdline = os.environ.get("FAKE_RUNNER_CMDLINE", "")
                command = str(args[-1])
                expected_checks = (
                    "kill -0" in command
                    and "/proc/$pid/cmdline" in command
                    and "tr " in command
                    and "*psql*" in command
                    and "*run.sql*" in command
                )
                if not expected_checks:
                    raise SystemExit(2)
                if "psql" in runner_cmdline and "run.sql" in runner_cmdline:
                    raise SystemExit(0)
                if 'rm -f "$pid_file"' not in command:
                    raise SystemExit(2)
                raise SystemExit(1)
            if "run.log" in joined and "-d" not in args:
                log_lines = os.environ.get("FAKE_LOG_LINES", "").splitlines()
                command = str(args[-1])
                if "grep -E" in command:
                    exit_lines = [
                        line
                        for line in log_lines
                        if line.startswith("exit=") and line[5:].isdigit()
                    ]
                    if exit_lines:
                        print(exit_lines[-1])
                elif log_lines:
                    print("\\n".join(log_lines))
                raise SystemExit(0)
            if "run.sql" in joined and "-i" in args:
                raise SystemExit(0)
            if "-d" in args:
                marker.touch()
                raise SystemExit(0)
            raise SystemExit(2)
            """
        ),
        encoding="utf-8",
    )

    for executable in (python314, hostname, sleep, docker):
        executable.chmod(0o755)
    return fake_bin, docker_log


def _run_action(
    tmp_path: Path,
    operation: str,
    *,
    ledger_sha: str = MIGRATION_SHA,
    unvalidated: tuple[str, ...] = (),
    active: bool = False,
    runner_kill_succeeds: bool = False,
    runner_cmdline: str = "",
    log_lines: tuple[str, ...] = (),
    ledger_query_fails: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
    fake_bin, docker_log = _make_fake_path(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
            "TEST_DOCKER_LOG": str(docker_log),
            "TEST_DOCKER_MARKER": str(tmp_path / "runner-launched"),
            "TEST_PYTHON_LOG": str(tmp_path / "python-calls.log"),
            "FAKE_LEDGER_SHA": ledger_sha,
            "FAKE_LEDGER_QUERY_FAIL": "1" if ledger_query_fails else "0",
            "FAKE_UNVALIDATED": ",".join(unvalidated),
            "FAKE_ACTIVE": "1" if active else "0",
            "FAKE_RUNNER_KILL_SUCCEEDS": (
                "1" if runner_kill_succeeds else "0"
            ),
            "FAKE_RUNNER_CMDLINE": runner_cmdline,
            "FAKE_LOG_LINES": "\n".join(log_lines),
        }
    )
    result = subprocess.run(
        ["bash", str(ACTION), operation],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return result, _docker_calls(docker_log)


def _was_detached(calls: list[dict[str, object]]) -> bool:
    return any("-d" in call["args"] for call in calls)


def test_constraint_validation_operations_are_allowlisted_through_trusted_main():
    workflow = _read(WORKFLOW)
    operations = (
        "v3-system-search-validate-constraints-start",
        "v3-system-search-validate-constraints-status",
    )
    for operation in operations:
        assert f"          - {operation}\n" in workflow
        assert f"|{operation}" in workflow or f"{operation})" in workflow
        assert f"steps.request.outputs.operation == '{operation}'" in workflow

    script_path = (
        "trusted-main/scripts/operator/actions/"
        "v3-system-search-validate-constraints.sh"
    )
    assert workflow.count(script_path) == 2
    assert "'cd /opt/ed-finder && bash -s -- start'" in workflow
    assert "'cd /opt/ed-finder && bash -s -- status'" in workflow
    assert "Upload V3 Search constraint validation receipt" in workflow
    assert "name: v3-system-search-validate-constraints-operation" in workflow
    assert "retention-days: 30" in workflow
    assert (
        "always() && (steps.request.outputs.operation == "
        "'v3-system-search-validate-constraints-start' || "
        "steps.request.outputs.operation == "
        "'v3-system-search-validate-constraints-status')"
    ) in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in workflow
    assert "IdentitiesOnly=yes" in workflow


def test_constraint_validation_action_has_fixed_targets_and_catalog_contract():
    source = _read(ACTION)

    assert 'TARGET_HOSTNAME="ed-finder-prod"' in source
    assert 'TARGET_FQDN="nb79a3d.mevnode.com"' in source
    assert (
        'POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"'
        in source
    )
    assert 'DATABASE_USER="edfinder_v3"' in source
    assert 'DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"' in source
    assert 'MIGRATION_NAME="010_v3_system_search_body_type_counts.sql"' in source
    assert f'MIGRATION_SHA="{MIGRATION_SHA}"' in source

    array_match = re.search(r"\bCONSTRAINTS=\((.*?)\n\)", source, re.DOTALL)
    assert array_match is not None
    names = re.findall(r"system_search_[a-z_]+_check", array_match.group(1))
    assert tuple(names) == CONSTRAINTS
    for name in CONSTRAINTS:
        assert array_match.group(1).count(name) == 1

    assert "lock_timeout = '5s'" in source
    assert "statement_timeout = '45min'" in source
    assert "VALIDATE CONSTRAINT" in source
    assert "ON_ERROR_STOP" in source
    assert "BEGIN READ ONLY" in source
    assert "AND state <> 'idle'" in source


def test_constraint_validation_action_excludes_forbidden_operations_and_ddl():
    source = _read(ACTION)

    for forbidden in (
        "DROP ",
        "DELETE ",
        "TRUNCATE",
        "INSERT ",
        "UPDATE ",
        "CREATE ",
        "NOT VALID",
        "docker restart",
        "docker compose",
        "docker stop",
        "docker rm",
        "systemctl",
        "pg_dump",
        "pg_restore",
        ".env",
        "Config.Env",
        "ADMIN_TOKEN",
        "FRONTIER_CLIENT_SECRET",
        "DATABASE_URL",
        "/root/.ssh",
    ):
        assert forbidden not in source

    ddl = list(re.finditer(r"ALTER TABLE", source))
    assert len(ddl) == 1
    assert source[ddl[0].start() :].startswith(
        "ALTER TABLE v3_derived.system_search VALIDATE CONSTRAINT"
    )


def test_constraint_validation_action_shell_syntax_is_valid():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable")
    result = subprocess.run([bash, "-n", str(ACTION)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_start_launches_only_the_two_unvalidated_constraints(tmp_path: Path):
    unvalidated = (CONSTRAINTS[3], CONSTRAINTS[14])
    result, calls = _run_action(tmp_path, "start", unvalidated=unvalidated)

    assert result.returncode == 0, result.stderr or result.stdout
    receipt = _receipt(result)
    assert receipt["status"] == "success"
    assert receipt["result"] == "launched"
    assert receipt["constraints_queued"] == list(unvalidated)
    assert receipt["constraints_validated_before"] == 16
    assert receipt["catalog_validation_launched"] is True
    assert receipt["db_writes_performed"] is True
    assert receipt["catalog_writes"] == "pg_constraint.convalidated only"
    assert receipt["data_rows_modified"] is False

    sql_calls = [call for call in calls if call["stdin"]]
    assert len(sql_calls) == 1
    sql = str(sql_calls[0]["stdin"])
    validation_lines = [
        line for line in sql.splitlines() if line.startswith("ALTER TABLE")
    ]
    assert validation_lines == [
        f"ALTER TABLE v3_derived.system_search VALIDATE CONSTRAINT {name};"
        for name in unvalidated
    ]
    assert "SET lock_timeout = '5s';" in sql
    assert "SET statement_timeout = '45min';" in sql
    assert "\\set ON_ERROR_STOP on" in sql
    assert _was_detached(calls)

    launch_calls = [call for call in calls if "-d" in call["args"]]
    assert len(launch_calls) == 1
    launch_command = str(launch_calls[0]["args"][-1])
    assert (
        "echo $! > /tmp/edfinder-validate-constraints/run.pid"
        in launch_command
    )
    assert "-f /tmp/edfinder-validate-constraints/run.sql" in launch_command
    assert "> /tmp/edfinder-validate-constraints/run.log 2>&1" in launch_command
    exit_line = (
        'echo "exit=$?" >> /tmp/edfinder-validate-constraints/run.log'
    )
    remove_pid = "rm -f /tmp/edfinder-validate-constraints/run.pid"
    assert remove_pid in launch_command
    assert launch_command.index(exit_line) < launch_command.index(remove_pid)

    python_calls = (tmp_path / "python-calls.log").read_text(encoding="utf-8")
    assert "platform.python_implementation" in python_calls
    assert "v3-system-search-validate-constraints-start" in python_calls


def test_start_stops_on_wrong_migration_hash_without_launch(tmp_path: Path):
    result, calls = _run_action(
        tmp_path,
        "start",
        ledger_sha="0" * 64,
        unvalidated=(CONSTRAINTS[-1],),
    )

    assert result.returncode != 0
    receipt = _receipt(result)
    assert receipt["status"] == "stopped"
    assert "migration_010_not_applied_or_hash_mismatch" in receipt["failures"]
    assert receipt["db_writes_performed"] is False
    assert receipt["catalog_writes"] == "pg_constraint.convalidated only"
    assert _was_detached(calls) is False


def test_start_is_a_noop_when_every_constraint_is_validated(tmp_path: Path):
    result, calls = _run_action(tmp_path, "start")

    assert result.returncode == 0, result.stderr or result.stdout
    receipt = _receipt(result)
    assert receipt["status"] == "success"
    assert receipt["result"] == "nothing_to_validate"
    assert receipt["constraints_queued"] == []
    assert receipt["constraints_validated_before"] == 18
    assert receipt["db_writes_performed"] is False
    assert receipt["catalog_writes"] == "pg_constraint.convalidated only"
    assert _was_detached(calls) is False


def test_start_stops_when_catalog_reports_an_active_validation(tmp_path: Path):
    result, calls = _run_action(
        tmp_path,
        "start",
        unvalidated=(CONSTRAINTS[-1],),
        active=True,
    )

    assert result.returncode != 0
    receipt = _receipt(result)
    assert receipt["status"] == "stopped"
    assert "validation_already_running" in receipt["failures"]
    assert _was_detached(calls) is False


def test_start_removes_stale_unrelated_pid_and_launches(tmp_path: Path):
    result, calls = _run_action(
        tmp_path,
        "start",
        unvalidated=(CONSTRAINTS[-1],),
        runner_kill_succeeds=True,
        runner_cmdline="sleep 600",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    receipt = _receipt(result)
    assert receipt["status"] == "success"
    assert receipt["result"] == "launched"
    assert _was_detached(calls) is True

    pid_calls = [
        call
        for call in calls
        if "run.pid" in " ".join(str(arg) for arg in call["args"])
        and "-d" not in call["args"]
    ]
    assert len(pid_calls) == 1
    pid_command = str(pid_calls[0]["args"][-1])
    assert "kill -0" in pid_command
    assert "/proc/$pid/cmdline" in pid_command
    assert 'tr "\\0" " "' in pid_command
    assert 'rm -f "$pid_file"' in pid_command


def test_start_stops_for_live_psql_run_sql_runner(tmp_path: Path):
    result, calls = _run_action(
        tmp_path,
        "start",
        unvalidated=(CONSTRAINTS[-1],),
        runner_kill_succeeds=True,
        runner_cmdline=(
            "psql -X --no-psqlrc -f "
            "/tmp/edfinder-validate-constraints/run.sql"
        ),
    )

    assert result.returncode != 0
    receipt = _receipt(result)
    assert receipt["status"] == "stopped"
    assert "validation_already_running" in receipt["failures"]
    assert _was_detached(calls) is False


def test_status_reports_catalog_state_and_canned_log_tail(tmp_path: Path):
    log_lines = ("validating system_search_ww_count_check", "Time: 42.000 ms")
    result, calls = _run_action(
        tmp_path,
        "status",
        unvalidated=(CONSTRAINTS[-1],),
        log_lines=log_lines,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    receipt = _receipt(result)
    assert receipt["operation"] == "v3-system-search-validate-constraints-status"
    assert receipt["status"] == "success"
    assert receipt["read_only"] is True
    assert receipt["db_writes_performed"] is False
    assert receipt["validated_count"] == 17
    assert receipt["all_validated"] is False
    assert len(receipt["constraints"]) == 18
    assert [row["name"] for row in receipt["constraints"]] == list(CONSTRAINTS)
    assert receipt["constraints"][-1]["validated"] is False
    assert receipt["runner_exit_code"] is None
    assert receipt["log_tail"] == list(log_lines)
    assert "validation_runner_failed" not in receipt["failures"]
    assert _was_detached(calls) is False


def test_status_stops_when_runner_failed_with_unvalidated_constraint(
    tmp_path: Path,
):
    result, _ = _run_action(
        tmp_path,
        "status",
        unvalidated=(CONSTRAINTS[-1],),
        log_lines=("exit=2", "not-an-exit", "exit=7"),
    )

    assert result.returncode == 1
    receipt = _receipt(result)
    assert receipt["status"] == "stopped"
    assert receipt["validated_count"] == 17
    assert receipt["all_validated"] is False
    assert receipt["runner_exit_code"] == 7
    assert "validation_runner_failed" in receipt["failures"]


def test_status_keeps_success_when_runner_failed_after_all_validated(
    tmp_path: Path,
):
    result, _ = _run_action(tmp_path, "status", log_lines=("exit=9",))

    assert result.returncode == 0, result.stderr or result.stdout
    receipt = _receipt(result)
    assert receipt["status"] == "success"
    assert receipt["validated_count"] == 18
    assert receipt["all_validated"] is True
    assert receipt["runner_exit_code"] == 9
    assert "validation_runner_failed" not in receipt["failures"]


def test_status_prints_stopped_receipt_and_fails_when_ledger_query_fails(
    tmp_path: Path,
):
    result, calls = _run_action(tmp_path, "status", ledger_query_fails=True)

    assert result.returncode == 1
    receipt = _receipt(result)
    assert receipt["status"] == "stopped"
    assert "migration_ledger_query_failed" in receipt["failures"]
    assert _was_detached(calls) is False


@pytest.mark.parametrize(
    ("ledger_sha", "expected_failure"),
    (
        ("0" * 64, "migration_010_hash_mismatch"),
        ("", "migration_010_not_applied"),
    ),
)
def test_status_stops_when_migration_identity_is_not_verified(
    tmp_path: Path,
    ledger_sha: str,
    expected_failure: str,
):
    result, _ = _run_action(tmp_path, "status", ledger_sha=ledger_sha)

    assert result.returncode == 1
    receipt = _receipt(result)
    assert receipt["status"] == "stopped"
    assert receipt["migration_010_in_ledger"] is False
    assert receipt["all_validated"] is True
    assert expected_failure in receipt["failures"]


def test_action_stops_when_exact_cpython_314_is_unavailable(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python3 = fake_bin / "python3"
    python3.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            # Simulate a discoverable interpreter that is not CPython 3.14.
            exit 1
            """
        ),
        encoding="utf-8",
    )
    python3.chmod(0o755)

    bash = shutil.which("bash")
    assert bash is not None
    env = os.environ.copy()
    env["PATH"] = str(fake_bin)
    result = subprocess.run(
        [bash, str(ACTION), "status"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )

    assert result.returncode == 1
    receipt = _receipt(result)
    assert receipt["status"] == "stopped"
    assert receipt["failures"] == ["python314_required"]
