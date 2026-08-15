"""Test mapping between observation/comparison enums and canonical confidence."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Setup sys.path for API imports before importing from edfinder_api
ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('ENVIRONMENT', 'test')

from edfinder_api.mechanics.confidence import (  # noqa: E402
    CanonicalConfidence,
    ConfidenceBand,
    ConfidenceLayer,
    SourceAuthority,
)
from edfinder_api.observations.models import ObservedConfidence  # noqa: E402
from edfinder_api.observations.comparison_models import ComparisonConfidence  # noqa: E402


class TestObservedConfidenceFromCanonical:
    """Test ObservedConfidence.from_canonical() mapping."""

    def test_high_band_to_high(self):
        """High band → HIGH."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.LIVE_EVIDENCE,
            score=90.0,
            band=ConfidenceBand.HIGH,
            layer=ConfidenceLayer.OBSERVATION,
            reason='Test',
        )
        assert ObservedConfidence.from_canonical(c) == ObservedConfidence.HIGH

    def test_usable_band_to_medium(self):
        """Usable band → MEDIUM."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.COMMUNITY,
            score=75.0,
            band=ConfidenceBand.USABLE,
            layer=ConfidenceLayer.OBSERVATION,
            reason='Test',
        )
        assert ObservedConfidence.from_canonical(c) == ObservedConfidence.MEDIUM

    def test_exploratory_band_to_medium(self):
        """Exploratory band → MEDIUM."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.INFERRED,
            score=60.0,
            band=ConfidenceBand.EXPLORATORY,
            layer=ConfidenceLayer.OBSERVATION,
            reason='Test',
        )
        assert ObservedConfidence.from_canonical(c) == ObservedConfidence.MEDIUM

    def test_weak_band_to_low(self):
        """Weak band → LOW."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.INFERRED,
            score=40.0,
            band=ConfidenceBand.WEAK,
            layer=ConfidenceLayer.OBSERVATION,
            reason='Test',
        )
        assert ObservedConfidence.from_canonical(c) == ObservedConfidence.LOW

    def test_insufficient_band_to_low(self):
        """Insufficient band → LOW."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.INFERRED,
            score=0.0,
            band=ConfidenceBand.INSUFFICIENT,
            layer=ConfidenceLayer.OBSERVATION,
            reason='Test',
        )
        assert ObservedConfidence.from_canonical(c) == ObservedConfidence.LOW


class TestComparisonConfidenceFromCanonical:
    """Test ComparisonConfidence.from_canonical() mapping."""

    def test_high_band_to_high(self):
        """High band → HIGH."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.LIVE_EVIDENCE,
            score=90.0,
            band=ConfidenceBand.HIGH,
            layer=ConfidenceLayer.EVIDENCE_RECONCILIATION,
            reason='Test',
        )
        assert ComparisonConfidence.from_canonical(c) == ComparisonConfidence.HIGH

    def test_usable_band_to_medium(self):
        """Usable band → MEDIUM."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.COMMUNITY,
            score=75.0,
            band=ConfidenceBand.USABLE,
            layer=ConfidenceLayer.EVIDENCE_RECONCILIATION,
            reason='Test',
        )
        assert ComparisonConfidence.from_canonical(c) == ComparisonConfidence.MEDIUM

    def test_exploratory_band_to_medium(self):
        """Exploratory band → MEDIUM."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.INFERRED,
            score=60.0,
            band=ConfidenceBand.EXPLORATORY,
            layer=ConfidenceLayer.EVIDENCE_RECONCILIATION,
            reason='Test',
        )
        assert ComparisonConfidence.from_canonical(c) == ComparisonConfidence.MEDIUM

    def test_weak_band_to_low(self):
        """Weak band → LOW."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.INFERRED,
            score=40.0,
            band=ConfidenceBand.WEAK,
            layer=ConfidenceLayer.EVIDENCE_RECONCILIATION,
            reason='Test',
        )
        assert ComparisonConfidence.from_canonical(c) == ComparisonConfidence.LOW

    def test_insufficient_band_to_unknown(self):
        """Insufficient band → UNKNOWN."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.INFERRED,
            score=0.0,
            band=ConfidenceBand.INSUFFICIENT,
            layer=ConfidenceLayer.EVIDENCE_RECONCILIATION,
            reason='Test',
        )
        assert ComparisonConfidence.from_canonical(c) == ComparisonConfidence.UNKNOWN
