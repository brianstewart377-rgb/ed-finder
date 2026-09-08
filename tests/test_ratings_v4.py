from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.ratings_v4 import (
    BodyFact,
    Opportunity,
    SystemFacts,
    local_opportunity_score,
    opportunities_from_facts,
    rate_all,
    rate_economy,
    rate_system_facts,
)


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


def body(candidate_id: str, body_class: str, **overrides) -> BodyFact:
    values = {
        'candidate_id': candidate_id,
        'body_class': body_class,
        'rings': False,
        'biologicals': False,
        'geologicals': False,
        'volcanism': False,
        'terraformable': False,
        'tidally_locked': False,
        'completeness': 1.0,
        'confidence': 1.0,
    }
    values.update(overrides)
    return BodyFact(**values)


def rating(facts: SystemFacts, economy: str):
    return rate_system_facts(facts)[economy]


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


# F1 — Pure Rocky Refinery specialist
def test_f1_pure_rocky_refinery_specialist():
    facts = SystemFacts(
        bodies=tuple(body(f'r{i}', 'Rocky body') for i in range(4)),
        reserve_level='Pristine',
    )
    ratings = rate_system_facts(facts)
    assert ratings['Refinery'].potential_score >= 80
    assert ratings['Refinery'].specialisation_quality >= 95
    assert ratings['Extraction'].potential_score == 0
    assert ratings['Industrial'].potential_score == 0


# F2 — Mixed Rocky contamination
def test_f2_mixed_rocky_changes_specialisation_more_than_refinery_potential():
    clean = SystemFacts(bodies=(body('r', 'Rocky body'),), reserve_level='Pristine')
    mixed = SystemFacts(bodies=(body('r', 'Rocky body', rings=True, biologicals=True, geologicals=True),), reserve_level='Pristine')
    clean_ref = rating(clean, 'Refinery')
    mixed_ratings = rate_system_facts(mixed)
    mixed_ref = mixed_ratings['Refinery']
    assert clean_ref.potential_score == mixed_ref.potential_score
    assert clean_ref.specialisation_quality > mixed_ref.specialisation_quality
    assert mixed_ratings['Extraction'].potential_score > 0
    assert mixed_ratings['Industrial'].potential_score > 0
    assert mixed_ratings['Agriculture'].potential_score > 0


# F3 — Pure Icy Industrial
def test_f3_pure_icy_industrial_specialist():
    facts = SystemFacts(
        bodies=tuple(body(f'i{i}', 'Icy body') for i in range(4)),
        reserve_level='Pristine',
    )
    ratings = rate_system_facts(facts)
    assert ratings['Industrial'].potential_score >= 80
    assert ratings['Industrial'].specialisation_quality >= 95
    assert ratings['Refinery'].potential_score == 0
    assert ratings['Extraction'].potential_score == 0


# F4 — Rocky-Ice dual Industrial / Refinery
def test_f4_rocky_ice_dual_economies_are_not_attenuated():
    facts = SystemFacts(bodies=tuple(body(f'ri{i}', 'Rocky ice body') for i in range(3)))
    ratings = rate_system_facts(facts)
    assert ratings['Industrial'].potential_score == ratings['Refinery'].potential_score
    assert ratings['Industrial'].potential_score >= 70
    assert ratings['Industrial'].specialisation_quality >= 90
    assert ratings['Refinery'].specialisation_quality >= 90


# F5 — Reserve ladder
def test_f5_extraction_reserve_ladder_orders_pristine_average_depleted():
    b = (body('hmc', 'High metal content world'),)
    pristine = rating(SystemFacts(bodies=b, reserve_level='Pristine'), 'Extraction')
    average = rating(SystemFacts(bodies=b, reserve_level='Common'), 'Extraction')
    depleted = rating(SystemFacts(bodies=b, reserve_level='Depleted'), 'Extraction')
    assert pristine.potential_score > average.potential_score > depleted.potential_score


# F6 — Geological + volcanic Extraction
def test_f6_geologicals_and_volcanism_are_distinct_and_composable():
    geo = rating(SystemFacts(bodies=(body('hmc', 'High metal content world', geologicals=True),)), 'Extraction')
    volcanic = rating(SystemFacts(bodies=(body('hmc', 'High metal content world', volcanism=True),)), 'Extraction')
    both = rate_system_facts(SystemFacts(bodies=(body('hmc', 'High metal content world', geologicals=True, volcanism=True),)))
    assert geo.local_scores[0] == 85
    assert volcanic.local_scores[0] == 85
    assert both['Extraction'].local_scores[0] == 95
    assert both['Industrial'].potential_score > 0
    assert both['Extraction'].specialisation_quality < 100


# F7 — Water World Agriculture / Tourism
def test_f7_four_water_worlds_are_exceptional_agriculture_tourism():
    facts = SystemFacts(bodies=tuple(body(f'ww{i}', 'Water world') for i in range(4)))
    ratings = rate_system_facts(facts)
    assert 80 <= ratings['Agriculture'].potential_score <= 90
    assert ratings['Tourism'].potential_score == ratings['Agriculture'].potential_score
    assert ratings['Military'].potential_score == 0
    assert ratings['Agriculture'].specialisation_quality >= 95
    assert ratings['Tourism'].specialisation_quality >= 95


# F8 — ELW mixed economy
def test_f8_elw_does_not_flatten_military_with_better_supported_economies():
    facts = SystemFacts(bodies=(body('elw', 'Earth-like world'),))
    ratings = rate_system_facts(facts)
    assert ratings['Agriculture'].potential_score > ratings['Military'].potential_score
    assert ratings['Tourism'].potential_score > ratings['Military'].potential_score
    assert ratings['HighTech'].potential_score > ratings['Military'].potential_score


# F9 — Ammonia High-Tech / Tourism
def test_f9_ammonia_world_is_hightech_tourism_not_agriculture_military():
    ratings = rate_system_facts(SystemFacts(bodies=(body('amm', 'Ammonia world'),)))
    assert ratings['HighTech'].potential_score >= 65
    assert ratings['Tourism'].potential_score >= 65
    assert ratings['Agriculture'].potential_score == 0
    assert ratings['Military'].potential_score == 0


# F10 — Exotic-star High-Tech / Tourism
def test_f10_exotic_star_favours_hightech_tourism_not_military():
    facts = SystemFacts(
        bodies=(body('n', 'Neutron star'),),
        exotic_star='Neutron star',
    )
    ratings = rate_system_facts(facts)
    assert ratings['Tourism'].potential_score > ratings['HighTech'].potential_score
    assert ratings['HighTech'].potential_score > 0
    assert ratings['Military'].potential_score == 0


# F11 — Main-sequence Military
def test_f11_main_sequence_star_is_clean_military_fixture():
    ratings = rate_system_facts(SystemFacts(bodies=(body('star', 'Main sequence star'),)))
    assert ratings['Military'].potential_score > 0
    assert ratings['Military'].specialisation_quality == 100
    assert all(
        ratings[economy].potential_score == 0
        for economy in ('Agriculture', 'Refinery', 'Industrial', 'HighTech', 'Tourism', 'Extraction')
    )


# F12 — Diminishing returns
def test_f12_depth_caps_after_four_candidates():
    one = rate_economy('Refinery', [op('Refinery', '1', strong_positive_rules=('x', 'y', 'z'))])
    two = rate_economy('Refinery', [op('Refinery', str(i), strong_positive_rules=('x', 'y', 'z')) for i in range(2)])
    three = rate_economy('Refinery', [op('Refinery', str(i), strong_positive_rules=('x', 'y', 'z')) for i in range(3)])
    four = rate_economy('Refinery', [op('Refinery', str(i), strong_positive_rules=('x', 'y', 'z')) for i in range(4)])
    twenty = rate_economy('Refinery', [op('Refinery', str(i), strong_positive_rules=('x', 'y', 'z')) for i in range(20)])
    assert one.potential_score == 82
    assert two.potential_score == 93
    assert three.potential_score == 98
    assert four.potential_score == 100
    assert twenty.potential_score == 100


# F13 — One excellent vs many mediocre
def test_f13_one_excellent_candidate_beats_many_mediocre_candidates():
    excellent = rate_economy('Tourism', [op('Tourism', 'excellent', strong_positive_rules=('a', 'b', 'c'))])
    mediocre = rate_economy('Tourism', [op('Tourism', str(i), native=False, modifier=True) for i in range(10)])
    assert excellent.potential_score > mediocre.potential_score


# F14 — Unknown != absent
def test_f14_unknown_evidence_reduces_completeness_not_known_score():
    complete = rate_economy('Industrial', [op('Industrial', 'icy')])
    partial = rate_economy('Industrial', [op('Industrial', 'icy', completeness=0.5, confidence=1.0)])
    assert complete.potential_score == partial.potential_score
    assert complete.evidence_completeness > partial.evidence_completeness
    assert partial.confidence <= 0.75


# F15 — Top-two protection / no global attenuation
def test_f15_multiple_strong_economies_remain_independent():
    opportunities = [
        op('Agriculture', 'ww', strong_positive_rules=('water-world-agriculture',), competing_economies=('Tourism',)),
        op('Tourism', 'ww', strong_positive_rules=('water-world-tourism',), competing_economies=('Agriculture',)),
        op('HighTech', 'gg'),
    ]
    ratings = rate_all(opportunities)
    assert ratings['Agriculture'].local_scores[0] == 85
    assert ratings['Tourism'].local_scores[0] == 85
    assert ratings['HighTech'].local_scores[0] == 75
    assert ratings['Agriculture'].specialisation_quality >= 90
    assert ratings['Tourism'].specialisation_quality >= 90


# F16 — Terraformability amplifier only
def test_f16_terraformability_cannot_create_agriculture_without_eligibility():
    non_agri = rate_system_facts(SystemFacts(bodies=(body('hmc', 'High metal content world', terraformable=True),)))
    assert non_agri['Agriculture'].potential_score == 0

    eligible_plain = rating(SystemFacts(bodies=(body('ww', 'Water world'),)), 'Agriculture')
    eligible_tf = rating(SystemFacts(bodies=(body('ww', 'Water world', terraformable=True),)), 'Agriculture')
    assert eligible_tf.potential_score > eligible_plain.potential_score


# F17 — geologicals vs volcanism distinction
def test_f17_geologicals_can_create_extraction_but_volcanism_cannot():
    rocky_geo = rate_system_facts(SystemFacts(bodies=(body('rock', 'Rocky body', geologicals=True),)))
    rocky_volc = rate_system_facts(SystemFacts(bodies=(body('rock', 'Rocky body', volcanism=True),)))
    assert rocky_geo['Extraction'].potential_score > 0
    assert rocky_geo['Industrial'].potential_score > 0
    assert rocky_volc['Extraction'].potential_score == 0


# F18 — absolute score stability
def test_f18_unrelated_catalogue_population_cannot_change_score():
    base = SystemFacts(bodies=(body('ww', 'Water world'),))
    same_relevant_facts_with_irrelevant_bodies = SystemFacts(bodies=(
        body('ww', 'Water world'),
        body('unknown-1', 'Unknown body'),
        body('unknown-2', 'Unknown body'),
    ))
    assert rate_system_facts(base)['Tourism'].potential_score == rate_system_facts(same_relevant_facts_with_irrelevant_bodies)['Tourism'].potential_score


def test_invalid_economy_rejected():
    try:
        rate_economy('Terraforming', [])
    except ValueError as exc:
        assert 'unknown economy' in str(exc)
    else:
        raise AssertionError('expected ValueError')


def test_opportunity_adapter_records_competing_economies_on_elw():
    ops = opportunities_from_facts(SystemFacts(bodies=(body('elw', 'Earth-like world'),)))
    agriculture = next(item for item in ops if item.economy == 'Agriculture')
    assert set(agriculture.competing_economies) == {'HighTech', 'Military', 'Tourism'}
