from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import asyncpg

from observations.store import observed_fact_summary
from warehouse_planner_evidence_models import WarehousePlannerEvidenceItem


@dataclass(frozen=True)
class LivePlannerEvidenceResult:
    availability: str
    items: list[WarehousePlannerEvidenceItem]
    freshness_status: str
    evaluated_at: str | None
    manual_review_required: bool
    warnings: list[str] = field(default_factory=list)


async def load_live_planner_evidence(pool: asyncpg.Pool, id64: int) -> LivePlannerEvidenceResult:
    warnings: list[str] = []

    async with pool.acquire() as conn:
        system = await conn.fetchrow(
            'SELECT id64, name FROM systems WHERE id64 = $1',
            id64,
        )
        if not system:
            return LivePlannerEvidenceResult(
                availability='unavailable',
                items=[],
                freshness_status='unknown',
                evaluated_at=None,
                manual_review_required=True,
                warnings=[
                    'System is not present in canonical app data; selected-system evidence remains unavailable.',
                ],
            )

        body_count = await conn.fetchval(
            'SELECT COUNT(*)::int FROM bodies WHERE system_id64 = $1',
            id64,
        ) or 0
        station_count = await conn.fetchval(
            'SELECT COUNT(*)::int FROM stations WHERE system_id64 = $1',
            id64,
        ) or 0

        has_station_links = bool(
            await conn.fetchval("SELECT to_regclass('public.station_body_links') IS NOT NULL")
        )
        linked_station_count: int | None = None
        if has_station_links:
            linked_station_count = await conn.fetchval(
                """
                SELECT COUNT(*)::int
                FROM station_body_links l
                JOIN stations s ON s.id = l.station_id
                WHERE s.system_id64 = $1
                  AND l.association_status = 'local_matched'
                """,
                id64,
            ) or 0

        latest_canonical_at = await _safe_fetchval(
            conn,
            """
            SELECT MAX(ts)::text
            FROM (
                SELECT MAX(sf.updated_at) AS ts
                FROM body_scan_facts sf
                WHERE sf.system_address = $1
                UNION ALL
                SELECT MAX(s.distance_updated_at) AS ts
                FROM stations s
                WHERE s.system_id64 = $1
                UNION ALL
                SELECT MAX(s.station_type_updated_at) AS ts
                FROM stations s
                WHERE s.system_id64 = $1
                UNION ALL
                SELECT MAX(s.body_name_updated_at) AS ts
                FROM stations s
                WHERE s.system_id64 = $1
            ) AS evidence_ts
            """,
            id64,
        )
        if latest_canonical_at is None:
            warnings.append(
                'Canonical evidence timestamps are unavailable; freshness remains conservative.'
            )

    observed_summary = await _safe_observed_summary(pool, id64)
    observed_total = _int_or_zero(observed_summary.get('total_count'))
    observed_latest_at = _text_or_none(observed_summary.get('latest_observed_at'))

    items: list[WarehousePlannerEvidenceItem] = []

    if body_count > 0 or station_count > 0:
        linked_summary = (
            f'; {linked_station_count} local station-body links are matched'
            if linked_station_count is not None
            else ''
        )
        items.append(
            WarehousePlannerEvidenceItem(
                label='report_only',
                source='canonical',
                summary=(
                    f'Canonical app data for {system["name"]} includes {body_count} bodies and '
                    f'{station_count} stations{linked_summary}.'
                ),
            )
        )

    if observed_total > 0:
        items.append(
            WarehousePlannerEvidenceItem(
                label='needs_review',
                source='observed',
                summary=(
                    f'Observed evidence includes {observed_total} persisted facts'
                    f'{_fact_type_summary(observed_summary)}'
                    f'{_latest_summary(observed_latest_at)}.'
                ),
            )
        )

    if station_count > 0 and linked_station_count == 0:
        items.append(
            WarehousePlannerEvidenceItem(
                label='unresolved',
                source='unknown',
                summary='Station rows exist for this system, but no matched local station-body links are confirmed yet.',
            )
        )

    if observed_summary.get('_warning'):
        warnings.append(str(observed_summary['_warning']))

    if not items:
        return LivePlannerEvidenceResult(
            availability='unavailable',
            items=[],
            freshness_status='unknown',
            evaluated_at=None,
            manual_review_required=True,
            warnings=[
                'No safe selected-system evidence is currently linked for this system; unavailable remains unknown.',
                *warnings,
            ][:8],
        )

    if observed_total == 0:
        warnings.append(
            'No persisted observed facts were found for this system; selected-system evidence currently relies on canonical data only.'
        )

    warnings.append(
        'Per-system warehouse evidence is not included until a safe selected-system warehouse join exists; any source-run metadata remains review context only.'
    )

    return LivePlannerEvidenceResult(
        availability='report_only',
        items=items[:6],
        freshness_status='not_evaluated',
        evaluated_at=_max_timestamp(latest_canonical_at, observed_latest_at),
        manual_review_required=any(item.label in {'needs_review', 'verify', 'unresolved'} for item in items),
        warnings=warnings[:8],
    )


async def _safe_fetchval(conn: asyncpg.Connection, query: str, *args: Any) -> Any:
    try:
        return await conn.fetchval(query, *args)
    except asyncpg.PostgresError:
        return None


async def _safe_observed_summary(pool: asyncpg.Pool, id64: int) -> dict[str, Any]:
    async with pool.acquire() as conn:
        observed_table_present = bool(
            await conn.fetchval("SELECT to_regclass('public.observed_facts') IS NOT NULL")
        )
    if not observed_table_present:
        return {'_warning': 'Observed evidence storage is unavailable; selected-system evidence currently uses canonical data only.'}
    try:
        summary = await observed_fact_summary(pool, id64)
        if isinstance(summary, dict):
            return summary
    except asyncpg.PostgresError:
        return {'_warning': 'Observed evidence could not be summarized safely; selected-system evidence currently uses canonical data only.'}
    return {'_warning': 'Observed evidence summary returned an unexpected shape; selected-system evidence currently uses canonical data only.'}


def _fact_type_summary(summary: dict[str, Any]) -> str:
    value = summary.get('by_fact_type')
    if not isinstance(value, dict) or not value:
        return ''
    ranked = sorted(
        (
            (str(key), count)
            for key, count in value.items()
            if isinstance(key, str) and isinstance(count, int)
        ),
        key=lambda item: (-item[1], item[0]),
    )[:2]
    if not ranked:
        return ''
    return ' across ' + ', '.join(f'{label}:{count}' for label, count in ranked)


def _latest_summary(value: str | None) -> str:
    return f'; latest observed at {value}' if value else ''


def _max_timestamp(*values: str | None) -> str | None:
    present = [value for value in values if isinstance(value, str) and value.strip()]
    return max(present) if present else None


def _int_or_zero(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
