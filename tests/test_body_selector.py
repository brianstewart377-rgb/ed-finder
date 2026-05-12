from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.colonisation_rules import get_target_profile
from domain.facilities import FacilityTemplate
from recommendations.body_selector import select_body_candidates
from recommendations.build_generator import generate_build_drafts


def body(**overrides):
    row = {
        'body_id': 1,
        'body_name': 'Body 1',
        'body_type': 'Planet',
        'subtype': 'Rocky body',
        'is_landable': True,
        'is_terraformable': False,
        'is_ringed': False,
        'has_bio': False,
        'has_geo': False,
        'bio_signal_count': 0,
        'geo_signal_count': 0,
        'confidence': 0.8,
    }
    row.update(overrides)
    return row


def facility(
    id: str,
    economy: str | None,
    *,
    is_port: bool = False,
    is_colony_port: bool = False,
    is_support_facility: bool = False,
    tier: int = 2,
) -> FacilityTemplate:
    return FacilityTemplate(
        id=id,
        name=id.replace('_', ' ').title(),
        category='port' if is_port else 'support',
        tier=tier,
        economy=economy,
        is_port=is_port,
        is_colony_port=is_colony_port,
        is_support_facility=is_support_facility,
        yellow_cp_generated=4,
        green_cp_generated=1,
        yellow_cp_cost=0,
        green_cp_cost=0,
        strong_link_value=1.5,
        weak_link_value=0.1,
        allowed_location='orbital_or_surface',
        pad_size='L' if is_port else None,
        prerequisites=[],
        economy_effects={},
        stat_effects={'data_confidence': 'observed'},
    )


def catalogue() -> dict[str, FacilityTemplate]:
    items = [
        facility('colony_ship', 'Colony', is_port=True, is_colony_port=True, tier=1),
        facility('coriolis_station', None, is_port=True),
        facility('orbis_t3', None, is_port=True, tier=3),
        facility('refinery', 'Refinery', is_support_facility=True),
        facility('industrial_facility', 'Industrial', is_support_facility=True),
        facility('extraction_facility', 'Extraction', is_support_facility=True),
        facility('agricultural_facility', 'Agriculture', is_support_facility=True),
        facility('tourism_installation', 'Tourism', is_support_facility=True),
        facility('hightech_research', 'HighTech', is_support_facility=True),
    ]
    return {item.id: item for item in items}


def test_extraction_refinery_prefers_hmc_ringed_or_geo_candidates_over_elw():
    target = get_target_profile('extraction_refinery')
    candidates = select_body_candidates('extraction_refinery', target, [
        body(body_id=1, body_name='ELW', subtype='Earth-like world'),
        body(body_id=2, body_name='HMC', subtype='High metal content body'),
        body(body_id=3, body_name='Ringed Rocky', subtype='Rocky body', is_ringed=True),
        body(body_id=4, body_name='Geo Rocky', subtype='Rocky body', has_geo=True, geo_signal_count=2),
    ])

    assert candidates
    assert candidates[0].body_name in {'HMC', 'Ringed Rocky', 'Geo Rocky'}
    assert candidates[0].body_name != 'ELW'


def test_hitech_tourism_prefers_elw_ammonia_water_or_exotic_bodies():
    target = get_target_profile('hitech_tourism')
    candidates = select_body_candidates('hitech_tourism', target, [
        body(body_id=1, body_name='Plain Rocky', subtype='Rocky body'),
        body(body_id=2, body_name='ELW', subtype='Earth-like world'),
        body(body_id=3, body_name='Ammonia', subtype='Ammonia world'),
        body(body_id=4, body_name='Water', subtype='Water world'),
        body(body_id=5, body_name='Neutron', body_type='Star', subtype='Neutron Star'),
    ])

    assert candidates[0].body_name in {'ELW', 'Ammonia', 'Water', 'Neutron'}
    assert candidates[0].body_name != 'Plain Rocky'


def test_agriculture_terraforming_does_not_treat_industrial_as_fake_terraforming():
    target = get_target_profile('agriculture_terraforming')
    candidates = select_body_candidates('agriculture_terraforming', target, [
        body(body_id=1, body_name='Icy Industrial', subtype='Icy body'),
        body(body_id=2, body_name='Bio Rocky', subtype='Rocky body', has_bio=True, bio_signal_count=2),
    ])

    assert candidates
    assert candidates[0].body_name == 'Bio Rocky'
    assert all(candidate.body_name != 'Icy Industrial' for candidate in candidates)


def test_refinery_industrial_penalises_elw_as_anchor():
    target = get_target_profile('refinery_industrial')
    candidates = select_body_candidates('refinery_industrial', target, [
        body(body_id=1, body_name='ELW', subtype='Earth-like world'),
        body(body_id=2, body_name='Rocky Ice', subtype='Rocky ice body'),
        body(body_id=3, body_name='Clean Rocky', subtype='Rocky body'),
    ])

    assert candidates[0].body_name in {'Rocky Ice', 'Clean Rocky'}
    assert all(candidate.body_name != 'ELW' for candidate in candidates[:2])


def test_unsupported_archetype_returns_no_generated_plan_and_clear_warning():
    target = get_target_profile('unknown_future_archetype')
    candidates = select_body_candidates('unknown_future_archetype', target, [body()])
    drafts, warnings = generate_build_drafts(
        system_id64=123,
        target=target,
        body=body_candidate_stub(),
        catalogue=catalogue(),
        slot_confidence=0.8,
        total_slots=8,
    )

    assert candidates == []
    assert drafts == []
    assert warnings == ['Recommended build rules are not implemented for this archetype yet.']


def test_expansion_capital_rewards_slot_rich_high_confidence_systems():
    target = get_target_profile('expansion_capital')
    low = select_body_candidates('expansion_capital', target, [
        body(body_id=1, body_name='Plain Rocky', subtype='Rocky body', confidence=0.4),
    ], slot_confidence=0.35, total_slots=2)[0]
    high = select_body_candidates('expansion_capital', target, [
        body(body_id=2, body_name='Mixed ELW', subtype='Earth-like world', confidence=0.9),
    ], slot_confidence=0.85, total_slots=12)[0]

    assert high.score > low.score
    assert high.body_name == 'Mixed ELW'


def body_candidate_stub():
    from recommendations.body_selector import BodyCandidate
    from domain.colonisation_rules import profile_body

    profile = profile_body(body(body_id=99, body_name='Stub'))
    return BodyCandidate(profile=profile, score=1, reason='stub', caveats=[])
