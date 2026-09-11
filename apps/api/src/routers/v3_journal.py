"""Account-scoped V3 journal personal lane (``/api/v1/journal/*``).

Wire contract: docs/superpowers/plans/2026-08-28-v3-journal-intelligence-foundation.md
Task 3. The store/projection implementations live in the ``edfinder_api.journal.*``
package (parallel tasks) and are imported lazily so this router stays
import-checkable before those modules land.

Auth: every endpoint requires an authenticated account session (401 when
absent). Writes additionally require a trusted browser origin
(``require_same_origin``). All journal data is scoped by ``owner_account_id``
from the session — never by anything client-supplied.
"""

from __future__ import annotations

import importlib
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from edfinder_api.auth import AuthenticatedUser, get_request_user, require_same_origin
from edfinder_api.config import limiter
from edfinder_api.deps import get_pool
# Frozen 30-event allowlist — single source of truth is
# edfinder_api.journal.event_contract.JOURNAL_EVENT_ALLOWLIST (Task 2).
from edfinder_api.journal.event_contract import JOURNAL_EVENT_ALLOWLIST

router = APIRouter(prefix="/api/v1/journal", tags=["v3-journal"])

# Quotas (plan Global Constraints).
MAX_EVENTS_PER_REQUEST = 50_000
MAX_FILES_PER_IMPORT = 200
MAX_FILE_EVENT_COUNT = 1_000_000


class V1Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class V3JournalFileRef(V1Model):
    name: str = Field(min_length=1, max_length=512)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    line_count: int = Field(ge=0)
    event_count: int = Field(ge=0, le=MAX_FILE_EVENT_COUNT)
    first_event_at: datetime | None = None
    last_event_at: datetime | None = None

    @field_validator("first_event_at", "last_event_at", mode="before")
    @classmethod
    def _utc_normalized(cls, value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if not isinstance(value, datetime):
            raise ValueError("file event timestamps must be ISO-8601 timestamps")
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class V3JournalEventInput(V1Model):
    event_type: str
    event_timestamp: datetime
    source_record_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_file: str = Field(min_length=1, max_length=512)
    source_offset: int = Field(ge=0)
    payload: dict[str, Any]

    @field_validator("event_type")
    @classmethod
    def _event_type_allowlisted(cls, value: str) -> str:
        if value not in JOURNAL_EVENT_ALLOWLIST:
            raise ValueError("event_type is not in the journal allowlist")
        return value

    @field_validator("event_timestamp", mode="before")
    @classmethod
    def _utc_normalized(cls, value: object) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if not isinstance(value, datetime):
            raise ValueError("event_timestamp must be an ISO-8601 timestamp")
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class V3JournalImportRequest(V1Model):
    parser_version: str = Field(min_length=1, max_length=64)
    files: list[V3JournalFileRef] = Field(min_length=1, max_length=MAX_FILES_PER_IMPORT)
    events: list[V3JournalEventInput] = Field(default_factory=list, max_length=MAX_EVENTS_PER_REQUEST)


class V3JournalImportReceipt(V1Model):
    import_id: str
    # 'READY' on create; private_import.import_state on fetch.
    status: str
    files_received: int
    files_skipped: int
    files_admitted: int
    events_received: int
    events_inserted: int
    duplicates_skipped: int
    privacy_stripped_fields: int
    event_counts: dict[str, int]
    started_at: str
    finished_at: str


class V3JournalSummaryResponse(V1Model):
    events_stored: int
    unique_bodies: int
    unique_bio_observations: int
    systems_observed: int
    last_imported_at: str | None
    event_counts: dict[str, int]
    imported_files: int


class V3JournalSystemRow(V1Model):
    system_id64: str
    system_name: str | None
    first_observed_at: str | None
    last_observed_at: str | None
    visit_count: int


class V3JournalBodyRow(V1Model):
    system_id64: str
    body_id: str
    body_name: str | None
    first_observed_at: str | None
    last_observed_at: str | None
    scan_count: int


class V3CodexEntryRow(V1Model):
    entry_id: str
    name: str | None
    category: str | None
    subcategory: str | None
    region: str | None
    system_id64: str | None
    body_id: str | None
    first_observed_at: str | None
    last_observed_at: str | None


class V3OrganicProgressRow(V1Model):
    genus: str
    species: str
    variant: str | None
    stages: list[str]
    first_observed_at: str | None
    last_observed_at: str | None


class V3SaleRow(V1Model):
    bio_data: list[dict[str, Any]]
    market_id: str | None
    observed_at: str


Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=1_000)]


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _store() -> Any:
    return importlib.import_module("edfinder_api.journal.store")


def _projections() -> Any:
    return importlib.import_module("edfinder_api.journal.projections")


async def _require_user(request: Request) -> AuthenticatedUser:
    user = await get_request_user(request)
    if user is None:
        raise HTTPException(401, "Sign-in required")
    return user


async def _event_counts(pool: asyncpg.Pool, account_id: uuid.UUID) -> dict[str, int]:
    rows = await pool.fetch(
        """SELECT event_type, count(*)::int AS n
             FROM v3_private.journal_event
            WHERE owner_account_id = $1
            GROUP BY event_type""",
        account_id,
    )
    return {str(row["event_type"]): int(row["n"]) for row in rows}


async def _imported_files(pool: asyncpg.Pool, account_id: uuid.UUID) -> int:
    return int(await pool.fetchval(
        "SELECT count(*) FROM v3_private.journal_import_file WHERE owner_account_id = $1",
        account_id,
    ))


@router.post("/imports", response_model=V3JournalImportReceipt, operation_id="createV3JournalImport")
@limiter.limit("5/minute")
async def create_v3_journal_import(
    request: Request,
    body: V3JournalImportRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> V3JournalImportReceipt:
    user = await _require_user(request)
    require_same_origin(request)
    files = [
        {
            "name": ref.name,
            "content_sha256": ref.content_sha256,
            "size_bytes": ref.size_bytes,
            "line_count": ref.line_count,
            "event_count": ref.event_count,
            "first_event_at": ref.first_event_at,
            "last_event_at": ref.last_event_at,
        }
        for ref in body.files
    ]
    events = [
        {
            "event_type": event.event_type,
            "event_timestamp": event.event_timestamp,
            "source_record_hash": event.source_record_hash,
            "source_file": event.source_file,
            "source_offset": event.source_offset,
            "payload": event.payload,
        }
        for event in body.events
    ]
    store = _store()
    try:
        import_id, counts = await store.import_journal_batch(
            pool,
            account_id=user.account_id,
            commander_id=None,
            parser_version=body.parser_version,
            files=files,
            events=events,
        )
    except store.JournalQuotaExceededError as exc:
        raise HTTPException(429, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = await pool.fetchrow(
        """SELECT imported_at
             FROM v3_private.private_import
            WHERE private_import_id = $1 AND owner_account_id = $2""",
        import_id,
        user.account_id,
    )
    started_at = row["imported_at"] if row else datetime.now(timezone.utc)
    finished_at = datetime.now(timezone.utc)
    return V3JournalImportReceipt(
        import_id=str(import_id),
        status="READY",
        files_received=counts.files_received,
        files_skipped=counts.files_skipped,
        files_admitted=counts.files_admitted,
        events_received=counts.events_received,
        events_inserted=counts.events_inserted,
        duplicates_skipped=counts.duplicates_skipped,
        privacy_stripped_fields=counts.privacy_stripped_fields,
        event_counts=dict(counts.event_counts),
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
    )


@router.get("/imports/{import_id}", response_model=V3JournalImportReceipt, operation_id="getV3JournalImport")
@limiter.limit("60/minute")
async def get_v3_journal_import(
    import_id: uuid.UUID,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
) -> V3JournalImportReceipt:
    user = await _require_user(request)
    # Migration 003 persists no per-import request counters; the GET receipt
    # reconstructs the persisted subset (files/events actually admitted under
    # this import) and reports zeros for the transient request-level counters.
    row = await pool.fetchrow(
        """SELECT pi.private_import_id, pi.import_state, pi.imported_at,
                  (SELECT count(*)::int
                     FROM v3_private.journal_import_file f
                    WHERE f.private_import_id = pi.private_import_id
                      AND f.owner_account_id = pi.owner_account_id) AS files_admitted,
                  (SELECT count(*)::int
                     FROM v3_private.journal_event ev
                    WHERE ev.private_import_id = pi.private_import_id
                      AND ev.owner_account_id = pi.owner_account_id) AS events_inserted
             FROM v3_private.private_import pi
            WHERE pi.private_import_id = $1 AND pi.owner_account_id = $2""",
        import_id,
        user.account_id,
    )
    if row is None:
        raise HTTPException(404, f"Journal import {import_id} not found")
    imported_at = _iso(row["imported_at"])
    return V3JournalImportReceipt(
        import_id=str(row["private_import_id"]),
        status=str(row["import_state"]),
        files_received=0,
        files_skipped=0,
        files_admitted=int(row["files_admitted"]),
        events_received=0,
        events_inserted=int(row["events_inserted"]),
        duplicates_skipped=0,
        privacy_stripped_fields=0,
        event_counts={},
        started_at=imported_at or "",
        finished_at=imported_at or "",
    )


@router.get("/summary", response_model=V3JournalSummaryResponse, operation_id="getV3JournalSummary")
@limiter.limit("60/minute")
async def get_v3_journal_summary(
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
) -> V3JournalSummaryResponse:
    user = await _require_user(request)
    data = await _projections().journal_summary(pool, user.account_id)
    return V3JournalSummaryResponse(
        events_stored=int(data["events_stored"]),
        unique_bodies=int(data["unique_bodies"]),
        unique_bio_observations=int(data["unique_bio_observations"]),
        systems_observed=int(data["systems_observed"]),
        last_imported_at=_iso(data.get("last_imported_at")),
        event_counts=await _event_counts(pool, user.account_id),
        imported_files=await _imported_files(pool, user.account_id),
    )


@router.get("/systems", response_model=list[V3JournalSystemRow], operation_id="listV3JournalSystems")
@limiter.limit("60/minute")
async def list_v3_journal_systems(
    request: Request,
    offset: Offset = 0,
    limit: Limit = 50,
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[V3JournalSystemRow]:
    user = await _require_user(request)
    rows = await _projections().visited_systems(pool, user.account_id, offset=offset, limit=limit)
    return [
        V3JournalSystemRow(
            system_id64=str(row["system_id64"]),
            system_name=_opt_str(row.get("system_name")),
            first_observed_at=_iso(row.get("first_observed_at")),
            last_observed_at=_iso(row.get("last_observed_at")),
            visit_count=int(row["visit_count"]),
        )
        for row in rows
    ]


@router.get("/bodies", response_model=list[V3JournalBodyRow], operation_id="listV3JournalBodies")
@limiter.limit("60/minute")
async def list_v3_journal_bodies(
    request: Request,
    offset: Offset = 0,
    limit: Limit = 50,
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[V3JournalBodyRow]:
    user = await _require_user(request)
    rows = await _projections().scanned_bodies(pool, user.account_id, offset=offset, limit=limit)
    return [
        V3JournalBodyRow(
            system_id64=str(row["system_id64"]),
            body_id=str(row["body_id"]),
            body_name=_opt_str(row.get("body_name")),
            first_observed_at=_iso(row.get("first_observed_at")),
            last_observed_at=_iso(row.get("last_observed_at")),
            scan_count=int(row["scan_count"]),
        )
        for row in rows
    ]


@router.get("/codex", response_model=list[V3CodexEntryRow], operation_id="listV3JournalCodex")
@limiter.limit("60/minute")
async def list_v3_journal_codex(
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[V3CodexEntryRow]:
    user = await _require_user(request)
    rows = await _projections().codex_entries(pool, user.account_id)
    return [
        V3CodexEntryRow(
            entry_id=str(row["entry_id"]),
            name=_opt_str(row.get("name")),
            category=_opt_str(row.get("category")),
            subcategory=_opt_str(row.get("subcategory")),
            region=_opt_str(row.get("region")),
            system_id64=_opt_str(row.get("system_id64")),
            body_id=_opt_str(row.get("body_id")),
            first_observed_at=_iso(row.get("first_observed_at")),
            last_observed_at=_iso(row.get("last_observed_at")),
        )
        for row in rows
    ]


@router.get("/organics", response_model=list[V3OrganicProgressRow], operation_id="listV3JournalOrganics")
@limiter.limit("60/minute")
async def list_v3_journal_organics(
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[V3OrganicProgressRow]:
    user = await _require_user(request)
    rows = await _projections().organic_progress(pool, user.account_id)
    return [
        V3OrganicProgressRow(
            genus=str(row["genus"]),
            species=str(row["species"]),
            variant=_opt_str(row.get("variant")),
            stages=[str(stage) for stage in (row.get("stages") or [])],
            first_observed_at=_iso(row.get("first_observed_at")),
            last_observed_at=_iso(row.get("last_observed_at")),
        )
        for row in rows
    ]


@router.get("/sales", response_model=list[V3SaleRow], operation_id="listV3JournalSales")
@limiter.limit("60/minute")
async def list_v3_journal_sales(
    request: Request,
    offset: Offset = 0,
    limit: Limit = 50,
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[V3SaleRow]:
    user = await _require_user(request)
    rows = await _projections().sale_history(pool, user.account_id, offset=offset, limit=limit)
    return [
        V3SaleRow(
            bio_data=[dict(item) for item in (row.get("bio_data") or [])],
            market_id=_opt_str(row.get("market_id")),
            observed_at=_iso(row.get("observed_at")) or "",
        )
        for row in rows
    ]
