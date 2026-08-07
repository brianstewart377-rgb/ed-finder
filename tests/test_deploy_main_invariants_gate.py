"""2026-08-07 incident: scripts/deploy_main.sh's post-deploy invariants
check failed twice on dirty_truthful_no_bodies, a count documented
elsewhere (CLAUDE.md's "Dirty ratings maintenance" section) as expected to
be transiently nonzero between runs of the 30-minute reconciliation cron
job — not a real regression. The app was healthy and serving the new code
both times; only this verification step was miscalibrated. Regression
test for the fix, not a broader test of the whole (very large) script.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_post_deploy_invariants_allows_known_bounded_churn():
    deploy_main = (ROOT / 'scripts' / 'deploy_main.sh').read_text(encoding='utf-8')

    assert 'run_data_invariants_receipted.sh' in deploy_main
    assert '--allow-stale-colonisation-status' in deploy_main
    assert '--allow-stale-noneligible' in deploy_main, (
        'deploy_main.sh must pass --allow-stale-noneligible to the '
        'post-deploy invariants check — without it, a deploy fails '
        'whenever the dirty-ratings reconciliation job (which runs on its '
        'own 30-minute cron cycle, independent of deploys) happens to be '
        'mid-cycle, even though nothing is actually wrong.'
    )
