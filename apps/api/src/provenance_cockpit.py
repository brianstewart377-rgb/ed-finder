from __future__ import annotations

import json
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

FIXTURE_SYSTEMS: dict[int, dict[str, Any]] = {
    12866676218109: {
        'name': 'Shinrarta Dezhra',
        'primary_archetype': 'refinery_industrial',
        'summary_state': 'available',
        'warehouse_state': 'available',
        'planner_state': 'available',
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
    authority = _load_authority()
    stage20 = _mapping(authority.get('stage20'))
    stage19av_proof = _mapping(_mapping(authority.get('stage19ay_test_environment_closeout')).get('stage19av_proof'))

    fixture = FIXTURE_SYSTEMS.get(id64)
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
            guardrails=_guardrails(stage20),
            warnings=[
                'No provenance artifact is configured for this system yet; unknown values remain unknown.',
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
            latest_source_run_key=_text_or_none(stage19av_proof.get('source_run_key')),
            warehouse_state=fixture['warehouse_state'],
            planner_evidence_state=fixture['planner_state'],
        ),
        evidence_panels=EvidencePanels(
            source_run=SourceRunEvidencePanel(
                state='available',
                source_name='edsm',
                rows_read=_int_or_none(stage19av_proof.get('rows_read')),
                rows_staged=_int_or_none(stage19av_proof.get('rows_staged')),
                artifact_name=_basename(stage19av_proof.get('artifact_path')),
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
        guardrails=_guardrails(stage20),
        warnings=list(fixture['warnings']),
        ui_hints=UiHints(
            severity=fixture['severity'],
            empty_state_key=None,
        ),
    )


def _guardrails(stage20: Mapping[str, Any]) -> GuardrailsSummary:
    return GuardrailsSummary(
        stage19_paused=bool(stage20.get('stage19_remains_paused')),
        stage19_production_activation_complete=bool(stage20.get('stage19_production_activation_complete')),
        next_stage19_write_lane_authorized=bool(stage20.get('next_stage19_write_lane_authorized')),
        canonical_apply_complete=bool(stage20.get('canonical_apply_complete')),
        rebaseline_complete=bool(stage20.get('rebaseline_complete')),
        scheduler_enabled=bool(stage20.get('scheduler_enabled')),
        db_writes_authorized=bool(stage20.get('db_writes_authorized')),
        stage19_operator_commands_authorized=bool(stage20.get('stage19_operator_commands_authorized')),
    )


def _load_authority() -> dict[str, Any]:
    return json.loads(AUTHORITY_PATH.read_text(encoding='utf-8'))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _basename(value: Any) -> str | None:
    text = _text_or_none(value)
    return Path(text).name if text else None
