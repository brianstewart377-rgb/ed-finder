from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess

import pytest


pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/v3-system-archetype.sh"
MIGRATION_011 = ROOT / "sql/v3/migrations/011_v3_system_archetype.sql"
MIGRATION_015 = ROOT / "sql/v3/migrations/015_v3_derived_product_publication.sql"


def _source() -> str:
    return ACTION.read_text(encoding="utf-8")


def test_archetype_action_checks_attested_identity_before_target_preflight() -> None:
    source = _source()
    assert source.index("require_f2d_operator_code_identity") < source.index(
        "require_target()"
    )

    environment = os.environ.copy()
    environment.pop("F2D_OPERATOR_CODE_SHA256_ATTESTED", None)
    result = subprocess.run(
        ["bash", str(ACTION), "status", str(ROOT), "0" * 40],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 64
    assert "attested_identity_missing" in result.stderr
    assert "unexpected hostname" not in result.stderr


def test_archetype_action_pins_stage_target_and_generation() -> None:
    source = _source()
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
        'TARGET_CANONICAL_SEQUENCE="4"',
        'TARGET_CANONICAL_GENERATION="a7076522-54cd-52f3-a291-4e5406bea230"',
        'TARGET_EXPECTED_SYSTEMS="198528286"',
        'WORKER="edfinder-v3-system-archetype-p4-parallel-v1"',
        'OPERATION_LABEL="ed-finder.operation=v3-system-archetype"',
        'STATE_ROOT="${HOME}/.local/state/ed-finder/v3-system-archetype"',
        'TARGET_CPUS="8"',
        'TARGET_MEMORY="32g"',
    ):
        assert declaration in source

    assert '/var/tmp/edfinder-v3-archetype-build-"$SOURCE_SHA"' in source
    assert ".v3-archetype-build-source-sha" in source
    assert ".v3-archetype-wheelhouse" in source
    assert '"$state" = "PUBLISHED"' in source
    assert '"$current" = "true"' in source
    assert '"$sequence" = "$TARGET_PUBLICATION_SEQUENCE"' in source
    assert '"$identifier" = "$TARGET_GENERATION_ID"' in source


def test_archetype_action_pins_011_and_015_checkout_and_ledger_hashes() -> None:
    source = _source()
    expected_011 = hashlib.sha256(MIGRATION_011.read_bytes()).hexdigest()
    expected_015 = hashlib.sha256(MIGRATION_015.read_bytes()).hexdigest()

    assert 'MIGRATION_011_NAME="011_v3_system_archetype.sql"' in source
    assert f'MIGRATION_011_SHA="{expected_011}"' in source
    assert 'MIGRATION_015_NAME="015_v3_derived_product_publication.sql"' in source
    assert f'MIGRATION_015_SHA="{expected_015}"' in source
    assert "trusted migration $label source hash mismatch" in source
    assert "migration $label live ledger hash mismatch" in source
    assert "v3_meta.schema_migration" in source


def test_start_requires_finalized_verified_search_before_gate_and_launch() -> None:
    source = _source()
    start = source[source.index("start_operation()") : source.index("status_operation()")]

    assert "require_search_prerequisite" in start
    assert "product_code='system_search'" in source
    assert '"READY"' in source
    assert '"VERIFIED"' in source
    assert 'SEARCH_STATE_ROOT="${HOME}/.local/state/ed-finder/v3-system-search"' in source
    assert 'path="$SEARCH_STATE_ROOT/build-final-receipt.json"' in source
    assert "load_sealed" in source
    assert "'product_code': 'system_search'" in source
    assert "Search build-final receipt is missing" in source
    assert start.index("require_search_prerequisite") < start.index("run_capacity_gate")
    assert start.index("run_capacity_gate") < start.index("docker run -d")


def test_start_binds_complete_receipt_manifest_before_registration() -> None:
    source = _source()
    start = source[source.index("start_operation()") : source.index("status_operation()")]

    assert "COMPLETE_RECEIPT" in source
    assert "validate_complete_receipt(receipt)" in source
    assert "load_sealed" in source
    assert "expected_product_manifest" in source
    assert "expected_product_manifest_sha256" in source
    assert "canonical_sha256(manifest) != digest" in source
    assert "receipt.get('f2d_operator_code_sha256') != identity" in source
    assert "receipt.get('system_count') != int(systems)" in source
    assert start.index("run_capacity_gate") < start.index(
        'manifest_sha="$(expected_manifest_sha256)"'
    )
    assert start.index("write_build_start_receipt") < start.index("docker run -d")
    assert "--expected-manifest-sha256 \"$EXPECTED_MANIFEST_SHA256\"" in source


def test_start_writes_sealed_receipts_and_proves_a_committed_chunk() -> None:
    source = _source()

    assert '"$STATE_ROOT/capacity-gate-receipt.json"' in source
    assert "without a passed operation-result envelope" in source
    assert "'schema_version': 'ed-finder/v3-build-start-receipt/v1'" in source
    assert "'product_code': 'system_archetype'" in source
    assert "'relation_total_bytes_at_start': int(relation_size)" in source
    assert "'f2d_operator_code_sha256': identity" in source
    assert "pg_total_relation_size('v3_derived.system_archetype')" in source
    assert "v3_derived.archetype_build_chunk" in source
    # Ten-minute proof window: a resume installs wheels, registers and lists
    # ~198k chunks before its first cold chunk commit.
    assert "for _ in $(seq 1 300)" in source
    assert "for _ in $(seq 1 30)" not in source
    assert "sleep 2" in source
    assert "Archetype worker did not prove a chunk committed by this launch" in source
    # A worker that finds every chunk sealed only validates; it is left running.
    assert "validation_only=true" in source
    assert "result=launched-validation-only" in source


def test_build_and_validation_containers_are_bounded_offline_and_read_only() -> None:
    source = _source()

    assert '--cpus "$TARGET_CPUS"' in source
    assert '--memory "$TARGET_MEMORY"' in source
    assert '--memory-swap "$TARGET_MEMORY"' in source
    assert "--pids-limit 256" in source
    assert "--restart no" in source
    assert source.count("--read-only") >= 1
    assert source.count("--tmpfs /tmp:rw,nosuid,size=2g") >= 1
    assert 'dst=/work,readonly' in source
    assert '--require-hashes -r /work/deploy/v3-production/f2d-wheels.txt 1>&2' in source
    assert "--no-index" in source
    assert "--find-links /work/.v3-archetype-wheelhouse" in source
    assert "--target /tmp/v3-archetype-deps" in source
    assert 'PYTHONPATH="/tmp/v3-archetype-deps:/work:/work/apps/api/src"' in source
    assert "V3_SYSTEM_ARCHETYPE_DATABASE_URL=%s" in source
    assert '--env-file "$env_file"' in source
    assert '--env "V3_SYSTEM_ARCHETYPE_DATABASE_URL=' not in source


def test_build_and_validation_refuse_an_api_image_model_mismatch() -> None:
    source = _source()

    assert source.count("require_image_model_match") >= 1
    assert source.count(
        "/app/shared_contracts/v3_system_archetype_model.py"
    ) >= 1
    assert "scripts.v3_archetype_calibration_complete" in source


def test_finalize_requires_worker_validated_ready_product_before_vacuum() -> None:
    """Validation (every chunk re-read and re-scored, hours at 198.5 M systems)
    runs inside the detached worker after its last chunk, as Search does. A
    bounded foreground validate container could never finish and lost its log
    with --rm, so finalize never launches one: it requires the worker's clean
    exit and the READY/VERIFIED product, then VACUUMs."""
    source = _source()
    finalize = source[source.index("finalize_operation()") :]

    assert "Archetype worker has not exited successfully" in finalize
    assert "Archetype worker is still running" in finalize
    assert '"$worker_state" = "exited"' in finalize
    assert '"$worker_exit" = "0"' in finalize
    assert "run_archetype_container" not in source
    assert "timeout --signal=TERM 7200 docker run" not in source
    assert "--validate" not in source
    assert "ARCHETYPE_OPERATION_MODE" not in source
    assert "docker run -d" in source and "docker run --rm" not in source
    assert finalize.index('"$worker_exit" = "0"') < finalize.index(
        'product_code=\'system_archetype\''
    )
    assert finalize.index('product_code=\'system_archetype\'') < finalize.index(
        'db_maintenance "VACUUM (ANALYZE)'
    )
    assert "Archetype product is not READY/VERIFIED" in finalize
    assert "Archetype wide-row count differs from the generation expected systems" in finalize
    assert "--expected-manifest-sha256 \"$EXPECTED_MANIFEST_SHA256\"" in source


def test_finalize_vacuum_is_the_only_direct_database_write_and_is_not_transactional() -> None:
    source = _source()

    maintenance = 'db_maintenance "VACUUM (ANALYZE) v3_derived.system_archetype;"'
    assert source.count(maintenance) == 1
    assert "timeout --signal=TERM 7200 docker exec" in source
    assert "BEGIN; VACUUM" not in source
    assert "BEGIN READ ONLY" in source
    assert not re.search(r'command "(?:INSERT|UPDATE|DELETE|TRUNCATE)\b', source)
    assert "publish_derived_generation" not in source
    assert "publish_derived_product" not in source
    assert "docker compose" not in source
    assert "docker restart" not in source
    # The only stop allowed is of this action's own unproven worker; no
    # application or other container is ever stopped.
    assert source.count("docker stop") == source.count('docker stop --time 60 "$WORKER"') == 1


def test_finalize_receipts_post_insert_stats_and_is_idempotent() -> None:
    source = _source()

    assert "max(completed_at)::text" in source
    assert "COALESCE(sum(systems),0)::text" in source
    assert "pg_stat_user_tables" in source
    assert "last_vacuum" in source
    assert "last_analyze" in source
    assert "last_vacuum > c.final_insert_at" in source
    assert "last_analyze > c.final_insert_at" in source
    assert "'schema_version': 'ed-finder/v3-build-final-receipt/v1'" in source
    assert "'product_code': 'system_archetype'" in source
    assert "'chunk_count': int(chunk_count)" in source
    assert "'row_count': int(row_count)" in source
    assert "'lifecycle_state': lifecycle" in source
    assert "'validation_status': validation" in source
    assert "'vacuum_performed': performed == 'true'" in source
    assert "'idempotent_reverification': performed != 'true'" in source
    assert '"$STATE_ROOT/build-final-receipt.json"' in source


def test_status_is_read_only_and_reports_receipts() -> None:
    source = _source()
    status = source[source.index("status_operation()") : source.index("finalize_operation()")]

    assert "latest_status" in status
    assert "emit_receipt_status" in status
    assert "docker logs --tail 40" in status
    assert "db_maintenance" not in status
    assert "docker run" not in status
    assert "publication_performed=false" in status
    assert "canonical_writes_performed=false" in status
    assert "application_service_changes_performed=false" in status


def test_action_exposes_only_start_status_and_finalize_modes() -> None:
    source = _source()
    assert 'start) CURRENT_OPERATION="v3-system-archetype-start"; start_operation' in source
    assert 'status) CURRENT_OPERATION="v3-system-archetype-status"; status_operation' in source
    assert 'finalize) CURRENT_OPERATION="v3-system-archetype-finalize"; finalize_operation' in source
    assert 'fail "expected start, status, or finalize"' in source


def test_start_refuses_a_build_start_receipt_from_another_operator_identity():
    """A receipt written under a different attested identity is never resumed at start.

    The finalizers refuse such a receipt, so launching an irreversible build on it
    would strand the product; the start refuses first and names the reason.
    """
    source = (ROOT / "scripts/operator/actions/v3-system-archetype.sh").read_text()
    block = source[source.index("def write_build_start_receipt") if "def write_build_start_receipt" in source else source.index("write_build_start_receipt() {"):]
    block = block[: block.index("receipt_seal() {")]
    assert "if receipt['f2d_operator_code_sha256'] != identity:" in block
    assert "raise SystemExit(3)" in block
    assert "written under another operator identity" in block
