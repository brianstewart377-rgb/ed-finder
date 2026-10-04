"""Task 4: the legacy/V3 journey-system drift checker (pure logic).

Records are (name, x, y, z): legacy reads x/y/z from `systems`, V3 reads
x_ly/y_ly/z_ly from `v3_app.system_search`. The gate must catch both name and
coordinate drift, or a broken search->detail spatial handoff slips through."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ACHENAR = 10477373803000
LOSSLESS = 9007199254740993

# Matches the curated fixture + legacy seed coordinates.
_A = ('Achenar', 67.50, -119.47, 24.84)
_L = ('V3 Lossless Reach', 18.25, -7.5, 42.75)


def test_check_reports_missing_and_passes_when_consistent():
    from scripts.checks.assert_legacy_v3_consistency import diff_journey_systems

    legacy = {ACHENAR: _A, LOSSLESS: _L}
    v3 = {ACHENAR: _A}  # missing the lossless system
    problems = diff_journey_systems(legacy, v3)
    assert any(str(LOSSLESS) in p for p in problems)
    # fully consistent -> no problems
    assert diff_journey_systems(legacy, legacy) == []


def test_check_detects_name_mismatch():
    from scripts.checks.assert_legacy_v3_consistency import diff_journey_systems

    legacy = {ACHENAR: _A, LOSSLESS: _L}
    v3 = {ACHENAR: _A, LOSSLESS: ('Wrong Name', 18.25, -7.5, 42.75)}
    problems = diff_journey_systems(legacy, v3)
    assert any(str(LOSSLESS) in p and 'v3_app' in p for p in problems)


def test_check_detects_coordinate_drift():
    """The original P2: names agree but positions differ (e.g. V3 Achenar left
    at Sol's 0,0,0 while legacy Achenar is at 67.5,-119.47,24.84)."""
    from scripts.checks.assert_legacy_v3_consistency import diff_journey_systems

    legacy = {ACHENAR: _A, LOSSLESS: _L}
    v3 = {ACHENAR: ('Achenar', 0.0, 0.0, 0.0), LOSSLESS: _L}  # right name, wrong position
    problems = diff_journey_systems(legacy, v3)
    assert any(str(ACHENAR) in p and 'coordinates differ' in p for p in problems)
    # within tolerance -> no coordinate problem
    near = {ACHENAR: ('Achenar', 67.505, -119.472, 24.84), LOSSLESS: _L}
    assert diff_journey_systems(legacy, near) == []
