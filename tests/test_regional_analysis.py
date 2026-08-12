from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', str(Path.cwd() / 'test-local.log'))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'importer' / 'src'))

import build_regional_analysis
from build_regional_analysis import _load_targets
from edfinder_api.regional.regional_analysis import compute_regional_analysis, distance_ly, response_from_row
from edfinder_api.regional.regional_roles import classify_regional_role
from edfinder_api.regional.regional_scoring import archetype_regional_fit, regional_scores
from edfinder_api.models import RegionalAnalysisResponse
from edfinder_api.mechanics.versions import MECHANICS_VERSION


class RecordingCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, query: str) -> None:
        self.queries.append(' '.join(query.split()))

    def fetchall(self) -> list[dict[str, object]]:
        return []

    def fetchone(self) -> dict[str, int]:
        return {'excluded_count': 266_000}


def test_main_sets_bounded_session_statement_timeout(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = {'excluded_count': 0}
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(build_regional_analysis.psycopg2, 'connect', connect)
    monkeypatch.setattr(sys, 'argv', ['build_regional_analysis.py'])

    build_regional_analysis.main()

    assert 'statement_timeout=1800000' in connect.call_args.kwargs['options']


def test_load_targets_filters_coordinate_less_systems_in_all_modes(capsys):
    modes = (
        argparse.Namespace(dirty=True, all=False, limit=25),
        argparse.Namespace(dirty=False, all=False, limit=25),
        argparse.Namespace(dirty=False, all=True, limit=25),
    )

    for args in modes:
        cursor = RecordingCursor()

        assert _load_targets(cursor, args) == []
        assert len(cursor.queries) == 2
        target_query, excluded_query = cursor.queries
        assert 'x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL' in target_query
        assert 'x IS NULL OR y IS NULL OR z IS NULL' in excluded_query
        assert 'ORDER BY id64 LIMIT 25' in target_query

    assert capsys.readouterr().out.count('Excluded 266,000 coordinate-less systems') == 3


def test_load_targets_applies_zero_limit(capsys):
    cursor = RecordingCursor()
    args = argparse.Namespace(dirty=False, all=False, limit=0)

    assert _load_targets(cursor, args) == []
    assert 'ORDER BY id64 LIMIT 0' in cursor.queries[0]
    assert 'Excluded 266,000 coordinate-less systems' in capsys.readouterr().out


def test_regional_limit_parser_accepts_zero_and_rejects_negative(capsys):
    assert build_regional_analysis.parse_args(['--limit', '0']).limit == 0

    with pytest.raises(SystemExit) as exc_info:
        build_regional_analysis.parse_args(['--limit', '-1'])

    assert exc_info.value.code == 2
    assert 'must be a non-negative integer' in capsys.readouterr().err


class _FixedRowsCursor:
    """Unlike RecordingCursor above (always empty), returns real rows from
    the first fetchall() call and a fixed count from the second fetchone()
    call, matching _load_targets' two-query shape. Also records every
    UPSERT issued via _write, so a test can confirm non-finite targets get
    a persisted row (not just that they're excluded from the return value)."""
    def __init__(self, rows, excluded_count):
        self._rows = rows
        self._excluded_count = excluded_count
        self.upserted_rows = []

    def execute(self, query, params=None):
        if params is not None and 'INSERT INTO system_regional_analysis' in query:
            self.upserted_rows.append(params)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return {'excluded_count': self._excluded_count}


def test_load_targets_excludes_nan_and_infinity_and_folds_into_excluded_count(capsys):
    rows = [
        system(1, 0.0, 0.0, 0.0),
        system(2, float('nan'), 0.0, 0.0),
        system(3, 0.0, float('inf'), 0.0),
        system(4, 10.0, 10.0, 10.0),
    ]
    cursor = _FixedRowsCursor(rows, excluded_count=5)
    args = argparse.Namespace(dirty=False, all=False, limit=None)

    targets = _load_targets(cursor, args)

    assert [t['id64'] for t in targets] == [1, 4]
    assert 'Excluded 7 coordinate-less systems' in capsys.readouterr().out

    # Codex Review finding on #426: without a persisted row, NOT EXISTS
    # would keep re-selecting these same non-finite systems every run,
    # permanently eating into the --limit batch. Confirm they get the same
    # degenerate row a zero-candidate finite target would, tagged so a
    # later repair can still trigger a real reprocess (see the next test).
    upserted_ids = {row['system_id64'] for row in cursor.upserted_rows}
    assert upserted_ids == {2, 3}
    for row in cursor.upserted_rows:
        assert row['regional_role'] == 'unknown'
        assert row['data_source'] == build_regional_analysis.NON_FINITE_COORDS_SOURCE


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
