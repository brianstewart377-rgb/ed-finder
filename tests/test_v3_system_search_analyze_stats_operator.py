from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/operator/actions/v3-system-search-analyze-stats.sh"
WORKFLOW = ROOT / ".github/workflows/v3-system-search-analyze-stats.yml"


def test_analyze_operation_is_exactly_scoped_and_has_no_row_or_schema_mutations():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'CANONICAL_GENERATION="a7076522-54cd-52f3-a291-4e5406bea230"' in source
    assert 'CANONICAL_SEQUENCE="4"' in source
    assert 'CANONICAL_SCHEMA="v3_gen_phase4c_full_20260827_r5"' in source
    assert 'DERIVED_KEY="ratings_v4_prod_p4_opt1"' in source
    assert "ANALYZE ${CANONICAL_SCHEMA}.bodies (system_id64, lifecycle_state, is_landable, terraforming_state_id);" in source
    assert "ANALYZE ${CANONICAL_SCHEMA}.body_signal_current (body_pk, signal_type_id, signal_count);" in source
    assert "statement_timeout='15min'" in source
    assert "lock_timeout='5s'" in source
    assert "planner_statistics_updated=true" in source
    assert "canonical_row_writes_performed=false" in source
    assert "application_data_writes_performed=false" in source
    assert "schema_changes_performed=false" in source
    assert "publication_performed=false" in source
    assert "application_service_changes_performed=false" in source
    for forbidden in (
        "INSERT INTO ",
        "UPDATE ",
        "DELETE FROM ",
        "TRUNCATE ",
        "DROP ",
        "CREATE INDEX",
        "ALTER TABLE",
        "docker stop",
        "docker restart",
        "docker rm",
        "publish_derived_generation",
    ):
        assert forbidden not in source


def test_analyze_operation_verifies_generation_authority_before_statistics_refresh():
    source = SCRIPT.read_text(encoding="utf-8")
    authority = source.index("production generation authority is missing or ambiguous")
    analyze = source.index("ANALYZE ${CANONICAL_SCHEMA}.bodies")
    assert authority < analyze
    assert "current canonical generation changed" in source
    assert "current canonical publication sequence changed" in source
    assert "derived generation canonical identity changed" in source
    assert "derived generation canonical schema changed" in source
    assert "bodies ANALYZE receipt was not visible" in source
    assert "body_signal_current ANALYZE receipt was not visible" in source


def test_analyze_workflow_is_data_only_and_executes_trusted_main():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "chatgpt-ed-new-ops-requests" in source
    assert ".github/v3-search-analyze-requests/*.json" in source
    assert '{"operation": "v3-system-search-f1-analyze-stats"}' in source
    assert "Expected exactly one Search ANALYZE request file" in source
    assert "ref: main" in source
    assert "trusted-main/scripts/operator/actions/v3-system-search-analyze-stats.sh" in source
    assert "environment: ed-new-operator" in source
    assert "group: chatgpt-ed-new-ops" in source
