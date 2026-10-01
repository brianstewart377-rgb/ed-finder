"""Task 4: the legacy/V3 journey-system drift checker (pure logic)."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ACHENAR = 10477373803000
LOSSLESS = 9007199254740993


def test_check_reports_missing_and_passes_when_consistent():
    from scripts.checks.assert_legacy_v3_consistency import diff_journey_systems

    legacy = {ACHENAR: 'Achenar', LOSSLESS: 'V3 Lossless Reach'}
    v3 = {ACHENAR: 'Achenar'}  # missing the lossless system
    problems = diff_journey_systems(legacy, v3)
    assert any(str(LOSSLESS) in p for p in problems)
    # fully consistent -> no problems
    assert diff_journey_systems(legacy, legacy) == []


def test_check_detects_name_mismatch():
    from scripts.checks.assert_legacy_v3_consistency import diff_journey_systems

    legacy = {ACHENAR: 'Achenar', LOSSLESS: 'V3 Lossless Reach'}
    v3 = {ACHENAR: 'Achenar', LOSSLESS: 'Wrong Name'}
    problems = diff_journey_systems(legacy, v3)
    assert any(str(LOSSLESS) in p and 'v3_app' in p for p in problems)
