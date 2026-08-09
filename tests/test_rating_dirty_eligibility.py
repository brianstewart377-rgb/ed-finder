"""Regression test for the nightly rating_dirty verification bug (2026-08-09).

nightly_update.sh Step 3 counted `rating_dirty = TRUE` with no
`has_body_data` filter, both before and after running
`build_ratings.py --dirty`. `build_ratings.py --dirty` only ever rates
has_body_data=TRUE candidates - a has_body_data=FALSE system can never
satisfy that count going to zero, and no-body dirty rows are a normal,
continuously-regenerating byproduct of ingest. The unscoped check
therefore reported "Rating rebuild incomplete" every single night
(confirmed in /data/logs/nightly.log for at least six consecutive
nights, 2026-08-04 through 2026-08-09) regardless of whether the real,
rateable backlog was actually cleared.

The already-working `run_dirty_ratings_if_needed.sh` (the 30-minute
cron) solves this correctly: it runs `reconcile_no_body_ratings.py`
first to truthfully clear the no-body population, then scopes its own
dirty count to `rating_dirty = TRUE AND has_body_data = TRUE`. This is
also the same class of bug already fixed once before for the sibling
`cluster_dirty` query - see test_cluster_dirty_eligibility.py - but Step
3's rating_dirty check was never brought in line.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NIGHTLY_UPDATE_PATH = ROOT / 'scripts' / 'nightly_update.sh'
WORKING_SCRIPT_PATH = ROOT / 'scripts' / 'run_dirty_ratings_if_needed.sh'


def test_nightly_step3_runs_no_body_reconciliation_before_rebuild():
    source = NIGHTLY_UPDATE_PATH.read_text(encoding='utf-8')

    assert 'reconcile_no_body_ratings.py' in source
    assert '--apply' in source


def test_nightly_step3_dirty_counts_are_scoped_to_has_body_data():
    source = NIGHTLY_UPDATE_PATH.read_text(encoding='utf-8')

    assert (
        'pg_count_into DIRTY_COUNT '
        '"SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE AND has_body_data = TRUE"'
        in source
    )
    assert (
        'pg_count_into STILL_DIRTY '
        '"SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE AND has_body_data = TRUE"'
        in source
    )
    # The old unscoped queries must not still be present anywhere in Step 3.
    assert 'SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE"' not in source


def test_nightly_reconcile_invocation_uses_the_repo_mounted_script_path():
    source = NIGHTLY_UPDATE_PATH.read_text(encoding='utf-8')

    # build_ratings.py lives baked into the importer image at /app/; the
    # no-body reconcile script is repo-mounted at /opt/ed-finder/scripts/
    # (see docker-compose.yml's importer volumes) - using the wrong path
    # here would silently fail with "No such file".
    assert '/opt/ed-finder/scripts/reconcile_no_body_ratings.py' in source


def test_nightly_reconcile_invocation_matches_the_working_scripts_flags():
    nightly_source = NIGHTLY_UPDATE_PATH.read_text(encoding='utf-8')
    working_source = WORKING_SCRIPT_PATH.read_text(encoding='utf-8')

    for flag in ('--apply', '--batch-size', '--limit', '--skip-summary', '--json'):
        assert flag in nightly_source, f'nightly_update.sh missing {flag}'
        assert flag in working_source, f'run_dirty_ratings_if_needed.sh missing {flag}'
