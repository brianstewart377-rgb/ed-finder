from __future__ import annotations

import json
import os
from functools import lru_cache
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Mapping

from provenance_cockpit_models import (
    EvidencePanels,
    GuardrailsSummary,
    PlannerEvidencePanel,
    ProvenanceCockpitResponse,
    ProvenanceCockpitSystem,
    ProvenanceSummary,
    SourceRunEvidencePanel,
    UiHints,
    WarehouseEvidencePanel,
)


ROOT = Path(__file__).resolve().parents[3]
AUTHORITY_PATH = ROOT / 'docs' / 'colonisation-redesign' / 'stage-19-state-authority.json'
SCHEMA_VERSION = 'stage20a_provenance_cockpit/v1'
DEV_FIXTURE_ENV = 'ED_FINDER_ENABLE_PLANNER_EVIDENCE_DEV_FIXTURES'

DEVELOPMENT_FIXTURE_SYSTEMS: dict[int, dict[str, Any]] = {
    12866676218109: {
        'name': 'Shinrarta Dezhra',
        'primary_archetype': 'refinery_industrial',
        'summary_state': 'available',
        'warehouse_state': 'available',
        'planner_state': 'available',
        'source_run_state': 'available',
        'source_name': 'edsm',
        'rows_read': 250,
        'rows_staged': 250,
        'artifact_name': 'provenance-cockpit-dev-fixture.json',
        'latest_source_run_key': 'dev-fixture/warehouse-planner-evidence-shinrarta',
        'planner_observed_facts_count': 3,
        'planner_projected_build_count': 1,
        'planner_manual_review_required': True,
        'warehouse_stale_records': 0,
        'warnings': [],
        'severity': 'info',
    },
    9466842275401: {
        'name': 'Lave',
        'primary_archetype': 'tourism_agriculture',
        'summary_state': 'stale',
        'warehouse_state': 'stale',
        'planner_state': 'available',
        'source_run_state': 'available',
        'source_name': 'edsm',
        'rows_read': 250,
        'rows_staged': 250,
        'artifact_name': 'provenance-cockpit-dev-fixture.json',
        'latest_source_run_key': 'dev-fixture/warehouse-planner-evidence-lave',
        'planner_observed_facts_count': 1,
        'planner_projected_build_count': 0,
        'planner_manual_review_required': True,
        'warehouse_stale_records': 14,
        'warnings': [
            'Warehouse freshness is stale; treat the reconciliation summary as review-only evidence.',
        ],
        'severity': 'warning',
    },
}


def build_provenance_cockpit(id64: int) -> ProvenanceCockpitResponse:
    authority, authority_warning = _load_authority_snapshot()
    current_safety_state = _current_safety_state(authority)
    fixture = resolve_runtime_provenance_fixture(id64)
    warnings = _safe_warning_rows([authority_warning])

    if fixture is None:
        return ProvenanceCockpitResponse(
            schema_version=SCHEMA_VERSION,
            system=ProvenanceCockpitSystem(
                id64=id64,
                name=None,
                primary_archetype='unknown',
            ),
            provenance_summary=ProvenanceSummary(
                state='unknown',
                latest_source_run_key=None,
                warehouse_state='unknown',
                planner_evidence_state='unknown',
            ),
            evidence_panels=EvidencePanels(
                source_run=SourceRunEvidencePanel(
                    state='unknown',
                    source_name=None,
                    rows_read=None,
                    rows_staged=None,
                    artifact_name=None,
                ),
                warehouse=WarehouseEvidencePanel(
                    state='unknown',
                    report_only=True,
                    canonical_writes_planned=0,
                    stale_records=None,
                ),
                planner=PlannerEvidencePanel(
                    state='unknown',
                    observed_facts_count=0,
                    projected_build_count=0,
                    manual_review_required=True,
                ),
            ),
            guardrails=_guardrails(current_safety_state),
            warnings=[
                'No provenance artifact is configured for this system yet; unknown values remain unknown.',
                *warnings,
            ],
            ui_hints=UiHints(
                severity='neutral',
                empty_state_key='provenance.unknown',
            ),
        )

    return ProvenanceCockpitResponse(
        schema_version=SCHEMA_VERSION,
        system=ProvenanceCockpitSystem(
            id64=id64,
            name=fixture['name'],
            primary_archetype=fixture['primary_archetype'],
        ),
        provenance_summary=ProvenanceSummary(
            state=fixture['summary_state'],
            latest_source_run_key=_text_or_none(fixture.get('latest_source_run_key')),
            warehouse_state=fixture['warehouse_state'],
            planner_evidence_state=fixture['planner_state'],
        ),
        evidence_panels=EvidencePanels(
            source_run=SourceRunEvidencePanel(
                state=_text_or_none(fixture.get('source_run_state')) or 'unknown',
                source_name=_text_or_none(fixture.get('source_name')),
                rows_read=_int_or_none(fixture.get('rows_read')),
                rows_staged=_int_or_none(fixture.get('rows_staged')),
                artifact_name=_text_or_none(fixture.get('artifact_name')),
            ),
            warehouse=WarehouseEvidencePanel(
                state=fixture['warehouse_state'],
                report_only=True,
                canonical_writes_planned=0,
                stale_records=fixture['warehouse_stale_records'],
            ),
            planner=PlannerEvidencePanel(
                state=fixture['planner_state'],
                observed_facts_count=fixture['planner_observed_facts_count'],
                projected_build_count=fixture['planner_projected_build_count'],
                manual_review_required=fixture['planner_manual_review_required'],
            ),
        ),
        guardrails=_guardrails(current_safety_state),
        warnings=[
            'Development fixture evidence is enabled for this system; treat it as non-live example data.',
            *_safe_warning_rows(fixture.get('warnings')),
            *warnings,
        ],
        ui_hints=UiHints(
            severity=fixture['severity'],
            empty_state_key=None,
        ),
    )


def _guardrails(stage20: Mapping[str, Any]) -> GuardrailsSummary:
    return GuardrailsSummary(
        stage19_paused=_bool_or_default(stage20.get('stage19_remains_paused'), True),
        stage19_production_activation_complete=bool(stage20.get('stage19_production_activation_complete')),
        next_stage19_write_lane_authorized=bool(stage20.get('next_stage19_write_lane_authorized')),
        canonical_apply_complete=bool(stage20.get('canonical_apply_complete')),
        rebaseline_complete=bool(stage20.get('rebaseline_complete')),
        scheduler_enabled=bool(stage20.get('scheduler_enabled')),
        db_writes_authorized=bool(stage20.get('db_writes_authorized')),
        stage19_operator_commands_authorized=bool(stage20.get('stage19_operator_commands_authorized')),
    )


def resolve_runtime_provenance_fixture(id64: int) -> Mapping[str, Any] | None:
    if os.getenv(DEV_FIXTURE_ENV) != '1':
        return None
    fixture = DEVELOPMENT_FIXTURE_SYSTEMS.get(id64)
    return fixture if isinstance(fixture, Mapping) else None


@lru_cache(maxsize=1)
def _load_authority_snapshot() -> tuple[dict[str, Any], str | None]:
    try:
        return json.loads(AUTHORITY_PATH.read_text(encoding='utf-8')), None
    except FileNotFoundError:
        return {}, 'Current authority snapshot is unavailable; global safety status is shown conservatively.'
    except JSONDecodeError:
        return {}, 'Current authority snapshot is malformed; global safety status is shown conservatively.'


def _current_safety_state(authority: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ('stage22', 'stage21', 'stage20'):
        value = authority.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bool_or_default(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _safe_warning_rows(value: Any) -> list[str]:
    if isinstance(value, list):
        rows = [_text_or_none(item) for item in value]
        return [row for row in rows if row]
    text = _text_or_none(value)
    return [text] if text else []
