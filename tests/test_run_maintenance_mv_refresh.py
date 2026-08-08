"""Regression test for moving the mv_archetype_rankings refresh out of
scripts/nightly_update.sh into apps/maintenance/scripts/run_maintenance.sh
(2026-08-08). The view had outgrown every fixed nightly timeout tried
(10min, then 30min via inherited NIGHTLY_PGOPTIONS, then a dedicated 1h
budget) as it grew worse than linearly with row count (6m30s at 10M rows,
52m33s at 20M rows) — moving it to the maintenance container's nightly task
gives it the genuinely unbounded MAINTENANCE_PGOPTIONS budget that already
exists there for exactly this kind of long-running, best-effort step,
instead of repeatedly guessing a bigger fixed constant.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NIGHTLY_UPDATE = ROOT / 'scripts' / 'nightly_update.sh'
RUN_MAINTENANCE = ROOT / 'apps' / 'maintenance' / 'scripts' / 'run_maintenance.sh'

_CASE_LABEL = re.compile(r'\n {4}\w+\)')


def _nightly_case_block(text: str, case: str) -> str:
    start = text.index(f'    {case})')
    next_label = _CASE_LABEL.search(text, start + 1)
    end = next_label.start() if next_label else len(text)
    return text[start:end]


def test_nightly_update_no_longer_refreshes_mv_archetype_rankings():
    nightly = NIGHTLY_UPDATE.read_text(encoding='utf-8')

    assert 'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings' not in nightly
    assert 'run_psql_mv_refresh' not in nightly
    assert 'MV_REFRESH_PGOPTIONS' not in nightly


def test_run_maintenance_nightly_task_refreshes_mv_archetype_rankings_unbounded():
    maintenance = RUN_MAINTENANCE.read_text(encoding='utf-8')
    nightly_block = _nightly_case_block(maintenance, 'nightly')

    assert 'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings' in nightly_block
    # No inline SET statement_timeout ahead of this specific REFRESH — it
    # must inherit MAINTENANCE_PGOPTIONS' statement_timeout=0 (genuinely
    # unbounded), not a second fixed ceiling picked to clear today's
    # measured runtime.
    refresh_line_start = nightly_block.index('REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings')
    step_start = nightly_block.rindex('run_step', 0, refresh_line_start)
    step_call = nightly_block[step_start:refresh_line_start + len('REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings;')]
    assert 'SET statement_timeout' not in step_call


def test_run_maintenance_defines_a_genuinely_unbounded_pgoptions_budget():
    maintenance = RUN_MAINTENANCE.read_text(encoding='utf-8')

    assert 'statement_timeout=0' in maintenance
