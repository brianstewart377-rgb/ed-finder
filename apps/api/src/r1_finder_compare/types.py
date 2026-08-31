from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

AssessmentState = Literal['not_assessable', 'not_supported', 'conditionally_supported', 'supported']
EvidenceDisposition = Literal['sufficient', 'partial', 'missing', 'ambiguous', 'conflicting']
CarrierMode = Literal['no_carrier', 'carrier_available', 'compare_both']
ComparisonContextId = Literal['facts_only', 'role_extraction_v1', 'programme_p_er_01_v1']
PlanPairResilience = Literal['robust', 'fragile', 'mixed', 'unknown']
ReserveCapacity = Literal['tight', 'sufficient', 'resilient', 'expandable']
LogisticsState = Literal['compact', 'moderate', 'spread', 'extreme']


@dataclass(frozen=True)
class BodyFact:
    body_id: str
    base_identity: str
    distance_ls: float | None
    is_landable: bool | None
    is_terraformable: bool | None
    has_rings: bool | None
    has_geologicals: bool | None
    has_biologicals: bool | None
    volcanism: str | None
    atmosphere: str | None
    surface_temperature_k: float | None
    gravity_g: float | None
    radius_km: float | None


@dataclass(frozen=True)
class RequirementEvidence:
    evidence_id: str
    disposition: EvidenceDisposition
    satisfied: bool | None
    support: float | None
    evidence_refs: tuple[str, ...] = ()
    reason: str = ''


@dataclass(frozen=True)
class AllocationClaim:
    allocation_id: str
    resource_id: str
    node_id: str


@dataclass(frozen=True)
class CapacityEvidence:
    evidence_id: str
    disposition: EvidenceDisposition
    sufficient: bool | None
    usable_capacity: float | None
    reserve_capacity: ReserveCapacity | None
    allocations: tuple[AllocationClaim, ...] = ()


@dataclass(frozen=True)
class CandidateProgrammePlan:
    programme_id: str
    template_revision: str
    pair_resilience: PlanPairResilience
    allocation_trace_ids: tuple[str, ...]
    resilience_evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateEvidence:
    fixture_id: str
    fixture_revision: str
    system_id64: str
    system_name: str
    distance_ly: float | None
    bodies: tuple[BodyFact, ...]
    physical_capacity: CapacityEvidence
    extraction_evidence: RequirementEvidence
    refinery_evidence: RequirementEvidence
    logistics_no_carrier: LogisticsState | None
    logistics_carrier: LogisticsState | None
    evidence_disposition: EvidenceDisposition
    ambiguity_flags: tuple[str, ...]
    conflict_flags: tuple[str, ...]
    provenance_ids: tuple[str, ...]


@dataclass(frozen=True)
class AssessmentCondition:
    condition_id: str
    severity: Literal['blocker', 'requirement', 'warning']
    action: str
    reason: str
    evidence_refs: tuple[str, ...] = ()
    requirement_refs: tuple[str, ...] = ()
    allocation_refs: tuple[str, ...] = ()
    affected_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RequirementTrace:
    requirement_id: str
    outcome: Literal['met', 'unmet', 'conditional', 'unknown', 'contradictory']
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class FactualFilters:
    max_distance_ly: float | None = None
    require_hmc: bool = False
    require_metal_rich: bool = False
    require_rings: bool = False


@dataclass(frozen=True)
class FixtureSearchRequest:
    factual_filters: FactualFilters
    comparison_context_id: ComparisonContextId
    carrier_mode: CarrierMode = 'no_carrier'
    strategy_id: str | None = None


@dataclass(frozen=True)
class SearchCandidateResult:
    system_id64: str
    system_name: str
    distance_ly: float | None
    comparison_context_id: ComparisonContextId
    assessment_state: AssessmentState | None
    conditions: tuple[AssessmentCondition, ...]
    reserve_capacity: ReserveCapacity | None
    logistics: LogisticsState | None
    evidence_disposition: EvidenceDisposition
    plan_fit: int | None
    evidence_snapshot_id: str
    candidate_plan_id: str | None
    allocation_trace_ids: tuple[str, ...] = ()
    requirement_trace_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateHandoff:
    system_id64: str
    comparison_context_id: str
    programme_id: str
    template_revision: str
    carrier_mode: str
    evidence_snapshot_id: str
    candidate_plan_id: str
    plan_pair_resilience: PlanPairResilience
    allocation_trace_ids: tuple[str, ...]
    requirement_trace_ids: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioSearchResult:
    carrier_mode: Literal['no_carrier', 'carrier_available']
    results: tuple[SearchCandidateResult, ...]


@dataclass(frozen=True)
class CandidateAssessment:
    state: AssessmentState
    conditions: tuple[AssessmentCondition, ...]
    reserve_capacity: ReserveCapacity | None
    logistics: LogisticsState | None
    evidence_disposition: EvidenceDisposition
    dimensions: tuple[tuple[str, float], ...]
    plan_fit: int | None
    allocation_trace_ids: tuple[str, ...]
    requirement_trace: tuple[RequirementTrace, ...]

    @property
    def requirement_trace_ids(self) -> tuple[str, ...]:
        return tuple(item.requirement_id for item in self.requirement_trace)

    def base_payload(self) -> dict:
        payload = asdict(self)
        payload.pop('dimensions', None)
        payload.pop('plan_fit', None)
        return payload
