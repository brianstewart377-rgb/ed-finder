from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

JsonObject = dict[str, Any]

_ALLOWED_EVENT_TYPES = {
    'CarrierJump',
    'Docked',
    'FSDJump',
    'FSSAllBodiesFound',
    'FSSBodySignals',
    'FSSDiscoveryScan',
    'Location',
    'SAASignalsFound',
    'Scan',
}


def _strip_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class JournalImportFileRef(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(min_length=1, max_length=255)
    event_count: int = Field(ge=0, le=1_000_000)

    @field_validator('name')
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class JournalImportClientManifest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    parser_version: str = Field(min_length=1, max_length=64)
    files: list[JournalImportFileRef] = Field(default_factory=list, max_length=200)

    @field_validator('parser_version')
    @classmethod
    def strip_parser_version(cls, value: str) -> str:
        return value.strip()


class JournalObservationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    observation_key: str = Field(min_length=16, max_length=128)
    source_file: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=64)
    observed_at: str | None = None
    system_id64: int = Field(gt=0)
    system_name: str | None = Field(default=None, max_length=128)
    subject_type: Literal['system', 'body']
    subject_id: str | None = Field(default=None, max_length=128)
    summary: str | None = Field(default=None, max_length=300)
    payload: JsonObject = Field(default_factory=dict)
    privacy_boundary: JsonObject = Field(default_factory=dict)

    @field_validator('observation_key', 'source_file', 'system_name', 'subject_id', 'summary')
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @field_validator('event_type')
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        stripped = value.strip()
        if stripped not in _ALLOWED_EVENT_TYPES:
            raise ValueError(f'event_type must be one of {sorted(_ALLOWED_EVENT_TYPES)}')
        return stripped

    @field_validator('payload', 'privacy_boundary')
    @classmethod
    def validate_json_object(cls, value: JsonObject) -> JsonObject:
        if not isinstance(value, dict):
            raise ValueError('payload and privacy_boundary must be objects')
        return value


class JournalImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    client_manifest: JournalImportClientManifest
    observations: list[JournalObservationInput] = Field(default_factory=list, max_length=50_000)


class JournalImportSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    observations_received: int
    observations_staged: int
    duplicates_skipped: int
    conflicts_flagged: int = 0
    files_seen: int
    event_counts: dict[str, int] = Field(default_factory=dict)


class JournalImportReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_key: str
    status: str
    parser_version: str
    started_at: str | None = None
    finished_at: str | None = None
    files: list[JournalImportFileRef] = Field(default_factory=list)
    summary: JournalImportSummary
