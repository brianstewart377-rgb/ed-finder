"""Regression test for the Review Lab docker-build timeout bug (2026-08-09).

`up_review_stack()` ran `docker compose build review-api` under
`TIMEOUTS.stack_readiness` (60s) - a budget sized for polling a health
check, not for a cold image build (pip install of the full API
dependency tree, no layer cache on a fresh CI runner). This produced a
recurring `REVIEW_STACK_START_FAILED` / "Command timed out: docker"
flake on unrelated PRs. The build step needs its own, more generous
timeout, separate from the readiness-check budget it was sharing.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dev.review_lab.timeouts import TIMEOUTS  # noqa: E402

LIFECYCLE_SOURCE = (ROOT / 'scripts' / 'dev' / 'review_lab' / 'lifecycle.py').read_text(encoding='utf-8')


def test_image_build_has_its_own_timeout_distinct_from_stack_readiness():
    assert TIMEOUTS.image_build >= 180, (
        'A cold docker build of the API image needs a generous budget, not a '
        'health-check-sized one.'
    )
    assert TIMEOUTS.image_build > TIMEOUTS.stack_readiness, (
        'image_build must not silently collapse back to the same value as '
        'stack_readiness - they budget fundamentally different operations.'
    )


def test_docker_compose_build_uses_image_build_timeout_not_stack_readiness():
    build_line = next(
        line for line in LIFECYCLE_SOURCE.splitlines()
        if "run_compose('build', 'review-api'" in line
    )
    assert 'TIMEOUTS.image_build' in build_line, (
        f'review-api build must use TIMEOUTS.image_build, not stack_readiness: {build_line!r}'
    )


def test_cypress_browser_matrix_has_a_bounded_dedicated_timeout():
    assert 300 <= TIMEOUTS.cypress <= 600
    assert not hasattr(TIMEOUTS, 'playwright')
