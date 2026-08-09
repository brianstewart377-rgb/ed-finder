from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

import asyncpg

from edfinder_api.exploration.api_models import (
    ExplorationFactRow,
    ExplorationFactsResponse,
    ExplorationImportReceipt,
    ExplorationImportRequest,
    ExplorationImportSummary,
)

MAX_DAILY_ROWS_PER_SYNC_KEY = 50_000
DEFAULT_FACTS_LIMIT = 5_000


class ExplorationImportRateLimitError(RuntimeError):
    """Raised when the bounded exploration-import daily row budget is exceeded."""


def _json_object(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        decoded = json.loads(stripped)
        return dict(decoded) if isinstance(decoded, dict) else {}
    return dict(value)


def _dt_to_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


async def _daily_rows_for_sync_key(conn: asyncpg.Connection, sync_key: str) -> int:
    count = await conn.fetchval(
        '''
        SELECT COUNT(*)
        FROM exploration_facts
        WHERE sync_key = $1
          AND created_at >= (NOW() - INTERVAL '1 day')
        ''',
        sync_key,
    )
    return int(count or 0)


async def import_exploration_batch(
    pool: asyncpg.Pool,
    request: ExplorationImportRequest,
) -> ExplorationImportReceipt:
    event_counts: Counter[str] = Counter(observation.event_type for observation in request.observations)
    rows_read = len(request.observations)
    rows_staged = 0
    rows_skipped = 0

    async with pool.acquire() as conn:
        async with conn.transaction():
            daily_rows_before = await _daily_rows_for_sync_key(conn, request.sync_key)
            if daily_rows_before + rows_read > MAX_DAILY_ROWS_PER_SYNC_KEY:
                raise ExplorationImportRateLimitError(
                    f'Exploration import row budget exceeded for this sync key: '
                    f'{daily_rows_before + rows_read:,} rows in the last 24h '
                    f'(limit {MAX_DAILY_ROWS_PER_SYNC_KEY:,}).'
                )

            for observation in request.observations:
                inserted = await conn.fetchrow(
                    '''
                    INSERT INTO exploration_facts (
                        sync_key, source, source_record_hash, event_type,
                        system_id64, system_name, body_id, body_name,
                        observed_at, payload_json
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9::timestamptz, $10::jsonb
                    )
                    ON CONFLICT (sync_key, source_record_hash) DO NOTHING
                    RETURNING source_record_hash
                    ''',
                    request.sync_key,
                    request.source,
                    observation.observation_key,
                    observation.event_type,
                    observation.system_id64,
                    observation.system_name,
                    observation.body_id,
                    observation.body_name,
                    observation.observed_at,
                    observation.payload,
                )
                if inserted is None:
                    rows_skipped += 1
                    continue
                rows_staged += 1

    return ExplorationImportReceipt(
        sync_key=request.sync_key,
        status='succeeded',
        summary=ExplorationImportSummary(
            observations_received=rows_read,
            observations_staged=rows_staged,
            duplicates_skipped=rows_skipped,
            event_counts=dict(event_counts),
        ),
    )


async def get_exploration_facts(
    pool: asyncpg.Pool,
    sync_key: str,
    *,
    limit: int = DEFAULT_FACTS_LIMIT,
) -> ExplorationFactsResponse:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''
            SELECT event_type, system_id64, system_name, body_id, body_name, observed_at, payload_json
            FROM exploration_facts
            WHERE sync_key = $1
            ORDER BY observed_at DESC
            LIMIT $2
            ''',
            sync_key,
            limit,
        )

    facts = [
        ExplorationFactRow(
            event_type=str(row['event_type']),
            system_id64=int(row['system_id64']),
            system_name=row['system_name'],
            body_id=row['body_id'],
            body_name=row['body_name'],
            observed_at=_dt_to_str(row['observed_at']) or '',
            payload=_json_object(row['payload_json']),
        )
        for row in rows
    ]
    return ExplorationFactsResponse(sync_key=sync_key, facts=facts)
