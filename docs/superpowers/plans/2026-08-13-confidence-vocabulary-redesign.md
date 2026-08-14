# Confidence Vocabulary Redesign — Implementation Plan

**Status:** Phase 1 complete (commit 799ca640); Phase 2 and 3 pending.

**Goal:** Redesign `mechanics/confidence.py` to carry the canonical shape `{source_authority, confidence_score, band, layer}` while keeping existing display enums as thin projections.

**Scope:** confidence.py and all 25 dependent files. No runtime CRE consumption yet — this is the schema/shape layer only.

---

## Phase 1: Schema Redesign (confidence.py)

### Current state
- 7 independent confidence surfaces
- No common shape
- Mixing source-authority and confidence-degree

### Target shape (canonical)
```python
class SourceAuthority(Enum):
    """CRE SA-register classes"""
    OFFICIAL = 'official'  # SA-0001: official mechanics
    COMMUNITY = 'community'  # SA-0002: DaftMav, Mega Guide
    LIVE_EVIDENCE = 'live_evidence'  # SA-0003: in-game observation
    INFERRED = 'inferred'  # SA-0004: derived mechanics
    NARRATIVE = 'narrative'  # SA-0005: narrative evidence
    IDENTITY = 'identity'  # SA-0006: identity collision

class ConfidenceBand(Enum):
    """CRE confidence bands (0-100 score ranges)"""
    HIGH = 'high'  # 85-100: may drive automation
    USABLE = 'usable'  # 70-84: usable with review
    EXPLORATORY = 'exploratory'  # 50-69: exploratory only
    WEAK = 'weak'  # <50: discovery-lead
    INSUFFICIENT = 'insufficient'  # no assessment

class ConfidenceLayer(Enum):
    """CRE layer taxonomy (CM-0001 separation)"""
    OBSERVATION = 'observation'
    CATALOGUE = 'catalogue'
    PROJECTED_OPERATIONAL = 'projected_operational'
    EVIDENCE_RECONCILIATION = 'evidence_reconciliation'
    MECHANICS = 'mechanics'

@dataclass(frozen=True)
class CanonicalConfidence:
    """Single source of truth for all confidence"""
    source_authority: SourceAuthority
    score: float  # 0-100
    band: ConfidenceBand
    layer: ConfidenceLayer
    reason: str
    
    def __post_init__(self):
        # Validate score matches band
        if self.score >= 85:
            assert self.band == ConfidenceBand.HIGH
        elif self.score >= 70:
            assert self.band == ConfidenceBand.USABLE
        # ... etc
```

### Display projections (thin, computed)
```python
class ConfidenceLevel(str, Enum):
    """Projection of CanonicalConfidence onto UI display layer"""
    VERIFIED = 'verified'  # High band + official/evidence source
    OBSERVED = 'observed'  # High band + live_evidence source
    COMMUNITY_OBSERVED = 'community_observed'  # Usable+ band + community source
    INFERRED = 'inferred'  # Exploratory band + inferred source
    ESTIMATED = 'estimated'  # Weak band
    SPECULATIVE = 'speculative'  # Weak + identity/contradiction flag
    UNKNOWN = 'unknown'  # Insufficient
    
    @classmethod
    def from_canonical(cls, c: CanonicalConfidence) -> 'ConfidenceLevel':
        """Derive display projection from canonical shape"""
        # Implement the reverse mapping from §7 of reconciliation doc
```
```

### Phase 1 tasks (COMPLETE):
1. ✓ Read all 37 dependent files to understand usage patterns
2. ✓ Design migration strategy (add canonical alongside old enums as display projections)
3. ✓ Implement SourceAuthority, ConfidenceBand, ConfidenceLayer, CanonicalConfidence
4. ✓ Implement bidirectional mapping: `from_canonical()` / `to_canonical()`
5. ✓ Add to_dict() / from_dict() for API serialization
6. ✓ Add helper functions: `score_to_band()`, `score_to_confidence_level()`
7. ✓ All tests pass (57 confidence tests + 32 new canonical tests)

### Phase 1 Summary (Completed 2026-08-14)

Commit: `799ca640`

**What was implemented:**
- Canonical shape: `SourceAuthority`, `ConfidenceBand`, `ConfidenceLayer`, `CanonicalConfidence`
- Bidirectional projection: `ConfidenceLevel.from_canonical()` and `.to_canonical()`
- Serialization: `CanonicalConfidence.to_dict()` and `.from_dict()`
- Helper functions for numeric confidence (archetype scoring, body-data completeness)
- Comprehensive test suite: 32 new tests covering all mappings and round-trips

**Backward compatibility:** ConfidenceLevel remains a display enum; existing code using `ConfidenceSignal`, simulation signals, and queries is unchanged. New code can opt into canonical form.

**Next:** Phase 2 begins by adopting canonical shape in high-impact locations (ConfidenceSignal.canonical field, ObservedConfidence, ComparisonConfidence).

---

## Phase 2: Adopt canonical shape in key locations

**Priority order (by impact + adoption ease):**

1. **`ConfidenceSignal` (confidence.py:19)** — already structured; add canonical fields
2. **Observation enums** (observations/models.py) — replace ObservedConfidence with canonical
3. **Comparison models** (observations/comparison_models.py) — replace ComparisonConfidence
4. **Facility catalogue** (domain/facilities.py) — upgrade data_confidence to canonical
5. **Archetype scoring** (build_archetype_scores.py) — map numeric floats to canonical
6. **Simulation output** (simulation/*.py) — wire canonical into confidence signals

### Phase 2 tasks:
1. □ Migrate ConfidenceSignal
2. □ Migrate observation confidence
3. □ Migrate comparison confidence
4. □ Update API response shapes (models.py) to include canonical shape
5. □ Run full test suite
6. □ Update Codex Review findings if any

---

## Phase 3: Documentation & handoff

1. □ Document the migration in this file
2. □ Update CLAUDE.md with the canonical shape
3. □ Note: CRE consumption layer (translation) is authorized separately by roadmap

---

## Non-goals (deferred)

- Runtime CRE consumption / translation-layer code
- Letting translated confidence influence scoring, CP, economy, or optimiser
- Audit-response scoring cleanup (separate roadmap item)

---

## Risk mitigations

- **Backward compatibility:** Keep display enums working; they become computed projections
- **API stability:** Add canonical fields alongside old enums in responses (not replacement)
- **Testing:** Confidence-heavy tests (20+ files) must remain green
- **Review:** Each phase has a review gate; no silent schema drift

---

## Estimated effort

- Phase 1: 4-6 hours (schema design, reverse-mappings, tests)
- Phase 2: 6-10 hours (migrate 5-7 key locations, API responses, test)
- Phase 3: 1-2 hours (docs, handoff)

**Total: 11-18 hours** for a solid foundation.
