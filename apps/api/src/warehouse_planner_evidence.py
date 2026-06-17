from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping

from config import settings
from enrichment_operator_status import read_warehouse_status_snapshot
from warehouse_planner_evidence_models import (
    WarehousePlannerEvidenceContract,
    WarehousePlannerEvidenceFreshness,
    WarehousePlannerEvidenceItem,
    WarehousePlannerEvidenceSourceRun,
    WarehousePlannerEvidenceSummary,
)


SCHEMA_VERSION = 'warehouse_planner_evidence/v1'
DEV_FIXTURE_ENV = 'ED_FINDER_ENABLE_PLANNER_EVIDENCE_DEV_FIXTURES'

DEVELOPMENT_FIXTURE_SYSTEMS: dict[int, dict[str, Any]] = {
    12866676218109: {
        'generated_at': '2026-06-17T12:00:00Z',
        'freshness_status': 'fresh',
        'availability': 'report_only',
        'manual_review_required': False,
        'items': [
            {
                'label': 'report_only',
                'source': 'warehouse_report_only',
                'summary': 'Warehouse reconciliation evidence is available for this system as report-only context.',
            },
        ],
        'warnings': [],
    },
    9466842275401: {
        'generated_at': '2026-06-17T12:15:00Z',
        'freshness_status': 'stale',
        'availability': 'report_only',
        'manual_review_required': True,
        'items': [
            {
                'label': 'stale',
                'source': 'warehouse_report_only',
                'summary': 'Warehouse reconciliation evidence for this system is stale and requires review.',
            },
            {
                'label': 'needs_review',
                'source': 'warehouse_report_only',
                'summary': 'Use the evidence as review-only context; planner truth remains unchanged.',
            },
        ],
        'warnings': [
            'Warehouse freshness is stale; treat this per-system evidence as review-only context.',
        ],
    },
}


def build_warehouse_planner_evidence(id64: int) -> WarehousePlannerEvidenceContract:
    warehouse_status = read_warehouse_status_snapshot(settings.enrichment_warehouse_status_json_path)
    fixture = resolve_runtime_warehouse_fixture(id64)

    generated_at = (
        _text_or_none(_mapping(warehouse_status.get('artifact')).get('updated_at'))
        or _text_or_none(_mapping(warehouse_status.get('latest_reconciliation_run')).get('generated_at'))
        or datetime.now(timezone.utc).isoformat()
    )

    freshness = WarehousePlannerEvidenceFreshness(
        status=_freshness_status(warehouse_status, fixture),
        evaluated_at=_evaluated_at(generated_at, fixture),
    )
    source_run = WarehousePlannerEvidenceSourceRun(
        source_name='warehouse_reconciliation' if _source_run_key(warehouse_status) else None,
        run_key=_source_run_key(warehouse_status),
    )

    if fixture is None:
        return WarehousePlannerEvidenceContract(
            schema_version=SCHEMA_VERSION,
            system_id64=id64,
            generated_at=generated_at,
            freshness=freshness,
            source_run=source_run,
            evidence_summary=WarehousePlannerEvidenceSummary(
                availability='unavailable',
                report_only=True,
                manual_review_required=warehouse_status.get('available') is True,
                items=[],
            ),
            warnings=_fallback_warnings(warehouse_status),
        )

    return WarehousePlannerEvidenceContract(
        schema_version=SCHEMA_VERSION,
        system_id64=id64,
        generated_at=_text_or_none(fixture.get('generated_at')) or generated_at,
        freshness=freshness,
        source_run=source_run,
        evidence_summary=WarehousePlannerEvidenceSummary(
            availability='report_only',
            report_only=True,
            manual_review_required=bool(fixture.get('manual_review_required')),
            items=[
                WarehousePlannerEvidenceItem(
                    label=item['label'],
                    source=item['source'],
                    summary=item['summary'],
                )
                for item in fixture.get('items', [])
            ],
        ),
        warnings=[
            'Development fixture evidence is enabled for this system; treat it as non-live example data.',
            *(_safe_rows(fixture.get('warnings'))),
            *(_fallback_warnings(warehouse_status) if warehouse_status.get('available') is False else []),
        ][:8],
    )


def resolve_runtime_warehouse_fixture(id64: int) -> Mapping[str, Any] | None:
    if os.getenv(DEV_FIXTURE_ENV) != '1':
        return None
    fixture = DEVELOPMENT_FIXTURE_SYSTEMS.get(id64)
    return fixture if isinstance(fixture, Mapping) else None


def _fallback_warnings(warehouse_status: Mapping[str, Any]) -> list[str]:
    warnings = _safe_rows(warehouse_status.get('warnings'))
    if warehouse_status.get('available') is False:
        message = _text_or_none(warehouse_status.get('message'))
        if message:
            warnings.append(message)
    elif warehouse_status.get('available') is True:
        warnings.append(
            'No safe per-system warehouse evidence is published for this system yet; planner fallback must remain in place.'
        )
    else:
        warnings.append(
            'Per-system warehouse evidence has not been evaluated for this system yet; planner fallback must remain in place.'
        )
    return warnings[:8]


def _freshness_status(warehouse_status: Mapping[str, Any], fixture: Mapping[str, Any] | None) -> str:
    evidence_health = _mapping(warehouse_status.get('evidence_health'))
    stale_records = _int_or_none(evidence_health.get('stale_records')) or 0
    if stale_records > 0:
        return 'stale'
    if fixture is not None:
        status = _text_or_none(fixture.get('freshness_status'))
        if status in {'fresh', 'stale', 'unknown', 'not_evaluated'}:
            return status
        return 'not_evaluated'
    if warehouse_status.get('available') is True:
        return 'not_evaluated'
    return 'unknown'


def _evaluated_at(generated_at: str, fixture: Mapping[str, Any] | None) -> str | None:
    if fixture is None:
        return None
    return _text_or_none(fixture.get('generated_at')) or generated_at


def _source_run_key(warehouse_status: Mapping[str, Any]) -> str | None:
    latest = _mapping(warehouse_status.get('latest_reconciliation_run'))
    artifact = _mapping(warehouse_status.get('artifact'))
    report_name = _text_or_none(latest.get('report_file_name'))
    artifact_name = _text_or_none(artifact.get('file_name'))
    if report_name:
        return f'warehouse/{report_name}'
    if artifact_name:
        return f'warehouse/{artifact_name}'
    return None


def _safe_rows(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        text = _text_or_none(item)
        if text:
            rows.append(text)
    return rows

def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None
