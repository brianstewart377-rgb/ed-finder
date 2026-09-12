from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/operator/actions/v3-system-search-profile.sh"
WORKFLOW = ROOT / ".github/workflows/v3-system-search-profile.yml"


def test_search_profile_is_read_only_and_exact_targeted():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'TARGET_GENERATION_KEY="ratings_v4_prod_p4_opt1"' in source
    assert 'POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"' in source
    assert 'BEGIN READ ONLY;' in source
    assert 'EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY, FORMAT JSON)' in source
    assert "statement_timeout='60s'" in source
    assert "run_full_query_variant baseline \"\" select_plan_json" in source
    assert 'run_full_query_variant jit_off "SET LOCAL jit=off;" jit_off_select_plan_json' in source
    assert "run_full_query_variant indexed_no_seqscan" in source
    assert "SET LOCAL enable_seqscan=off;" in source
    assert "full_query_variant=%s" in source
    assert "database_writes_performed=false" in source
    assert "schema_changes_performed=false" in source
    assert "publication_performed=false" in source
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
    ):
        assert forbidden not in source


def test_search_profile_workflow_is_data_only_and_uses_trusted_main():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "chatgpt-ed-new-ops-requests" in source
    assert ".github/v3-search-profile-requests/*.json" in source
    assert '{"operation": "v3-system-search-f1-profile"}' in source
    assert "Expected exactly one Search profile request file" in source
    assert "ref: main" in source
    assert "trusted-main/scripts/operator/actions/v3-system-search-profile.sh" in source
    assert "environment: ed-new-operator" in source
    assert "group: chatgpt-ed-new-ops" in source
