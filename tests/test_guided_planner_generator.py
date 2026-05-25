import os

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest

from domain.facilities import FacilityTemplate
from optimiser.guided_planner import (
    GuidedBodyContext,
    GuidedPlanRequest,
    GuidedSystemContext,
    generate_guided_plan_report,
    guided_plan_report_to_dict,
)
from optimiser.plan_quality import PRESET_COUNT_RANGES


def facility(
    template_id: str,
    name: str,
    economy: str | None,
    *,
    is_port: bool = False,
    is_support_facility: bool = False,
    tier: int = 1,
    allowed_location: str = 'orbital',
    prerequisites: list[dict] | None = None,
) -> FacilityTemplate:
    return FacilityTemplate(
        id=template_id,
        name=name,
        category='port' if is_port else 'support',
        tier=tier,
        economy=economy,
        is_port=is_port,
        is_colony_port=False,
        is_support_facility=is_support_facility,
        yellow_cp_generated=4 if is_support_facility else 0,
        green_cp_generated=1 if is_support_facility else 0,
        yellow_cp_cost=10 if is_port else 0,
        green_cp_cost=5 if is_port else 0,
        strong_link_value=1.0,
        weak_link_value=0.1,
        allowed_location=allowed_location,
        pad_size='L' if is_port else None,
        prerequisites=prerequisites or [],
        economy_effects={},
        stat_effects={'data_confidence': 'confirmed'},
    )


def catalogue() -> dict[str, FacilityTemplate]:
    items = [
        facility('coriolis_station', 'Coriolis Station', None, is_port=True, tier=2, allowed_location='orbital'),
        facility('orbis_station', 'Orbis Station', None, is_port=True, tier=3, allowed_location='orbital'),
        facility('refinery_hub', 'Refinery Hub', 'Refinery', is_support_facility=True, allowed_location='orbital'),
        facility('smelter_array', 'Smelter Array', 'Refinery', is_support_facility=True, allowed_location='orbital'),
        facility('industrial_yard', 'Industrial Yard', 'Industrial', is_support_facility=True, allowed_location='orbital'),
        facility('assembly_plant', 'Assembly Plant', 'Industrial', is_support_facility=True, allowed_location='orbital'),
        facility('tourism_lodge', 'Tourism Lodge', 'Tourism', is_support_facility=True, allowed_location='ground'),
        facility('agriculture_farm', 'Agriculture Farm', 'Agriculture', is_support_facility=True, allowed_location='ground'),
        facility('military_settlement', 'Military Settlement', 'Military', is_support_facility=True, allowed_location='ground'),
        facility(
            'shipyard_complex',
            'Shipyard Complex',
            'Military',
            is_support_facility=True,
            allowed_location='ground',
            prerequisites=[{'description': 'Military Settlement'}],
        ),
    ]
    return {item.id: item for item in items}


def system_context(*, all_full: bool = False) -> GuidedSystemContext:
    occupied = 10 if all_full else 0
    return GuidedSystemContext(
        system_id64=123,
        system_name='Test System',
        bodies=[
            GuidedBodyContext(
                body_id='1',
                body_name='Prime Rocky Ice',
                subtype='Rocky ice body',
                predicted_orbital_slots=10,
                predicted_ground_slots=4,
                occupied_orbital_slots=occupied,
                occupied_ground_slots=4 if all_full else 0,
                confidence=0.9,
            ),
            GuidedBodyContext(
                body_id='2',
                body_name='Outer Rocky Ice',
                subtype='Rocky ice body',
                predicted_orbital_slots=10,
                predicted_ground_slots=4,
                occupied_orbital_slots=occupied,
                occupied_ground_slots=4 if all_full else 0,
                unresolved_existing_infrastructure=True,
                inferred_station_body_association=True,
                confidence=0.82,
            ),
            GuidedBodyContext(
                body_id='3',
                body_name='Tourist World',
                subtype='Earth-like world',
                predicted_orbital_slots=6,
                predicted_ground_slots=3,
                confidence=0.88,
            ),
        ],
    )


@pytest.mark.parametrize('preset', ['light', 'medium', 'high', 'maxed'])
def test_guided_planner_generates_quality_gated_preset_reports(preset):
    report = generate_guided_plan_report(
        GuidedPlanRequest(
            system_id64=123,
            preset=preset,
            target_economy='Refinery',
            secondary_economy='Industrial',
            avoid_economies=['Tourism', 'Agriculture', 'Military'],
            risk_tolerance='normal',
        ),
        system_context(),
        catalogue(),
    )

    minimum, maximum = PRESET_COUNT_RANGES[preset]
    assert report.no_strong_plan is False
    assert report.preset == preset
    assert report.target_economies == ['Refinery', 'Industrial']
    assert report.quality.status in {'ok', 'warning'}
    assert report.economy_discipline.status == 'ok'
    assert len(report.placements) >= minimum
    if maximum is not None:
        assert len(report.placements) <= maximum
    assert all(placement.lane in {'orbital', 'ground'} for placement in report.placements)
    assert all(placement.economy in {None, 'Refinery', 'Industrial'} for placement in report.placements)
    assert any(role.role == 'anchor' for role in report.body_roles)


def test_medium_report_is_system_wide_and_explains_body_roles():
    report = generate_guided_plan_report(
        GuidedPlanRequest(
            system_id64=123,
            preset='medium',
            target_economy='Refinery',
            secondary_economy='Industrial',
            requested_count=8,
        ),
        system_context(),
        catalogue(),
    )

    used_body_ids = {placement.body_id for placement in report.placements}
    assert len(used_body_ids) >= 2
    assert report.summary.startswith('Medium prototype report with 8 placements')
    assert report.explanation.why_this_body
    assert report.explanation.why_this_structure
    assert report.quality.placement_count == 8


def test_guided_planner_avoids_confirmed_occupied_slots_when_alternative_exists():
    context = GuidedSystemContext(
        system_id64=123,
        bodies=[
            GuidedBodyContext(
                body_id='1',
                body_name='Full Preferred Body',
                subtype='Rocky ice body',
                predicted_orbital_slots=2,
                predicted_ground_slots=0,
                occupied_orbital_slots=2,
            ),
            GuidedBodyContext(
                body_id='2',
                body_name='Open Backup Body',
                subtype='Rocky ice body',
                predicted_orbital_slots=8,
                predicted_ground_slots=2,
            ),
        ],
    )

    report = generate_guided_plan_report(
        GuidedPlanRequest(
            system_id64=123,
            preset='light',
            target_economy='Refinery',
            secondary_economy='Industrial',
            prefer_body_ids=['1'],
        ),
        context,
        catalogue(),
    )

    assert report.no_strong_plan is False
    assert {placement.body_id for placement in report.placements} == {'2'}
    assert report.occupied_slot_conflicts == []


def test_guided_planner_returns_no_strong_plan_when_capacity_blocks_preset():
    report = generate_guided_plan_report(
        GuidedPlanRequest(
            system_id64=123,
            preset='medium',
            target_economy='Refinery',
            secondary_economy='Industrial',
            requested_count=8,
        ),
        system_context(all_full=True),
        catalogue(),
    )

    assert report.no_strong_plan is True
    assert report.placements == []
    assert 'No body with available capacity' in report.no_strong_plan_reason
    assert report.quality.status == 'reject'


def test_guided_planner_includes_prerequisite_support_before_dependent_structure():
    context = GuidedSystemContext(
        system_id64=123,
        bodies=[
            GuidedBodyContext(
                body_id='4',
                body_name='Security Earthlike',
                subtype='Earth-like world',
                predicted_orbital_slots=4,
                predicted_ground_slots=8,
            ),
            GuidedBodyContext(
                body_id='5',
                body_name='Security Reserve',
                subtype='Earth-like world',
                predicted_orbital_slots=4,
                predicted_ground_slots=8,
            ),
        ],
    )

    report = generate_guided_plan_report(
        GuidedPlanRequest(
            system_id64=123,
            preset='medium',
            target_economy='Military',
            requested_count=6,
        ),
        context,
        catalogue(),
    )

    ids = [placement.facility_template_id for placement in report.placements]
    assert report.no_strong_plan is False
    assert 'shipyard_complex' in ids
    assert ids.index('military_settlement') < ids.index('shipyard_complex')
    assert report.missing_prerequisites == []


def test_guided_planner_respects_avoid_body_and_avoid_economy_inputs():
    report = generate_guided_plan_report(
        GuidedPlanRequest(
            system_id64=123,
            preset='light',
            target_economy='Refinery',
            secondary_economy='Industrial',
            avoid_economies=['Tourism', 'Agriculture', 'Military'],
            avoid_body_ids=['3'],
        ),
        system_context(),
        catalogue(),
    )

    assert report.no_strong_plan is False
    assert all(placement.body_id != '3' for placement in report.placements)
    assert all(placement.economy in {None, 'Refinery', 'Industrial'} for placement in report.placements)
    avoided = [role for role in report.body_roles if role.body_id == '3']
    assert avoided and avoided[0].role == 'avoided'


def test_guided_planner_does_not_pad_when_matching_support_templates_are_missing():
    sparse_catalogue = {
        key: value
        for key, value in catalogue().items()
        if not value.is_support_facility or value.economy != 'Refinery'
    }

    report = generate_guided_plan_report(
        GuidedPlanRequest(
            system_id64=123,
            preset='light',
            target_economy='Refinery',
        ),
        system_context(),
        sparse_catalogue,
    )

    assert report.no_strong_plan is True
    assert 'No support structures match' in report.no_strong_plan_reason
    assert report.placements == []


def test_guided_plan_report_has_json_ready_shape():
    report = generate_guided_plan_report(
        GuidedPlanRequest(
            system_id64=123,
            preset='light',
            target_economy='Refinery',
            secondary_economy='Industrial',
        ),
        system_context(),
        catalogue(),
    )

    payload = guided_plan_report_to_dict(report)

    assert payload['preset'] == 'light'
    assert payload['quality']['status'] in {'ok', 'warning'}
    assert payload['economy_discipline']['status'] == 'ok'
    assert payload['placements'][0]['facility_name']
    assert 'why_this_body' in payload['explanation']
