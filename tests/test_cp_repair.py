from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', str(Path.cwd() / 'test-local.log'))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.facilities import FacilityTemplate
from models import SimulateBuildResponse
from simulation.build_preview import PreviewContext, PreviewPlacement, simulate_build_preview


STANDARD_CONFIDENCE_LABELS = {
    'observed',
    'verified',
    'community_observed',
    'inferred',
    'estimated',
    'speculative',
    'unknown',
}


def facility(
    id: str,
    *,
    tier: int = 1,
    is_port: bool = False,
    yellow_generated: int = 0,
    green_generated: int = 0,
    yellow_cost: int = 0,
    green_cost: int = 0,
    allowed_location: str = 'orbital_or_surface',
) -> FacilityTemplate:
    return FacilityTemplate(
        id=id,
        name=id.replace('_', ' ').title(),
        category='port' if is_port else 'support',
        tier=tier,
        economy='Industrial' if not is_port else None,
        is_port=is_port,
        is_colony_port=False,
        is_support_facility=not is_port,
        yellow_cp_generated=yellow_generated,
        green_cp_generated=green_generated,
        yellow_cp_cost=yellow_cost,
        green_cp_cost=green_cost,
        strong_link_value=0,
        weak_link_value=0.05,
        allowed_location=allowed_location,
        pad_size='L' if is_port else None,
        prerequisites=[],
        economy_effects={},
        stat_effects={'data_confidence': 'observed', 'unlocks': []},
    )


CATALOGUE = {
    't2_port': facility('t2_port', tier=2, is_port=True, allowed_location='orbital'),
    't3_port': facility('t3_port', tier=3, is_port=True, allowed_location='orbital'),
    'support_small': facility('support_small', yellow_generated=20, green_generated=0),
    'support_green': facility('support_green', yellow_generated=20, green_generated=20),
    'support_big': facility('support_big', yellow_generated=120, green_generated=80),
}


def run(plan: list[PreviewPlacement]) -> dict:
    return simulate_build_preview(
        system_id64=9001,
        target_archetype='industrial_refinery',
        placements=plan,
        catalogue=CATALOGUE,
        context=PreviewContext(
            system_id64=9001,
            estimated_orbital_slots=8,
            estimated_ground_slots=8,
            slot_confidence=0.9,
        ),
    )


def suggestions(result: dict, suggestion_type: str | None = None) -> list[dict]:
    items = result['cp_repair_suggestions']
    if suggestion_type:
        return [item for item in items if item['type'] == suggestion_type]
    return items


def test_empty_or_no_placement_simulation_returns_empty_cp_repair_suggestions():
    result = run([])

    assert result['cp_repair_suggestions'] == []
    SimulateBuildResponse.model_validate(result)


def test_cp_negative_step_produces_high_or_critical_repair_suggestion():
    result = run([
        PreviewPlacement('t2_port', '1', build_order=1),
    ])

    negative = suggestions(result, 'cp_negative_detected')
    assert negative
    assert negative[0]['severity'] in {'high', 'critical'}
    assert negative[0]['affected_steps'] == [1]


def test_later_cp_generating_support_produces_move_earlier_suggestion():
    result = run([
        PreviewPlacement('t2_port', '1', build_order=1),
        PreviewPlacement('support_green', '1', build_order=2),
    ])

    move = suggestions(result, 'move_cp_generator_earlier')
    assert move
    assert move[0]['affected_steps'] == [1, 2]
    assert 'Move Support Green from step 2 to before step 1' in move[0]['action']


def test_first_non_primary_port_with_early_cp_pressure_suggests_primary_port():
    result = run([
        PreviewPlacement('t2_port', '1', build_order=1),
        PreviewPlacement('support_green', '1', build_order=2),
    ])

    primary = suggestions(result, 'mark_primary_port')
    assert primary
    assert primary[0]['affected_steps'] == [1]


def test_already_primary_port_does_not_duplicate_primary_suggestion():
    result = run([
        PreviewPlacement('t2_port', '1', is_primary_port=True, build_order=1),
    ])

    assert suggestions(result, 'mark_primary_port') == []


def test_late_t3_or_paid_port_pressure_produces_escalation_suggestion():
    result = run([
        PreviewPlacement('support_big', '1', build_order=1),
        PreviewPlacement('support_small', '1', build_order=2),
        PreviewPlacement('t2_port', '1', build_order=3),
        PreviewPlacement('t3_port', '1', build_order=4),
    ])

    escalation = suggestions(result, 'port_escalation_pressure')
    assert escalation
    assert escalation[0]['severity'] == 'medium'


def test_valid_but_fragile_sequence_produces_fragile_suggestion():
    result = run([
        PreviewPlacement('support_small', '1', build_order=1),
        PreviewPlacement('t2_port', '1', build_order=2),
    ])

    fragile = suggestions(result, 'sequence_is_valid_but_fragile')
    assert fragile
    assert fragile[0]['severity'] == 'medium'


def test_stable_sequence_produces_no_high_severity_suggestions():
    result = run([
        PreviewPlacement('support_big', '1', build_order=1),
        PreviewPlacement('t2_port', '1', build_order=2),
    ])

    assert not [item for item in suggestions(result) if item['severity'] in {'high', 'critical'}]


def test_cp_repair_suggestions_use_standard_confidence_labels_and_trace_events():
    result = run([
        PreviewPlacement('t2_port', '1', build_order=1),
        PreviewPlacement('support_green', '1', build_order=2),
    ])

    assert {item['confidence'] for item in result['cp_repair_suggestions']} <= STANDARD_CONFIDENCE_LABELS
    assert result['mechanics_trace']['cp_repair_effects']
    SimulateBuildResponse.model_validate(result)
