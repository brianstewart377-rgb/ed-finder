from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

import pytest
import yaml


pytestmark = pytest.mark.operator

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/v3-archetype-plan-probe.sh"
PROGRAM = ROOT / "scripts/v3_archetype_plan_probe.py"
GENERATOR = ROOT / "scripts/v3_plan_probe_statements.py"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_action_checks_attested_identity_before_target_or_database_work() -> None:
    source = _read(ACTION)
    identity = source.index("require_f2d_operator_code_identity")
    assert identity < source.index("require_target()")
    assert identity < source.index("db_query()")

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


def test_action_pins_target_generation_stage_and_product_publication() -> None:
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
    assert '/var/tmp/edfinder-v3-plan-probe-"$SOURCE_SHA"' in source
    assert ".v3-plan-probe-source-sha" in source
    assert "BEGIN READ ONLY" in source
    assert "current_derived_generation" in source
    assert "lifecycle_state" in source
    assert "published_at IS NOT NULL" in source
    assert "return 23" in source


def test_action_validates_sealed_final_receipts_and_current_spatial_anchor() -> None:
    source = _read(ACTION)
    assert "load_sealed(path)" in source
    assert "v3-system-search/build-final-receipt.json" in source
    assert "v3-system-archetype/build-final-receipt.json" in source
    for field in (
        "final_insert_at",
        "last_vacuum",
        "last_analyze",
        "f2d_operator_code_sha256",
    ):
        assert field in source
    assert "v3_spatial.current_spatial_generation" in source
    assert "g.canonical_generation_id" in source
    assert "max(c.level)" in source
    assert "ORDER BY c.system_count DESC, c.cell_key ASC" in source


def test_action_attests_image_and_generates_sql_inside_running_api() -> None:
    source = _read(ACTION)
    assert "docker inspect -f '{{.Config.Image}}'" in source
    assert "docker inspect -f '{{.Image}}'" in source
    assert "docker image inspect -f '{{index .RepoDigests 0}}'" in source
    assert "accepted_release_schema_compatibility" in source
    assert "['images']['backend']" in source
    assert '"$image_digest" = "$expected_digest"' in source
    assert 'docker exec -i "$api" /app/.venv/bin/python -' in source
    assert '< "$REPO_ROOT/scripts/v3_plan_probe_statements.py"' in source
    assert "--dense-anchor" in source
    assert "canonical_sha256(value)" in source
    assert "!= 80" in source


def test_action_runs_bounded_read_only_worker_with_env_file_dsn() -> None:
    source = _read(ACTION)
    assert "timeout --signal=TERM 1800 docker run --rm" in source
    for option in (
        "--cpus 2",
        "--memory 4g",
        "--memory-swap 4g",
        "--pids-limit 128",
        "--read-only",
        "--tmpfs /tmp",
        'dst=/work,readonly',
        'dst=/gate"',
        '"psycopg[binary]==3.3.4"',
        "--no-index",
        "--find-links /work/.v3-probe-wheelhouse",
        "--target /tmp/v3-plan-probe-deps",
        "/app/.venv/bin/python scripts/v3_archetype_plan_probe.py",
    ):
        assert option in source
    assert "V3_ARCHETYPE_PLAN_PROBE_DATABASE_URL=%s" in source
    assert '--env-file "$env_file"' in source
    assert '--env "V3_ARCHETYPE_PLAN_PROBE_DATABASE_URL=' not in source
    assert "--allow-unpublished" not in source


def test_probe_program_has_no_database_mutation_and_standalone_is_read_only() -> None:
    source = _read(PROGRAM)
    assert not re.search(
        r"\b(?:INSERT|UPDATE|DELETE|TRUNCATE|VACUUM|ALTER|CREATE|DROP)\b", source
    )
    assert "connection.read_only = True" in source
    assert "default_transaction_read_only" in source
    assert '"plan_cache_mode", "force_generic_plan"' in source
    assert '"statement_timeout", "60s"' in source
    assert "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)" in source
    assert "PREPARE {}" in source
    assert "DEALLOCATE {}" in source


def test_manifest_lists_action_and_both_programs_in_sorted_active_block() -> None:
    entries = [
        line
        for line in _read(ROOT / "deploy/v3-production/f2d-operator-code.txt").splitlines()
        if line and not line.startswith("#")
    ]
    assert entries == sorted(entries)
    assert "scripts/operator/actions/v3-archetype-plan-probe.sh" in entries
    assert "scripts/v3_archetype_plan_probe.py" in entries
    assert "scripts/v3_plan_probe_statements.py" in entries


def test_workflow_allowlists_stages_runs_and_uploads_plan_probe() -> None:
    workflow = _read(WORKFLOW)
    parsed = yaml.safe_load(workflow)
    operations = parsed[True]["workflow_dispatch"]["inputs"]["operation"]["options"]
    assert operations.count("v3-archetype-plan-probe") == 1
    assert "|v3-archetype-plan-probe|" in workflow
    assert workflow.count(
        "steps.request.outputs.operation == 'v3-archetype-plan-probe'"
    ) == 4
    steps = parsed["jobs"]["execute"]["steps"]
    names = {step.get("name") for step in steps}
    assert {
        "Prepare trusted V3 archetype plan probe bundle and dependencies",
        "Stage trusted main for V3 archetype plan probe",
        "Run V3 archetype plan probe",
        "Upload V3 archetype plan probe receipt",
    } <= names
    run_step = next(step for step in steps if step.get("name") == "Run V3 archetype plan probe")
    assert run_step["timeout-minutes"] == 35
    assert ".v3-plan-probe-source-sha" in workflow
    assert 'stage="/var/tmp/edfinder-v3-plan-probe-${source_sha}"' in workflow
    assert "bash -s -- run '$stage' '$source_sha'" in workflow
    assert "--preserve-env=F2D_OPERATOR_CODE_SHA256_ATTESTED" in workflow
    assert workflow.count(
        "trusted-main/scripts/operator/actions/v3-archetype-plan-probe.sh"
    ) == 1
    assert "name: v3-archetype-plan-probe-operation" in workflow
    assert "retention-days: 90" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in workflow
    assert "IdentitiesOnly=yes" in workflow
    assert "DATABASE_URL" not in workflow


def test_generator_is_stdin_safe_and_imports_only_deployed_ranking_modules() -> None:
    source = _read(GENERATOR)
    assert "edfinder_api.ranking.profile" in source
    assert "edfinder_api.ranking.ranking_sql" in source
    assert "/work" not in source
