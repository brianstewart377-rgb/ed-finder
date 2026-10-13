from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

import pytest
import yaml


pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/v3-finder-capacity-gate.sh"
PROGRAM = ROOT / "scripts/v3_finder_capacity_gate.py"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_action_checks_attested_identity_before_any_target_check() -> None:
    source = _read(ACTION)

    identity = source.index("require_f2d_operator_code_identity")
    target = source.index("require_target()")
    assert identity < target

    environment = os.environ.copy()
    environment.pop("F2D_OPERATOR_CODE_SHA256_ATTESTED", None)
    result = subprocess.run(
        ["bash", str(ACTION), "run", str(ROOT), "0" * 40],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 64
    assert "attested_identity_missing" in result.stderr
    assert "unexpected hostname" not in result.stderr


def test_action_pins_target_stage_and_published_generation() -> None:
    source = _read(ACTION)

    for declaration in (
        'TARGET_HOSTNAME="ed-finder-prod"',
        'TARGET_FQDN="nb79a3d.mevnode.com"',
        'POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"',
        'DATABASE_USER="edfinder_v3"',
        'DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"',
        'COMPOSE_PROJECT="edfinder-v3-production"',
        'WORKER_NETWORK="edfinder-v3-phase4c-full-20260827_r5-network"',
        'TARGET_GENERATION_KEY="ratings_v4_prod_p4_parallel_v1"',
        'TARGET_GENERATION_ID="cfc25d36-3bc7-4011-a465-d6460eaaf826"',
        'TARGET_PUBLICATION_SEQUENCE="1"',
    ):
        assert declaration in source

    assert '/var/tmp/edfinder-v3-capacity-gate-"$SOURCE_SHA"' in source
    assert ".v3-capacity-gate-source-sha" in source
    assert ".v3-probe-wheelhouse" in source
    # The Search and Archetype build actions call the gate from their own staged
    # checkouts (design 8.5), so those two namespaces and markers are accepted too,
    # each only with its own marker; anything else stays refused.
    assert '/var/tmp/edfinder-v3-search-"$SOURCE_SHA") marker=".v3-search-source-sha"' in source
    assert (
        '/var/tmp/edfinder-v3-archetype-build-"$SOURCE_SHA") marker=".v3-archetype-build-source-sha"'
        in source
    )
    assert '*) fail "trusted main bundle path is outside reviewed staging namespace"' in source
    search_action = (ROOT / "scripts/operator/actions/v3-system-search-f1.sh").read_text()
    archetype_action = (ROOT / "scripts/operator/actions/v3-system-archetype.sh").read_text()
    assert '/var/tmp/edfinder-v3-search-"$SOURCE_SHA"' in search_action
    assert '/var/tmp/edfinder-v3-archetype-build-"$SOURCE_SHA"' in archetype_action
    workflow = WORKFLOW.read_text()
    # Both build stages must carry the gate's wheelhouse for the in-stage gate run.
    assert "mkdir -p trusted-main/.v3-search-wheelhouse trusted-main/.v3-probe-wheelhouse" in workflow
    assert "mkdir -p trusted-main/.v3-archetype-wheelhouse trusted-main/.v3-probe-wheelhouse" in workflow
    assert "BEGIN READ ONLY" in source
    assert "current_derived_generation" in source
    assert '"$identifier" = "$TARGET_GENERATION_ID"' in source
    assert '"$state" = "PUBLISHED"' in source
    assert '"$sequence" = "$TARGET_PUBLICATION_SEQUENCE"' in source
    assert '"$current" = "true"' in source


def test_action_reads_the_postgres_mount_and_fresh_df_like_step_zero() -> None:
    source = _read(ACTION)

    assert (
        "{{range .Mounts}}{{.Source}}\\t{{.Destination}}\\n{{end}}" in source
    )
    assert '"$destination" = "/var/lib/postgresql/data"' in source
    # The production PostgreSQL 18 container mounts its volume at
    # /var/lib/postgresql (step 0 receipt host_disk.mount_destination), so the
    # step 0 fallback to the first /var/lib/postgresql* mount must be kept.
    assert '"$destination" == /var/lib/postgresql*' in source
    assert 'mount_source="$fallback_source"' in source
    step0 = json.loads(
        (ROOT / "docs/operations/evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json")
        .read_text(encoding="utf-8")
    )
    assert step0["footprint"]["host_disk"]["mount_destination"] == "/var/lib/postgresql"
    assert 'df -B1 --output=source,fstype,size,used,avail "$mount_source"' in source
    assert 'read_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"' in source
    for field in (
        '"filesystem"',
        '"filesystem_type"',
        '"size_bytes"',
        '"used_bytes"',
        '"avail_bytes"',
        '"read_at"',
        '"mount_source"',
        '"mount_destination"',
    ):
        assert field in source
    assert 'STATE_ROOT/runs/${timestamp}-$$' in source
    assert 'install -d -m 700 "$STATE_ROOT" "$STATE_ROOT/runs" "$run_dir"' in source


def test_action_runs_the_gate_in_a_bounded_read_only_container() -> None:
    source = _read(ACTION)

    assert "timeout --signal=TERM 2700 docker run --rm" in source
    assert "--cpus 2" in source
    assert "--memory 4g" in source
    assert "--memory-swap 4g" in source
    assert "--pids-limit 128" in source
    assert "--read-only" in source
    assert "--tmpfs /tmp" in source
    assert 'dst=/work,readonly' in source
    assert 'dst=/gate"' in source
    assert 'dst=/state/complete,readonly' in source
    assert 'dst=/state/search,readonly' in source
    assert 'dst=/state/archetype,readonly' in source
    assert 'if [ -d "$COMPLETE_STATE_ROOT" ]' in source
    assert 'if [ -d "$SEARCH_STATE_ROOT" ]' in source
    assert 'if [ -d "$ARCHETYPE_STATE_ROOT" ]' in source
    assert '"psycopg[binary]==3.3.4" 1>&2' in source
    assert "--no-index" in source
    assert "--find-links /work/.v3-probe-wheelhouse" in source
    assert "--target /tmp/v3-capacity-gate-deps" in source
    assert 'PYTHONPATH="/tmp/v3-capacity-gate-deps:/work:/work/apps/api/src"' in source


def test_action_passes_exact_gate_arguments_and_dsn_by_temporary_env_file() -> None:
    source = _read(ACTION)

    for argument in (
        "--generation-key ratings_v4_prod_p4_parallel_v1",
        "--generation-id cfc25d36-3bc7-4011-a465-d6460eaaf826",
        "--publication-sequence 1",
        "--volume-reading /gate/volume-reading.json",
        "--complete-state /state/complete",
        "--search-state /state/search",
        "--archetype-state /state/archetype",
        "--output /gate/receipt.json",
    ):
        assert argument in source
    assert "V3_FINDER_CAPACITY_GATE_DATABASE_URL=%s" in source
    assert "F2D_OPERATOR_CODE_SHA256_ATTESTED=%s" in source
    assert '--env-file "$env_file"' in source
    assert 'chmod 600 "$env_file"' in source
    assert source.count('rm -f -- "$env_file"') >= 2
    assert '--env "V3_FINDER_CAPACITY_GATE_DATABASE_URL=' not in source
    assert "--env V3_FINDER_CAPACITY_GATE_DATABASE_URL=" not in source


def test_action_emits_the_required_operation_envelope_and_preserves_exit_code() -> None:
    source = _read(ACTION)

    for field in (
        '"schema_version": "ed-finder/operator-operation-result/v1"',
        '"operation": "v3-finder-capacity-gate"',
        '"status": status',
        '"exit_code": exit_code',
        '"failures": failures',
        '"read_only": True',
        '"db_writes_performed": False',
        '"publication_performed": False',
        '"canonical_writes_performed": False',
        '"application_service_changes_performed": False',
        '"f2d_operator_code_sha256": os.environ["F2D_IDENTITY_VALUE"]',
        '"volume_reading": volume',
        '"receipt": receipt',
    ):
        assert field in source
    assert "{2, 3, 10, 11, 12, 13, 14, 15, 16}" in source
    assert 'emit_result "$exit_code" "$run_dir"' in source
    assert 'return "$exit_code"' in source


def test_gate_program_is_read_only() -> None:
    source = _read(PROGRAM)

    assert not re.search(r"\b(?:INSERT|UPDATE|DELETE|TRUNCATE)\b", source)
    assert "connection.read_only = True" in source
    assert "default_transaction_read_only" in source


def test_ops_workflow_allowlists_attestation_only_for_f2d_actions() -> None:
    workflow = _read(WORKFLOW)
    parsed = yaml.safe_load(workflow)
    # PyYAML's YAML 1.1 resolver treats the unquoted Actions key `on` as true.
    inputs = parsed[True]["workflow_dispatch"]["inputs"]
    operation_options = inputs["operation"]["options"]

    assert operation_options.count("v3-finder-capacity-gate") == 1
    assert "f2d_operator_code_sha256_attested" in inputs
    assert inputs["f2d_operator_code_sha256_attested"]["required"] is False
    assert "|v3-finder-capacity-gate|" in workflow
    assert (
        '[[ "$INPUT_F2D_OPERATOR_CODE_SHA256_ATTESTED" =~ ^[0-9a-f]{64}$ ]]'
        in workflow
    )
    governed_operations = (
        "v3-finder-capacity-gate",
        "v3-archetype-plan-probe",
        "v3-system-search-f1-start",
        "v3-system-search-f1-status",
        "v3-system-search-f1-finalize",
        "v3-system-archetype-start",
        "v3-system-archetype-status",
        "v3-system-archetype-finalize",
    )
    governed_case = "|".join(governed_operations)
    assert governed_case in workflow
    assert "accepted only for F2d governed actions" in workflow


def test_ops_workflow_wires_f2d_build_operations() -> None:
    workflow = _read(WORKFLOW)
    parsed = yaml.safe_load(workflow)
    inputs = parsed[True]["workflow_dispatch"]["inputs"]
    operation_options = inputs["operation"]["options"]
    execute_job = parsed["jobs"]["execute"]
    step_names = {step.get("name") for step in execute_job["steps"]}

    for operation in (
        "v3-system-search-f1-finalize",
        "v3-system-archetype-start",
        "v3-system-archetype-status",
        "v3-system-archetype-finalize",
    ):
        assert operation_options.count(operation) == 1
        assert operation in workflow

    assert {
        "Stage trusted main for V3 Search F1",
        "Launch V3 Search F1",
        "Inspect V3 Search F1 status",
        "Finalize V3 Search F1",
        "Upload V3 Search F1 operation receipt",
        "Prepare trusted V3 Archetype build bundle and dependencies",
        "Stage trusted main for V3 Archetype build",
        "Launch V3 Archetype build",
        "Inspect V3 Archetype build status",
        "Finalize V3 Archetype build",
        "Upload V3 Archetype build operation receipt",
    } <= step_names
    assert 'stage="/var/tmp/edfinder-v3-archetype-build-${source_sha}"' in workflow
    assert ".v3-archetype-build-source-sha" in workflow
    assert ".v3-archetype-wheelhouse" in workflow
    assert "trusted-main/scripts/operator/actions/v3-system-archetype.sh" in workflow
    assert workflow.count("--preserve-env=F2D_OPERATOR_CODE_SHA256_ATTESTED") >= 5
    assert workflow.count('[[ "$F2D_OPERATOR_CODE_SHA256_ATTESTED" =~ ^[0-9a-f]{64}$ ]]') >= 7
    assert "DATABASE_URL" not in workflow


def test_ops_workflow_stages_runs_and_uploads_capacity_gate_receipt() -> None:
    workflow = _read(WORKFLOW)
    parsed = yaml.safe_load(workflow)
    execute_job = parsed["jobs"]["execute"]
    step_names = {step.get("name") for step in execute_job["steps"]}

    assert "Prepare trusted V3 Finder capacity gate bundle and dependencies" in step_names
    assert "Stage trusted main for V3 Finder capacity gate" in step_names
    assert "Run V3 Finder capacity gate" in step_names
    assert "Upload V3 Finder capacity gate receipt" in step_names
    assert workflow.count(
        "steps.request.outputs.operation == 'v3-finder-capacity-gate'"
    ) == 4
    assert 'stage="/var/tmp/edfinder-v3-capacity-gate-${source_sha}"' in workflow
    assert ".v3-capacity-gate-source-sha" in workflow
    assert ".v3-probe-wheelhouse" in workflow
    assert "psycopg[binary]==3.3.4" in workflow
    assert "bash -s -- run '$stage' '$source_sha'" in workflow
    assert "sudo -n --preserve-env=F2D_OPERATOR_CODE_SHA256_ATTESTED" in workflow
    assert (
        workflow.count(
            "trusted-main/scripts/operator/actions/v3-finder-capacity-gate.sh"
        )
        == 1
    )
    assert "name: v3-finder-capacity-gate-operation" in workflow
    assert "retention-days: 90" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in workflow
    assert "IdentitiesOnly=yes" in workflow


def test_step0_capacity_evidence_is_bound_by_the_operator_code_manifest() -> None:
    """The gate derives real_pre010_bytes_per_row from the committed step-0 receipt.

    That receipt carries no seal of its own, so it is bound through the
    operator-code manifest instead: any change to it moves
    f2d_operator_code_sha256 and every F2d action refuses until a later accepted
    release re-attests the new value.
    """
    manifest = (ROOT / "deploy/v3-production/f2d-operator-code.txt").read_text().splitlines()
    assert "docs/operations/evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json" in manifest
    evidence = (ROOT / "scripts/operator/lib/f2d_evidence.py").read_text()
    assert "2026-10-10-v3-derived-lifecycle-status-receipt.json" in evidence


def test_archetype_finalize_bound_covers_validation_then_vacuum() -> None:
    action = (ROOT / "scripts/operator/actions/v3-system-archetype.sh").read_text(
        encoding="utf-8"
    )
    # Both sequential finalize phases carry their own two-hour bound.
    assert "command=(timeout --signal=TERM 7200 docker run --rm)" in action
    assert 'timeout --signal=TERM 7200 docker exec "$POSTGRES_CONTAINER"' in action
    finalize = action[action.index("finalize_operation() {"):]
    assert finalize.index("run_archetype_container") < finalize.index("VACUUM (ANALYZE)")

    parsed = yaml.safe_load(_read(WORKFLOW))
    execute_job = parsed["jobs"]["execute"]
    step = next(
        step for step in execute_job["steps"] if step.get("name") == "Finalize V3 Archetype build"
    )
    assert step["timeout-minutes"] * 60 >= 7200 + 7200
    assert execute_job["timeout-minutes"] > step["timeout-minutes"]
    # GitHub-hosted runners stop every job at six hours.
    assert execute_job["timeout-minutes"] <= 360


def test_search_and_archetype_status_use_the_start_privilege_boundary() -> None:
    parsed = yaml.safe_load(_read(WORKFLOW))
    steps = {step.get("name"): step for step in parsed["jobs"]["execute"]["steps"]}
    for name in (
        "Inspect V3 Search F1 status",
        "Inspect V3 Archetype build status",
        "Inspect V3 archetype calibration complete-read status",
    ):
        run = steps[name]["run"]
        assert 'if [ \\"\\$(id -u)\\" -eq 0 ]; then exec bash -s -- status' in run
        assert "exec sudo -n --preserve-env=F2D_OPERATOR_CODE_SHA256_ATTESTED bash -s -- status" in run


@pytest.mark.parametrize(
    ("action_path", "table"),
    [
        ("scripts/operator/actions/v3-system-archetype.sh", "archetype_build_chunk"),
        ("scripts/operator/actions/v3-system-search-f1.sh", "search_build_chunk"),
    ],
)
def test_build_start_proof_requires_a_chunk_from_this_launch(action_path, table) -> None:
    action = (ROOT / action_path).read_text(encoding="utf-8")
    start = action[action.index("start_operation() {"):action.index("status_operation() {")]
    baseline = start.index("baseline_chunks=\"$(db_query")
    launch = start.index("docker run -d")
    assert baseline < launch
    assert f"FROM v3_derived.{table}" in start[baseline:launch]
    proof = start[launch:]
    # A resumed build's earlier chunks are not proof for the new worker.
    assert '[ "$proof" -gt "$baseline_chunks" ] && break' in proof
    assert '[ "$proof" -ge 1 ]' not in proof


def _function_source(action: str, name: str) -> str:
    start = action.index(f"{name}() {{\n")
    end = action.index("\n}\n", start) + 3
    return action[start:end]


@pytest.mark.parametrize(
    "action_path",
    [
        "scripts/operator/actions/v3-system-archetype.sh",
        "scripts/operator/actions/v3-system-search-f1.sh",
    ],
)
@pytest.mark.parametrize("stops", [True, False])
def test_unproven_worker_is_stopped_before_start_reports_failure(
    tmp_path, action_path, stops
) -> None:
    action = (ROOT / action_path).read_text(encoding="utf-8")
    start = action[action.index("start_operation() {"):action.index("status_operation() {")]
    failure = start[start.index('[ "$proof" -le "$baseline_chunks" ]; then'):]
    assert failure.index("stop_unproven_worker") < failure.index("fail ")

    state = tmp_path / "state"
    state.write_text("running", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  inspect) if [ "$2" = "-f" ]; then cat "$STATE_FILE"; fi; exit 0 ;;\n'
        '  stop) echo "$*" >> "$STOP_LOG"; '
        '[ "$STOPS" = 1 ] && printf exited > "$STATE_FILE"; exit 0 ;;\n'
        "esac\n"
        "exit 2\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    script = (
        "set -euo pipefail\n"
        "WORKER=edfinder-test-worker\n"
        "fail() { printf 'FAIL: %s\\n' \"$*\" >&2; exit 64; }\n"
        + _function_source(action, "stop_unproven_worker")
        + "stop_unproven_worker\necho returned\n"
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "STATE_FILE": str(state),
        "STOP_LOG": str(tmp_path / "stop.log"),
        "STOPS": "1" if stops else "0",
    }
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env, timeout=10
    )
    assert "stop --time 60 edfinder-test-worker" in (tmp_path / "stop.log").read_text()
    if stops:
        assert result.returncode == 0, result.stderr
        assert state.read_text() == "exited"
    else:
        assert result.returncode == 64
        assert "could not be stopped and may still be writing" in result.stderr


def test_complete_read_start_stops_an_unproven_worker_before_failing() -> None:
    action = (
        ROOT / "scripts/operator/actions/v3-archetype-calibration-complete.sh"
    ).read_text(encoding="utf-8")
    failure = action[action.index('  if [ "$proof" != true ]; then'):]
    failure = failure[: failure.index("\n  fi\n") + 6]
    assert failure.index('docker stop --time 60 "$WORKER"') < failure.index("did not prove this launch")


@pytest.mark.parametrize("write_succeeds", [True, False])
def test_volume_reading_is_refreshed_atomically_while_the_gate_runs(
    tmp_path, write_succeeds
) -> None:
    action = (ROOT / "scripts/operator/actions/v3-finder-capacity-gate.sh").read_text(
        encoding="utf-8"
    )
    run = action[action.index("run_operation() {"):]
    assert run.index('refresh_volume_reading "$volume_file" &') < run.index("docker run --rm")
    assert run.rindex('kill "$refresher"') > run.index("docker run --rm")

    output = tmp_path / "volume-reading.json"
    output.write_text("old\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    # Two loop iterations, then the fake sleep fails to end the loop.
    (fake_bin / "sleep").write_text(
        '#!/bin/sh\nn=$(cat "$COUNT" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$COUNT"; '
        '[ "$n" -le 2 ]\n',
        encoding="utf-8",
    )
    (fake_bin / "sleep").chmod(0o755)
    script = (
        "set -euo pipefail\n"
        "fail() { exit 64; }\n"
        'write_volume_reading() { [ "$WRITE_OK" = 1 ] || fail; '
        'printf "new %s\\n" "$(cat "$COUNT")" > "$1"; }\n'
        + _function_source(action, "refresh_volume_reading")
        + f'refresh_volume_reading "{output}"\n'
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "COUNT": str(tmp_path / "count"),
        "WRITE_OK": "1" if write_succeeds else "0",
    }
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env, timeout=10
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "volume-reading.json.next").exists()
    # A failed refresh keeps the previous reading (which the gate's freshness
    # check then judges); a successful one replaces it.
    assert output.read_text() == ("new 2\n" if write_succeeds else "old\n")


@pytest.mark.parametrize(
    ("validation_only", "worker", "exit_code", "chunks_after", "expected"),
    [
        # Every planned chunk was already committed: validation-only resume.
        ("true", "exited", "0", 10, "result=validated"),
        ("true", "running", "0", 10, "result=launched-validation-only"),
        ("true", "exited", "1", 10, "FAIL: Search validation-only worker did not exit"),
        # Normal resume: proven only by a chunk this launch commits.
        ("false", "running", "0", 11, "result=launched"),
        ("false", "running", "0", 10, "FAIL: Search worker did not prove a chunk"),
    ],
)
def test_search_start_post_launch_proof(
    tmp_path, validation_only, worker, exit_code, chunks_after, expected
) -> None:
    action = (ROOT / "scripts/operator/actions/v3-system-search-f1.sh").read_text(
        encoding="utf-8"
    )
    start = action[action.index("start_operation() {"):action.index("status_operation() {")]
    begin = start.index("  sleep 3\n")
    end = start.index("  printf 'operation=v3-system-search-f1-start", begin)
    segment = start[begin:end]
    assert "validation_only" in segment
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "docker").write_text(
        "#!/bin/sh\n"
        'case "$3" in *ExitCode*) echo "$EXIT_CODE";; *) echo "$WORKER_STATE";; esac\n',
        encoding="utf-8",
    )
    (fake_bin / "docker").chmod(0o755)
    (fake_bin / "sleep").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake_bin / "sleep").chmod(0o755)
    script = (
        "set -euo pipefail\n"
        "fail() { printf 'FAIL: %s\\n' \"$*\"; exit 64; }\n"
        "stop_unproven_worker() { echo STOPPED; }\n"
        'db_query() { echo "$CHUNKS_AFTER"; }\n'
        "run() {\n"
        "  local WORKER=w TARGET_GENERATION_ID=g baseline_chunks=10 proof worker_state\n"
        f"  local validation_only={validation_only} result=launched\n"
        + segment
        + '  echo "result=$result"\n}\nrun\n'
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "WORKER_STATE": worker,
        "EXIT_CODE": exit_code,
        "CHUNKS_AFTER": str(chunks_after),
    }
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env, timeout=10
    )
    assert expected in result.stdout, result.stdout + result.stderr
    # Only an unproven normal launch is stopped; a validating worker is not.
    assert ("STOPPED" in result.stdout) == (expected.startswith("FAIL: Search worker did not prove"))


@pytest.mark.parametrize(
    "action_path",
    [
        "scripts/operator/actions/v3-system-archetype.sh",
        "scripts/operator/actions/v3-system-search-f1.sh",
    ],
)
@pytest.mark.parametrize(
    ("state", "source", "receipt", "expected"),
    [
        ("missing", "src", True, "EXISTING=absent"),
        ("exited", "src", True, "EXISTING=absent"),
        ("running", "src", True, "EXISTING=running"),
        ("running", "other", True, "FAIL: running worker w was launched by another source"),
        ("running", "src", False, "FAIL: running worker w has no build-start receipt"),
    ],
)
def test_running_worker_is_verified_before_any_receipt_is_written(
    tmp_path, action_path, state, source, receipt, expected
) -> None:
    action = (ROOT / action_path).read_text(encoding="utf-8")
    start = action[action.index("start_operation() {"):action.index("status_operation() {")]
    check = start.index("  existing_worker_state\n")
    assert check < start.index("run_capacity_gate")
    assert check < start.index("write_build_start_receipt")

    state_root = tmp_path / "state"
    state_root.mkdir()
    if receipt:
        (state_root / "build-start-receipt.json").write_text("{}", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "docker").write_text(
        "#!/bin/sh\n"
        '[ "$STATE" = missing ] && exit 1\n'
        'case "$3" in\n'
        '  *State.Status*) echo "$STATE" ;;\n'
        '  *source-sha*) echo "$LABEL_SOURCE" ;;\n'
        '  *f2d-operator-code*) echo id ;;\n'
        '  *generation-id*) echo gen ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    (fake_bin / "docker").chmod(0o755)
    script = (
        "set -euo pipefail\n"
        "fail() { printf 'FAIL: %s\\n' \"$*\"; exit 64; }\n"
        f"WORKER=w SOURCE_SHA=src F2D_IDENTITY=id TARGET_GENERATION_ID=gen STATE_ROOT={state_root}\n"
        + _function_source(action, "existing_worker_state")
        + 'existing_worker_state\necho "EXISTING=$EXISTING_WORKER"\n'
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "STATE": state,
        "LABEL_SOURCE": source,
    }
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env, timeout=10
    )
    assert expected in result.stdout, result.stdout + result.stderr

