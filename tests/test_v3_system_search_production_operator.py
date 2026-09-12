from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/v3-system-search-f1.sh"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
AUTHORITY = ROOT / "deploy/v3-production/target-authority.json"
IDENTITY_TOOL = ROOT / "scripts/operator/v3_schema_identity.py"
MIGRATION = ROOT / "sql/v3/migrations/006_v3_derived_product_lifecycle.sql"


def test_search_production_operation_is_allowlisted_through_trusted_main():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for operation in ("v3-system-search-f1-start", "v3-system-search-f1-status"):
        assert f"          - {operation}\n" in workflow
        assert operation in workflow
    assert "trusted-main/scripts/operator/actions/v3-system-search-f1.sh" in workflow
    assert ".github/ed-new-ops-requests/*.json" in workflow
    assert "ref: main" in workflow
    assert "V3 Search start requires root or passwordless sudo before any schema change" in workflow
    assert workflow.index("V3 Search start requires root or passwordless sudo") < workflow.index(
        "trusted-main/scripts/operator/actions/v3-system-search-f1.sh"
    )


def test_search_operator_pins_exact_generation_and_migration():
    source = ACTION.read_text(encoding="utf-8")
    assert 'TARGET_GENERATION_KEY="ratings_v4_prod_p4_opt1"' in source
    assert 'TARGET_CANONICAL_SEQUENCE="4"' in source
    assert 'TARGET_CANONICAL_GENERATION="a7076522-54cd-52f3-a291-4e5406bea230"' in source
    assert 'MIGRATION_NAME="006_v3_derived_product_lifecycle.sql"' in source
    expected = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
    assert f'MIGRATION_SHA="{expected}"' in source
    assert "expected only migration 006 to be pending" in source
    assert "production migration authority still reports pending migrations" in source


def test_search_operator_is_bounded_and_cannot_publish_or_touch_canonical():
    source = ACTION.read_text(encoding="utf-8")
    assert 'TARGET_CPUS="8"' in source
    assert 'TARGET_MEMORY="32g"' in source
    assert '--memory-swap "$TARGET_MEMORY"' in source
    assert "--pids-limit 256" in source
    assert "--restart no" in source
    assert "--generation-key ratings_v4_prod_p4_opt1 --follow --poll-seconds 5" in source
    assert "publication_performed=false" in source
    assert "canonical_writes_performed=false" in source
    assert "application_service_changes_performed=false" in source
    assert "publish_derived_generation(" not in source
    assert "docker compose" not in source
    assert "docker restart" not in source
    assert "docker stop" not in source
    assert "TRUNCATE " not in source
    assert "DROP TABLE" not in source
    assert "DROP SCHEMA" not in source


def test_search_worker_dependencies_are_offline_and_pinned():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    source = ACTION.read_text(encoding="utf-8")
    requirement = "psycopg[binary]==3.3.4"
    assert requirement in workflow
    assert requirement in source
    assert "--only-binary=:all:" in workflow
    assert ".v3-search-wheelhouse" in workflow
    assert ".v3-search-wheelhouse" in source
    assert "--no-index" in source
    assert "--find-links /work/.v3-search-wheelhouse" in source
    assert "--target /tmp/v3-search-deps" in source
    assert 'PYTHONPATH="/tmp/v3-search-deps:/work:/work/apps/api/src"' in source


def test_search_operator_uses_reviewed_migration_authority_before_worker_launch():
    source = ACTION.read_text(encoding="utf-8")
    identity = source.index("install_target_schema_identity")
    migrate = source.index("apply_pending_migration")
    launch = source.index("docker run -d")
    assert identity < migrate < launch
    assert "scripts/operator/v3_production_migrate.py" in source
    assert "--operation plan" in source
    assert "--operation apply" in source
    assert "--operation authority-gate" in source
    assert 'dst=/work,readonly' in source


def test_target_authority_pins_identity_derived_from_lineage_006():
    import importlib.util

    spec = importlib.util.spec_from_file_location("v3_schema_identity_test", IDENTITY_TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    document = module.build(ROOT)
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    expected_sha = hashlib.sha256(payload).hexdigest()
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    assert authority["external_authority"]["schema_identity_sha256"] == expected_sha
    assert expected_sha == "05bbf65bcb06d59249cd0436aeeca6e529934f999cafc099aa5af8fa7cf4303d"
    assert document["migration_set_entries"][-1]["ledger_name"] == "006_v3_derived_product_lifecycle.sql"


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
