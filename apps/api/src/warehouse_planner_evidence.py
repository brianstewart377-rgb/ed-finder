from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping

from config import settings
from enrichment_operator_status import read_warehouse_status_snapshot
from warehouse_planner_evidence_models import (
    WarehousePlannerEvidenceBoundedStaging,
    WarehousePlannerEvidenceContract,
    WarehousePlannerEvidenceEnvelope,
    WarehousePlannerEvidenceFreshness,
    WarehousePlannerEvidenceItem,
    WarehousePlannerEvidenceSourceRun,
    WarehousePlannerEvidenceSummary,
)
from warehouse_planner_evidence_provider import LivePlannerEvidenceResult, load_stage19bb_closeout_metadata


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
def build_warehouse_planner_evidence(
    id64: int,
    *,
    live_result: LivePlannerEvidenceResult | None = None,
) -> WarehousePlannerEvidenceContract:
    warehouse_status = read_warehouse_status_snapshot(settings.enrichment_warehouse_status_json_path)
    fixture = resolve_runtime_warehouse_fixture(id64)

    generated_at = (
        _text_or_none(_mapping(warehouse_status.get('artifact')).get('updated_at'))
        or _text_or_none(_mapping(warehouse_status.get('latest_reconciliation_run')).get('generated_at'))
        or datetime.now(timezone.utc).isoformat()
    )

    freshness = WarehousePlannerEvidenceFreshness(
        status=_freshness_status(warehouse_status, fixture, live_result),
        evaluated_at=_evaluated_at(generated_at, fixture, live_result),
    )
    source_run = WarehousePlannerEvidenceSourceRun(
        source_name='warehouse_reconciliation' if _source_run_key(warehouse_status) else None,
        run_key=_source_run_key(warehouse_status),
    )

    if fixture is not None:
        return WarehousePlannerEvidenceContract(
            schema_version=SCHEMA_VERSION,
            system_id64=id64,
            generated_at=_text_or_none(fixture.get('generated_at')) or generated_at,
            freshness=freshness,
            source_run=source_run,
            evidence_envelope=_build_evidence_envelope(
                status='available',
                items=[
                    WarehousePlannerEvidenceItem(
                        label=item['label'],
                        source=item['source'],
                        summary=item['summary'],
                    )
                    for item in fixture.get('items', [])
                ],
                bounded_staging=_fixture_bounded_staging(fixture),
            ),
            bounded_staging=_fixture_bounded_staging(fixture),
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

    if live_result is not None:
        return WarehousePlannerEvidenceContract(
            schema_version=SCHEMA_VERSION,
            system_id64=id64,
            generated_at=generated_at,
            freshness=freshness,
            source_run=source_run,
            evidence_envelope=_build_evidence_envelope(
                status=live_result.envelope_status,
                items=live_result.items,
                bounded_staging=live_result.bounded_staging,
            ),
            bounded_staging=live_result.bounded_staging,
            evidence_summary=WarehousePlannerEvidenceSummary(
                availability=live_result.availability,
                report_only=True,
                manual_review_required=live_result.manual_review_required,
                items=live_result.items,
            ),
            warnings=live_result.warnings[:8] or _fallback_warnings(warehouse_status),
        )

    return WarehousePlannerEvidenceContract(
        schema_version=SCHEMA_VERSION,
        system_id64=id64,
        generated_at=generated_at,
        freshness=freshness,
        source_run=source_run,
        evidence_envelope=_build_evidence_envelope(
            status=_fallback_envelope_status(warehouse_status),
            items=[],
            bounded_staging=_default_bounded_staging_contract(status='not_evaluated'),
        ),
        bounded_staging=_default_bounded_staging_contract(status='not_evaluated'),
        evidence_summary=WarehousePlannerEvidenceSummary(
            availability='unavailable',
            report_only=True,
            manual_review_required=warehouse_status.get('available') is True,
            items=[],
        ),
        warnings=_fallback_warnings(warehouse_status),
    )


def resolve_runtime_warehouse_fixture(id64: int) -> Mapping[str, Any] | None:
    if os.getenv(DEV_FIXTURE_ENV) != '1':
        return None
    fixture = DEVELOPMENT_FIXTURE_SYSTEMS.get(id64)
    return fixture if isinstance(fixture, Mapping) else None


def _fixture_bounded_staging(fixture: Mapping[str, Any]) -> WarehousePlannerEvidenceBoundedStaging:
    staged = _mapping(fixture.get('bounded_staging'))
    status = _text_or_none(staged.get('status')) or 'not_evaluated'
    available_row_limits = [
        value for value in staged.get('available_row_limits', [])
        if isinstance(value, int)
    ] if isinstance(staged.get('available_row_limits'), list) else []
    matched_row_count = _int_or_none(staged.get('matched_row_count'))
    row_limit = _int_or_none(staged.get('row_limit'))
    return _default_bounded_staging_contract(
        status=status,
        source_run_key=_text_or_none(staged.get('source_run_key')),
        bridge_key=_text_or_none(staged.get('bridge_key')),
        row_limit=row_limit,
        available_row_limits=available_row_limits,
        matched_row_count=matched_row_count,
        latest_source_updated_at=_text_or_none(staged.get('latest_source_updated_at')),
        summary=_text_or_none(staged.get('summary')),
    )


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


def _default_bounded_staging_contract(
    *,
    status: str,
    source_run_key: str | None = None,
    bridge_key: str | None = None,
    row_limit: int | None = None,
    available_row_limits: list[int] | None = None,
    matched_row_count: int | None = None,
    latest_source_updated_at: str | None = None,
    summary: str | None = None,
) -> WarehousePlannerEvidenceBoundedStaging:
    metadata = load_stage19bb_closeout_metadata()
    return WarehousePlannerEvidenceBoundedStaging(
        status=status,  # type: ignore[arg-type]
        report_only=True,
        bounded_staging_only=True,
        source_name=metadata.source_name if metadata else None,
        source_batch_label=metadata.source_batch_label if metadata else None,
        source_sha256=metadata.source_sha256 if metadata else None,
        source_run_key=source_run_key,
        bridge_key=bridge_key,
        row_limit=row_limit,
        available_row_limits=available_row_limits or [],
        matched_row_count=matched_row_count,
        latest_source_updated_at=latest_source_updated_at,
        summary=summary,
    )


def _build_evidence_envelope(
    *,
    status: str,
    items: list[WarehousePlannerEvidenceItem],
    bounded_staging: WarehousePlannerEvidenceBoundedStaging,
) -> WarehousePlannerEvidenceEnvelope:
    source_classes = _source_classes(items, bounded_staging)
    semantics = _semantics(items, bounded_staging)
    source_labels = {
        'canonical': 'canonical evidence',
        'observed_facts': 'observed-facts evidence',
        'bounded_staging': 'bounded staging evidence',
        'derived_report': 'derived report evidence',
        'unavailable': 'no linked selected-system evidence',
    }
    status_text = {
        'available': 'Selected-system evidence is available in this read-only planner envelope.',
        'unavailable': 'Selected-system evidence is unavailable in this read-only planner envelope.',
        'not_evaluated': 'Selected-system evidence was not evaluated in this runtime.',
        'unknown': 'Selected-system evidence remains unknown in this runtime.',
    }[status]
    source_summary = ', '.join(source_labels[value] for value in source_classes)
    return WarehousePlannerEvidenceEnvelope(
        status=status,  # type: ignore[arg-type]
        source_classes=source_classes,
        semantics=semantics,
        report_only=True,
        selected_system_only=True,
        planner_truth_source_class='canonical' if any(item.source == 'canonical' for item in items) else 'unavailable',
        claims_canonical_truth=False,
        claims_full_coverage=False,
        summary=f'{status_text} Source classes: {source_summary}.',
    )


def _source_classes(
    items: list[WarehousePlannerEvidenceItem],
    bounded_staging: WarehousePlannerEvidenceBoundedStaging,
) -> list[str]:
    values: list[str] = []
    for item in items:
        mapped = {
            'canonical': 'canonical',
            'observed': 'observed_facts',
            'warehouse_report_only': 'derived_report',
            'unknown': 'unavailable',
        }[item.source]
        if mapped not in values:
            values.append(mapped)
    if bounded_staging.status == 'available' and 'bounded_staging' not in values:
        values.append('bounded_staging')
    if not values:
        values.append('unavailable')
    return values


def _semantics(
    items: list[WarehousePlannerEvidenceItem],
    bounded_staging: WarehousePlannerEvidenceBoundedStaging,
) -> list[str]:
    values = ['report_only_review_context', 'not_full_coverage']
    if any(item.source == 'canonical' for item in items):
        values.insert(0, 'canonical_truth')
    if any(item.source == 'observed' for item in items) and 'observed_report' not in values:
        values.append('observed_report')
    if bounded_staging.status == 'available' and 'bounded_staging_evidence' not in values:
        values.append('bounded_staging_evidence')
    return values


def _fallback_envelope_status(warehouse_status: Mapping[str, Any]) -> str:
    if warehouse_status.get('available') is True:
        return 'not_evaluated'
    if warehouse_status.get('available') is False:
        return 'unavailable'
    return 'unknown'


def _freshness_status(
    warehouse_status: Mapping[str, Any],
    fixture: Mapping[str, Any] | None,
    live_result: LivePlannerEvidenceResult | None,
) -> str:
    evidence_health = _mapping(warehouse_status.get('evidence_health'))
    stale_records = _int_or_none(evidence_health.get('stale_records')) or 0
    if live_result is not None:
        return live_result.freshness_status
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


def _evaluated_at(
    generated_at: str,
    fixture: Mapping[str, Any] | None,
    live_result: LivePlannerEvidenceResult | None,
) -> str | None:
    if live_result is not None:
        return live_result.evaluated_at
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
