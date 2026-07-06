import os
import re
import sys
import inspect
import subprocess
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
import build_ratings
from import_spansh import _extract_system_coords
from dirty_flags import (
    RATING_AFFECTING_BODY_FIELDS,
    RATING_AFFECTING_SYSTEM_FIELDS,
    mark_systems_rating_dirty,
)


def _schema_text(name: str) -> str:
    return Path(ROOT, 'sql', name).read_text(encoding='utf-8')


def _table_definition(schema: str, table_name: str) -> str:
    match = re.search(
        rf'CREATE TABLE IF NOT EXISTS {re.escape(table_name)} \((.*?)\n\);',
        schema,
        flags=re.DOTALL,
    )
    assert match is not None, f'{table_name} table definition missing'
    return match.group(1)


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


def test_system_station_payload_ignores_transient_confirmed_links_for_occupancy():
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
    assert station['body_id'] is None
    assert station['lane'] == 'unknown'
    assert station['association_status'] == 'unresolved'
    assert station['association_source'] == 'transient_non_slot'


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
    assert "SYSTEM_CACHE_VERSION = 'v7'" in systems_source
    assert "BODY_CACHE_VERSION = 'v3'" in systems_source


def test_base_schema_preserves_nullable_system_coordinates():
    systems = _table_definition(_schema_text('001_schema.sql'), 'systems')

    for column in ('x', 'y', 'z'):
        assert re.search(rf'\b{column}\s+REAL\s+DEFAULT NULL\b', systems)
        assert not re.search(rf'\b{column}\s+REAL\s+NOT NULL\s+DEFAULT 0\b', systems)


def test_nullable_coordinate_migration_remains_for_existing_deployments():
    migration = _schema_text('019_nullable_coords.sql')

    for column in ('x', 'y', 'z'):
        assert f'ALTER TABLE systems ALTER COLUMN {column} DROP NOT NULL;' in migration
        assert f'ALTER TABLE systems ALTER COLUMN {column} DROP DEFAULT;' in migration

    assert 'SET x = NULL, y = NULL, z = NULL' in migration
    assert 'id64 != 10477373803' in migration


def test_base_schema_includes_rating_version_and_migration_remains():
    ratings = _table_definition(_schema_text('001_schema.sql'), 'ratings')
    migration = _schema_text('020_rating_version.sql')

    assert re.search(r'\brating_version\s+TEXT\s+DEFAULT NULL\b', ratings)
    assert 'ADD COLUMN IF NOT EXISTS rating_version TEXT DEFAULT NULL' in migration


def test_base_schema_and_migration_include_body_rings_with_provenance():
    schema = _schema_text('001_schema.sql')
    body_rings = _table_definition(schema, 'body_rings')
    migration = _schema_text('024_body_rings.sql')

    for source in (body_rings, migration):
        assert 'system_id64' in source
        assert 'body_id' in source
        assert 'source_body_id' in source
        assert 'ring_name' in source
        assert 'ring_type' in source
        assert 'ring_class' in source
        assert 'mass_mt' in source
        assert 'inner_radius' in source
        assert 'outer_radius' in source
        assert 'source' in source
        assert 'confidence' in source
        assert 'association_status' in source
        assert 'updated_at' in source

    assert 'body_rings' in migration
    assert 'idx_body_rings_system_id64' in migration
    assert 'idx_body_rings_body_id' in migration
    assert 'idx_body_rings_source_body_id' in migration
    assert 'idx_body_rings_local_matched' in migration
    assert 'Consumers count only local_matched rows' in schema
    assert 'Missing rows mean unknown ring state' in schema
    assert 'Missing body_rings rows mean ring state' in migration


def test_eddn_ring_identity_hardening_migration_preserves_source_body_id_separately():
    migration = _schema_text('025_eddn_ring_identity_hardening.sql')

    assert 'ADD COLUMN IF NOT EXISTS source_body_id BIGINT DEFAULT NULL' in migration
    assert 'Journal BodyID is source identity' in migration
    assert 'ED-Finder local bodies.id' in migration
    assert 'ADD COLUMN IF NOT EXISTS association_status TEXT NOT NULL DEFAULT' in migration
    assert "'local_matched'" in migration
    assert "'unresolved_body_identity'" in migration
    assert "'ambiguous_body_identity'" in migration
    assert "'belt_source_evidence'" in migration
    assert 'body_rings_eddn_identity_report' in migration


def test_ring_consumers_require_local_body_id_not_unresolved_name_fallback():
    checked_paths = [
        'apps/importer/src/build_ratings.py',
        'apps/importer/src/build_archetype_scores.py',
        'apps/importer/src/build_topology.py',
        'apps/api/src/routers/systems.py',
        'apps/api/src/routers/simulate.py',
        'apps/api/src/routers/simulation.py',
        'apps/api/src/routers/archetypes.py',
        'sql/008_body_filter_aggregates.sql',
    ]
    forbidden = re.compile(
        r'br\.body_id\s+IS\s+NULL\s+AND\s+br\.body_name\s*=\s*(?:bodies|b)\.name',
        flags=re.IGNORECASE,
    )

    for relative_path in checked_paths:
        text = Path(ROOT, relative_path).read_text(encoding='utf-8')
        assert not forbidden.search(text), relative_path
        if relative_path != 'sql/008_body_filter_aggregates.sql':
            assert "br.association_status = 'local_matched'" in text, relative_path

    backfill_sql = _schema_text('008_body_filter_aggregates.sql')
    assert 'COALESCE(body_id::text' not in backfill_sql
    assert "br.association_status = 'local_matched'" in backfill_sql


def test_body_scan_facts_is_ringed_is_nullable_not_default_false():
    base = _schema_text('001_schema.sql')
    migration = _schema_text('015_simulation_engine.sql')
    body_scan_facts = _table_definition(migration, 'body_scan_facts')
    ring_migration = _schema_text('024_body_rings.sql')

    assert 'is_ringed        BOOLEAN     DEFAULT NULL' in body_scan_facts
    assert 'is_ringed BOOLEAN DEFAULT FALSE' not in base
    assert 'is_ringed        BOOLEAN     DEFAULT FALSE' not in migration
    assert 'ALTER COLUMN is_ringed DROP DEFAULT' in ring_migration
    assert 'Tri-state scan-derived ring evidence' in ring_migration


def test_ratings_schema_includes_ring_count_without_removing_rating_version():
    ratings = _table_definition(_schema_text('001_schema.sql'), 'ratings')
    migration = _schema_text('024_body_rings.sql')

    assert re.search(r'\bring_count\s+SMALLINT\s+NOT NULL\s+DEFAULT 0\b', ratings)
    assert re.search(r'\brating_version\s+TEXT\s+DEFAULT NULL\b', ratings)
    assert 'ADD COLUMN IF NOT EXISTS ring_count SMALLINT NOT NULL DEFAULT 0' in migration


def test_base_schema_and_migration_include_station_provenance_columns():
    stations = _table_definition(_schema_text('001_schema.sql'), 'stations')
    migration = _schema_text('023_station_data_provenance.sql')

    for column in (
        'distance_source',
        'distance_confidence',
        'distance_updated_at',
        'station_type_source',
        'station_type_confidence',
        'station_type_updated_at',
        'body_name_source',
        'body_name_confidence',
        'body_name_updated_at',
    ):
        assert column in stations
        assert f'ADD COLUMN IF NOT EXISTS {column}' in migration

    assert 'edsm_body_name' in migration
    assert 'edsm_distance' in migration


def test_rating_dirty_trigger_migration_remains_for_existing_deployments():
    base_functions = _schema_text('003_functions.sql')
    migration = _schema_text('022_rating_dirty_triggers.sql')

    for source in (base_functions, migration):
        assert 'OLD.main_star_type         IS DISTINCT FROM NEW.main_star_type' in source
        assert 'OLD.updated_at             IS DISTINCT FROM NEW.updated_at' in source
        assert 'AFTER DELETE ON bodies' in source
        assert 'trg_body_dirty_update' in source
        assert 'WHEN (' in source
        assert 'OLD.distance_from_star  IS DISTINCT FROM NEW.distance_from_star' in source


def test_rating_affecting_field_lists_document_current_inputs():
    assert 'main_star_type' in RATING_AFFECTING_SYSTEM_FIELDS
    assert 'updated_at' in RATING_AFFECTING_SYSTEM_FIELDS
    assert 'distance_from_star' in RATING_AFFECTING_BODY_FIELDS
    assert 'is_tidal_lock' in RATING_AFFECTING_BODY_FIELDS
    assert 'bio_signal_count' in RATING_AFFECTING_BODY_FIELDS


def test_spansh_importer_missing_coords_stay_null():
    assert _extract_system_coords({'id64': 1, 'name': 'Missing'}) == (None, None, None)
    assert _extract_system_coords({'coords': {'x': 1, 'y': None, 'z': 3}}) == (None, None, None)
    assert _extract_system_coords({'coords': {'x': '78.5', 'y': '-100.25', 'z': '16.78125'}}) == (
        78.5,
        -100.25,
        16.78125,
    )


def test_spansh_temp_upsert_skips_noop_updates():
    source = Path(ROOT, 'apps', 'importer', 'src', 'import_spansh.py').read_text()

    assert "if c not in {'updated_at', 'rating_dirty', 'cluster_dirty'}" in source
    assert 'IS DISTINCT FROM EXCLUDED' in source
    assert 'WHERE {comparisons}' in source


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


def test_rating_scorer_uses_trusted_ring_flag_for_ring_count():
    rating = rate_system(2008132031194, [
        {'subtype': 'Rocky body', 'has_rings': True},
        {'subtype': 'Rocky body'},
        {'subtype': 'Ringed-looking subtype without evidence'},
    ], 'K')

    assert rating['ring_count'] == 1


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


def test_dirty_mode_selects_only_rating_dirty_systems():
    source = inspect.getsource(build_ratings.main)

    assert 'WHERE  rating_dirty = TRUE' in source
    assert 'Query: dirty systems only' in source


def test_dirty_ratings_maintenance_script_is_host_cron_safe():
    script_path = Path(ROOT, 'scripts', 'run_dirty_ratings_if_needed.sh')
    source = script_path.read_text(encoding='utf-8')

    syntax = subprocess.run(
        ['bash', '-n', str(script_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert syntax.returncode == 0, syntax.stderr
    assert 'DIRTY_RATING_THRESHOLD="${DIRTY_RATING_THRESHOLD:-250}"' in source
    assert 'DIRTY_RATING_WORKERS="${DIRTY_RATING_WORKERS:-2}"' in source
    assert 'DIRTY_RATING_CHUNK="${DIRTY_RATING_CHUNK:-1000}"' in source
    assert 'flock -n 9' in source
    assert 'SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE;' in source
    assert 'docker compose --profile import run --rm' in source
    assert '/app/build_ratings.py' in source
    assert '--dirty' in source
    assert '--rebuild' not in source
    assert '--workers "$DIRTY_RATING_WORKERS"' in source
    assert '--chunk "$DIRTY_RATING_CHUNK"' in source
    assert 'redis-cli' not in source


def test_dirty_ratings_runbook_documents_host_cron_installation():
    runbook = Path(ROOT, 'docs', 'operations', 'stage17n2c-data-trust-runbook.md').read_text(
        encoding='utf-8'
    )

    assert 'host cron that invokes the importer container' in runbook
    assert 'deploy_main.sh` rebuilds/restarts' in runbook
    assert (
        '*/30 * * * * cd /opt/ed-finder && DIRTY_RATING_THRESHOLD=250 '
        'DIRTY_RATING_WORKERS=2 DIRTY_RATING_CHUNK=1000 '
        'bash scripts/run_dirty_ratings_if_needed.sh >> /data/logs/dirty-ratings.log 2>&1'
    ) in runbook
    assert 'SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE;' in runbook
    assert 'grep -E "start time=|dirty_count=|below threshold|' in runbook
    assert 'does not clear Redis caches automatically' in runbook


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


class _DirtyHelperCursor:
    def __init__(self, rowcount_by_chunk=None):
        self.rowcount = 0
        self.statements = []
        self.chunks = []
        self.rowcount_by_chunk = list(rowcount_by_chunk or [])

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, sql, params=None):
        self.statements.append(sql)
        chunk = list(params[0])
        self.chunks.append(chunk)
        if self.rowcount_by_chunk:
            self.rowcount = self.rowcount_by_chunk.pop(0)
        else:
            self.rowcount = len(chunk)


class _DirtyHelperConn:
    def __init__(self, rowcount_by_chunk=None):
        self.cursor_obj = _DirtyHelperCursor(rowcount_by_chunk)
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1


def test_mark_systems_rating_dirty_ignores_empty_list():
    conn = _DirtyHelperConn()

    marked = mark_systems_rating_dirty(conn, [], chunk_size=2)

    assert marked == 0
    assert conn.commits == 0
    assert conn.cursor_obj.chunks == []


def test_mark_systems_rating_dirty_marks_one_and_is_idempotent_by_predicate():
    conn = _DirtyHelperConn(rowcount_by_chunk=[1, 0])

    marked_first = mark_systems_rating_dirty(conn, [42], chunk_size=10)
    marked_second = mark_systems_rating_dirty(conn, [42], chunk_size=10)

    assert marked_first == 1
    assert marked_second == 0
    assert 's.rating_dirty IS DISTINCT FROM TRUE' in conn.cursor_obj.statements[0]


def test_mark_systems_rating_dirty_marks_many_in_chunks_and_dedupes():
    conn = _DirtyHelperConn()

    marked = mark_systems_rating_dirty(conn, [1, 2, 2, 3, 4, 5], chunk_size=2)

    assert marked == 5
    assert conn.cursor_obj.chunks == [[1, 2], [3, 4], [5]]
    assert conn.commits == 1


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
