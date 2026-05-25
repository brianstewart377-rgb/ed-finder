import os
import sys
import inspect
from pathlib import Path

os.environ.setdefault('LOG_FILE', '/dev/null')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, 'apps', 'api', 'src'))
sys.path.insert(0, os.path.join(ROOT, 'apps', 'importer', 'src'))

import psycopg2

from helpers import safe_coords_from_row, sys_row_to_dict
from local_search import _build_system_record, _safe_distance, local_db_search
from models import AutocompleteHit, StationModel, SystemDetailRow, SystemRow
from progress import ProgressReporter
from routers.systems import _station_with_association
from build_ratings import (
    RATING_CONFLICT_UPDATE_COLUMNS,
    RATING_INSERT_COLUMNS,
    RATING_VALUES_TEMPLATE,
    RATING_VERSION,
    _clean_ids_for_batch,
    _connect_with_retry,
    _mark_ratings_clean,
    _rating_row_tuple,
    _rating_template_placeholder_count,
    _ratings_insert_sql,
    attenuate_economy_scores,
    rate_system,
    worker_process,
)
from import_spansh import _extract_system_coords


def test_safe_coords_treats_non_sol_origin_as_unknown():
    assert safe_coords_from_row({'id64': 123, 'x': 0, 'y': 0, 'z': 0}) == {
        'x': None,
        'y': None,
        'z': None,
    }


def test_safe_coords_allows_sol_origin():
    assert safe_coords_from_row({'id64': 10477373803, 'x': 0, 'y': 0, 'z': 0}) == {
        'x': 0.0,
        'y': 0.0,
        'z': 0.0,
    }


def test_safe_distance_rejects_fake_zero():
    assert _safe_distance(0.0) is None


def test_safe_distance_preserves_valid_distance():
    assert _safe_distance(12.345) == 12.35


def test_search_record_preserves_null_distance_and_fake_coords():
    row = {
        'id64': 2008132031194,
        'name': 'Exioce',
        'x': 0,
        'y': 0,
        'z': 0,
        'dist': None,
        'updated_at': None,
        'population': 0,
    }
    record = _build_system_record(row)
    assert record['coords'] == {'x': None, 'y': None, 'z': None}
    assert record['distance'] is None


def test_search_record_preserves_null_population():
    row = {
        'id64': 2008132031194,
        'name': 'Unknown Population',
        'x': 78.5,
        'y': -100.25,
        'z': 16.78125,
        'dist': None,
        'updated_at': None,
        'population': None,
    }

    record = _build_system_record(row)

    assert record['population'] is None


def test_sys_row_to_dict_does_not_invent_origin_coords():
    record = sys_row_to_dict({'id64': 123, 'name': 'Unknown place', 'x': 0, 'y': 0, 'z': 0})
    assert record['x'] is None
    assert record['y'] is None
    assert record['z'] is None
    assert record['coords'] == {'x': None, 'y': None, 'z': None}


def test_sys_row_to_dict_preserves_null_population():
    record = sys_row_to_dict({
        'id64': 123,
        'name': 'Unknown place',
        'x': None,
        'y': None,
        'z': None,
        'population': None,
    })

    assert record['population'] is None


def test_api_contracts_allow_null_population_and_station_body_name():
    assert SystemRow(id64=1, population=None).population is None
    assert SystemDetailRow(id64=1, name='Null Pop', population=None).population is None
    assert AutocompleteHit(id64=1, name='Null Pop', population=None).population is None
    station = StationModel(
        id=5,
        market_id=5,
        name='Port',
        body_name='A 1',
        body_id=7,
        lane='orbital',
        association_status='confirmed',
        association_confidence='exact',
        association_source='resolver_body_name',
        resolver_notes=None,
        primary_economy='Refinery',
        secondary_economy=None,
        has_refuel=True,
        has_repair=False,
        has_rearm=False,
    )
    assert station.body_name == 'A 1'
    assert station.body_id == 7
    assert station.lane == 'orbital'
    assert station.association_status == 'confirmed'
    assert station.market_id == 5
    assert station.primary_economy == 'Refinery'


def test_system_station_payload_exposes_confirmed_association():
    station = _station_with_association({
        'id': 5,
        'market_id': 5,
        'system_id64': 1,
        'name': 'Confirmed Port',
        'station_type': 'Coriolis',
        'station_body_name': 'Raw A 1',
        'body_name': 'A 1',
        'body_id': 7,
        'lane': 'orbital',
        'association_status': 'confirmed',
        'association_confidence': 'exact',
        'association_source': 'manual',
        'resolver_notes': 'curated',
    }, [{'id': 7, 'name': 'A 1'}])

    assert station['body_id'] == 7
    assert station['body_name'] == 'A 1'
    assert station['lane'] == 'orbital'
    assert station['association_status'] == 'confirmed'
    assert station['association_confidence'] == 'exact'
    assert station['association_source'] == 'manual'


def test_system_station_payload_exposes_inferred_association():
    station = _station_with_association({
        'id': 6,
        'market_id': 6,
        'system_id64': 1,
        'name': 'Inferred Outpost',
        'station_type': 'Outpost',
        'station_body_name': None,
        'body_name': 'A 2',
        'body_id': 8,
        'lane': 'orbital',
        'association_status': 'inferred',
        'association_confidence': 'strong_inference',
        'association_source': 'resolver_distance',
        'resolver_notes': 'Unique distance_from_star match within 0.01 ls.',
    }, [{'id': 8, 'name': 'A 2'}])

    assert station['body_id'] == 8
    assert station['association_status'] == 'inferred'
    assert station['association_confidence'] == 'strong_inference'
    assert station['association_source'] == 'resolver_distance'


def test_system_station_payload_keeps_unresolved_station_visible():
    station = _station_with_association({
        'id': 7,
        'market_id': 7,
        'system_id64': 1,
        'name': 'Unresolved Megaship',
        'station_type': 'MegaShip',
        'station_body_name': 'A 1',
        'body_name': 'A 1',
        'body_id': 7,
        'lane': 'unknown',
        'association_status': 'confirmed',
        'association_confidence': 'exact',
        'association_source': 'resolver_body_name',
        'resolver_notes': 'MegaShip is not treated as permanent colony-slot infrastructure.',
    }, [{'id': 7, 'name': 'A 1'}])

    assert station['name'] == 'Unresolved Megaship'
    assert station['body_id'] == 7
    assert station['lane'] == 'unknown'
    assert station['association_status'] == 'confirmed'


def test_local_search_galaxy_wide_projects_null_distance():
    source = inspect.getsource(local_db_search)
    assert 'dist_expr = "NULL::float"' in source
    assert 'reference_coords must include x, y, z' in source


def test_data_trust_cache_versions_are_bumped():
    search_source = Path(ROOT, 'apps', 'api', 'src', 'routers', 'search.py').read_text()
    systems_source = Path(ROOT, 'apps', 'api', 'src', 'routers', 'systems.py').read_text()

    assert "AUTOCOMPLETE_CACHE_VERSION = 'v3'" in search_source
    assert "SEARCH_CACHE_VERSION = 'v4'" in search_source
    assert "GALAXY_CACHE_VERSION = 'v4'" in search_source
    assert "CLUSTER_CACHE_VERSION = 'v4'" in search_source
    assert "SYSTEM_CACHE_VERSION = 'v3'" in systems_source
    assert "BODY_CACHE_VERSION = 'v2'" in systems_source


def test_spansh_importer_missing_coords_stay_null():
    assert _extract_system_coords({'id64': 1, 'name': 'Missing'}) == (None, None, None)
    assert _extract_system_coords({'coords': {'x': 1, 'y': None, 'z': 3}}) == (None, None, None)
    assert _extract_system_coords({'coords': {'x': '78.5', 'y': '-100.25', 'z': '16.78125'}}) == (
        78.5,
        -100.25,
        16.78125,
    )


def test_current_rating_scorer_attenuates_multi_economy_saturation():
    bodies = (
        [{'subtype': 'Earth-like world', 'is_earth_like': True}] * 3
        + [{'subtype': 'Gas giant'}] * 5
        + [{'subtype': 'Rocky body', 'is_landable': True}] * 10
        + [{'subtype': 'Rocky Ice world', 'is_landable': True}] * 2
    )

    rating = rate_system(2008132031194, bodies, 'K')
    scores = [
        rating['score_refinery'],
        rating['score_industrial'],
        rating['score_hightech'],
        rating['score_military'],
    ]

    assert scores.count(100) <= 2
    assert rating['rating_version'] == RATING_VERSION


def test_v34_attenuation_preserves_top_pair_and_reduces_third_fourth():
    raw = {
        'Agriculture': 100,
        'Refinery': 100,
        'Industrial': 100,
        'HighTech': 100,
        'Military': 80,
        'Tourism': 60,
        'Extraction': 40,
    }

    final = attenuate_economy_scores(raw)

    assert list(raw.values()).count(100) == 4
    assert final['Agriculture'] == 100
    assert final['Refinery'] == 100
    assert final['Industrial'] == 85
    assert final['HighTech'] == 70


def test_score_breakdown_contains_rating_version_34():
    rating = rate_system(123, [], None)
    assert rating['rating_version'] == '3.4'
    assert rating['score_breakdown']['rating_version'] == '3.4'


def test_build_ratings_insert_shape_counts_match():
    rating = rate_system(123, [], None)
    row = _rating_row_tuple(rating, '2026-05-25T00:00:00+00:00')

    assert len(RATING_INSERT_COLUMNS) == len(row)
    assert len(RATING_INSERT_COLUMNS) == _rating_template_placeholder_count(RATING_VALUES_TEMPLATE)
    assert RATING_INSERT_COLUMNS[row.index(RATING_VERSION)] == 'rating_version'


def test_rating_version_write_shape_is_explicit():
    sql = _ratings_insert_sql()

    assert 'rating_version' in RATING_INSERT_COLUMNS
    assert 'rating_version' in RATING_CONFLICT_UPDATE_COLUMNS
    assert 'rating_version' in sql
    assert 'EXCLUDED.rating_version' in sql


def test_worker_connection_uses_timeout_disabled_helper():
    worker_source = inspect.getsource(worker_process)
    helper_source = inspect.getsource(_connect_with_retry)

    assert '_connect_with_retry' in worker_source
    assert 'psycopg2.connect' not in worker_source
    assert 'statement_timeout=0' in helper_source
    assert 'lock_timeout=0' in helper_source
    assert 'idle_in_transaction_session_timeout=3600000' in helper_source


def test_dirty_cleanup_uses_timeout_disabled_chunked_update():
    source = inspect.getsource(_mark_ratings_clean)

    assert 'SET LOCAL statement_timeout = 0' in source
    assert 'SET LOCAL lock_timeout = 0' in source
    assert 'UPDATE systems s' in source
    assert 'unnest(%s::bigint[])' in source


def test_clean_ids_exclude_failed_rating_ids():
    assert _clean_ids_for_batch([1, 2, 3, 4], {2, 4}) == [1, 3]


class _FakeConn:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _FakeCursor:
    def __init__(self, fail_first_update=False):
        self.rowcount = 0
        self.statements = []
        self.update_chunks = []
        self.fail_first_update = fail_first_update

    def execute(self, sql, params=None):
        self.statements.append(sql)
        if 'UPDATE systems s' not in sql:
            return
        if self.fail_first_update:
            self.fail_first_update = False
            raise psycopg2.errors.QueryCanceled('canceling statement due to statement timeout')
        chunk = list(params[0])
        self.update_chunks.append(chunk)
        self.rowcount = len(chunk)


def test_dirty_cleanup_chunks_large_clean_id_list():
    conn = _FakeConn()
    cur = _FakeCursor()

    marked, left_dirty = _mark_ratings_clean(
        conn, cur, list(range(2505)), worker_id=7, chunk_size=1000, retries=1,
    )

    assert marked == 2505
    assert left_dirty == 0
    assert [len(chunk) for chunk in cur.update_chunks] == [1000, 1000, 505]


def test_dirty_cleanup_retries_transient_statement_timeout():
    conn = _FakeConn()
    cur = _FakeCursor(fail_first_update=True)

    marked, left_dirty = _mark_ratings_clean(
        conn, cur, [1, 2, 3], worker_id=8, chunk_size=1000, retries=2, retry_delay=0,
    )

    assert marked == 3
    assert left_dirty == 0
    assert conn.rollbacks == 1


class _CaptureLog:
    def __init__(self):
        self.lines = []

    def info(self, message):
        self.lines.append(str(message))


def test_dirty_progress_unknown_total_does_not_emit_fake_percent():
    log = _CaptureLog()
    progress = ProgressReporter(log, total=None, label='ratings', interval=0, heartbeat=0)

    progress.update(55_000, force=True)

    text = '\n'.join(log.lines)
    assert '55,000 / unknown' in text
    assert '55,000 / 1' not in text
    assert '%' not in text
