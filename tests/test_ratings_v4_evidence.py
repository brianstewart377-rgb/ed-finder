from __future__ import annotations

from dataclasses import replace
from itertools import permutations
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.ratings_v4 import (
    BodyFact, Opportunity, SystemFacts, candidate_specialisation,
    opportunities_from_facts, rate_all, rate_economy, rate_system_facts,
)


def known_body(body_class='Water world', **overrides):
    return replace(BodyFact(
        'site', body_class, rings=False, biologicals=False, geologicals=False,
        volcanism=False, terraformable=False, tidally_locked=False,
    ), **overrides)


def facts_for(body, **overrides):
    return SystemFacts(bodies=(body,), body_inventory_complete=True, **overrides)


@pytest.mark.parametrize(('canonical', 'alias'), [
    ('High metal content world', 'High metal content body'),
    ('Rocky ice body', 'Rocky Ice world'),
    ('Earth-like world', 'Earthlike body'),
    ('Rocky ice body', '  ROCKY-ICE   WORLD  '),
])
def test_canonical_planet_aliases_have_identical_ratings(canonical, alias):
    assert rate_system_facts(facts_for(known_body(canonical))) == rate_system_facts(
        facts_for(known_body(alias))
    )


@pytest.mark.parametrize(('body_class', 'spectral', 'economies'), [
    ('G (White-Yellow) Star', None, {'Military'}),
    ('Star', 'K', {'Military'}),
    ('Star', 'G2', {'Military'}),
    ('L (Brown dwarf) Star', None, {'Military'}),
    ('Star', 'T', {'Military'}),
    ('White Dwarf (DA) Star', None, {'HighTech', 'Tourism'}),
    ('Star', 'DB', {'HighTech', 'Tourism'}),
    ('Star', 'DA3', {'HighTech', 'Tourism'}),
    ('Star', 'N', {'HighTech', 'Tourism'}),
    ('Star', 'H', {'HighTech', 'Tourism'}),
])
def test_stars_use_canonical_classification(body_class, spectral, economies):
    ratings = rate_system_facts(facts_for(known_body(body_class, spectral_class=spectral)))
    assert {economy for economy, rating in ratings.items() if rating.potential_score} == economies


def test_main_star_flag_does_not_guess_a_stellar_class():
    ratings = rate_system_facts(facts_for(known_body('Star', is_main_star=True)))
    assert ratings['Military'].potential_score == 0
    assert ratings['Military'].evidence_completeness < 1


@pytest.mark.parametrize('reserve', ['Pristine', 'Major', 'Common', 'Low', 'Depleted'])
@pytest.mark.parametrize(('body_class', 'economy'), [
    ('High metal content body', 'Extraction'), ('Icy body', 'Industrial'), ('Rocky body', 'Refinery'),
])
def test_raw_reserve_enums_match_display_values(reserve, body_class, economy):
    body = known_body(body_class)
    assert rate_system_facts(facts_for(body, reserve_level=reserve))[economy] == rate_system_facts(
        facts_for(body, reserve_level=f'{reserve}Resources')
    )[economy]


@pytest.mark.parametrize('reserve', [None, '', 'UnrecognisedResources'])
def test_missing_or_unrecognised_reserves_remain_unknown(reserve):
    body = known_body('High metal content body')
    unknown = rate_system_facts(facts_for(body, reserve_level=reserve))
    common = rate_system_facts(facts_for(body, reserve_level='Common'))
    assert unknown['Extraction'].potential_score == common['Extraction'].potential_score
    assert unknown['Extraction'].evidence_completeness < common['Extraction'].evidence_completeness == 1
    assert unknown['Extraction'].confidence < 1
    assert unknown['Agriculture'] == common['Agriculture']


@pytest.mark.parametrize(('body_class', 'field', 'economy'), [
    ('Water world', 'biologicals', 'Agriculture'),
    ('Water world', 'terraformable', 'Agriculture'),
    ('Water world', 'tidally_locked', 'Agriculture'),
    ('Ammonia world', 'geologicals', 'HighTech'),
    ('High metal content body', 'rings', 'Extraction'),
    ('High metal content body', 'volcanism', 'Extraction'),
])
def test_unknown_local_facts_reduce_coverage_without_inventing_penalties(body_class, field, economy):
    complete_body = known_body(body_class)
    complete = rate_system_facts(facts_for(complete_body, reserve_level='Common'))[economy]
    partial = rate_system_facts(facts_for(replace(complete_body, **{field: None}), reserve_level='Common'))[economy]
    assert partial.potential_score == complete.potential_score
    assert partial.evidence_completeness < complete.evidence_completeness == 1
    assert partial.confidence < complete.confidence
    assert any(field in line for line in partial.explanation if 'unknown evidence' in line)


def test_known_absence_is_distinct_from_missing_opportunity_evidence():
    known = rate_system_facts(facts_for(known_body('High metal content body')))['Agriculture']
    unknown = rate_system_facts(facts_for(known_body('High metal content body', biologicals=None)))['Agriculture']
    empty = rate_system_facts(SystemFacts(bodies=()))['Agriculture']
    assert known.potential_score == unknown.potential_score == empty.potential_score == 0
    assert known.best_candidate_id is unknown.best_candidate_id is empty.best_candidate_id is None
    assert known.evidence_completeness == known.confidence == 1
    assert empty.evidence_completeness < unknown.evidence_completeness < known.evidence_completeness
    assert known.specialisation_quality == unknown.specialisation_quality == 0


def test_inventory_coverage_must_be_explicit():
    body = known_body()
    complete = rate_system_facts(facts_for(body))['Agriculture']
    partial = rate_system_facts(SystemFacts(bodies=(body,)))['Agriculture']
    assert partial.potential_score == complete.potential_score
    assert partial.evidence_completeness < complete.evidence_completeness == 1


def test_feature_confidence_only_affects_economies_using_the_feature():
    body = known_body('Earth-like world', biologicals=True)
    trusted = rate_system_facts(facts_for(body))
    uncertain = rate_system_facts(facts_for(replace(
        body, feature_confidence={'biologicals': 0.2},
        feature_provenance={'biologicals': 'test:low-confidence-observation'},
    )))
    assert uncertain['Military'] == trusted['Military']
    for economy in ('Agriculture', 'HighTech', 'Tourism'):
        assert uncertain[economy].potential_score == trusted[economy].potential_score
        assert uncertain[economy].evidence_completeness == trusted[economy].evidence_completeness
        assert uncertain[economy].confidence < trusted[economy].confidence
        feature = next(f for f in uncertain[economy].contributions[0].evidence if f.feature_type == 'biologicals')
        assert feature.confidence == 0.2
        assert feature.provenance == 'test:low-confidence-observation'
        assert feature.value is True


def test_exotic_stars_are_derived_deduplicated_and_combined():
    neutron = known_body('Neutron star')
    inferred = rate_system_facts(facts_for(neutron))['Tourism']
    explicit = rate_system_facts(facts_for(neutron, exotic_star='Neutron star'))['Tourism']
    assert inferred == explicit
    multiple = rate_system_facts(SystemFacts(
        bodies=(neutron, known_body('Black hole', candidate_id='black-hole')),
        body_inventory_complete=True,
    ))['Tourism']
    assert set(multiple.contributions[0].positive_rules) == {
        'neutron star-system-tourism', 'black hole-system-tourism',
    }
    assert multiple.local_scores[0] > inferred.local_scores[0]


def test_stellar_source_confidence_follows_derived_system_modifiers():
    star = known_body('Star', spectral_class='N', candidate_id='star')
    world = known_body()
    trusted = rate_system_facts(SystemFacts(bodies=(star, world), body_inventory_complete=True))
    uncertain = rate_system_facts(SystemFacts(bodies=(replace(
        star, feature_confidence={'spectral_class': 0.1},
        feature_provenance={'spectral_class': 'test:uncertain-star'},
    ), world), body_inventory_complete=True))
    assert uncertain['Agriculture'].potential_score == trusted['Agriculture'].potential_score
    assert uncertain['Tourism'].potential_score == trusted['Tourism'].potential_score
    assert uncertain['Tourism'].confidence < trusted['Tourism'].confidence
    contribution = next(c for c in uncertain['Tourism'].contributions if c.candidate_id == 'site')
    feature = next(f for f in contribution.evidence if f.feature_type == 'exotic_star')
    assert feature.confidence == 0.1
    assert 'star:test:uncertain-star' in feature.provenance


def test_duplicate_candidates_cannot_create_system_depth():
    candidate = Opportunity('Refinery', 'same-site', native=True)
    assert rate_economy('Refinery', [candidate] * 4) == rate_economy('Refinery', [candidate])
    with pytest.raises(ValueError, match='conflicting duplicate candidate'):
        rate_economy('Refinery', [candidate, replace(candidate, modifier=True)])
    body = known_body('Neutron star')
    assert rate_system_facts(SystemFacts(bodies=(body,) * 4)) == rate_system_facts(SystemFacts(bodies=(body,)))


def test_ratings_are_deterministic_for_ties_and_input_order():
    candidates = [Opportunity('Military', key, native=True) for key in ('c', 'b', 'a')]
    expected = rate_economy('Military', candidates)
    assert expected.best_candidate_id == 'a'
    for ordering in permutations(candidates):
        assert rate_economy('Military', ordering) == expected


def test_ineligible_candidate_does_not_receive_specialisation_or_a_depth_slot():
    candidate = Opportunity('Agriculture', 'terraformable-only', strong_positive_rules=('terraformable',))
    rating = rate_economy('Agriculture', [candidate])
    assert candidate_specialisation(candidate) == rating.specialisation_quality == 0
    assert rating.potential_score == 0
    assert rating.best_candidate_id is None
    assert rating.local_scores == rating.contributions == ()
    assert rating.evidence_completeness == 1


def test_unobserved_candidates_outside_top_four_affect_coverage():
    candidates = [Opportunity('Industrial', str(i), native=True) for i in range(4)]
    complete = rate_economy('Industrial', candidates)
    partial = rate_economy('Industrial', candidates + [Opportunity('Industrial', 'unknown', completeness=0)])
    assert partial.potential_score == complete.potential_score
    assert partial.evidence_completeness < complete.evidence_completeness
    assert partial.confidence < complete.confidence


def test_every_weighted_site_and_capped_rule_is_auditable():
    candidates = [Opportunity(
        'Extraction', str(i), native=True,
        strong_positive_rules=('volcanism', 'reserve', 'third', 'reserve'),
        strong_negative_rules=('negative',), contributors=(f'source:{i}',),
    ) for i in range(5)]
    rating = rate_economy('Extraction', candidates)
    assert len(rating.contributions) == 4
    assert round(sum(c.local_score * c.system_weight for c in rating.contributions)) == rating.potential_score
    for contribution in rating.contributions:
        assert contribution.positive_adjustment == 25
        assert contribution.negative_adjustment == 10
        assert contribution.local_score == contribution.base_score + 25 - 10
        assert len(contribution.positive_rules) == 3
        assert f'source:{contribution.candidate_id}' in '\n'.join(rating.explanation)
    assert 'volcanism' in '\n'.join(rating.explanation)
    assert 'negative' in '\n'.join(rating.explanation)


def test_contaminated_depth_never_becomes_pure():
    bodies = tuple(known_body('Rocky Ice world', candidate_id=str(i), usable_ground_opportunity=True) for i in range(4))
    ratings = rate_system_facts(SystemFacts(bodies=bodies))
    assert ratings['Industrial'].potential_score == ratings['Refinery'].potential_score == 75
    assert ratings['Industrial'].specialisation_quality == ratings['Refinery'].specialisation_quality == 92


def test_water_world_is_a_preferred_tourism_site():
    opportunities = opportunities_from_facts(facts_for(known_body()))
    tourism = next(item for item in opportunities if item.economy == 'Tourism')
    assert tourism.preferred_specialisation
    assert candidate_specialisation(tourism) == 97


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -0.1, 1.1])
def test_invalid_evidence_values_are_rejected(bad):
    with pytest.raises(ValueError, match='evidence value'):
        rate_all([Opportunity('Military', 'a', native=True, confidence=bad)])
    with pytest.raises(ValueError, match='evidence value'):
        rate_system_facts(facts_for(known_body(feature_confidence={'biologicals': bad})))


def test_unknown_opportunity_economies_are_not_silently_discarded():
    with pytest.raises(ValueError, match='unknown economy'):
        rate_all([Opportunity('High Tech', 'typo', native=True)])
