from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/operator/actions/v3-system-search-signal-plan-profile.sh"
WORKFLOW = ROOT / ".github/workflows/v3-system-search-profile.yml"


def test_signal_profile_only_explains_read_only_variants():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'TARGET_GENERATION_KEY="ratings_v4_prod_p4_opt1"' in source
    assert "BEGIN READ ONLY;" in source
    assert "EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY, FORMAT JSON)" in source
    assert "signal_plan_json=" in source
    assert "grep -E" not in source
    assert "statement_timeout='60s'" in source
    assert "enable_hashjoin=off" in source
    assert "enable_seqscan=off" in source
    assert "work_mem='256MB'" in source
    assert "join_collapse_limit=1" in source
    assert "from_collapse_limit=1" in source
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


def test_profile_workflow_runs_signal_comparison_from_trusted_main():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "trusted-main/scripts/operator/actions/v3-system-search-profile.sh" in source
    assert "trusted-main/scripts/operator/actions/v3-system-search-signal-plan-profile.sh" in source
    assert 'tee -a "$RECEIPT"' in source
    assert "ref: main" in source
