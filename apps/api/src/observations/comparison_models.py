"""Stage 6C predicted-vs-observed comparison models.

These dataclasses describe the deterministic output of the Stage 6C
comparison engine. They are intentionally separate from the legacy
Stage 4D comparison models (``ObservedFact`` / ``PredictionObservationDiff``
/ ``ObservationSummary`` in ``observations.models``) so that:

* the Stage 4D code path used by ``simulate_build_preview`` keeps running
  unchanged;
* the new Stage 6C engine can evolve its own status / severity / summary
  vocabulary tuned to the persisted Stage 6A observed-fact contract;
* downstream Stage 6D UI rendering has a single, explicit response
  shape to consume.

Stage 6C is **comparison only**. Nothing in this module is consumed by
Simulation Preview scoring, optimiser candidate generation, or optimiser
ranking. See ``docs/ROADMAP.md`` for the
boundary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


# ──────────────────────────────────────────────────────────────────────
# Enumerated vocabularies
# ──────────────────────────────────────────────────────────────────────
class ComparisonStatus(str, Enum):
    """Per-comparison status for a single (prediction subject, observation) pair."""

    CONFIRMED = 'confirmed'
    CONTRADICTED = 'contradicted'
    PREDICTED_ONLY = 'predicted_only'
    OBSERVED_ONLY = 'observed_only'
    UNKNOWN = 'unknown'
    UNVERIFIED = 'unverified'


class ComparisonSeverity(str, Enum):
    INFO = 'info'
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'


class ComparisonConfidence(str, Enum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    UNKNOWN = 'unknown'


class ComparisonOverallStatus(str, Enum):
    """Top-level summary status for a full comparison run."""

    NO_OBSERVATIONS = 'no_observations'
    CONFIRMED = 'confirmed'
    MIXED = 'mixed'
    NEEDS_REVIEW = 'needs_review'
    INSUFFICIENT_EVIDENCE = 'insufficient_evidence'


class ComparisonConfidenceImpact(str, Enum):
    """How the observations move our trust in the prediction.

    Stage 6C is conservative: confidence impact is reported but **must
    not** be plumbed back into Simulation Preview scoring or optimiser
    ranking. It is a UI hint only.
    """

    NONE = 'none'
    STRENGTHENED = 'strengthened'
    WEAKENED = 'weakened'
    MIXED = 'mixed'
    INSUFFICIENT_EVIDENCE = 'insufficient_evidence'


class ComparisonArea(str, Enum):
    """High-level grouping for a comparison row.

    Areas are deliberately broad. Fine-grained subject identity goes in
    ``subject_type`` + ``subject_id``.
    """

    SERVICE = 'service'
    ECONOMY = 'economy'
    CP = 'cp'
    FACILITY = 'facility'
    BUILD_OUTCOME = 'build_outcome'
    NOTE = 'note'
    OTHER = 'other'


# ──────────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ObservationEvidenceMatch:
    """One observed fact that contributed to a comparison row.

    The full ``PersistedObservedFact`` is not embedded here — only the
    fields a UI needs to render the evidence shelf alongside the
    comparison. This keeps the response compact and avoids leaking
    server-only fields like ``build_fingerprint``.
    """

    observation_id: str
    fact_type: str
    subject_type: str
    subject_id: str | None
    status: str
    confidence: str
    observed_value: Any | None = None
    expected_value: Any | None = None
    notes: str | None = None


@dataclass(frozen=True)
class PredictionObservationComparison:
    """One predicted-vs-observed comparison row.

    ``predicted_value`` and ``observed_value`` are kept loose (``Any``)
    so the same dataclass can describe a service status string, an
    economy list, or a CP numeric/object value.
    """

    comparison_id: str
    area: str
    subject_type: str
    subject_id: str | None
    predicted_value: Any | None
    observed_value: Any | None
    status: str
    severity: str
    confidence: str
    reason: str
    recommended_action: str | None = None
    evidence: list[ObservationEvidenceMatch] = field(default_factory=list)
    prediction_source: str | None = None


@dataclass(frozen=True)
class PredictionObservationComparisonSummary:
    status: str
    observed_facts_count: int
    compared_predictions_count: int
    confirmed_count: int
    contradicted_count: int
    observed_only_count: int
    predicted_only_count: int
    unknown_count: int
    unverified_count: int
    confidence_impact: str
    summary: str


@dataclass(frozen=True)
class PredictionObservationComparisonResult:
    system_id64: int
    target_archetype: str | None
    generated_at: str
    summary: PredictionObservationComparisonSummary
    comparisons: list[PredictionObservationComparison]
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# Serialisation helpers
# ──────────────────────────────────────────────────────────────────────
# ``asdict`` already produces JSON-safe primitives for the shapes we
# emit (str/int/float/bool/None/list/dict). We still wrap them in named
# helpers so call sites read self-documenting and tests can assert on
# exact dict keys without poking at dataclass internals.
def evidence_match_to_dict(match: ObservationEvidenceMatch) -> dict[str, Any]:
    return asdict(match)


def comparison_to_dict(comparison: PredictionObservationComparison) -> dict[str, Any]:
    return asdict(comparison)


def comparison_summary_to_dict(summary: PredictionObservationComparisonSummary) -> dict[str, Any]:
    return asdict(summary)


def comparison_result_to_dict(result: PredictionObservationComparisonResult) -> dict[str, Any]:
    return asdict(result)


__all__ = [
    'ComparisonArea',
    'ComparisonConfidence',
    'ComparisonConfidenceImpact',
    'ComparisonOverallStatus',
    'ComparisonSeverity',
    'ComparisonStatus',
    'ObservationEvidenceMatch',
    'PredictionObservationComparison',
    'PredictionObservationComparisonResult',
    'PredictionObservationComparisonSummary',
    'comparison_result_to_dict',
    'comparison_summary_to_dict',
    'comparison_to_dict',
    'evidence_match_to_dict',
]

