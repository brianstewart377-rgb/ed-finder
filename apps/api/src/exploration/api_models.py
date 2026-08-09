from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

JsonObject = dict[str, Any]
_SYNC_KEY_RE = re.compile(r'^[A-Za-z0-9_-]{16,128}$')
MAX_PAYLOAD_BYTES = 32_768

ALLOWED_EXPLORATION_EVENT_TYPES = {
    'FSDJump',
    'Location',
    'Scan',
    'FSSDiscoveryScan',
    'SAASignalsFound',
    'FSSBodySignals',
    'CodexEntry',
    'SAAScanComplete',
    'ScanOrganic',
}


def _strip_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _reject_nul_byte(value: str) -> None:
    # PostgreSQL TEXT columns cannot store a NUL (0x00) byte, but it is a
    # perfectly valid JSON string character - without this check, a NUL
    # anywhere in these fields reaches the INSERT and PostgreSQL rejects it,
    # turning one malformed observation into a 500 that rolls back the whole
    # batch instead of a clean 422 for the one bad row.
    if '\x00' in value:
        raise ValueError('value must not contain a NUL character')


class ExplorationObservationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    observation_key: str = Field(min_length=16, max_length=128)
    event_type: str = Field(min_length=1, max_length=64)
    observed_at: datetime
    system_id64: int = Field(gt=0, le=9_223_372_036_854_775_807)
    system_name: str | None = Field(default=None, max_length=128)
    body_id: int | None = Field(default=None, ge=0, le=2_147_483_647)
    body_name: str | None = Field(default=None, max_length=128)
    payload: JsonObject = Field(default_factory=dict)

    @field_validator('system_name', 'body_name')
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_nul_byte(value)
        return _strip_text(value)

    @field_validator('observation_key')
    @classmethod
    def reject_blank_observation_key(cls, value: str) -> str:
        # observation_key is a client-computed dedupe hash, not free-text, so it is
        # validated as-is (unstripped) against Field(min_length=16, max_length=128).
        # Field alone only checks length, not content, so a whitespace-only value of
        # valid length would otherwise pass; reject it explicitly without normalizing
        # the stored value (no stripping/truncation here).
        _reject_nul_byte(value)
        if not value.strip():
            raise ValueError('observation_key must not be blank or whitespace-only')
        return value

    @field_validator('event_type')
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        stripped = value.strip()
        if stripped not in ALLOWED_EXPLORATION_EVENT_TYPES:
            raise ValueError(f'event_type must be one of {sorted(ALLOWED_EXPLORATION_EVENT_TYPES)}')
        return stripped

    @field_validator('observed_at', mode='before')
    @classmethod
    def validate_observed_at(cls, value: object) -> datetime:
        if isinstance(value, str):
            stripped = value.strip()
            value = datetime.fromisoformat(stripped.replace('Z', '+00:00'))
        if not isinstance(value, datetime):
            raise ValueError('observed_at must be an ISO-8601 timestamp')
        try:
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        except OverflowError as exc:
            raise ValueError(f'observed_at is outside the representable timestamp range: {exc}') from exc

    @field_validator('payload')
    @classmethod
    def validate_payload(cls, value: JsonObject) -> JsonObject:
        if not isinstance(value, dict):
            raise ValueError('payload must be an object')
        try:
            serialized_size = len(json.dumps(value, allow_nan=False))
        except ValueError as exc:
            raise ValueError(f'payload contains a value PostgreSQL JSON cannot store: {exc}') from exc
        if serialized_size > MAX_PAYLOAD_BYTES:
            raise ValueError(f'payload exceeds the {MAX_PAYLOAD_BYTES}-byte limit ({serialized_size} bytes)')
        return value


class ExplorationImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    sync_key: str = Field(min_length=16, max_length=128)
    source: Literal['journal', 'edsm'] = 'journal'
    observations: list[ExplorationObservationInput] = Field(default_factory=list, max_length=20_000)

    @field_validator('sync_key')
    @classmethod
    def validate_sync_key(cls, value: str) -> str:
        stripped = value.strip()
        if stripped == 'legacy':
            raise ValueError('sync_key="legacy" is reserved for migration')
        if not _SYNC_KEY_RE.match(stripped):
            raise ValueError('sync_key must be 16-128 chars, alphanumeric + "_" or "-" only.')
        return stripped


class ExplorationImportSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    observations_received: int
    observations_staged: int
    duplicates_skipped: int
    event_counts: dict[str, int] = Field(default_factory=dict)


class ExplorationImportReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')

    sync_key: str
    status: str
    summary: ExplorationImportSummary


class ExplorationFactRow(BaseModel):
    model_config = ConfigDict(extra='forbid')

    event_type: str
    system_id64: int
    system_name: str | None = None
    body_id: int | None = None
    body_name: str | None = None
    observed_at: str
    payload: JsonObject = Field(default_factory=dict)
    source: str


class ExplorationFactsResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    sync_key: str
    facts: list[ExplorationFactRow] = Field(default_factory=list)
    count: int
    truncated: bool
