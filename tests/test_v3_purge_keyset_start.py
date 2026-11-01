"""Copy-and-drop keyset start (migration 022) on disposable PostgreSQL 18, never production.

Reuses the 019 fixtures (canonical_database, the chain through 016, then 019,
020, 021 and 022 by the payload owner). Production copy-economy-opportunity
(runs 41140926027 and 41155213939) slowed from 2.92 s to 6.85 s per chunk:
019's chunk read and 021's verification re-read paired a row comparison led by
derived_generation_id with a separate equality, so the equality positioned
every chunk's btree scan at the first survivor entry. 022's predicate bounds
the generation with <= so the row comparison is the start key, and a purge
authorized before 022 accepts exactly 022's own ledger row.
"""
import json
import os
from uuid import UUID

import psycopg
from psycopg.conninfo import make_conninfo
import pytest

from tests import test_v3_purge_copy_and_drop as copy_tests
from tests.helpers.purge_pg import canonical_database, connect
from tests.test_v3_governed_derived_purge import MIGRATIONS, RELATIONS, SURVIVOR, installed_purge
from tests.test_v3_purge_copy_and_drop import (
    _authorize, _owner, abandon, build, chunk, events, finish, prepare, staged, vacuum, verify,
)

superuser_database = copy_tests.superuser_database  # fixture: per-test database, 001-016 chain, 019-022

KEYSET = '022_v3_purge_keyset_start.sql'
REPLACED = {
    'v3_meta.purge_copy_chunk(uuid,text,integer)': (True, ['lock_timeout=5s', 'search_path=pg_catalog',
                                                           'statement_timeout=60s'], True),
    'v3_meta.purge_copy_verify(uuid,text)': (True, ['lock_timeout=5s', 'search_path=pg_catalog'], True),
    'v3_meta.purge_assert_request(uuid)': (False, ['search_path=pg_catalog'], False),
}


@pytest.fixture
def before_022():
    """The production lineage before 022: through 021, no keyset helper."""
    with canonical_database() as data:
        with installed_purge(data[0], apply_chain=True) as installed:
            copy_tests._install_copy(installed, keyset=False)
            yield (installed, *data[1:])


def _install_022(c):
    _owner(c).execute((MIGRATIONS / KEYSET).read_text())


def _ledger(c, name):
    """Record a ledger row the way the migration runner does (any digest)."""
    _owner(c).execute('INSERT INTO v3_meta.schema_migration(migration_name, migration_sha256) VALUES (%s, %s)',
                      (name, (name.encode() * 32)[:32]))


def test_replaced_functions_keep_their_owner_settings_and_grants(superuser_database):
    c = _owner(superuser_database[0])
    for signature, (definer, settings, executor_grant) in REPLACED.items():
        prosecdef, config, executor, public, owner = c.execute(
            """SELECT prosecdef, proconfig,
                      has_function_privilege('v3_derived_purge_executor', oid, 'EXECUTE'),
                      has_function_privilege('public', oid, 'EXECUTE'), proowner::regrole::text
               FROM pg_proc WHERE oid=%s::regprocedure""", (signature,)).fetchone()
        assert prosecdef is definer and sorted(config) == settings, signature
        assert executor is executor_grant and public is False, signature
        assert owner == c.execute(
            "SELECT proowner::regrole::text FROM pg_proc WHERE oid='v3_meta.purge_copy_prepare(uuid,text)'::regprocedure"
        ).fetchone()[0], signature
    definition = c.execute("SELECT pg_get_functiondef('v3_meta.purge_copy_chunk(uuid,text,integer)'::regprocedure)").fetchone()[0]
    assert 'v3_meta.purge_copy_keyset(code_,false)' in definition and 'derived_generation_id=$1%2$s' not in definition
    definition = c.execute("SELECT pg_get_functiondef('v3_meta.purge_copy_verify(uuid,text)'::regprocedure)").fetchone()[0]
    assert 'v3_meta.purge_copy_keyset(code_,true)' in definition and 'derived_generation_id=$1 AND %4$s' not in definition
    # The helper is internal: neither the executor nor PUBLIC may call it.
    executor, public = c.execute(
        """SELECT has_function_privilege('v3_derived_purge_executor', oid, 'EXECUTE'),
                  has_function_privilege('public', oid, 'EXECUTE')
           FROM pg_proc WHERE oid='v3_meta.purge_copy_keyset(text,boolean)'::regprocedure""").fetchone()
    assert executor is False and public is False


@pytest.mark.parametrize('code,predicate', (
    ('economy_opportunity',
     'derived_generation_id<=$1 AND (derived_generation_id,system_id64,body_pk,economy_ordinal) > '
     '($1,$2[1],$2[2],$2[3]::smallint)'),
    ('body_mechanics', 'derived_generation_id<=$1 AND (derived_generation_id,system_id64,body_pk) > ($1,$2[1],$2[2])'),
    ('system_search', 'derived_generation_id<=$1 AND (derived_generation_id,system_id64) > ($1,$2[1])'),
    ('system_rating_vector', 'derived_generation_id<=$1 AND (derived_generation_id,system_id64) > ($1,$2[1])'),
))
def test_keyset_helper_text(superuser_database, code, predicate):
    c = _owner(superuser_database[0])
    assert c.execute('SELECT v3_meta.purge_copy_keyset(%s,false)', (code,)).fetchone()[0] == predicate
    assert c.execute('SELECT v3_meta.purge_copy_keyset(%s,true)', (code,)).fetchone()[0] == predicate.replace(') > (', ') >= (')
    with pytest.raises(psycopg.errors.RaiseException, match='keyset bound required'):
        c.execute('SELECT v3_meta.purge_copy_keyset(%s,NULL)', (code,))
    c.execute('ROLLBACK')
    with pytest.raises(psycopg.errors.RaiseException, match='nonallowlisted purge relation'):
        c.execute("SELECT v3_meta.purge_copy_keyset('system_archetype',false)")
    c.execute('ROLLBACK')


_PROBES = iter(range(1, 1000))


def _index_buffers(c, predicate, generation, key, limit):
    """Shared buffers one chunk read touches, and the rows it returns."""
    name = 'keyset_probe_%d' % next(_PROBES)
    c.execute('PREPARE ' + name + '(uuid, bigint[]) AS SELECT * FROM keyset_probe.economy_opportunity WHERE '
              + predicate + ' ORDER BY derived_generation_id,system_id64,body_pk,economy_ordinal LIMIT '
              + str(int(limit)))
    # EXECUTE takes literals, not bind parameters; every value here is the test's own.
    arguments = "'{}'::uuid, ARRAY[{}]::bigint[]".format(UUID(str(generation)), ','.join(str(int(k)) for k in key))
    plan = c.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) EXECUTE ' + name + '(' + arguments + ')').fetchone()[0]
    node = plan[0]['Plan']
    rows = c.execute('EXECUTE ' + name + '(' + arguments + ')').fetchall()
    c.execute('DEALLOCATE ' + name)
    return node['Shared Hit Blocks'] + node['Shared Read Blocks'], rows, json.dumps(plan)


def test_chunk_read_cost_does_not_grow_with_its_position(superuser_database):
    """The production failure in miniature: 019's predicate reads every
    survivor index entry before the chunk; 022's helper reads the chunk only."""
    c = _owner(superuser_database[0])
    c.execute('CREATE SCHEMA keyset_probe')
    c.execute('''CREATE TABLE keyset_probe.economy_opportunity (
                   derived_generation_id uuid NOT NULL, system_id64 bigint NOT NULL, body_pk bigint NOT NULL,
                   economy_ordinal smallint NOT NULL, payload text,
                   PRIMARY KEY (derived_generation_id, system_id64, body_pk, economy_ordinal))''')
    before, after = '00000000-0000-4000-8000-000000000001', 'ffffffff-ffff-4fff-bfff-ffffffffffff'
    for generation, systems in ((before, 20_000), (SURVIVOR, 50_000), (after, 20_000)):
        c.execute('''INSERT INTO keyset_probe.economy_opportunity
                     SELECT %s, s, s*10+b, o, 'x' FROM generate_series(1,%s) s, generate_series(1,4) b,
                     generate_series(1,2) o''', (generation, systems))
    c.execute('ANALYZE keyset_probe.economy_opportunity')
    c.execute('SELECT count(*) FROM keyset_probe.economy_opportunity')
    new = c.execute("SELECT v3_meta.purge_copy_keyset('economy_opportunity',false)").fetchone()[0]
    old = ('derived_generation_id=$1 AND (derived_generation_id,system_id64,body_pk,economy_ordinal) > '
           '($1,$2[1],$2[2],$2[3]::smallint)')
    early, late = [1_250, 12_504, 2], [43_750, 437_504, 2]  # after 10,000 and 350,000 survivor rows
    costs = {}
    for name, predicate in (('old', old), ('new', new)):
        for position, key in (('early', early), ('late', late)):
            # Twice, so the second read is measured with the pages cached.
            _index_buffers(c, predicate, SURVIVOR, key, 10_000)
            costs[name, position], rows, plan = _index_buffers(c, predicate, SURVIVOR, key, 10_000)
            assert len(rows) == 10_000 and 'Index Scan' in plan, plan
            assert tuple(rows[0][1:4]) > tuple(key), plan
            costs[name, position, 'rows'] = rows
    # Same rows either way.
    assert costs['old', 'early', 'rows'] == costs['new', 'early', 'rows']
    assert costs['old', 'late', 'rows'] == costs['new', 'late', 'rows']
    # 019's read grows with the survivor rows before the chunk; 022's does not.
    assert costs['old', 'late'] > 3 * costs['old', 'early'], costs
    assert costs['new', 'late'] <= costs['new', 'early'] + 10, costs
    assert costs['new', 'early'] <= costs['old', 'early'], costs


@pytest.mark.parametrize('rows', (1, 3))
def test_chunks_copied_before_022_verify_after_it(before_022, rows):
    c = before_022[0]
    purge, _ = _authorize(before_022)
    for code in RELATIONS:
        prepare(c, purge, code)
        if code == RELATIONS[0]:
            # The first chunk has no keyset; the second uses 019's row
            # comparison. Both are copied before 022, the rest after it.
            for _ in range(2):
                assert chunk(c, purge, code, rows) == rows
            _install_022(c)
        while chunk(c, purge, code, rows) == rows:
            pass
        build(c, purge, code)
        vacuum(c, code)
        verify(c, purge, code)
        assert events(c, code)[-1] == 'VERIFIED'
        finish(c, purge, code)
        assert events(c, code)[-1] == 'DROPPED'


def _ledger_rows(c):
    return [row[0] for row in _owner(c).execute(
        'SELECT migration_name FROM v3_meta.schema_migration ORDER BY migration_name').fetchall()]


def test_a_purge_authorized_before_022_accepts_exactly_its_ledger_row(before_022):
    c = before_022[0]
    for name in ('016_v3_governed_derived_purge.sql', '019_v3_purge_copy_and_drop.sql',
                 '020_v3_purge_swap_lock_order.sql', '021_v3_purge_long_phase_bounds.sql'):
        if name not in _ledger_rows(c):
            _ledger(c, name)
    purge, _ = _authorize(before_022)
    code = RELATIONS[0]
    prepare(c, purge, code)
    assert chunk(c, purge, code, 1) == 1
    # Without 022 installed, any new ledger row is drift, 022's included.
    _ledger(c, KEYSET)
    with pytest.raises(psycopg.errors.RaiseException, match='purge schema ledger drift'):
        chunk(c, purge, code, 1)
    c.execute('ROLLBACK')
    _owner(c).execute('DELETE FROM v3_meta.schema_migration WHERE migration_name=%s', (KEYSET,))
    # The governed apply: 022's DDL and its ledger row together.
    _install_022(c)
    _ledger(c, KEYSET)
    assert chunk(c, purge, code, 1) == 1
    # Any other row still refuses, beside 022's or in its place.
    _ledger(c, '023_v3_unreviewed.sql')
    with pytest.raises(psycopg.errors.RaiseException, match='purge schema ledger drift'):
        chunk(c, purge, code, 1)
    c.execute('ROLLBACK')
    _owner(c).execute('DELETE FROM v3_meta.schema_migration WHERE migration_name=%s', ('023_v3_unreviewed.sql',))
    original = _owner(c).execute('SELECT migration_sha256 FROM v3_meta.schema_migration WHERE migration_name=%s',
                                 ('021_v3_purge_long_phase_bounds.sql',)).fetchone()[0]
    _owner(c).execute('UPDATE v3_meta.schema_migration SET migration_sha256=%s WHERE migration_name=%s',
                      (b'z' * 32, '021_v3_purge_long_phase_bounds.sql'))
    with pytest.raises(psycopg.errors.RaiseException, match='purge schema ledger drift'):
        chunk(c, purge, code, 1)
    c.execute('ROLLBACK')
    _owner(c).execute('UPDATE v3_meta.schema_migration SET migration_sha256=%s WHERE migration_name=%s',
                      (original, '021_v3_purge_long_phase_bounds.sql'))
    # The whole route then completes for every relation.
    while chunk(c, purge, code, 2) == 2:
        pass
    build(c, purge, code)
    vacuum(c, code)
    verify(c, purge, code)
    finish(c, purge, code)
    for code in RELATIONS[1:]:
        staged(c, purge, code)
        finish(c, purge, code)
    assert {code: events(c, code)[-1] for code in RELATIONS} == dict.fromkeys(RELATIONS, 'DROPPED')


def test_a_purge_authorized_after_022_compares_the_whole_ledger(superuser_database):
    c = superuser_database[0]
    for name in ('021_v3_purge_long_phase_bounds.sql', KEYSET):
        if name not in _ledger_rows(c):
            _ledger(c, name)
    purge, _ = _authorize(superuser_database)
    code = RELATIONS[0]
    prepare(c, purge, code)
    assert chunk(c, purge, code, 1) == 1
    # Removing 022's row is drift for a request that froze it.
    digest = _owner(c).execute('SELECT migration_sha256 FROM v3_meta.schema_migration WHERE migration_name=%s',
                               (KEYSET,)).fetchone()[0]
    _owner(c).execute('DELETE FROM v3_meta.schema_migration WHERE migration_name=%s', (KEYSET,))
    with pytest.raises(psycopg.errors.RaiseException, match='purge schema ledger drift'):
        chunk(c, purge, code, 1)
    c.execute('ROLLBACK')
    _owner(c).execute('INSERT INTO v3_meta.schema_migration(migration_name, migration_sha256) VALUES (%s, %s)',
                      (KEYSET, digest))
    assert chunk(c, purge, code, 1) == 1
    _ledger(c, '023_v3_unreviewed.sql')
    with pytest.raises(psycopg.errors.RaiseException, match='purge schema ledger drift'):
        chunk(c, purge, code, 1)
    c.execute('ROLLBACK')
    # Recovery never compared the ledger: the partial copy can still be abandoned.
    abandon(c, purge, code)
    assert events(c, code)[-1] == 'FAILED_STOP'


def test_installation_refuses_a_second_time(before_022):
    c = _owner(before_022[0])
    _install_022(c)
    with pytest.raises(psycopg.errors.RaiseException, match='keyset start is already installed'):
        _install_022(c)
    c.execute('ROLLBACK')


def test_installation_requires_the_owner_of_the_replaced_functions(before_022):
    c = _owner(before_022[0])
    admin = connect(make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'],
                                  dbname=c.info.dbname), autocommit=True)
    try:
        admin.execute('DROP ROLE IF EXISTS keyset_outsider')
        admin.execute('CREATE ROLE keyset_outsider NOLOGIN')
        admin.execute('GRANT USAGE ON SCHEMA v3_meta TO keyset_outsider')
        admin.execute('SET ROLE keyset_outsider')
        with pytest.raises(psycopg.errors.RaiseException,
                           match='must be installed by the owner of the 016 and 019 functions'):
            admin.execute((MIGRATIONS / KEYSET).read_text())
        admin.execute('ROLLBACK')
        admin.execute('RESET ROLE')
    finally:
        admin.execute('RESET ROLE')
        admin.execute('DROP OWNED BY keyset_outsider')
        admin.execute('DROP ROLE keyset_outsider')
        admin.close()
    assert c.execute("SELECT to_regprocedure('v3_meta.purge_copy_keyset(text,boolean)')").fetchone()[0] is None
