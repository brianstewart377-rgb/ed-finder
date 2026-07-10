from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', str(Path.cwd() / 'test-local.log'))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from regional.regional_analysis import compute_regional_analysis, distance_ly, response_from_row
from regional.regional_roles import classify_regional_role
from regional.regional_scoring import archetype_regional_fit, regional_scores
from models import RegionalAnalysisResponse
from mechanics.versions import MECHANICS_VERSION


def system(id64: int, x: float, y: float, z: float, *, colonised: bool = False, population: int = 0):
    return {
        'id64': id64,
        'name': f'System {id64}',
        'x': x,
        'y': y,
        'z': z,
        'is_colonised': colonised,
        'is_being_colonised': False,
        'population': population,
    }


def test_distance_calculation_correct():
    assert distance_ly(system(1, 0, 0, 0), system(2, 3, 4, 12)) == 13


def test_nearest_and_density_counts():
    target = system(1, 0, 0, 0)
    neighbours = [
        system(2, 20, 0, 0, colonised=True),
        system(3, 40, 0, 0, colonised=True),
        system(4, 80, 0, 0, colonised=True),
        system(5, 150, 0, 0, colonised=True),
        system(6, 300, 0, 0, colonised=True),
    ]

    result = compute_regional_analysis(target, neighbours)

    assert result['nearest_colonised_system_id64'] == 2
    assert result['nearest_colonised_system_distance_ly'] == 20
    assert result['colonised_within_25ly'] == 1
    assert result['colonised_within_50ly'] == 2
    assert result['colonised_within_100ly'] == 3
    assert result['colonised_within_250ly'] == 4


def test_regional_role_classifications():
    assert classify_regional_role(nearest_distance_ly=180, within_25=0, within_50=0, within_100=0, within_250=1) == 'isolated_frontier'
    assert classify_regional_role(nearest_distance_ly=95, within_25=0, within_50=1, within_100=2, within_250=8) == 'frontier_hub'
    assert classify_regional_role(nearest_distance_ly=110, within_25=0, within_50=2, within_100=6, within_250=14) == 'bridge_system'
    assert classify_regional_role(nearest_distance_ly=10, within_25=3, within_50=8, within_100=20, within_250=40) == 'dense_developed_cluster'
    assert classify_regional_role(nearest_distance_ly=8, within_25=6, within_50=14, within_100=45, within_250=90) == 'oversaturated_region'
    assert classify_regional_role(nearest_distance_ly=60, within_25=0, within_50=1, within_100=3, within_250=9) == 'emerging_cluster'


def test_archetype_regional_preferences_are_not_generic_near_good():
    frontier_scores = regional_scores(nearest_distance_ly=95, within_25=0, within_50=1, within_100=2, within_250=8)
    dense_scores = regional_scores(nearest_distance_ly=10, within_25=5, within_50=12, within_100=40, within_250=90)
    isolated_scores = regional_scores(nearest_distance_ly=180, within_25=0, within_50=0, within_100=0, within_250=1)

    frontier = archetype_regional_fit(
        regional_role='frontier_hub',
        nearest_distance_ly=95,
        scores=frontier_scores,
        within_50=1,
        within_100=2,
    )
    dense = archetype_regional_fit(
        regional_role='dense_developed_cluster',
        nearest_distance_ly=10,
        scores=dense_scores,
        within_50=12,
        within_100=40,
    )
    isolated = archetype_regional_fit(
        regional_role='isolated_frontier',
        nearest_distance_ly=180,
        scores=isolated_scores,
        within_50=0,
        within_100=0,
    )

    assert frontier['expansion_capital'] > dense['expansion_capital']
    assert dense['hitech_tourism'] > isolated['hitech_tourism']
    assert isolated['extraction_refinery'] > dense['extraction_refinery']


def test_missing_coordinates_returns_unknown():
    result = compute_regional_analysis({'id64': 1, 'name': 'Broken', 'x': None, 'y': 0, 'z': 0}, [])

    assert result['regional_role'] == 'unknown'
    assert result['archetype_regional_fit'] == {}


def test_api_response_shape_adapter():
    row = {
        'nearest_colonised_system_id64': 2,
        'nearest_colonised_system_name': 'Anchor',
        'nearest_colonised_system_distance_ly': 74.2,
        'colonised_within_25ly': 0,
        'colonised_within_50ly': 1,
        'colonised_within_100ly': 3,
        'colonised_within_250ly': 18,
        'regional_isolation_score': 82.0,
        'regional_density_score': 31.0,
        'regional_expansion_score': 91.0,
        'regional_competition_score': 12.0,
        'regional_role': 'frontier_hub',
        'archetype_regional_fit': {'expansion_capital': 94.0},
        'rationale': {'summary': 'good', 'strengths': [], 'warnings': [], 'archetype_notes': {}},
        'computed_at': '2026-05-13T00:00:00Z',
    }

    response = response_from_row(row, 1)

    assert response['nearest_colonised_system']['distance_ly'] == 74.2
    assert response['mechanics_version'] == MECHANICS_VERSION
    assert response['claim_range_ly'] == 16.0
    assert response['analysis_radius_ly'] == 250.0
    assert response['counts']['within_100ly'] == 3
    assert response['scores']['expansion'] == 91.0
    assert response['regional_role'] == 'frontier_hub'
    assert response['data_quality']['regional_position'] == 'inferred'
    assert response['confidence_signals'][0]['level'] == 'inferred'
    RegionalAnalysisResponse.model_validate(response)
