from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.operator.render_v3_system_search_profile import (  # noqa: E402
    render_profile, shell_query,
)
from scripts.v3_system_search import projection_query_sql  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/operator/actions/v3-system-search-profile.sh"
WORKFLOW = ROOT / ".github/workflows/v3-system-search-profile.yml"


def test_search_profile_is_read_only_and_exact_targeted():
    source = render_profile()
    assert 'TARGET_GENERATION_KEY="ratings_v4_prod_p4_opt1"' in source
    assert 'POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"' in source
    assert 'BEGIN READ ONLY;' in source
    assert 'EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY, FORMAT JSON)' in source
    assert "statement_timeout='60s'" in source
    assert "full_query_variant=baseline" in source
    assert "full_query_variant=jit_off" in source
    assert "full_query_variant=indexed_no_seqscan" in source
    assert "full_query_variant=candidate_default" in source
    assert "full_query_variant=candidate_jit_off" in source
    assert "SET LOCAL enable_seqscan=off;" in source
    assert "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;" in source
    assert 'run_cohort search_frontier "$search_frontier"' in source
    assert 'run_cohort ratings_tip "$ratings_tip"' in source
    assert "EXCEPT ALL" in source
    assert "expected_rows>0" in source
    assert "\\quit 3" in source
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
    assert "trusted-main/scripts/operator/render_v3_system_search_profile.py" in source
    assert '< "${{ runner.temp }}/search-profile.sh"' in source
    assert "environment: ed-new-operator" in source
    assert "group: chatgpt-ed-new-ops" in source
    assert "timeout-minutes: 12" in source


def test_profile_uses_exact_writer_select_and_has_valid_shell_syntax():
    source = render_profile()
    assert shell_query(projection_query_sql()) in source
    assert '__SEARCH_CANDIDATE_SQL__' not in source
    assert '__SEARCH_LEGACY_SQL__' not in source
    subprocess.run(['bash', '-n'], input=source, text=True, check=True)
    # Only the diagnostic control may disable sequential scans. The candidate
    # is measured after both settings have been restored to session defaults.
    reset = source.index('SET LOCAL enable_seqscan=DEFAULT;')
    candidate = source.index('full_query_variant=candidate_default')
    assert reset < candidate
    assert 'SET LOCAL jit=DEFAULT;' in source[reset:candidate]
