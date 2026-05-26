from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.colonisation_rules import get_target_profile, profile_body


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


def test_water_world_profile_supports_tourism_and_agriculture():
    profile = profile_body(body(subtype='Water world'))

    assert profile.base_economies == ['Tourism', 'Agriculture']


def test_ammonia_profile_keeps_hightech_as_supporting_modifier():
    profile = profile_body(body(subtype='Ammonia world'))

    assert profile.base_economies == ['Tourism']
    assert profile.modifier_economies == ['HighTech']
    assert 'exotic' in profile.strategic_tags
    assert any('supporting' in caveat for caveat in profile.caveats)


def test_hmc_profile_uses_extraction_and_observed_modifiers():
    clean = profile_body(body(subtype='High metal content body'))
    geo = profile_body(body(subtype='High metal content body', has_geo=True, geo_signal_count=2))
    bio = profile_body(body(subtype='High metal content body', has_bio=True, bio_signal_count=1))

    assert clean.base_economies == ['Extraction']
    assert 'Refinery' not in clean.base_economies
    assert geo.modifier_economies == ['Industrial']
    assert bio.modifier_economies == ['Agriculture']
    assert 'terraforming_pressure' in bio.strategic_tags


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


def test_ring_like_subtype_without_evidence_is_not_ringed():
    profile = profile_body(body(subtype='Ringed-looking rocky body', is_ringed=None))

    assert 'ringed' not in profile.strategic_tags
    assert 'Extraction' not in profile.modifier_economies


def test_icy_profile_gives_industrial():
    icy = profile_body(body(subtype='Icy body'))

    assert icy.base_economies == ['Industrial']


def test_rocky_ice_profile_gives_industrial_and_refinery():
    profile = profile_body(body(subtype='Rocky ice body'))

    assert profile.base_economies == ['Industrial', 'Refinery']


def test_gas_giant_profile_gives_hightech_and_industrial():
    profile = profile_body(body(subtype='Class I gas giant'))

    assert profile.base_economies == ['HighTech', 'Industrial']


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
