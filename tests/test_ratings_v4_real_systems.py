from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from domain.ratings_v4 import BodyFact, SCORER_VERSION, SystemFacts, rate_system_facts  # noqa: E402


FIXTURE_PATH = ROOT / 'tests' / 'fixtures' / 'ratings_v4_real_systems.json'
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))
CASES = FIXTURE['systems']
CODES = FIXTURE['codes']


def _facts(case: dict) -> SystemFacts:
    bodies = []
    for index, (code, flags) in enumerate(case['b']):
        bodies.append(
            BodyFact(
                candidate_id=f"{case['id']}:{index}",
                body_class=CODES[code],
                rings=bool(flags & 1),
                biologicals=bool(flags & 2),
                geologicals=bool(flags & 4),
                volcanism=bool(flags & 8),
                terraformable=bool(flags & 16),
                tidally_locked=bool(flags & 32),
            )
        )
    return SystemFacts(
        bodies=tuple(bodies),
        reserve_level=case['res'],
        exotic_star=case['ex'],
        body_inventory_complete=True,
    )


def test_real_system_baseline_uses_the_current_candidate_version() -> None:
    assert FIXTURE['scorer'] == SCORER_VERSION


@pytest.mark.parametrize('case', CASES, ids=[case['n'] for case in CASES])
def test_v4_real_system_frozen_potential_scores(case: dict) -> None:
    ratings = rate_system_facts(_facts(case))
    actual = {economy: rating.potential_score for economy, rating in ratings.items()}
    assert actual == case['p']


@pytest.mark.parametrize('case', CASES, ids=[case['n'] for case in CASES])
def test_v4_real_system_frozen_specialisation_scores(case: dict) -> None:
    ratings = rate_system_facts(_facts(case))
    actual = {economy: rating.specialisation_quality for economy, rating in ratings.items()}
    assert actual == case['s']


@pytest.mark.parametrize('case', CASES, ids=[case['n'] for case in CASES])
def test_real_system_refinery_constraints_preserve_missing_ground_evidence(case: dict) -> None:
    rating = rate_system_facts(_facts(case))['Refinery']
    assert rating.specialisation_quality_min == 0
    assert rating.specialisation_quality_max == case['s_candidate_2']['Refinery']
    if case['s_candidate_2']['Refinery']:
        assert rating.specialisation_quality is None
        assert rating.best_specialisation_candidate_id is None
        assert all(
            constraint.satisfied is None
            for candidate in rating.specialisation_candidates
            for constraint in candidate.constraints
        )
    else:
        assert rating.specialisation_quality == 0
        assert rating.specialisation_candidates == ()


def _case(name: str) -> dict:
    return next(case for case in CASES if case['n'] == name)


def test_wregoe_remains_a_mining_refining_regression_anchor() -> None:
    ratings = rate_system_facts(_facts(_case('Wregoe ZN-X c28-28')))
    assert ratings['Extraction'].potential_score == 100
    assert ratings['Industrial'].potential_score >= 90
    assert ratings['Refinery'].potential_score >= 85


def test_praea_four_water_worlds_are_exceptional_without_hiding_resource_strength() -> None:
    case = _case('Praea Euq WV-W b2-2')
    assert sum(code == 'ww' for code, _ in case['b']) == 4

    ratings = rate_system_facts(_facts(case))
    assert ratings['Agriculture'].potential_score >= 80
    assert ratings['Tourism'].potential_score >= 85
    assert abs(
        ratings['Agriculture'].potential_score - ratings['Tourism'].potential_score
    ) <= 2
    assert ratings['Industrial'].potential_score > ratings['Tourism'].potential_score
    assert ratings['Extraction'].potential_score > ratings['Agriculture'].potential_score


def test_achenar_elw_economies_outrank_military() -> None:
    ratings = rate_system_facts(_facts(_case('Achenar')))
    military = ratings['Military'].potential_score
    assert ratings['Agriculture'].potential_score > military
    assert ratings['HighTech'].potential_score > military
    assert ratings['Tourism'].potential_score > military


def test_alioth_depleted_reserves_do_not_crush_habitable_world_economies() -> None:
    case = _case('Alioth')
    assert case['res'] == 'Depleted'
    ratings = rate_system_facts(_facts(case))
    assert ratings['Agriculture'].potential_score >= 90
    assert ratings['Tourism'].potential_score >= 80
    assert ratings['Refinery'].potential_score < ratings['Tourism'].potential_score
    assert ratings['Industrial'].potential_score < ratings['Tourism'].potential_score


def test_maia_keeps_exotic_and_resource_evidence_separate() -> None:
    case = _case('Maia')
    assert case['ex'] == 'Black hole'
    ratings = rate_system_facts(_facts(case))
    assert ratings['HighTech'].potential_score > 0
    assert ratings['Tourism'].potential_score > 0
    assert ratings['Military'].potential_score > 0
    assert ratings['Extraction'].potential_score > ratings['Tourism'].potential_score


def test_borann_demonstrates_resource_depth_without_exceeding_one_hundred() -> None:
    ratings = rate_system_facts(_facts(_case('Borann')))
    assert ratings['Industrial'].potential_score >= 90
    assert ratings['Extraction'].potential_score >= 90
    assert max(rating.potential_score for rating in ratings.values()) <= 100


def test_hd_38179_separates_extraction_from_military() -> None:
    ratings = rate_system_facts(_facts(_case('HD 38179')))
    assert ratings['Extraction'].potential_score == 100
    assert ratings['Military'].potential_score >= 70
    assert ratings['Extraction'].potential_score > ratings['Military'].potential_score


def test_col_285_keeps_industrial_and_refinery_independent() -> None:
    ratings = rate_system_facts(_facts(_case('Col 285 Sector BW-U c3-5')))
    assert ratings['Industrial'].potential_score >= 85
    assert ratings['Refinery'].potential_score >= 85
    assert ratings['Industrial'].potential_score == ratings['Refinery'].potential_score


def test_smojoo_is_genuinely_multirole_without_an_overall_score() -> None:
    ratings = rate_system_facts(_facts(_case('Smojoo ZE-R d4-109')))
    strong = [
        rating.potential_score
        for rating in ratings.values()
        if rating.potential_score >= 75
    ]
    assert len(strong) == 7


def test_thaile_keeps_exotic_habitable_and_resource_evidence_independent() -> None:
    ratings = rate_system_facts(_facts(_case('Thaile HW-V e2-7')))
    assert ratings['Tourism'].potential_score >= 95
    assert ratings['HighTech'].potential_score >= 80
    assert ratings['Agriculture'].potential_score >= 90
    assert ratings['Extraction'].potential_score >= 95


def test_deriv_dar_proves_arrival_distance_is_not_a_raw_economy_penalty() -> None:
    case = _case('Deriv-Dar')
    assert case['max_ls'] > 100_000
    ratings = rate_system_facts(_facts(case))
    assert ratings['Agriculture'].potential_score >= 90
    assert ratings['Tourism'].potential_score >= 80
