from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest
import yaml


pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/v3-archetype-calibration-probe.sh"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
GENERATION_KEY = "ratings_v4_prod_p4_parallel_v1"
API_IMAGE = "registry.example.test/ed-finder-api@sha256:0123456789abcdef"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _docker_calls(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _make_fake_path(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker-calls.jsonl"

    (fake_bin / "hostname").write_text(
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
    (fake_bin / "python3.14").write_text(
        '#!/bin/sh\nexec "$TEST_PYTHON_BIN" "$@"\n', encoding="utf-8"
    )
    (fake_bin / "docker").write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json
            import os
            from pathlib import Path
            import sys

            args = sys.argv[1:]
            joined = " ".join(args)
            log_path = Path(os.environ["TEST_DOCKER_LOG"])
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(args) + "\\n")

            if "derived_generation_purge_event" in joined:
                print(json.dumps({{"database": "edfinder_v3_phase4c_full_20260827_r5",
                    "read_only": "on", "ledger_present": True, "unresolved": []}}))
                raise SystemExit(0)
            if args[:2] == ["context", "show"]:
                print("default")
                raise SystemExit(0)
            if args[:3] == ["context", "inspect", "default"]:
                print('{{"Endpoints":{{"docker":{{"Host":"unix:///var/run/docker.sock"}}}}}}')
                raise SystemExit(0)
            if args[:1] == ["inspect"]:
                if "State.Running" in joined:
                    print("true")
                elif "com.docker.compose.service" in joined:
                    print("api-blue")
                elif ".Config.Image" in joined:
                    print({API_IMAGE!r})
                elif ".Config.Env" in joined:
                    print("DATABASE_URL=postgresql://postgres/probe_test")
                else:
                    print("{{}}")
                raise SystemExit(0)
            if args[:1] == ["ps"]:
                print("api-active")
                raise SystemExit(0)
            if args[:1] == ["exec"] and "current_derived_generation" in joined:
                current = "true" if os.environ["FAKE_CURRENT"] == "1" else "false"
                print({GENERATION_KEY!r} + "\\tPUBLISHED\\t" + current)
                raise SystemExit(0)
            if args[:1] == ["run"]:
                print(os.environ["FAKE_PROBE_OUTPUT"], end="")
                raise SystemExit(0)
            raise SystemExit(2)
            """
        ),
        encoding="utf-8",
    )
    for executable in ("hostname", "python3.14", "docker"):
        (fake_bin / executable).chmod(0o755)
    return fake_bin, docker_log


def _run_action(
    tmp_path: Path,
    *,
    current_pointer: bool,
    probe_output: str = (
        '{"probe_version":"v3-archetype-calibration-probe-1",'
        '"read_only":true}\n'
    ),
) -> tuple[subprocess.CompletedProcess[str], list[list[str]], Path, Path]:
    fake_bin, docker_log = _make_fake_path(tmp_path)
    source_sha = hashlib.sha1(str(tmp_path).encode()).hexdigest()
    stage = Path(f"/var/tmp/edfinder-v3-probe-{source_sha}")
    stage.mkdir(mode=0o700)
    (stage / "scripts").mkdir()
    helper_dir = stage / "scripts/operator/lib"
    helper_dir.mkdir(parents=True)
    for helper_name in ("v3-purge-state.sh", "v3_purge_state.py"):
        shutil.copyfile(ROOT / "scripts/operator/lib" / helper_name, helper_dir / helper_name)
    (stage / ".v3-probe-wheelhouse").mkdir()
    (stage / ".v3-probe-source-sha").write_text(
        f"{source_sha}\n", encoding="utf-8"
    )
    for script in (
        "v3_archetype_calibration_probe.py",
        "v3_system_archetype.py",
        "v3_system_archetype_model.py",
    ):
        (stage / "scripts" / script).write_text(
            "# staged test module\n", encoding="utf-8"
        )
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
            "HOME": str(home),
            "TEST_DOCKER_LOG": str(docker_log),
            "TEST_PYTHON_BIN": sys.executable,
            "FAKE_CURRENT": "1" if current_pointer else "0",
            "FAKE_PROBE_OUTPUT": probe_output,
        }
    )
    try:
        result = subprocess.run(
            ["bash", str(ACTION), "run", str(stage), source_sha],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
    finally:
        shutil.rmtree(stage)
    return result, _docker_calls(docker_log), home, stage


def test_probe_operation_is_allowlisted_through_trusted_main():
    workflow = _read(WORKFLOW)
    parsed_workflow = yaml.safe_load(workflow)
    execute_job = parsed_workflow["jobs"]["execute"]
    probe_step = next(
        step
        for step in execute_job["steps"]
        if step.get("name")
        == "Stage trusted main and run V3 archetype calibration probe"
    )

    # Finalization shares this job: Archetype finalize runs validation and the
    # VACUUM (ANALYZE), each bounded at two hours, in sequence; retain a small
    # orchestration margin around that bound.
    assert execute_job["timeout-minutes"] == 270
    assert probe_step["timeout-minutes"] == 35
    assert "          - v3-archetype-calibration-probe\n" in workflow
    assert "|v3-archetype-calibration-probe|" in workflow
    condition = "steps.request.outputs.operation == 'v3-archetype-calibration-probe'"
    assert workflow.count(condition) == 3
    assert "Prepare trusted V3 archetype probe bundle marker and dependencies" in workflow
    assert "Stage trusted main and run V3 archetype calibration probe" in workflow
    assert "Upload V3 archetype calibration probe receipt" in workflow
    assert ".v3-probe-source-sha" in workflow
    assert ".v3-probe-wheelhouse" in workflow
    assert "--require-hashes -r trusted-main/deploy/v3-production/f2d-wheels.txt" in workflow
    assert "stage=\"/var/tmp/edfinder-v3-probe-${source_sha}\"" in workflow
    assert "bash -s -- run '$stage' '$source_sha'" in workflow
    script = "trusted-main/scripts/operator/actions/v3-archetype-calibration-probe.sh"
    assert workflow.count(script) == 1
    assert "V3 archetype calibration probe requires root or passwordless sudo" in workflow
    assert "sudo -n bash -s -- run '$stage' '$source_sha'" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in workflow
    assert "IdentitiesOnly=yes" in workflow
    assert "name: v3-archetype-calibration-probe-operation" in workflow
    assert "retention-days: 90" in workflow


def test_complete_read_operations_are_allowlisted_and_use_a_trusted_bundle():
    workflow = _read(WORKFLOW)
    parsed_workflow = yaml.safe_load(workflow)
    execute_job = parsed_workflow["jobs"]["execute"]
    # PyYAML's YAML 1.1 resolver treats the unquoted Actions key `on` as true.
    operation_options = parsed_workflow[True]["workflow_dispatch"]["inputs"][
        "operation"
    ]["options"]

    operations = (
        "v3-archetype-calibration-complete-start",
        "v3-archetype-calibration-complete-status",
    )
    for operation in operations:
        assert operation_options.count(operation) == 1
        assert f"|{operation}|" in workflow or f"|{operation})" in workflow

    step_names = {step.get("name") for step in execute_job["steps"]}
    assert "Prepare trusted V3 archetype complete-read bundle and dependencies" in step_names
    assert "Stage trusted main for V3 archetype complete read" in step_names
    assert "Launch V3 archetype calibration complete read" in step_names
    assert "Inspect V3 archetype calibration complete-read status" in step_names
    assert "Upload V3 archetype calibration complete-read operation receipt" in step_names

    assert ".v3-archetype-complete-source-sha" in workflow
    assert ".v3-probe-wheelhouse" in workflow
    assert "--require-hashes -r trusted-main/deploy/v3-production/f2d-wheels.txt" in workflow
    assert 'stage="/var/tmp/edfinder-v3-archetype-complete-${source_sha}"' in workflow
    assert "bash -s -- start '$stage' '$source_sha'" in workflow
    assert "bash -s -- status '$stage' '$source_sha'" in workflow
    script = "trusted-main/scripts/operator/actions/v3-archetype-calibration-complete.sh"
    assert workflow.count(script) == 2
    assert "V3 archetype complete-read start requires root or passwordless sudo" in workflow
    assert "V3 archetype complete-read status requires root or passwordless sudo" in workflow
    assert "name: v3-archetype-calibration-complete-operation" in workflow
    assert "retention-days: 90" in workflow


def test_capacity_gate_operation_is_allowlisted_and_uses_a_trusted_bundle():
    workflow = _read(WORKFLOW)
    parsed_workflow = yaml.safe_load(workflow)
    execute_job = parsed_workflow["jobs"]["execute"]
    operation_options = parsed_workflow[True]["workflow_dispatch"]["inputs"][
        "operation"
    ]["options"]

    assert operation_options.count("v3-finder-capacity-gate") == 1
    assert "|v3-finder-capacity-gate|" in workflow
    step_names = {step.get("name") for step in execute_job["steps"]}
    assert "Prepare trusted V3 Finder capacity gate bundle and dependencies" in step_names
    assert "Stage trusted main for V3 Finder capacity gate" in step_names
    assert "Run V3 Finder capacity gate" in step_names
    assert "Upload V3 Finder capacity gate receipt" in step_names

    gate_step = next(
        step
        for step in execute_job["steps"]
        if step.get("name") == "Run V3 Finder capacity gate"
    )
    assert gate_step["timeout-minutes"] == 50
    assert "^[0-9a-f]{64}$" in workflow
    assert ".v3-capacity-gate-source-sha" in workflow
    assert ".v3-probe-wheelhouse" in workflow
    assert 'stage="/var/tmp/edfinder-v3-capacity-gate-${source_sha}"' in workflow
    assert "bash -s -- run '$stage' '$source_sha'" in workflow
    assert "--preserve-env=F2D_OPERATOR_CODE_SHA256_ATTESTED" in workflow
    assert "trusted-main/scripts/operator/actions/v3-finder-capacity-gate.sh" in workflow
    assert "name: v3-finder-capacity-gate-operation" in workflow
    assert "retention-days: 90" in workflow


def test_probe_action_has_fixed_targets_and_bounded_read_only_container():
    source = _read(ACTION)

    assert 'TARGET_HOSTNAME="ed-finder-prod"' in source
    assert 'TARGET_FQDN="nb79a3d.mevnode.com"' in source
    assert (
        'POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"'
        in source
    )
    assert 'DATABASE_USER="edfinder_v3"' in source
    assert 'DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"' in source
    assert 'COMPOSE_PROJECT="edfinder-v3-production"' in source
    assert 'WORKER_NETWORK="edfinder-v3-phase4c-full-20260827_r5-network"' in source
    assert f'TARGET_GENERATION_KEY="{GENERATION_KEY}"' in source
    assert "BEGIN READ ONLY" in source
    assert '"$state" = "PUBLISHED"' in source
    assert "current_derived_generation" in source
    assert "timeout --signal=TERM 1500 docker run --rm" in source
    assert "--cpus 2" in source
    assert "--memory 4g" in source
    assert "--memory-swap 4g" in source
    assert "--pids-limit 128" in source
    assert "--read-only" in source
    assert "--tmpfs /tmp" in source
    assert 'dst=/work,readonly' in source
    assert ".v3-probe-wheelhouse" in source
    assert "pip install --quiet" in source
    assert '"psycopg[binary]==3.3.4" 1>&2' in source
    assert "--target /tmp/v3-probe-deps" in source
    assert 'PYTHONPATH="/tmp/v3-probe-deps:/work:/work/apps/api/src"' in source
    assert f"--generation-key {GENERATION_KEY} --max-systems 200000" in source
    assert "flock" not in source


def test_probe_action_excludes_mutation_and_service_control_commands():
    source = _read(ACTION)

    for forbidden in (
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "TRUNCATE",
        "ALTER ",
        "DROP ",
        "CREATE ",
        "publish_derived_generation",
        "register_product",
        "build_available",
        "validate_product",
        "docker restart",
        "docker compose",
        "systemctl",
        "pg_dump",
        "pg_restore",
    ):
        assert forbidden not in source
    assert "probe.envfile" in source
    assert "search.env" not in source
    assert ".Config.Env" in source


def test_probe_action_shell_syntax_is_valid():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable")
    result = subprocess.run([bash, "-n", str(ACTION)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_wrong_current_pointer_fails_before_probe_container_run(tmp_path: Path):
    result, calls, _, _ = _run_action(tmp_path, current_pointer=False)

    assert result.returncode != 0
    assert "not the current published pointer" in result.stderr
    assert not [args for args in calls if args[:1] == ["run"]]


def test_current_pointer_runs_once_removes_env_file_and_prints_receipt(
    tmp_path: Path,
):
    probe_output = (
        '{"probe_version":"v3-archetype-calibration-probe-1",'
        '"read_only":true}\n'
    )
    result, calls, home, stage = _run_action(
        tmp_path, current_pointer=True, probe_output=probe_output
    )

    assert result.returncode == 0, result.stderr
    runs = [args for args in calls if args[:1] == ["run"]]
    assert len(runs) == 1
    run = runs[0]
    assert "--read-only" in run
    assert "--rm" in run
    assert f"type=bind,src={stage},dst=/work,readonly" in run
    assert API_IMAGE in run
    joined = " ".join(run)
    assert (
        "scripts/v3_archetype_calibration_probe.py "
        f"--generation-key {GENERATION_KEY} --max-systems 200000"
    ) in joined
    env_file = home / ".local/state/ed-finder/v3-archetype-probe/probe.envfile"
    assert not env_file.exists()
    assert "operation=v3-archetype-calibration-probe\n" in result.stdout
    assert "result=completed\n" in result.stdout
    _, marker, captured_probe = result.stdout.partition("probe_json=\n")
    assert marker
    assert captured_probe == probe_output


def test_non_json_prefix_fails_closed_and_prints_raw_probe_output(tmp_path: Path):
    probe_output = (
        "pip installation chatter\n"
        '{"probe_version":"v3-archetype-calibration-probe-1",'
        '"read_only":true}\n'
    )

    result, calls, _, _ = _run_action(
        tmp_path, current_pointer=True, probe_output=probe_output
    )

    assert len([args for args in calls if args[:1] == ["run"]]) == 1
    assert result.returncode == 65
    assert "result=failed\n" in result.stdout
    assert "exit_code=65\n" in result.stdout
    assert "failure=invalid_probe_output\n" in result.stdout
    assert "probe_json=\n" not in result.stdout
    _, marker, captured_probe = result.stdout.partition("probe_output_raw=\n")
    assert marker
    assert captured_probe == probe_output
