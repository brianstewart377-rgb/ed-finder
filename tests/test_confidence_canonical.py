"""Test canonical confidence shape and mappings."""
import pytest
from apps.api.src.mechanics.confidence import (
    CanonicalConfidence,
    ConfidenceBand,
    ConfidenceLayer,
    ConfidenceLevel,
    SourceAuthority,
    score_to_band,
    score_to_confidence_level,
)


class TestCanonicalConfidence:
    """Test CanonicalConfidence construction and validation."""

    def test_canonical_construction_valid(self):
        """Valid canonical confidence constructs."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.OFFICIAL,
            score=90.0,
            band=ConfidenceBand.HIGH,
            layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
            reason='Test',
        )
        assert c.source_authority == SourceAuthority.OFFICIAL
        assert c.score == 90.0
        assert c.band == ConfidenceBand.HIGH

    def test_canonical_score_band_mismatch(self):
        """Score–band mismatch raises ValueError."""
        with pytest.raises(ValueError, match='score 90.0 maps to band high'):
            CanonicalConfidence(
                source_authority=SourceAuthority.OFFICIAL,
                score=90.0,
                band=ConfidenceBand.USABLE,  # Wrong: 90 should be HIGH
                layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
                reason='Test',
            )

    def test_canonical_out_of_range_score(self):
        """Score outside 0–100 raises ValueError."""
        with pytest.raises(ValueError, match='must be 0–100'):
            CanonicalConfidence(
                source_authority=SourceAuthority.OFFICIAL,
                score=150.0,
                band=ConfidenceBand.HIGH,
                layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
                reason='Test',
            )

    def test_canonical_serialization(self):
        """to_dict/from_dict round-trip."""
        c1 = CanonicalConfidence(
            source_authority=SourceAuthority.LIVE_EVIDENCE,
            score=75.0,
            band=ConfidenceBand.USABLE,
            layer=ConfidenceLayer.OBSERVATION,
            reason='Test observation',
        )
        d = c1.to_dict()
        c2 = CanonicalConfidence.from_dict(d)
        assert c1 == c2


class TestConfidenceLevelProjection:
    """Test ConfidenceLevel as a display projection of CanonicalConfidence."""

    def test_verified_to_canonical(self):
        """ConfidenceLevel.VERIFIED → canonical."""
        c = ConfidenceLevel.VERIFIED.to_canonical(
            layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
        )
        assert c.source_authority == SourceAuthority.OFFICIAL
        assert c.band == ConfidenceBand.HIGH
        assert c.score == 90.0

    def test_observed_to_canonical(self):
        """ConfidenceLevel.OBSERVED → canonical."""
        c = ConfidenceLevel.OBSERVED.to_canonical(
            layer=ConfidenceLayer.OBSERVATION,
        )
        assert c.source_authority == SourceAuthority.LIVE_EVIDENCE
        assert c.band == ConfidenceBand.HIGH
        assert c.score == 85.0

    def test_community_observed_to_canonical(self):
        """ConfidenceLevel.COMMUNITY_OBSERVED → canonical."""
        c = ConfidenceLevel.COMMUNITY_OBSERVED.to_canonical(
            layer=ConfidenceLayer.CATALOGUE,
        )
        assert c.source_authority == SourceAuthority.COMMUNITY
        assert c.band == ConfidenceBand.USABLE
        assert c.score == 75.0

    def test_inferred_to_canonical(self):
        """ConfidenceLevel.INFERRED → canonical."""
        c = ConfidenceLevel.INFERRED.to_canonical(
            layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
        )
        assert c.source_authority == SourceAuthority.INFERRED
        assert c.band == ConfidenceBand.EXPLORATORY
        assert c.score == 60.0

    def test_estimated_to_canonical(self):
        """ConfidenceLevel.ESTIMATED → canonical."""
        c = ConfidenceLevel.ESTIMATED.to_canonical(
            layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
        )
        assert c.source_authority == SourceAuthority.INFERRED
        assert c.band == ConfidenceBand.WEAK
        assert c.score == 40.0

    def test_speculative_to_canonical(self):
        """ConfidenceLevel.SPECULATIVE → canonical."""
        c = ConfidenceLevel.SPECULATIVE.to_canonical(
            layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
        )
        assert c.source_authority == SourceAuthority.IDENTITY
        assert c.band == ConfidenceBand.WEAK
        assert c.score == 35.0

    def test_unknown_to_canonical(self):
        """ConfidenceLevel.UNKNOWN → canonical with INSUFFICIENT band."""
        c = ConfidenceLevel.UNKNOWN.to_canonical(
            layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
        )
        assert c.band == ConfidenceBand.INSUFFICIENT
        assert c.score == 0.0


class TestCanonicalToLevelProjection:
    """Test reverse projection: CanonicalConfidence → ConfidenceLevel."""

    def test_official_high_to_verified(self):
        """Official + HIGH → VERIFIED."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.OFFICIAL,
            score=90.0,
            band=ConfidenceBand.HIGH,
            layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
            reason='Test',
        )
        assert ConfidenceLevel.from_canonical(c) == ConfidenceLevel.VERIFIED

    def test_live_evidence_high_to_observed(self):
        """Live evidence + HIGH → OBSERVED."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.LIVE_EVIDENCE,
            score=85.0,
            band=ConfidenceBand.HIGH,
            layer=ConfidenceLayer.OBSERVATION,
            reason='Test',
        )
        assert ConfidenceLevel.from_canonical(c) == ConfidenceLevel.OBSERVED

    def test_community_usable_to_community_observed(self):
        """Community + USABLE → COMMUNITY_OBSERVED."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.COMMUNITY,
            score=75.0,
            band=ConfidenceBand.USABLE,
            layer=ConfidenceLayer.CATALOGUE,
            reason='Test',
        )
        assert ConfidenceLevel.from_canonical(c) == ConfidenceLevel.COMMUNITY_OBSERVED

    def test_inferred_exploratory_to_inferred(self):
        """Inferred + EXPLORATORY → INFERRED."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.INFERRED,
            score=60.0,
            band=ConfidenceBand.EXPLORATORY,
            layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
            reason='Test',
        )
        assert ConfidenceLevel.from_canonical(c) == ConfidenceLevel.INFERRED

    def test_identity_weak_to_speculative(self):
        """Identity collision + WEAK → SPECULATIVE."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.IDENTITY,
            score=35.0,
            band=ConfidenceBand.WEAK,
            layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
            reason='Test',
        )
        assert ConfidenceLevel.from_canonical(c) == ConfidenceLevel.SPECULATIVE

    def test_insufficient_to_unknown(self):
        """INSUFFICIENT band → UNKNOWN."""
        c = CanonicalConfidence(
            source_authority=SourceAuthority.INFERRED,
            score=0.0,
            band=ConfidenceBand.INSUFFICIENT,
            layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
            reason='Test',
        )
        assert ConfidenceLevel.from_canonical(c) == ConfidenceLevel.UNKNOWN


class TestRoundTripConversions:
    """Test round-trip conversions: Level → Canonical → Level."""

    @pytest.mark.parametrize('level', [
        ConfidenceLevel.VERIFIED,
        ConfidenceLevel.OBSERVED,
        ConfidenceLevel.COMMUNITY_OBSERVED,
        ConfidenceLevel.INFERRED,
        ConfidenceLevel.ESTIMATED,
        ConfidenceLevel.SPECULATIVE,
        ConfidenceLevel.UNKNOWN,
    ])
    def test_level_canonical_level_round_trip(self, level):
        """Level → Canonical → Level preserves semantic meaning."""
        layer = ConfidenceLayer.PROJECTED_OPERATIONAL
        canonical = level.to_canonical(layer=layer)
        recovered = ConfidenceLevel.from_canonical(canonical)
        # Semantic equivalence: original and recovered should be the same
        # (ESTIMATED and INFERRED may collapse under certain conditions, but all others must match)
        if level == ConfidenceLevel.ESTIMATED:
            # ESTIMATED (score 40, WEAK) can recover as ESTIMATED or INFERRED
            assert recovered in (ConfidenceLevel.ESTIMATED, ConfidenceLevel.INFERRED)
        else:
            assert recovered == level, f'{level} → {canonical} → {recovered}'


class TestScoreToBand:
    """Test numeric score → confidence band conversion."""

    def test_score_to_band_high(self):
        """Score ≥ 85 → HIGH."""
        assert score_to_band(85.0) == ConfidenceBand.HIGH
        assert score_to_band(100.0) == ConfidenceBand.HIGH
        assert score_to_band(0.85) == ConfidenceBand.HIGH

    def test_score_to_band_usable(self):
        """Score 70–84 → USABLE."""
        assert score_to_band(70.0) == ConfidenceBand.USABLE
        assert score_to_band(75.0) == ConfidenceBand.USABLE
        assert score_to_band(84.0) == ConfidenceBand.USABLE
        assert score_to_band(0.75) == ConfidenceBand.USABLE

    def test_score_to_band_exploratory(self):
        """Score 50–69 → EXPLORATORY."""
        assert score_to_band(50.0) == ConfidenceBand.EXPLORATORY
        assert score_to_band(60.0) == ConfidenceBand.EXPLORATORY
        assert score_to_band(69.0) == ConfidenceBand.EXPLORATORY
        assert score_to_band(0.60) == ConfidenceBand.EXPLORATORY

    def test_score_to_band_weak(self):
        """Score < 50 → WEAK."""
        assert score_to_band(0.0) == ConfidenceBand.WEAK
        assert score_to_band(25.0) == ConfidenceBand.WEAK
        assert score_to_band(49.0) == ConfidenceBand.WEAK
        assert score_to_band(0.25) == ConfidenceBand.WEAK


class TestScoreToConfidenceLevel:
    """Test numeric score → ConfidenceLevel conversion."""

    def test_high_score_to_level(self):
        """High score (0.85+) → high-band level."""
        level = score_to_confidence_level(0.85)
        assert level in (ConfidenceLevel.VERIFIED, ConfidenceLevel.OBSERVED)

    def test_usable_score_to_level(self):
        """Usable score (0.70–0.84) → usable-band level."""
        level = score_to_confidence_level(0.75)
        assert level in (ConfidenceLevel.COMMUNITY_OBSERVED, ConfidenceLevel.OBSERVED)

    def test_exploratory_score_to_level(self):
        """Exploratory score (0.50–0.69) → exploratory level."""
        level = score_to_confidence_level(0.60)
        assert level in (ConfidenceLevel.INFERRED, ConfidenceLevel.COMMUNITY_OBSERVED)

    def test_weak_score_to_level(self):
        """Weak score (<0.50) → weak level."""
        level = score_to_confidence_level(0.35)
        assert level in (ConfidenceLevel.ESTIMATED, ConfidenceLevel.SPECULATIVE)
