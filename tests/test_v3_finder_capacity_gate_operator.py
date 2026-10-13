from __future__ import annotations

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


def test_ops_workflow_allowlists_only_the_capacity_gate_attestation_input() -> None:
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
    assert 'if [ "$operation" = "v3-finder-capacity-gate" ]' in workflow
    assert (
        "F2d operator-code attestation input is accepted only for "
        "v3-finder-capacity-gate" in workflow
    )


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
