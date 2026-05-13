"""Observation domain models for observed-vs-predicted comparisons.

Stage 4D intentionally stores and compares observed facts without treating them
as automatic mechanics upgrades. Differences are surfaced for review.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


STANDARD_CONFIDENCE_LABELS = {
    'observed',
    'verified',
    'community_observed',
    'inferred',
    'estimated',
    'speculative',
    'unknown',
}


class ObservationArea(str, Enum):
    SLOTS = 'slots'
    SERVICES = 'services'
    SERVICE_UNLOCKS = 'service_unlocks'
    ECONOMY_OUTCOME = 'economy_outcome'
    BUILD_STEP = 'build_step'
    CP_BALANCE = 'cp_balance'
    COLONY_PROGRESS = 'colony_progress'
    TOPOLOGY = 'topology'


class ObservationSourceType(str, Enum):
    JOURNAL_UPLOAD = 'journal_upload'
    MANUAL_ENTRY = 'manual_entry'
    EDMC_IMPORT = 'edmc_import'
    API_IMPORT = 'api_import'
    TEST_FIXTURE = 'test_fixture'
    UNKNOWN = 'unknown'


class ObservationComparisonStatus(str, Enum):
    CONFIRMED = 'confirmed'
    MISMATCH = 'mismatch'
    OBSERVED_ONLY = 'observed_only'
    PREDICTED_ONLY = 'predicted_only'
    UNKNOWN = 'unknown'


class ObservationSeverity(str, Enum):
    INFO = 'info'
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'


@dataclass(frozen=True)
class ObservedFact:
    area: str
    subject_id: str
    subject_type: str
    observed_value: Any
    source_type: str
    observed_at: str | None = None
    system_id64: int | None = None
    body_id: str | None = None
    facility_id: str | None = None
    commander: str | None = None
    raw_event_ref: str | None = None
    confidence: str = 'observed'
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PredictionObservationDiff:
    area: str
    subject_id: str
    subject_type: str
    predicted_value: Any
    observed_value: Any
    status: str
    severity: str
    confidence: str
    reason: str
    recommended_action: str | None = None
    source_type: str | None = None
    observed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObservationSummary:
    status: str
    observed_facts_count: int
    confirmed_count: int
    mismatch_count: int
    observed_only_count: int
    predicted_only_count: int
    unknown_count: int
    confidence_impact: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def observed_fact_from_any(value: Any) -> ObservedFact:
    if isinstance(value, ObservedFact):
        return value
    if isinstance(value, dict):
        confidence = str(value.get('confidence') or 'observed')
        if confidence not in STANDARD_CONFIDENCE_LABELS:
            confidence = 'unknown'
        return ObservedFact(
            area=str(value.get('area') or ''),
            subject_id=str(value.get('subject_id') or ''),
            subject_type=str(value.get('subject_type') or ''),
            observed_value=value.get('observed_value'),
            source_type=str(value.get('source_type') or ObservationSourceType.UNKNOWN.value),
            observed_at=value.get('observed_at'),
            system_id64=value.get('system_id64'),
            body_id=value.get('body_id'),
            facility_id=value.get('facility_id'),
            commander=value.get('commander') or value.get('source_commander'),
            raw_event_ref=value.get('raw_event_ref'),
            confidence=confidence,
            notes=list(value.get('notes') or []),
        )
    raise TypeError(f'Unsupported observed fact value: {type(value)!r}')
