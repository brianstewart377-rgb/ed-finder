from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/v3-system-search-f1.sh"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
AUTHORITY = ROOT / "deploy/v3-production/target-authority.json"
IDENTITY_TOOL = ROOT / "scripts/operator/v3_schema_identity.py"
MIGRATIONS = {
    "006": ROOT / "sql/v3/migrations/006_v3_derived_product_lifecycle.sql",
    "010": ROOT / "sql/v3/migrations/010_v3_system_search_body_type_counts.sql",
    "015": ROOT / "sql/v3/migrations/015_v3_derived_product_publication.sql",
}


def test_search_production_operation_is_allowlisted_through_trusted_main():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for operation in (
        "v3-system-search-f1-start",
        "v3-system-search-f1-status",
        "v3-system-search-f1-finalize",
    ):
        assert f"          - {operation}\n" in workflow
        assert operation in workflow
    assert "trusted-main/scripts/operator/actions/v3-system-search-f1.sh" in workflow
    assert ".github/ed-new-ops-requests/*.json" in workflow
    assert "ref: main" in workflow
    assert "V3 Search start requires root or passwordless sudo for the bounded worker launch" in workflow
    assert workflow.index("V3 Search start requires root or passwordless sudo") < workflow.index(
        "trusted-main/scripts/operator/actions/v3-system-search-f1.sh"
    )


def test_search_operator_pins_exact_generation_and_migration():
    source = ACTION.read_text(encoding="utf-8")
    assert 'TARGET_GENERATION_KEY="ratings_v4_prod_p4_parallel_v1"' in source
    assert 'TARGET_GENERATION_ID="cfc25d36-3bc7-4011-a465-d6460eaaf826"' in source
    assert 'TARGET_PUBLICATION_SEQUENCE="1"' in source
    assert 'TARGET_CANONICAL_SEQUENCE="4"' in source
    assert 'TARGET_CANONICAL_GENERATION="a7076522-54cd-52f3-a291-4e5406bea230"' in source
    assert 'TARGET_EXPECTED_SYSTEMS="198528286"' in source
    for number, migration in MIGRATIONS.items():
        assert f'MIGRATION_{number}_NAME="{migration.name}"' in source
        expected = hashlib.sha256(migration.read_bytes()).hexdigest()
        assert f'MIGRATION_{number}_SHA="{expected}"' in source
        assert f'verify_migration "$MIGRATION_{number}_NAME" "$MIGRATION_{number}_SHA" {number}' in source
    assert 'trusted migration $label source hash mismatch' in source
    assert 'migration $label live ledger hash mismatch' in source
    assert "target generation is not PUBLISHED" in source
    assert "target generation is not the current pointer" in source


def test_search_operator_is_bounded_and_cannot_publish_or_touch_canonical():
    source = ACTION.read_text(encoding="utf-8")
    assert 'TARGET_CPUS="8"' in source
    assert 'TARGET_MEMORY="32g"' in source
    assert '--memory-swap "$TARGET_MEMORY"' in source
    assert "--pids-limit 256" in source
    assert "--restart no" in source
    assert "--generation-key ratings_v4_prod_p4_parallel_v1 --follow --poll-seconds 5" in source
    assert '--expected-manifest-sha256 "$EXPECTED_MANIFEST_SHA256"' in source
    assert "publication_performed=false" in source
    assert "canonical_writes_performed=false" in source
    assert "application_service_changes_performed=false" in source
    assert "publish_derived_generation(" not in source
    assert "publish_derived_product(" not in source
    assert "docker compose" not in source
    assert "docker restart" not in source
    # The only stop allowed is of this action's own unproven worker; no
    # application or other container is ever stopped.
    assert source.count("docker stop") == source.count('docker stop --time 60 "$WORKER"') == 1
    assert "TRUNCATE " not in source
    assert "DROP TABLE" not in source
    assert "DROP SCHEMA" not in source


def test_search_worker_dependencies_are_offline_and_pinned():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    source = ACTION.read_text(encoding="utf-8")
    assert "--require-hashes -r trusted-main/deploy/v3-production/f2d-wheels.txt" in workflow
    assert "--require-hashes -r /work/deploy/v3-production/f2d-wheels.txt" in source
    assert "--only-binary=:all:" in workflow
    assert ".v3-search-wheelhouse" in workflow
    assert ".v3-search-wheelhouse" in source
    assert "--no-index" in source
    assert "--find-links /work/.v3-search-wheelhouse" in source
    assert "--target /tmp/v3-search-deps" in source
    assert 'PYTHONPATH="/tmp/v3-search-deps:/work:/work/apps/api/src"' in source


def test_search_operator_only_verifies_its_required_schema_before_worker_launch():
    source = ACTION.read_text(encoding="utf-8")
    verify = source.index("require_search_schema")
    launch = source.index("docker run -d")
    assert verify < launch
    assert 'api_image="$(docker inspect -f' in source
    assert "active API image identity is empty" in source
    assert "scripts/operator/v3_production_migrate.py" not in source
    assert "install_target_schema_identity" not in source
    assert "apply_pending_migration" not in source
    assert 'dst=/work,readonly' in source


def test_search_identity_gate_and_start_receipt_precede_worker_launch():
    source = ACTION.read_text(encoding="utf-8")
    identity = source.index("require_f2d_operator_code_identity")
    target = source.index("require_target()")
    start = source[source.index("start_operation()") :]
    gate = start.index("run_capacity_gate")
    receipt = start.index("write_build_start_receipt")
    launch = start.index("docker run -d")
    assert identity < target
    assert gate < receipt < launch
    assert "capacity-gate-receipt.json" in source
    assert "build-start-receipt.json" in source
    assert "ed-finder/v3-build-start-receipt/v1" in source
    assert "pg_total_relation_size('v3_derived.system_search')" in source


def test_search_finalize_is_verified_receipted_and_vacuums_outside_transaction():
    source = ACTION.read_text(encoding="utf-8")
    finalize = source[source.index("finalize_operation()") : source.index('case "$ACTION"')]
    assert 'worker_state" = "exited"' in finalize
    assert 'worker_exit" = "0"' in finalize
    assert 'lifecycle" = "READY"' in finalize
    assert 'validation" = "VERIFIED"' in finalize
    assert "max(completed_at)" in finalize
    assert 'db_maintenance "VACUUM (ANALYZE) v3_derived.system_search;"' in finalize
    assert "timeout --signal=TERM 7200" in source
    maintenance = source[
        source.index("db_maintenance()") : source.index("search_vacuum_is_current()")
    ]
    assert "BEGIN" not in maintenance
    assert source.count("VACUUM (ANALYZE)") == 1
    assert "last_vacuum" in finalize
    assert "last_analyze" in finalize
    assert "last_vacuum > c.final_insert_at" in source
    assert "last_analyze > c.final_insert_at" in source
    assert "ed-finder/v3-build-final-receipt/v1" in finalize
    assert "idempotent_reverification" in finalize


def test_target_authority_reviews_transition_from_through_012_to_finder_lineage():
    import importlib.util

    spec = importlib.util.spec_from_file_location("v3_schema_identity_test", IDENTITY_TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    document = module.build(ROOT)
    # Reproduce the installed prefix independently and assert both endpoints of
    # the through-012 -> through-012-014-010-011-013-015-016 transition.
    desired_document = dict(document)
    entries = document['migration_set_entries']
    stop = next(i for i, row in enumerate(entries) if row['ledger_name'] == '012_v3_spatial_pyramid_decouple.sql') + 1
    prefix = entries[:stop]
    document = {**document, 'migration_set_entries': prefix,
                'migration_set_identity': module.migration_set_identity(prefix)}
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    expected_sha = hashlib.sha256(payload).hexdigest()
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    transition = authority["schema_transition"]
    assert transition["from_schema_identity_sha256"] == expected_sha
    assert expected_sha == "4cae7d2be2e1909d468b82c6802b265118303cc0fe1c257c2f6c9e963f3a39f5"
    assert transition["from_migration_set_identity"] == document["migration_set_identity"]
    assert transition["from_migration_set_identity"] == "sha256:17263a9748eb936d3c6a7f3e3f75224a40d5e48e011276aedf511946abfff4fe"
    assert document["migration_set_entries"][-1]["ledger_name"] == "012_v3_spatial_pyramid_decouple.sql"
    assert [row['ledger_name'] for row in entries[stop:]] == [
        '014_v3_watchlist.sql',
        '010_v3_system_search_body_type_counts.sql',
        '011_v3_system_archetype.sql',
        '013_v3_system_search_parallel.sql',
        '015_v3_derived_product_publication.sql',
        '016_v3_governed_derived_purge.sql',
    ]
    assert transition["to_migration_set_identity"] == desired_document["migration_set_identity"]
    assert transition["to_migration_set_identity"] == "sha256:6fc1109f4d876fb108a479e8d999667e1c25a1622cc0e1ceb27705b5a8007e93"
    desired_payload = (json.dumps(desired_document, indent=2, sort_keys=True) + "\n").encode()
    assert authority["external_authority"]["schema_identity_sha256"] == hashlib.sha256(desired_payload).hexdigest()
    assert authority["external_authority"]["schema_identity_sha256"] == "7efc1308b7cb47299971bf559bc61c1987c36db2ff30769865841b6fd8a6247b"
    compatible = authority['accepted_release_schema_compatibility']['compatible_migration_sets']
    reachable = {
        module.migration_set_identity(entries[:prefix_length])
        for prefix_length in range(stop, len(entries) + 1)
    }
    assert reachable <= set(compatible)
    assert transition['from_migration_set_identity'] in compatible
    assert transition['to_migration_set_identity'] in compatible


def test_search_status_is_read_only_and_reports_both_products():
    source = ACTION.read_text(encoding="utf-8")
    assert "ratings_completed_systems" in source
    assert "search_completed_systems" in source
    assert "search_product_state" in source
    assert "search_validation_status" in source
    assert "search_rows" in source
    status = source[source.index("status_operation()") :]
    assert "docker logs --tail 40" in status
    assert "INSERT " not in status
    assert "UPDATE " not in status
    assert "DELETE " not in status


def test_start_refuses_a_build_start_receipt_from_another_operator_identity():
    """A receipt written under a different attested identity is never resumed at start.

    The finalizers refuse such a receipt, so launching an irreversible build on it
    would strand the product; the start refuses first and names the reason.
    """
    source = (ROOT / "scripts/operator/actions/v3-system-search-f1.sh").read_text()
    block = source[source.index("def write_build_start_receipt") if "def write_build_start_receipt" in source else source.index("write_build_start_receipt() {"):]
    block = block[: block.index("receipt_seal() {")]
    assert "if receipt['f2d_operator_code_sha256'] != identity:" in block
    assert "raise SystemExit(3)" in block
    assert "written under another operator identity" in block
