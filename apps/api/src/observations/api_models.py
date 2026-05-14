from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import (
    ObservationFactSummary,
    ObservationSource,
    ObservedConfidence,
    ObservedFactType,
    ObservedStatus,
    ObservedSubjectType,
    PersistedObservedFact,
)

JsonValue = str | int | float | bool | dict[str, Any] | list[Any] | None

_ALLOWED_STAGE_6A_SOURCES = {ObservationSource.MANUAL, ObservationSource.TEST_FIXTURE}
_MAX_TAGS = 20
_MAX_NOTE_LENGTH = 2000


def _normalise_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    normalised: list[str] = []
    for tag in tags:
        value = str(tag).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalised.append(value)
        if len(normalised) >= _MAX_TAGS:
            break
    return normalised


class ObservedFactBase(BaseModel):
    model_config = ConfigDict(extra='forbid')

    source: ObservationSource = ObservationSource.MANUAL
    fact_type: ObservedFactType
    subject_type: ObservedSubjectType
    subject_id: str | None = None
    status: ObservedStatus
    observed_value: JsonValue = None
    expected_value: JsonValue = None
    confidence: ObservedConfidence = ObservedConfidence.MEDIUM
    notes: str | None = Field(default=None, max_length=_MAX_NOTE_LENGTH)
    build_fingerprint: str | None = None
    simulation_fingerprint: str | None = None
    target_archetype: str | None = None
    facility_template_id: str | None = None
    local_body_id: str | None = None
    service_id: str | None = None
    economy: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator('source')
    @classmethod
    def stage_6a_sources_only(cls, value: ObservationSource) -> ObservationSource:
        if value not in _ALLOWED_STAGE_6A_SOURCES:
            raise ValueError('Stage 6A accepts only manual or test_fixture observations')
        return value

    @field_validator('tags')
    @classmethod
    def normalise_tags(cls, value: list[str]) -> list[str]:
        return _normalise_tags(value)

    @field_validator('metadata')
    @classmethod
    def metadata_must_be_object(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError('metadata must be an object')
        return value

    @model_validator(mode='after')
    def encourage_structured_subject_fields(self) -> 'ObservedFactBase':
        if self.fact_type == ObservedFactType.SERVICE_PRESENCE and not self.service_id:
            raise ValueError('service_presence observations require service_id')
        if self.fact_type == ObservedFactType.ECONOMY_PRESENCE and not self.economy:
            raise ValueError('economy_presence observations require economy')
        if self.fact_type == ObservedFactType.FACILITY_STATE and not self.facility_template_id:
            raise ValueError('facility_state observations require facility_template_id')
        return self


class ObservedFactCreateRequest(ObservedFactBase):
    system_id64: int = Field(gt=0)


class ObservedFactUpdateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    source: ObservationSource | None = None
    fact_type: ObservedFactType | None = None
    subject_type: ObservedSubjectType | None = None
    subject_id: str | None = None
    status: ObservedStatus | None = None
    observed_value: JsonValue = None
    expected_value: JsonValue = None
    confidence: ObservedConfidence | None = None
    notes: str | None = Field(default=None, max_length=_MAX_NOTE_LENGTH)
    build_fingerprint: str | None = None
    simulation_fingerprint: str | None = None
    target_archetype: str | None = None
    facility_template_id: str | None = None
    local_body_id: str | None = None
    service_id: str | None = None
    economy: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator('source')
    @classmethod
    def stage_6a_sources_only(cls, value: ObservationSource | None) -> ObservationSource | None:
        if value is not None and value not in _ALLOWED_STAGE_6A_SOURCES:
            raise ValueError('Stage 6A accepts only manual or test_fixture observations')
        return value

    @field_validator('tags')
    @classmethod
    def normalise_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalise_tags(value)

    @field_validator('metadata')
    @classmethod
    def metadata_must_be_object(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None and not isinstance(value, dict):
            raise ValueError('metadata must be an object')
        return value


class ObservedFactResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    observation_id: str
    system_id64: int
    created_at: str
    updated_at: str | None
    source: str
    fact_type: str
    subject_type: str
    subject_id: str | None
    status: str
    observed_value: JsonValue = None
    expected_value: JsonValue = None
    confidence: str
    notes: str | None = None
    build_fingerprint: str | None = None
    simulation_fingerprint: str | None = None
    target_archetype: str | None = None
    facility_template_id: str | None = None
    local_body_id: str | None = None
    service_id: str | None = None
    economy: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, fact: PersistedObservedFact) -> 'ObservedFactResponse':
        return cls.model_validate(fact.to_dict())


class ObservationFactSummaryResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    total_count: int
    by_fact_type: dict[str, int]
    by_status: dict[str, int]
    by_confidence: dict[str, int]
    latest_observed_at: str | None

    @classmethod
    def from_domain(cls, summary: ObservationFactSummary) -> 'ObservationFactSummaryResponse':
        return cls.model_validate(summary.to_dict())


class ObservedFactListResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    facts: list[ObservedFactResponse]
    total: int
    limit: int
    offset: int
    summary: ObservationFactSummaryResponse


class ObservedFactDeleteResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    observation_id: str
    deleted: bool
