import os

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from domain.facilities import FacilityTemplate
from optimiser.models import CandidatePlacement, OptimiserCandidate
from optimiser.plan_quality import (
    PlanBodySlotState,
    PlanQualityOptions,
    detect_economy_soup,
    validate_generated_plan_quality,
)


def facility(
    template_id: str,
    economy: str | None,
    *,
    is_port: bool = False,
    is_support_facility: bool = False,
    allowed_location: str = 'orbital',
    prerequisites: list[dict] | None = None,
) -> FacilityTemplate:
    return FacilityTemplate(
        id=template_id,
        name=template_id.replace('_', ' ').title(),
        category='port' if is_port else 'support',
        tier=2 if is_port else 1,
        economy=economy,
        is_port=is_port,
        is_colony_port=False,
        is_support_facility=is_support_facility,
        yellow_cp_generated=4 if is_support_facility else 0,
        green_cp_generated=1 if is_support_facility else 0,
        yellow_cp_cost=8 if is_port else 0,
        green_cp_cost=4 if is_port else 0,
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
        facility('coriolis_station', None, is_port=True, allowed_location='orbital'),
        facility('refinery_hub', 'Refinery', is_support_facility=True, allowed_location='orbital'),
        facility('industrial_yard', 'Industrial', is_support_facility=True, allowed_location='orbital'),
        facility('extraction_outpost', 'Extraction', is_support_facility=True, allowed_location='orbital'),
        facility('tourism_lodge', 'Tourism', is_support_facility=True, allowed_location='surface'),
        facility('agriculture_farm', 'Agriculture', is_support_facility=True, allowed_location='surface'),
        facility('military_garrison', 'Military', is_support_facility=True, allowed_location='surface'),
        facility('hightech_lab', 'HighTech', is_support_facility=True, allowed_location='orbital'),
        facility('military_settlement', 'Military', is_support_facility=True, allowed_location='surface'),
        facility(
            'shipyard_complex',
            'Military',
            is_support_facility=True,
            allowed_location='surface',
            prerequisites=[{'description': 'Military Settlement'}],
        ),
        facility('flex_support', 'Industrial', is_support_facility=True, allowed_location='orbital_or_surface'),
    ]
    return {item.id: item for item in items}


def candidate(
    placement_ids: list[str],
    *,
    body_ids: list[str] | None = None,
    target: str = 'refinery_industrial',
    preset_label: str = 'Coherent refinery industrial plan',
    rationale: list[str] | None = None,
    assumptions: list[str] | None = None,
) -> OptimiserCandidate:
    body_ids = body_ids or ['1', '1', '2', '2', '1', '2', '1', '2']
    placements = [
        CandidatePlacement(
            facility_template_id=template_id,
            local_body_id=body_ids[index % len(body_ids)],
            is_primary_port=index == 0,
            build_order=index + 1,
        )
        for index, template_id in enumerate(placement_ids)
    ]
    return OptimiserCandidate(
        candidate_id='candidate',
        label=preset_label,
        target_archetype=target,
        strategy='guided_contract',
        placements=placements,
        rationale=rationale or ['Targets Refinery and Industrial as a clear two-economy spine.'],
        warnings=[],
        assumptions=assumptions or [],
        tags=[],
        preview_summary=None,
    )


def test_coherent_refinery_industrial_plan_passes_quality_contract():
    plan = candidate([
        'coriolis_station',
        'refinery_hub',
        'industrial_yard',
        'refinery_hub',
        'industrial_yard',
        'refinery_hub',
    ])

    report = validate_generated_plan_quality(
        plan,
        catalogue(),
        options=PlanQualityOptions(target_archetype='refinery_industrial', preset='medium', requested_count=6),
        body_slots=[
            PlanBodySlotState('1', predicted_orbital_slots=5, predicted_ground_slots=2),
            PlanBodySlotState('2', predicted_orbital_slots=5, predicted_ground_slots=2),
        ],
    )

    assert report.status == 'ok'
    assert report.economy_soup.status == 'ok'
    assert report.missing_prerequisites == []


def test_random_economy_soup_is_rejected_for_disciplined_target():
    plan = candidate([
        'coriolis_station',
        'refinery_hub',
        'tourism_lodge',
        'agriculture_farm',
        'military_garrison',
        'hightech_lab',
    ], rationale=['Adds many interesting structures.'])

    assessment = detect_economy_soup(
        plan,
        catalogue(),
        target_economies=['Refinery', 'Industrial'],
    )
    report = validate_generated_plan_quality(
        plan,
        catalogue(),
        options=PlanQualityOptions(target_archetype='refinery_industrial', preset='medium'),
    )

    assert assessment.status == 'reject'
    assert report.status == 'reject'
    assert any('too many unrelated economy families' in reason for reason in report.rejections)
    assert report.suggested_fixes


def test_justified_support_economy_is_allowed_without_soup_warning():
    plan = candidate([
        'coriolis_station',
        'refinery_hub',
        'industrial_yard',
        'refinery_hub',
        'hightech_lab',
        'industrial_yard',
    ], rationale=['Targets Refinery and Industrial; HighTech is an explicit support economy for services.'])

    report = validate_generated_plan_quality(
        plan,
        catalogue(),
        options=PlanQualityOptions(
            target_archetype='refinery_industrial',
            target_economies=['Refinery', 'Industrial', 'HighTech'],
            preset='medium',
        ),
    )

    assert report.economy_soup.status == 'ok'
    assert report.status == 'ok'


def test_maxed_plan_can_be_broader_when_mixed_risk_is_explained():
    plan = candidate([
        'coriolis_station',
        'refinery_hub',
        'industrial_yard',
        'extraction_outpost',
        'refinery_hub',
        'industrial_yard',
        'tourism_lodge',
        'agriculture_farm',
        'military_garrison',
        'hightech_lab',
        'refinery_hub',
        'industrial_yard',
        'extraction_outpost',
        'tourism_lodge',
        'agriculture_farm',
        'military_garrison',
        'hightech_lab',
    ], rationale=['Maxed mixed plan keeps Refinery and Industrial as the spine and labels contamination risk.'])

    report = validate_generated_plan_quality(
        plan,
        catalogue(),
        options=PlanQualityOptions(target_archetype='refinery_industrial', preset='maxed'),
        body_slots=[
            PlanBodySlotState('1', predicted_orbital_slots=10, predicted_ground_slots=8),
            PlanBodySlotState('2', predicted_orbital_slots=10, predicted_ground_slots=8),
        ],
    )

    assert report.economy_soup.status == 'ok'
    assert not report.rejections


def test_requested_count_mismatch_without_scale_explanation_is_rejected():
    plan = candidate([
        'coriolis_station',
        'refinery_hub',
        'industrial_yard',
    ])

    report = validate_generated_plan_quality(
        plan,
        catalogue(),
        options=PlanQualityOptions(target_archetype='refinery_industrial', requested_count=10),
    )

    assert report.status == 'reject'
    assert any('requested about 10' in reason for reason in report.rejections)
    assert any('Do not pad' in fix for fix in report.suggested_fixes)


def test_confirmed_occupied_slot_capacity_rejects_plan_usage():
    plan = candidate([
        'coriolis_station',
        'refinery_hub',
        'industrial_yard',
    ], body_ids=['1', '1', '1'])

    report = validate_generated_plan_quality(
        plan,
        catalogue(),
        options=PlanQualityOptions(target_archetype='refinery_industrial'),
        body_slots=[PlanBodySlotState('1', predicted_orbital_slots=2, predicted_ground_slots=0, occupied_orbital_slots=2)],
    )

    assert report.status == 'reject'
    assert any('no confirmed remaining orbital slots' in reason for reason in report.rejections)


def test_missing_prerequisite_warns_and_included_prerequisite_passes():
    missing = candidate(['coriolis_station', 'shipyard_complex'])
    with_support = candidate(['coriolis_station', 'military_settlement', 'shipyard_complex'])

    missing_report = validate_generated_plan_quality(
        missing,
        catalogue(),
        options=PlanQualityOptions(target_economies=['Military']),
    )
    supported_report = validate_generated_plan_quality(
        with_support,
        catalogue(),
        options=PlanQualityOptions(target_economies=['Military']),
    )

    assert missing_report.status == 'warning'
    assert missing_report.missing_prerequisites[0].description == 'Military Settlement'
    assert supported_report.missing_prerequisites == []


def test_lane_flexible_placement_warns_until_guided_plan_chooses_lane():
    plan = candidate(['coriolis_station', 'flex_support'])

    report = validate_generated_plan_quality(
        plan,
        catalogue(),
        options=PlanQualityOptions(target_economies=['Industrial']),
        body_slots=[PlanBodySlotState('1', predicted_orbital_slots=3, predicted_ground_slots=3)],
    )

    assert report.status == 'warning'
    assert any('does not choose a lane' in warning for warning in report.warnings)


def test_raw_ids_in_user_facing_explanation_are_warned():
    plan = candidate(
        ['coriolis_station', 'refinery_hub', 'industrial_yard'],
        rationale=['Use body123 because refinery_hub has good numbers.'],
    )

    report = validate_generated_plan_quality(
        plan,
        catalogue(),
        options=PlanQualityOptions(target_archetype='refinery_industrial'),
    )

    assert report.status == 'warning'
    assert any('raw identifiers' in warning for warning in report.warnings)
