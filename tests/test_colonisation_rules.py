from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.colonisation_rules import get_target_profile, profile_body
from recommendations.body_selector import select_body_candidates


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


def test_elw_profile_is_mixed_and_not_industrial():
    profile = profile_body(body(subtype='Earth-like world'))

    assert set(profile.base_economies) == {'Agriculture', 'HighTech', 'Military', 'Tourism'}
    assert 'Industrial' not in profile.base_economies
    assert any('mixed economy' in caveat for caveat in profile.caveats)


def test_rocky_profile_modifiers_follow_mega_guide_table():
    clean = profile_body(body(subtype='Rocky body'))
    ringed = profile_body(body(subtype='Rocky body', is_ringed=True))
    bio = profile_body(body(subtype='Rocky body', has_bio=True, bio_signal_count=2))
    geo = profile_body(body(subtype='Rocky body', has_geo=True, geo_signal_count=1))

    assert clean.base_economies == ['Refinery']
    assert ringed.base_economies == ['Refinery']
    assert 'Extraction' in ringed.modifier_economies
    assert 'Agriculture' in bio.modifier_economies
    assert 'terraforming_pressure' in bio.strategic_tags
    assert 'Industrial' in geo.modifier_economies
    assert 'Extraction' in geo.modifier_economies


def test_icy_and_hmc_profiles_do_not_use_old_refinery_guess():
    icy = profile_body(body(subtype='Icy body'))
    hmc = profile_body(body(subtype='High metal content body'))

    assert icy.base_economies == ['Industrial']
    assert hmc.base_economies == ['Extraction']
    assert 'Refinery' not in hmc.base_economies


def test_agriculture_terraforming_target_does_not_fake_industrial():
    target = get_target_profile('agriculture_terraforming')

    assert target.primary_economies == ['Agriculture']
    assert 'terraforming_candidate' in target.strategic_tags
    assert 'Industrial' in target.avoid_dominant
    assert 'Industrial' not in target.expected_economies


def test_unsupported_archetype_has_no_silent_fallback():
    target = get_target_profile('unknown_future_archetype')

    assert not target.supported
    assert target.expected_economies == []
    assert target.warning == 'Recommended build rules are not implemented for this archetype yet.'


def test_extraction_refinery_does_not_pick_elw_over_hmc_or_ringed_body():
    target = get_target_profile('extraction_refinery')
    candidates = select_body_candidates('extraction_refinery', target, [
        body(body_id=1, body_name='ELW', subtype='Earth-like world'),
        body(body_id=2, body_name='HMC', subtype='High metal content body'),
        body(body_id=3, body_name='Ringed Rocky', subtype='Rocky body', is_ringed=True),
    ])

    assert candidates
    assert candidates[0].body_name in {'HMC', 'Ringed Rocky'}
    assert candidates[0].body_name != 'ELW'


def test_hitech_tourism_can_prefer_elw_ammonia_or_water_world():
    target = get_target_profile('hitech_tourism')
    candidates = select_body_candidates('hitech_tourism', target, [
        body(body_id=1, body_name='Plain Rocky', subtype='Rocky body'),
        body(body_id=2, body_name='ELW', subtype='Earth-like world'),
        body(body_id=3, body_name='Ammonia', subtype='Ammonia world'),
    ])

    assert candidates[0].body_name in {'ELW', 'Ammonia'}


def test_expansion_capital_prefers_slot_confidence_and_diversity():
    target = get_target_profile('expansion_capital')
    candidates = select_body_candidates('expansion_capital', target, [
        body(body_id=1, body_name='Plain Rocky', subtype='Rocky body', confidence=0.4),
        body(body_id=2, body_name='Mixed ELW', subtype='Earth-like world', confidence=0.9),
    ], slot_confidence=0.85, total_slots=12)

    assert candidates[0].body_name == 'Mixed ELW'
