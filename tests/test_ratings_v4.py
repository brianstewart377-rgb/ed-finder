from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.ratings_v4 import Opportunity, local_opportunity_score, rate_all, rate_economy


def op(economy: str, candidate_id: str, **overrides) -> Opportunity:
    values = {
        'economy': economy,
        'candidate_id': candidate_id,
        'native': True,
        'modifier': False,
        'strong_positive_rules': (),
        'strong_negative_rules': (),
        'competing_economies': (),
        'preferred_specialisation': False,
        'completeness': 1.0,
        'confidence': 1.0,
        'contributors': (),
    }
    values.update(overrides)
    return Opportunity(**values)


def test_native_and_modifier_bases_are_ordered():
    native = local_opportunity_score(op('Extraction', 'a'))
    modifier = local_opportunity_score(op('Extraction', 'b', native=False, modifier=True))
    both = local_opportunity_score(op('Extraction', 'c', modifier=True))
    assert modifier < native < both


def test_strong_link_rules_deduplicate_and_cap():
    one = local_opportunity_score(op('Tourism', 'a', strong_positive_rules=('ww',)))
    duplicate = local_opportunity_score(op('Tourism', 'a', strong_positive_rules=('ww', 'ww')))
    many = local_opportunity_score(op('Tourism', 'a', strong_positive_rules=('a', 'b', 'c', 'd')))
    assert one == duplicate
    assert many == 100


def test_four_water_world_style_depth_is_exceptional_not_body_count_infinite():
    opportunities = [
        op('Agriculture', f'ww-{i}', strong_positive_rules=('water-world',))
        for i in range(4)
    ]
    rating = rate_economy('Agriculture', opportunities)
    assert 80 <= rating.potential_score <= 90
    assert rating.local_scores == (85, 85, 85, 85)


def test_more_than_four_candidates_do_not_inflate_potential():
    four = rate_economy('Refinery', [op('Refinery', str(i)) for i in range(4)])
    twenty = rate_economy('Refinery', [op('Refinery', str(i)) for i in range(20)])
    assert four.potential_score == twenty.potential_score


def test_mixed_economy_pressure_hits_specialisation_not_potential():
    clean = rate_economy('Extraction', [op('Extraction', 'clean', strong_positive_rules=('pristine',))])
    mixed = rate_economy('Extraction', [op(
        'Extraction', 'mixed', strong_positive_rules=('pristine',),
        competing_economies=('Industrial',),
    )])
    assert clean.potential_score == mixed.potential_score
    assert clean.specialisation_quality > mixed.specialisation_quality


def test_top_two_style_single_competitor_is_modest_penalty():
    rating = rate_economy('Tourism', [op(
        'Tourism', 'ww', strong_positive_rules=('water-world',),
        competing_economies=('Agriculture',), preferred_specialisation=True,
    )])
    assert rating.specialisation_quality >= 95


def test_unknown_evidence_reduces_completeness_not_known_score():
    complete = rate_economy('Industrial', [op('Industrial', 'icy')])
    partial = rate_economy('Industrial', [op('Industrial', 'icy', completeness=0.5, confidence=1.0)])
    assert complete.potential_score == partial.potential_score
    assert complete.evidence_completeness > partial.evidence_completeness
    assert partial.confidence <= 0.75


def test_elw_can_support_multiple_raw_economies_without_attenuation():
    opportunities = [
        op('Agriculture', 'elw', strong_positive_rules=('elw-agri',)),
        op('Tourism', 'elw', strong_positive_rules=('elw-tourism',)),
        op('HighTech', 'elw', strong_positive_rules=('elw-hightech',)),
        op('Military', 'elw'),
    ]
    ratings = rate_all(opportunities)
    assert ratings['Agriculture'].potential_score > ratings['Military'].potential_score
    assert ratings['Tourism'].potential_score > ratings['Military'].potential_score
    assert ratings['HighTech'].potential_score > ratings['Military'].potential_score


def test_geologicals_and_volcanism_can_be_distinct_rules():
    geological = op('Extraction', 'hmc', modifier=True, strong_positive_rules=())
    volcanic = op('Extraction', 'hmc', strong_positive_rules=('volcanism',))
    both = op('Extraction', 'hmc', modifier=True, strong_positive_rules=('volcanism',))
    assert local_opportunity_score(geological) == 85
    assert local_opportunity_score(volcanic) == 85
    assert local_opportunity_score(both) == 95


def test_invalid_economy_rejected():
    try:
        rate_economy('Terraforming', [])
    except ValueError as exc:
        assert 'unknown economy' in str(exc)
    else:
        raise AssertionError('expected ValueError')
