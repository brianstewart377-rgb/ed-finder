"""Opt-in PostgreSQL 18 representative-scale proof required to unblock F4b.

The F4 design sections 7/8 and owner answer 5 require all eight archetypes at
the B/A/S floors on at least one million systems, with unchanged warm/cold
budgets. This is synthetic query-plan evidence, not a Ratings validation or a
claim of full production-scale parity. A passing receipt unblocks F4b's scale
gate; merely adding this test does not.

With the usual local RATINGS_V4_VALIDATION_DATABASE_URL, run:

    EDF_RANKINGS_SCALE_PROOF=1 EDF_RANKINGS_SCALE_RESTART_CMD='<command that restarts the disposable PostgreSQL 18 server and returns once it accepts connections>' EDF_RANKINGS_SCALE_RECEIPT=/tmp/rankings-scale-proof.json python -m pytest -q tests/test_archetype_rankings_scale_postgres.py

EDF_RANKINGS_SCALE_PROOF is the explicit opt-in. EDF_RANKINGS_SCALE_RESTART_CMD
is mandatory and runs before EACH of the 72 cold measurements (120 s timeout).
EDF_RANKINGS_SCALE_RECEIPT optionally selects the JSON output path, including
failed plan/budget receipts. The cold label defaults to "buffer-cold"; set
EDF_RANKINGS_SCALE_COLD_LABEL=io-cold only if the restart command also evicts
the OS page cache. Use only a disposable server dedicated to this run.

The Finder CI lane discovers this module but must skip it even with
EDF_DB_TESTS_REQUIRED=1: opting out is not a database-availability failure.
Each run measures a prepared statement with EXPLAIN (ANALYZE, BUFFERS, FORMAT
JSON) EXECUTE under force_generic_plan, proven by pg_prepared_statements counters.
The receipt keeps the warm median's lossless compact JSON from that same
execution and only the cold run's plan summary.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
from statistics import median
import subprocess
import sys
from uuid import UUID

import pytest

if os.environ.get('EDF_RANKINGS_SCALE_PROOF') != '1':
    pytest.skip('opt in with EDF_RANKINGS_SCALE_PROOF=1', allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps/api/src'))
os.environ.setdefault('CORS_ORIGINS', 'https://rankings-scale-proof.invalid')

from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402

from edfinder_api.ranking.profile import (  # noqa: E402
    ARCHETYPE_KEYS, RANKING_VERSION, ranking_sha256,
)
from edfinder_api.ranking.ranking_sql import (  # noqa: E402
    build_count_query, build_ranked_query,
)
from edfinder_api.routers import archetypes  # noqa: E402

pytestmark = [pytest.mark.db, pytest.mark.slow]

SYSTEMS = 1_000_000
SEED = 20261031
GENERATION = UUID('00000000-0000-4000-8000-000020261031')
PREPARED_STATEMENT = 'edf_rankings_scale_proof'
FLOORS = {60: 'b', 76: 'a', 88: 's'}
QUERIES = {
    'first_page': (0, 300, 1500),
    'near_ceiling_page': (9950, 600, 2500),
    'count': (None, 600, 2500),
}
SETTINGS = (
    'shared_buffers', 'work_mem', 'effective_cache_size', 'random_page_cost',
    'jit', 'max_parallel_workers_per_gather', 'plan_cache_mode',
    'enable_seqscan', 'enable_indexscan', 'enable_indexonlyscan',
)
MIGRATIONS = (
    '003_ratings_v4_derived.sql', '004_v3_search_spatial_clusters.sql',
    '006_v3_derived_product_lifecycle.sql',
    '010_v3_system_search_body_type_counts.sql', '011_v3_system_archetype.sql',
    '015_v3_derived_product_publication.sql',
)


@contextmanager
def _restart_safe_database(monkeypatch):
    """Keep canonical_database's local guard and random-database teardown.

    Its admin connection normally stays open across the yield. Only that first
    connection is replaced: CREATE and DROP each get a fresh real connection,
    so DROP still works after server restarts. No generator internals or shared
    fixture code are changed. The yielded seed connection is closed before any
    restart; psycopg's context exit accepts an already closed connection.
    """
    import psycopg

    connect = psycopg.connect
    first_connection = True

    @contextmanager
    def admin_connection(*args, **kwargs):
        class Admin:
            def execute(self, statement):
                with connect(*args, **kwargs) as connection:
                    connection.execute(statement)

        yield Admin()

    def fixture_connect(*args, **kwargs):
        nonlocal first_connection
        if first_connection:
            first_connection = False
            return admin_connection(*args, **kwargs)
        return connect(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(psycopg, 'connect', fixture_connect)
        with canonical_database() as (connection, *_):
            try:
                yield connection
            finally:
                connection.close()


def _seed(connection):
    """Set-based synthetic rows; all foreign keys and lifecycle guards stay on."""
    from psycopg.types.json import Jsonb

    for migration in MIGRATIONS:
        connection.execute((ROOT / 'sql/v3/migrations' / migration).read_text())
    canonical_id, canonical_sequence = connection.execute(
        'SELECT generation_id, publication_sequence '
        'FROM v3_meta.current_canonical_generation WHERE singleton'
    ).fetchone()
    manifest = {
        'fixture': 'rankings-scale-proof', 'systems': SYSTEMS, 'seed': SEED,
        'archetype_model_sha256': hashlib.sha256(b'synthetic-scale-model').hexdigest(),
    }
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).digest()
    verified = Jsonb({'status': 'VERIFIED', 'synthetic_scale_fixture': True})
    connection.execute('''
        INSERT INTO v3_meta.derived_generation (
            derived_generation_id, canonical_generation_id,
            canonical_publication_sequence, generation_key,
            mechanics_version, scorer_version, adapter_version,
            manifest, manifest_sha256, expected_systems, expected_bodies
        ) VALUES (%s,%s,%s,'rankings_scale_proof',
                  'synthetic-scale','synthetic-scale','synthetic-scale',%s,%s,%s,0)
    ''', (GENERATION, canonical_id, canonical_sequence, Jsonb(manifest), digest, SYSTEMS))
    for product in ('system_search', 'system_archetype'):
        connection.execute('''
            INSERT INTO v3_meta.derived_product (
                derived_generation_id, product_code, product_version,
                manifest, manifest_sha256, expected_rows
            ) VALUES (%s,%s,'synthetic-scale',%s,%s,%s)
        ''', (GENERATION, product, Jsonb(manifest), digest, SYSTEMS))

    # These are INSERTs into disposable derived relations, not canonical-table
    # updates. Trigger enforcement is required for the generation/product and
    # deferred FK contracts; replica mode would invalidate this fixture.
    connection.execute('''
        INSERT INTO v3_derived.build_chunk (
            derived_generation_id, chunk_ordinal, source_projection_sha256,
            canonical_input_sha256, content_sha256, systems,
            canonical_bodies, physical_bodies, eligible_opportunities
        ) SELECT %s, n, %s, %s, %s, 1000, 0, 0, 0
          FROM generate_series(0, %s::bigint / 1000 - 1) n
    ''', (GENERATION, digest, digest, digest, SYSTEMS))
    _insert_ranges(connection, '''
        INSERT INTO v3_derived.system_rating_vector (
            derived_generation_id, system_id64, chunk_ordinal,
            loaded_body_count, physical_body_count, subtype_projection_sha256,
            potential, quality, quality_min, quality_max, completeness, confidence
        ) SELECT %s, n, (n - 1) / 1000, 0, 0, %s,
                 array_fill(0::smallint, ARRAY[7]),
                 array_fill(0::smallint, ARRAY[7]),
                 array_fill(0::smallint, ARRAY[7]),
                 array_fill(0::smallint, ARRAY[7]),
                 array_fill((5000 + mod(n * 104729 + %s, 5001))::smallint, ARRAY[7]),
                 array_fill(10000::smallint, ARRAY[7])
          FROM generate_series(%s::bigint, %s::bigint) n
    ''', (GENERATION, digest, SEED))
    _insert_ranges(connection, '''
        INSERT INTO v3_derived.system_search (
            derived_generation_id, system_id64, name, x_ly, y_ly, z_ly,
            position_ly, galaxy_region_id, region_name, main_star_class,
            body_count, landable_count, station_count, has_rings,
            has_biologicals, has_geologicals, has_terraformable,
            completeness, confidence
        ) SELECT %s, n, 'Scale system ' || n, x, y, z,
                 cube(ARRAY[x,y,z]), mod(n,42)::integer, 'Synthetic region', 'K',
                 0, 0, 0, false, false, false, false,
                 (5000 + mod(n * 104729 + %s, 5001)) / 10000.0, 1.0
          FROM (
              SELECT n, (mod(n * 7919, 240001) - 120000)::float8 AS x,
                     (mod(n * 104729, 24001) - 12000)::float8 AS y,
                     (mod(n * 15485863, 240001) - 120000)::float8 AS z
                FROM generate_series(%s::bigint, %s::bigint) n
          ) coordinates
    ''', (GENERATION, SEED))

    # Each odd multiplier below is coprime to 101. Every block of 101 systems
    # therefore visits every score 0..100 for EVERY key: at least
    # floor(1_000_000/101)*13 = 128,700 S-tier rows per key. Key-specific offsets
    # and confidence/completeness permutations spread the weighted index order
    # across the heap deterministically, with integer-key ties to test id64 ASC.
    # Completeness is the vector's minimum (in 1e-4 units) times 100, as F2d
    # requires, and Search exposes the same value on its 0..1 scale.
    score_columns, insert_columns, values = [], [], []
    for ordinal, key in enumerate(ARCHETYPE_KEYS):
        score_columns.extend((
            f'mod(n * {2 * ordinal + 1} + {SEED + ordinal * 17}, 101) AS {key}_score',
            f'(500000 + mod(n * {7919 + 2 * ordinal} + {SEED}, 500001)) '
            f'AS {key}_confidence_ppm',
        ))
        insert_columns.extend(f'{key}_{suffix}' for suffix in (
            'score', 'tier', 'confidence_ppm', 'weighted_e4',
        ))
        values.extend((
            f'{key}_score', _tier_sql(f'{key}_score'), f'{key}_confidence_ppm',
            # F2d/PROFILE_SPEC's exact integer half-up expression, not float round.
            f'(({key}_score::bigint * {key}_confidence_ppm * completeness_ppm '
            '+ 50000000) / 100000000)',
        ))
    scores = ', '.join(f'{key}_score' for key in ARCHETYPE_KEYS)
    keys = ', '.join(f"'{key}'" for key in ARCHETYPE_KEYS)
    best = f'greatest({scores})'
    # All interpolated identifiers/expressions are from the server-owned key
    # list and fixed fixture constants. Database values use bound parameters.
    _insert_ranges(connection, f'''
        INSERT INTO v3_derived.system_archetype (
            derived_generation_id, system_id64, archetype_version,
            {', '.join(insert_columns)},
            primary_archetype, secondary_archetype, best_colony_potential,
            best_tier, archetype_confidence_ppm, weighted_potential, completeness_ppm
        ) SELECT %s, n, 'synthetic-scale', {', '.join(values)},
                 (ARRAY[{keys}])[array_position(ARRAY[{scores}], {best})],
                 NULL, {best}, {_tier_sql(best)}, 0,
                 {best} * completeness_ppm / 1000000.0, completeness_ppm
          FROM (
              SELECT n, {', '.join(score_columns)},
                     100 * (5000 + mod(n * 104729 + {SEED}, 5001)) AS completeness_ppm
                FROM generate_series(%s::bigint, %s::bigint) n
          ) distribution
    ''', (GENERATION,))

    connection.execute('''
        UPDATE v3_meta.derived_product
           SET lifecycle_state='READY', validation_receipt=%s,
               validation_sha256=%s, validated_at=now()
         WHERE derived_generation_id=%s
    ''', (verified, digest, GENERATION))
    connection.execute('''
        UPDATE v3_meta.derived_generation
           SET lifecycle_state='VALIDATING', source_receipt=%s, content_sha256=%s
         WHERE derived_generation_id=%s
    ''', (Jsonb({'synthetic_scale_fixture': True}), digest, GENERATION))
    connection.execute('''
        UPDATE v3_meta.derived_generation
           SET lifecycle_state='READY', validation_receipt=%s, validated_at=now()
         WHERE derived_generation_id=%s
    ''', (verified, GENERATION))
    # 015 atomically records the base pointer/audit, PUBLISHED state, and each
    # READY product's publication timestamp + matching product audit row.
    connection.execute(
        'SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s,%s)',
        (GENERATION, None, 0, canonical_id, canonical_sequence,
         'scale-proof', 'disposable synthetic scale fixture',
         ['system_search', 'system_archetype']),
    )
    # canonical_database yields an autocommit connection. VACUUM must run
    # outside a transaction: ANALYZE alone would leave index-only heap fetches.
    for relation in ('system_search', 'system_archetype'):
        connection.execute(f'VACUUM (ANALYZE) v3_derived.{relation}')


def _tier_sql(score):
    return (f"CASE WHEN {score} >= 88 THEN 'S' WHEN {score} >= 76 THEN 'A' "
            f"WHEN {score} >= 60 THEN 'B' WHEN {score} >= 45 THEN 'C' ELSE 'D' END")


def _insert_ranges(connection, statement, params):
    # Bound the deferred-FK event queue and statement transition tables, while
    # retaining set-based writes (40 statements/relation, no per-row trips).
    # Each statement commits independently on the fixture's autocommit session.
    for start in range(1, SYSTEMS + 1, 25_000):
        connection.execute(statement, (*params, start, min(start + 24_999, SYSTEMS)))


def _fixture_evidence(connection, receipt):
    """Independent, unbounded eligibility counts and canonical order oracle."""
    expected = {}
    for relation in ('system_search', 'system_archetype'):
        count = connection.execute(f'SELECT count(*) FROM v3_derived.{relation}').fetchone()[0]
        receipt['row_counts'][relation] = count
        assert count == SYSTEMS, f'all archetypes/all floors/setup: {relation} count {count}'
        visible = connection.execute(
            f'SELECT derived_generation_id, count(*) FROM v3_app.{relation} '
            'GROUP BY derived_generation_id'
        ).fetchall()
        assert visible == [(GENERATION, SYSTEMS)], (
            f'all archetypes/all floors/setup: {relation} published generation coverage'
        )
    assert connection.execute(
        "SELECT relkind FROM pg_class WHERE oid='v3_app.system_archetype_summary'::regclass"
    ).fetchone()[0] == 'v', 'all archetypes/all floors/setup: summary must remain a view'
    for key in ARCHETYPE_KEYS:
        for floor in FLOORS:
            eligible = connection.execute(
                f'SELECT count(*) FROM v3_derived.system_archetype '
                f'WHERE derived_generation_id=%s AND {key}_score >= %s',
                (GENERATION, floor),
            ).fetchone()[0]
            receipt['eligible_counts'].append({'archetype': key, 'floor': floor, 'rows': eligible})
            assert eligible >= 10_001, f'{key}/{floor}/setup: unsaturated window ({eligible})'
            expected[key, floor] = connection.execute(
                f'SELECT system_id64, {key}_weighted_e4 FROM v3_derived.system_archetype '
                f'WHERE derived_generation_id=%s AND {key}_score >= %s '
                f'ORDER BY {key}_weighted_e4 DESC, system_id64 ASC LIMIT 10000',
                (GENERATION, floor),
            ).fetchall()
            assert len(expected[key, floor]) == 10_000, f'{key}/{floor}/setup: order oracle size'
    return expected


async def _asyncpg_pool(database):
    import asyncpg
    from psycopg.conninfo import conninfo_to_dict

    settings = conninfo_to_dict(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'])
    return await asyncpg.create_pool(
        host=settings.get('host'), port=int(settings.get('port', 5432)),
        user=settings.get('user'), password=settings.get('password'),
        database=database, min_size=1, max_size=1, statement_cache_size=0,
    )


def _plan_nodes(node):
    yield node
    for child in node.get('Plans', ()):
        yield from _plan_nodes(child)


def _execute_arguments(params):
    """EXECUTE arguments must be literals; accept only exact ints, never bools."""
    if any(type(param) is not int for param in params):
        raise TypeError('prepared-statement arguments must be exact ints')
    return '(' + ', '.join(str(param) for param in params) + ')' if params else ''


async def _explain_json(connection, sql):
    raw = await connection.fetchval(f'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)\n{sql}')
    return (json.loads(raw) if isinstance(raw, str) else raw)[0]


def _store_warm_explain(measurement, document):
    measurement['warm_explain_json'] = json.dumps(document, separators=(',', ':'), sort_keys=True)


def _write_receipt(destination, receipt):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def test_receipt_stores_compact_warm_explain_json(tmp_path):
    document = {'Plan': {'Plans': [], 'Node Type': 'Result'}, 'Execution Time': 1.25}
    measurement = {}
    _store_warm_explain(measurement, document)
    destination = tmp_path / 'receipt.json'
    _write_receipt(destination, {'measurements': [measurement]})
    stored = json.loads(destination.read_text(encoding='utf-8'))['measurements'][0]['warm_explain_json']
    assert stored == '{"Execution Time":1.25,"Plan":{"Node Type":"Result","Plans":[]}}'
    assert json.loads(stored) == document


@pytest.mark.parametrize(('params', 'expected'), [([50, 9950], '(50, 9950)'), ([], '')])
def test_execute_arguments_renders_integer_literals(params, expected):
    assert _execute_arguments(params) == expected


@pytest.mark.parametrize('param', [True, 1.0, '1', None])
def test_execute_arguments_rejects_non_ints(param):
    with pytest.raises(TypeError, match='must be exact ints'):
        _execute_arguments([50, param])


def _total_rows(node):
    # EXPLAIN's Actual Rows is per loop: a one-row probe repeated a million
    # times is not bounded work. Missing instrumentation fails closed.
    return node.get('Actual Rows', float('inf')) * node.get('Actual Loops', float('inf'))


def _check(condition, message, failures):
    if not condition:
        failures.append(message)


def _plan_evidence(document, key, floor, query, label, failures):
    context = f'{key}/{floor}/{query}/{label}'
    nodes = list(_plan_nodes(document['Plan']))
    index = f'system_archetype_{key}_{FLOORS[floor]}_weighted'
    bound = 10_001 if query == 'count' else 10_000
    windows = [node for node in nodes if node.get('Index Name') == index]
    _check(len(windows) == 1, f'{context}: expected exactly one window on {index}', failures)
    for node in windows:
        _check(node['Node Type'] == 'Index Only Scan', f'{context}: window is not index-only', failures)
        _check(node.get('Heap Fetches') == 0, f'{context}: window heap fetches are not zero', failures)
        _check(node.get('Actual Loops') == 1 and 0 < _total_rows(node) <= bound,
               f'{context}: window exceeds {bound} rows or did not execute once', failures)
    relations = [node for node in nodes if node.get('Relation Name') in {
        'system_search', 'system_archetype',
    }]
    for node in relations:
        _check('Seq Scan' not in node['Node Type'],
               f'{context}: sequential scan on {node["Relation Name"]}', failures)
        _check(_total_rows(node) <= bound,
               f'{context}: relation scan exceeds {bound} total rows', failures)
    sorts = [node for node in nodes if node['Node Type'] in {'Sort', 'Incremental Sort'}]
    sort_inputs = [_total_rows(child) for node in sorts for child in node.get('Plans', ())
                   if child.get('Parent Relationship') not in {'InitPlan', 'SubPlan'}]
    fetches = [node for node in relations if node.get('Relation Name') == 'system_archetype'
               and node.get('Index Name') != index]
    if query != 'count':
        _check(bool(sorts) and bool(sort_inputs), f'{context}: missing page sort input', failures)
        _check(all(rows <= 10_000 for rows in sort_inputs),
               f'{context}: sort consumes more than 10000 rows', failures)
        _check(bool(fetches), f'{context}: missing per-page archetype fetch', failures)
        for node in fetches:
            _check(node['Node Type'] in {'Index Scan', 'Index Only Scan'}
                   and bool(node.get('Index Name')),
                   f'{context}: per-row fetch is not an index scan', failures)
            _check(0 < _total_rows(node) <= 50 and 0 < node.get('Actual Loops', 0) <= 50,
                   f'{context}: per-row fetch exceeds page size 50 or did not execute', failures)

    def scan_summary(node):
        return {
            'node_type': node['Node Type'], 'index_name': node.get('Index Name'),
            'heap_fetches': node.get('Heap Fetches'), 'actual_rows': node.get('Actual Rows'),
            'actual_loops': node.get('Actual Loops'), 'total_rows': _total_rows(node),
        }

    return {
        'window': [scan_summary(node) for node in windows],
        'sort_input_rows': sort_inputs,
        'fetch': [scan_summary(node) for node in fetches],
        # Root counters already include descendants: summing nodes double-counts.
        'shared_hit_blocks': document['Plan'].get('Shared Hit Blocks', 0),
        'shared_read_blocks': document['Plan'].get('Shared Read Blocks', 0),
        'planning_shared_hit_blocks': document.get('Planning', {}).get('Shared Hit Blocks', 0),
        'planning_shared_read_blocks': document.get('Planning', {}).get('Shared Read Blocks', 0),
    }


def _query(key, floor, query):
    options = dict(
        picked_archetype=key, picked_economy=None, hard_filters={},
        reference_coords=None, min_score=floor,
    )
    if query == 'count':
        return build_count_query(archetypes.PROFILE_SPEC, **options)
    return build_ranked_query(
        archetypes.PROFILE_SPEC, **options, limit=50, offset=QUERIES[query][0],
    )


async def _run(pool, sql, params, *, context, failures, check_results=True):
    execute_sql = f'EXECUTE {PREPARED_STATEMENT}{_execute_arguments(params)}'
    async with pool.acquire() as connection:
        prepared = False
        try:
            async with connection.transaction(isolation='repeatable_read', readonly=True):
                await connection.execute('SET LOCAL plan_cache_mode = force_generic_plan')
                await connection.execute(f'PREPARE {PREPARED_STATEMENT} AS {sql}')
                prepared = True
                document = await _explain_json(connection, execute_sql)
                counters = await connection.fetchrow(
                    'SELECT generic_plans, custom_plans FROM pg_prepared_statements WHERE name = $1',
                    PREPARED_STATEMENT,
                )
                plan_cache = (dict(counters) if counters is not None else
                              {'generic_plans': None, 'custom_plans': None})
                _check(plan_cache['generic_plans'] == 1 and plan_cache['custom_plans'] == 0,
                       f'{context}: expected generic_plans=1 and custom_plans=0; got {plan_cache}',
                       failures)
                # EXPLAIN discards results. Verify them in the same snapshot,
                # after the cold measurement and its first-use counters.
                rows = await connection.fetch(execute_sql) if check_results else []
        finally:
            # PREPARE survives commit/rollback; clean up before pool release.
            # A failed PREPARE stays fatal and never reuses an existing name.
            if prepared:
                await connection.execute(f'DEALLOCATE {PREPARED_STATEMENT}')
    return document, rows, plan_cache


async def _server_evidence(pool):
    async with pool.acquire() as connection:
        async with connection.transaction(isolation='repeatable_read', readonly=True):
            await connection.execute('SET LOCAL plan_cache_mode = force_generic_plan')
            settings = {name: await connection.fetchval('SELECT current_setting($1)', name)
                        for name in SETTINGS}
            started = await connection.fetchval('SELECT pg_postmaster_start_time()')
    return settings, started.isoformat()


def _run_evidence(document, rows, plan_cache, expected, key, floor, query, label, failures):
    plan = _plan_evidence(document, key, floor, query, label, failures)
    context = f'{key}/{floor}/{query}/{label}'
    if query == 'count':
        _check(len(rows) == 1 and rows[0][0] == 10_001,
               f'{context}: count did not return 10001 sentinel', failures)
    else:
        offset = QUERIES[query][0]
        actual = [(row['system_id64'], row['selected_archetype_weighted_e4']) for row in rows]
        _check(len(actual) == 50, f'{context}: expected 50 results', failures)
        _check(actual == expected[offset:offset + 50],
               f'{context}: page does not continue canonical weighted DESC/id64 ASC order', failures)
    planning = document['Planning Time']
    execution = document['Execution Time']
    return {'planning_ms': planning, 'execution_ms': execution,
            'total_ms': planning + execution, 'plan_summary': plan, 'plan_cache': plan_cache}


def _restart(command):
    # Operator-supplied command for the already local-guarded disposable service.
    # Capture output: neither it nor the command (possibly containing connection
    # details) belongs in the receipt or pytest's failure message.
    subprocess.run(command, shell=True, timeout=120, check=True, capture_output=True)


@pytest.mark.asyncio
async def test_selected_archetype_rankings_representative_scale(monkeypatch):
    restart_command = os.environ.get('EDF_RANKINGS_SCALE_RESTART_CMD', '').strip()
    if not restart_command:
        pytest.fail('EDF_RANKINGS_SCALE_RESTART_CMD is required: a receipt without cold timings is not a passing receipt.',
                    pytrace=False)
    receipt = {
        'schema': 'ed-finder/v3-archetype-rankings-scale-proof/v1',
        'git_head_sha': subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip(),
        'ranking_version': RANKING_VERSION, 'ranking_sha256': ranking_sha256(),
        'seed': SEED, 'row_counts': {}, 'eligible_counts': [], 'settings': {},
        'cold_label': ('io-cold' if os.environ.get('EDF_RANKINGS_SCALE_COLD_LABEL') == 'io-cold'
                       else 'buffer-cold'),
        'explain_format': (
            'prepared statement measured with EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) EXECUTE '
            'under force_generic_plan; generic plan proven for every run by pg_prepared_statements; '
            'warm_median_compact_json_same_execution; cold_plan_summary_only'
        ),
        'measurements': [], 'failures': [], 'passed': False,
    }
    failures = receipt['failures']
    context = 'all archetypes/all floors/setup'
    try:
        with _restart_safe_database(monkeypatch) as connection:
            version = connection.execute('SHOW server_version').fetchone()[0]
            receipt['server_version'] = version
            version_number = int(connection.execute('SHOW server_version_num').fetchone()[0])
            assert 180000 <= version_number < 190000, f'{context}: PostgreSQL 18 required'
            _seed(connection)
            expected = _fixture_evidence(connection, receipt)
            database = connection.info.dbname
            connection.close()
            pool = await _asyncpg_pool(database)
            try:
                receipt['settings'], receipt['server_started_at'] = await _server_evidence(pool)
                last_started = receipt['server_started_at']
                assert receipt['settings']['enable_seqscan'] == 'on', (
                    f'{context}: enable_seqscan must not be forced off'
                )
                for key in ARCHETYPE_KEYS:
                    for floor in FLOORS:
                        for query, (_, warm_budget, cold_budget) in QUERIES.items():
                            context = f'{key}/{floor}/{query}'
                            measurement = {
                                'archetype': key, 'floor': floor, 'query': query,
                                'warm_budget_ms': warm_budget, 'cold_budget_ms': cold_budget,
                                'warm_runs': [], 'warm_median_ms': None, 'cold_run': None,
                                'passed': False, 'failures': [],
                            }
                            receipt['measurements'].append(measurement)
                            sql, params = _query(key, floor, query)
                            await _run(  # One discarded warm-up.
                                pool, sql, params, context=f'{context}/warm-up',
                                failures=measurement['failures'], check_results=False,
                            )
                            documents = []
                            for run in range(5):
                                document, rows, plan_cache = await _run(
                                    pool, sql, params, context=f'{context}/warm-{run + 1}',
                                    failures=measurement['failures'],
                                )
                                documents.append(document)
                                measurement['warm_runs'].append(_run_evidence(
                                    document, rows, plan_cache, expected[key, floor], key, floor, query,
                                    f'warm-{run + 1}', measurement['failures'],
                                ))
                            totals = [run['total_ms'] for run in measurement['warm_runs']]
                            warm_median = median(totals)
                            measurement['warm_median_ms'] = warm_median
                            median_index = totals.index(warm_median)
                            measurement['warm_median_run'] = median_index + 1
                            _store_warm_explain(measurement, documents[median_index])
                            _check(warm_median <= warm_budget,
                                   f'{context}: warm median {warm_median:.3f} ms > {warm_budget} ms',
                                   measurement['failures'])

                        # Exercise the real route's response-level sentinel too,
                        # outside all timed runs. No private helpers from tests.
                        context = f'{key}/{floor}/count/route'
                        result = await archetypes._archetype_rankings_v3(
                            archetype=key, min_score=floor, galaxy_region=None,
                            max_distance_ly=None, has_elw=None, min_slots=None,
                            max_contamination=None, limit=50, offset=0, pool=pool,
                        )
                        assert result['total'] == 10_000 and result['is_truncated'] is True, (
                            f'{context}: route must report total=10000 and is_truncated=true'
                        )
            finally:
                await pool.close()

            # No existing seed/admin/pool connection spans a restart. A fresh
            # pool is opened only AFTER each command has returned ready.
            for measurement in receipt['measurements']:
                key, floor, query = (measurement[name] for name in ('archetype', 'floor', 'query'))
                context = f'{key}/{floor}/{query}/cold'
                _restart(restart_command)
                pool = await _asyncpg_pool(database)
                try:
                    sql, params = _query(key, floor, query)
                    document, rows, plan_cache = await _run(
                        pool, sql, params, context=f'{key}/{floor}/{query}/{receipt["cold_label"]}',
                        failures=measurement['failures'],
                    )
                    measurement['cold_run'] = _run_evidence(
                        document, rows, plan_cache, expected[key, floor], key, floor, query,
                        receipt['cold_label'], measurement['failures'],
                    )
                    # Read these AFTER the cold EXPLAIN. A no-op command is not
                    # a restart, and a settings reload must not silently make
                    # the warm/cold comparison describe different configurations.
                    settings, started = await _server_evidence(pool)
                    measurement['cold_run']['settings'] = settings
                    measurement['cold_run']['server_started_at'] = started
                    _check(started != last_started, f'{context}: server did not restart',
                           measurement['failures'])
                    _check(settings == receipt['settings'], f'{context}: server settings changed',
                           measurement['failures'])
                    last_started = started
                    cold_ms = measurement['cold_run']['total_ms']
                    budget = measurement['cold_budget_ms']
                    _check(cold_ms <= budget,
                           f'{context}: {receipt["cold_label"]} {cold_ms:.3f} ms > {budget} ms',
                           measurement['failures'])
                finally:
                    await pool.close()
                measurement['passed'] = not measurement['failures']
    except AssertionError as exc:
        failures.append(str(exc))
    except Exception as exc:
        # Database/subprocess exceptions can contain credentials, hostnames or
        # the restart command. Record only the class and measurement identity.
        failures.append(f'{context}: {type(exc).__name__} (connection/command details omitted)')
    finally:
        for measurement in receipt['measurements']:
            failures.extend(measurement['failures'])
        complete = len(receipt['measurements']) == 72 and all(
            len(item['warm_runs']) == 5 and item['cold_run'] is not None and item['passed']
            for item in receipt['measurements']
        )
        receipt['passed'] = complete and not failures
        path = os.environ.get('EDF_RANKINGS_SCALE_RECEIPT')
        if path:
            _write_receipt(Path(path), receipt)
    if not receipt['passed']:
        pytest.fail('\n'.join(failures) or f'{context}: incomplete 72-measurement receipt', pytrace=False)
