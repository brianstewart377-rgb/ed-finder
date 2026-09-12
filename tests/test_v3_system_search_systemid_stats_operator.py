from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/operator/actions/v3-system-search-tune-systemid-stats.sh"
WORKFLOW = ROOT / ".github/workflows/v3-system-search-tune-systemid-stats.yml"


def test_systemid_stats_tuning_is_exact_and_row_safe():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'CANONICAL_GENERATION="a7076522-54cd-52f3-a291-4e5406bea230"' in source
    assert 'CANONICAL_SEQUENCE="4"' in source
    assert 'CANONICAL_SCHEMA="v3_gen_phase4c_full_20260827_r5"' in source
    assert 'DERIVED_KEY="ratings_v4_prod_p4_opt1"' in source
    assert 'STATISTICS_TARGET="1000"' in source
    assert 'N_DISTINCT_OVERRIDE="-0.10"' in source
    assert "ALTER COLUMN system_id64 SET STATISTICS ${STATISTICS_TARGET};" in source
    assert "ALTER COLUMN system_id64 SET (n_distinct = ${N_DISTINCT_OVERRIDE});" in source
    assert "ANALYZE ${CANONICAL_SCHEMA}.bodies (system_id64);" in source
    assert "statement_timeout='15min'" in source
    assert "lock_timeout='5s'" in source
    assert "planner_statistics_updated=true" in source
    assert "planner_metadata_changes_performed=true" in source
    assert "canonical_row_writes_performed=false" in source
    assert "application_data_writes_performed=false" in source
    assert "publication_performed=false" in source
    assert "application_service_changes_performed=false" in source
    for forbidden in (
        "INSERT INTO ",
        "UPDATE ",
        "DELETE FROM ",
        "TRUNCATE ",
        "DROP ",
        "CREATE INDEX",
        "docker stop",
        "docker restart",
        "docker rm",
        "publish_derived_generation",
    ):
        assert forbidden not in source


def test_systemid_stats_tuning_reports_before_and_after_selectivity():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "before_stats=" in source
    assert "after_stats=" in source
    assert "n_distinct_override=" in source
    assert "'attribute_options',a.attoptions" in source
    assert "'n_distinct',s.n_distinct" in source
    assert "'implied_distinct'" in source
    assert "'implied_rows_per_system'" in source
    assert "system_id64 statistics target was not applied" in source
    assert "system_id64 n_distinct is missing after ANALYZE" in source
    assert "system_id64 n_distinct override was not applied" in source


def test_systemid_stats_workflow_is_data_only_and_uses_trusted_main():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "chatgpt-ed-new-ops-requests" in source
    assert ".github/v3-search-systemid-stats-requests/*.json" in source
    assert '{"operation": "v3-system-search-f1-tune-systemid-stats"}' in source
    assert "Expected exactly one Search system-id statistics request file" in source
    assert "ref: main" in source
    assert "trusted-main/scripts/operator/actions/v3-system-search-tune-systemid-stats.sh" in source
    assert "environment: ed-new-operator" in source
    assert "group: chatgpt-ed-new-ops" in source
