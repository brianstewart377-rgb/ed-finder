from __future__ import annotations

from dataclasses import asdict, replace
from itertools import permutations
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.ratings_v4 import (
    BodyFact, Opportunity, REFINERY_GROUND_RULE, SpecialisationConstraint,
    SystemFacts, candidate_specialisation, rate_economy, rate_system_facts,
)


def refinery(candidate_id='rocky', ground=None, competitors=()):
    return Opportunity(
        'Refinery', candidate_id, native=True, competing_economies=competitors,
        specialisation_constraints=(SpecialisationConstraint(
            REFINERY_GROUND_RULE, ground, 'usable_ground_opportunity',
            confidence=0.9, provenance='test:ground-survey',
        ),),
    )


@pytest.mark.parametrize(('ground', 'quality', 'bounds'), [
    (True, 100, (100, 100)),
    (False, 0, (0, 0)),
    (None, None, (0, 100)),
])
def test_ground_constraint_is_three_state_and_never_changes_raw_potential(ground, quality, bounds):
    candidate = refinery(ground=ground)
    rating = rate_economy('Refinery', [candidate])
    assert rating.potential_score == 62
    assert rating.local_scores == (75,)
    assert rating.evidence_completeness == rating.confidence == 1
    assert candidate_specialisation(candidate) == rating.specialisation_quality == quality
    assert (rating.specialisation_quality_min, rating.specialisation_quality_max) == bounds
    assert rating.best_candidate_id == 'rocky'
    assert rating.best_specialisation_candidate_id == ('rocky' if ground is True else None)


def test_omitted_refinery_constraint_cannot_claim_verified_quality():
    rating = rate_economy('Refinery', [Opportunity('Refinery', 'rocky', native=True)])
    assert rating.specialisation_quality is None
    constraint = rating.specialisation_candidates[0].constraints[0]
    assert constraint.rule_id == REFINERY_GROUND_RULE
    assert constraint.satisfied is None


def test_default_body_facts_keep_ground_unknown():
    rating = rate_system_facts(SystemFacts(bodies=(BodyFact('rocky', 'Rocky body'),)))['Refinery']
    assert rating.potential_score > 0
    assert rating.specialisation_quality is None
    assert rating.specialisation_quality_max == 100


@pytest.mark.parametrize('ground', [True, False, None])
def test_facts_adapter_keeps_ground_evidence_out_of_raw_fields(ground):
    body = BodyFact(
        'ri', 'Rocky Ice world', rings=False, biologicals=False, geologicals=False,
        volcanism=False, terraformable=False, tidally_locked=False,
        feature_confidence={'usable_ground_opportunity': 0.6},
        feature_provenance={'usable_ground_opportunity': 'test:surface-evidence'},
    )
    original = rate_system_facts(SystemFacts(bodies=(body,), reserve_level='Pristine'))
    ratings = rate_system_facts(SystemFacts(
        bodies=(replace(body, usable_ground_opportunity=ground),), reserve_level='Pristine',
    ))
    for economy in ratings:
        actual, previous = ratings[economy], original[economy]
        if economy != 'Refinery':
            assert actual == previous
        else:
            for field in ('potential_score', 'local_scores', 'best_candidate_id',
                          'evidence_completeness', 'confidence', 'contributions'):
                assert getattr(actual, field) == getattr(previous, field)
    constraint = ratings['Refinery'].specialisation_candidates[0].constraints[0]
    assert constraint.satisfied is ground
    assert constraint.confidence == 0.6
    assert constraint.provenance == 'test:surface-evidence'


def test_best_raw_site_and_best_usable_specialisation_site_can_differ():
    raw_best = replace(refinery('raw-best', False), modifier=True)
    usable = refinery('usable', True, ('Industrial',))
    rating = rate_economy('Refinery', [raw_best, usable])
    assert rating.best_candidate_id == 'raw-best'
    assert rating.best_specialisation_candidate_id == 'usable'
    assert rating.specialisation_quality == 92
    assert rating.specialisation_quality_min == rating.specialisation_quality_max == 92


def test_unknown_better_site_keeps_system_quality_unresolved():
    rating = rate_economy('Refinery', [
        refinery('usable-mixed', True, ('Industrial',)), refinery('unknown-clean'),
    ])
    assert rating.specialisation_quality is None
    assert (rating.specialisation_quality_min, rating.specialisation_quality_max) == (92, 100)
    assert rating.best_specialisation_candidate_id is None


def test_proven_perfect_site_is_not_downgraded_by_unknown_other_sites():
    rating = rate_economy('Refinery', [refinery('usable', True), refinery('unknown')])
    assert rating.specialisation_quality == 100
    assert rating.best_specialisation_candidate_id == 'usable'
    assert any(c.satisfied is None for site in rating.specialisation_candidates for c in site.constraints)


@pytest.mark.parametrize('ground', [False, None])
def test_nonconfirmed_sites_never_supply_confirmed_clean_depth(ground):
    rating = rate_economy('Refinery', [
        refinery('usable', True, ('Industrial',)),
        *(refinery(str(i), ground) for i in range(6)),
    ])
    assert rating.specialisation_quality_min == 92
    assert rating.specialisation_quality_max == (100 if ground is None else 92)


def test_specialisation_checks_usable_candidates_beyond_the_raw_top_four():
    blocked = [replace(refinery(str(i), False), modifier=True) for i in range(4)]
    rating = rate_economy('Refinery', [*blocked, refinery('fifth', True)])
    assert 'fifth' not in {contribution.candidate_id for contribution in rating.contributions}
    assert rating.best_specialisation_candidate_id == 'fifth'
    assert rating.specialisation_quality == 100
    assert len(rating.specialisation_candidates) == 5


def test_confirmed_constraint_failure_dominates_another_unknown_requirement():
    candidate = refinery(ground=False)
    candidate = replace(candidate, specialisation_constraints=candidate.specialisation_constraints + (
        SpecialisationConstraint('additional-test-requirement', None, 'test_fact'),
    ))
    assert candidate_specialisation(candidate) == 0


def test_constraints_cannot_create_specialisation_without_inheritance():
    rating = rate_economy('Refinery', [replace(refinery(ground=True), native=False)])
    assert rating.potential_score == rating.specialisation_quality == 0
    assert rating.best_specialisation_candidate_id is None
    assert rating.specialisation_candidates == ()


def test_constraint_explanation_preserves_state_provenance_and_local_quality():
    rating = rate_economy('Refinery', [refinery(ground=False)])
    site = rating.specialisation_candidates[0]
    assert site.intrinsic_quality == 100
    assert site.quality == site.minimum_quality == site.maximum_quality == 0
    assert site.constraints[0].provenance == 'test:ground-survey'
    assert any(REFINERY_GROUND_RULE in line and 'blocked' in line for line in rating.explanation)


def test_unknown_quality_serialises_as_null_with_explicit_bounds():
    payload = json.loads(json.dumps(asdict(rate_economy('Refinery', [refinery()]))))
    assert payload['specialisation_quality'] is None
    assert payload['specialisation_quality_min'] == 0
    assert payload['specialisation_quality_max'] == 100
    assert payload['specialisation_candidates'][0]['constraints'][0]['satisfied'] is None


def test_constraint_results_and_traces_are_stable_across_input_order():
    candidates = [refinery('unknown'), refinery('known', True), refinery('blocked', False)]
    expected = rate_economy('Refinery', candidates)
    for ordering in permutations(candidates):
        assert rate_economy('Refinery', ordering) == expected


def test_exact_constraint_duplicates_are_deduplicated_and_conflicts_rejected():
    candidate = refinery(ground=True)
    duplicate = replace(candidate, specialisation_constraints=candidate.specialisation_constraints * 2)
    assert rate_economy('Refinery', [duplicate]) == rate_economy('Refinery', [candidate])
    conflicting = replace(candidate, specialisation_constraints=candidate.specialisation_constraints + (
        replace(candidate.specialisation_constraints[0], satisfied=False),
    ))
    with pytest.raises(ValueError, match='conflicting specialisation constraint'):
        rate_economy('Refinery', [conflicting])


@pytest.mark.parametrize('bad', ['unknown', 'false', 0, 1])
def test_constraint_state_rejects_values_other_than_bool_or_none(bad):
    with pytest.raises(ValueError, match='constraint state'):
        rate_economy('Refinery', [refinery(ground=bad)])


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -0.1, 1.1])
def test_constraint_confidence_is_validated(bad):
    candidate = refinery(ground=True)
    with pytest.raises(ValueError, match='evidence value'):
        rate_economy('Refinery', [replace(candidate, specialisation_constraints=(
            replace(candidate.specialisation_constraints[0], confidence=bad),
        ))])
