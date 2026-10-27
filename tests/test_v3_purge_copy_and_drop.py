"""Copy-and-drop purge capability (019) on disposable PostgreSQL 18, never production.

The canonical_database import also makes CI's PG18 discovery select this file.
Fixtures reuse 016's: a per-test database, the migration chain through 016,
two authorized target generations and a published survivor.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
from time import monotonic

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v3_archetype_plan_probe import PRIMARY_INDEXES  # noqa: E402
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402
from tests.test_v3_governed_derived_purge import (  # noqa: E402
    CHAIN, EXECUTOR, MIGRATIONS, RELATIONS, SURVIVOR, TARGETS,
    _count, _plan, _seed, _sign_plan, installed_purge,
)

COPY_MIGRATION = '019_v3_purge_copy_and_drop.sql'
# 020 replaces the swap's locking; the copy capability is 019 plus 020.
LOCK_ORDER_MIGRATION = '020_v3_purge_swap_lock_order.sql'
COPY_KINDS = {
    'COPY_STARTED', 'CHUNK_COPIED', 'INDEXES_BUILT', 'VERIFIED', 'SWAPPED',
    'SWAPPED_BACK', 'FK_VALIDATED', 'DROPPED', 'COMPLETED', 'FAILED_STOP',
}
SEARCH_INDEXES = {
    'system_search_pkey', 'system_search_position_gist',
    'system_search_name_lower', 'system_search_region',
}
VECTOR_CHILDREN = {
    'v3_derived.body_mechanics', 'v3_derived.system_search',
    'v3_derived.system_archetype', 'v3_spatial.cluster_member',
}
PUBLIC_FUNCTIONS = (
    'purge_copy_prepare(uuid,text)', 'purge_copy_chunk(uuid,text,integer)',
    'purge_copy_build_indexes(uuid,text)', 'purge_copy_verify(uuid,text)',
    'purge_copy_swap(uuid,text)', 'purge_copy_swap_back(uuid,text)',
    'purge_copy_validate_fks(uuid,text)', 'purge_copy_drop(uuid,text)',
    'purge_copy_abandon(uuid,text,jsonb)', 'purge_copy_record_failure(uuid,text,jsonb)',
    'purge_copy_complete(uuid)', 'purge_copy_status()', 'purge_copy_backup_skip()',
    'purge_copy_fingerprint(regclass)',
)


def _install_copy(connection):
    connection.execute((MIGRATIONS / COPY_MIGRATION).read_text())
    connection.execute((MIGRATIONS / LOCK_ORDER_MIGRATION).read_text())
    # Keep autovacuum workers off the new ledger, as 016's fixture does for v3_*.
    for table in ('derived_purge_copy_request', 'derived_purge_copy_event'):
        connection.execute(sql.SQL('ALTER TABLE {} SET (autovacuum_enabled=false)').format(
            sql.Identifier('v3_meta', table)))


@pytest.fixture(params=('superuser', 'non_superuser'))
def copy_database(request):
    with canonical_database() as data:
        with installed_purge(data[0], creator=request.param, apply_chain=True) as installed:
            _install_copy(installed)
            yield (installed, *data[1:])


@pytest.fixture
def superuser_database():
    with canonical_database() as data:
        with installed_purge(data[0], apply_chain=True) as installed:
            _install_copy(installed)
            yield (installed, *data[1:])


def _authorize(data, *, published=True):
    """Seed the survivor and two targets, then authorize one reviewed plan."""
    connection = data[0]
    _seed(data, survivor_products_published=published)
    plan = _plan(connection)
    if published:
        rows = _count(connection, 'v3_derived.system_search', SURVIVOR)
        plan['published_survivors'] = {
            'system_archetype_rows': _count(connection, 'v3_derived.system_archetype', SURVIVOR),
            'products': {'system_search': {'expected_rows': rows}},
        }
        plan = _sign_plan(connection, plan)
    connection.execute('SET ROLE v3_derived_purge_executor')
    ids = connection.execute('SELECT v3_meta.begin_derived_generation_purge(%s)', (Jsonb(plan),)).fetchone()[0]
    connection.execute('RESET ROLE')
    return ids[0], plan


def _x(connection, statement, *parameters):
    """Call a public copy function as the executor, never as the owner."""
    connection.execute('SET ROLE v3_derived_purge_executor')
    try:
        return connection.execute(statement, parameters).fetchone()[0]
    finally:
        if not connection.info.transaction_status == psycopg.pq.TransactionStatus.INERROR:
            connection.execute('RESET ROLE')


def _owner(connection):
    connection.execute('RESET ROLE')
    return connection


def prepare(c, purge, code):
    return _x(c, 'SELECT v3_meta.purge_copy_prepare(%s,%s)', purge, code)


def chunk(c, purge, code, rows):
    return _x(c, 'SELECT v3_meta.purge_copy_chunk(%s,%s,%s)', purge, code, rows)


def build(c, purge, code):
    return _x(c, 'SELECT v3_meta.purge_copy_build_indexes(%s,%s)', purge, code)


def verify(c, purge, code):
    return _x(c, 'SELECT v3_meta.purge_copy_verify(%s,%s)', purge, code)


def swap(c, purge, code):
    return _x(c, 'SELECT v3_meta.purge_copy_swap(%s,%s)', purge, code)


def swap_back(c, purge, code):
    return _x(c, 'SELECT v3_meta.purge_copy_swap_back(%s,%s)', purge, code)


def validate(c, purge, code):
    return _x(c, 'SELECT v3_meta.purge_copy_validate_fks(%s,%s)', purge, code)


def drop(c, purge, code):
    return _x(c, 'SELECT v3_meta.purge_copy_drop(%s,%s)', purge, code)


def abandon(c, purge, code):
    return _x(c, 'SELECT v3_meta.purge_copy_abandon(%s,%s,%s)', purge, code, Jsonb({'reason': 'test'}))


def skip(c):
    return _x(c, 'SELECT v3_meta.purge_copy_backup_skip()')


def vacuum(c, code):
    c.execute('SET ROLE v3_derived_purge_executor')
    c.execute(sql.SQL('VACUUM (FREEZE, ANALYZE) {}').format(sql.Identifier('v3_purge_staging', code)))
    c.execute('RESET ROLE')


def copy_all(c, purge, code, rows=2):
    prepare(c, purge, code)
    copied = 0
    while (n := chunk(c, purge, code, rows)) == rows:
        copied += n
    return copied + n


def staged(c, purge, code, rows=2):
    copy_all(c, purge, code, rows)
    build(c, purge, code)
    vacuum(c, code)
    return verify(c, purge, code)


def finish(c, purge, code):
    swap(c, purge, code)
    validate(c, purge, code)
    return drop(c, purge, code)


def events(c, code=None):
    statement = 'SELECT event_kind FROM v3_meta.derived_purge_copy_event'
    if code is None:
        return [row[0] for row in _owner(c).execute(statement + ' ORDER BY event_sequence').fetchall()]
    return [row[0] for row in _owner(c).execute(
        statement + ' WHERE relation_code=%s ORDER BY event_sequence', (code,)).fetchall()]


def oid(c, name):
    return _owner(c).execute('SELECT to_regclass(%s)::oid', (name,)).fetchone()[0]


def fingerprint(c, name):
    return _owner(c).execute('SELECT v3_meta.purge_copy_fingerprint(%s::regclass)', (name,)).fetchone()[0]


def mismatch(c, live, copy, mode='full'):
    return _owner(c).execute('SELECT v3_meta.purge_copy_fingerprint_mismatch(%s,%s,%s)',
                             (Jsonb(live), Jsonb(copy), mode)).fetchone()[0]


def state(c):
    """Ledger plus every relation, trigger and constraint the copy can touch."""
    _owner(c)
    return (
        c.execute('SELECT * FROM v3_meta.derived_purge_copy_request ORDER BY copy_id').fetchall(),
        c.execute('SELECT event_sequence,event_kind,relation_code FROM v3_meta.derived_purge_copy_event '
                  'ORDER BY event_sequence').fetchall(),
        c.execute('''SELECT n.nspname,c.relname,c.oid,c.relfilenode,c.reloptions::text,c.relacl::text
                     FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                     WHERE n.nspname IN ('v3_derived','v3_purge_staging','v3_retired','v3_app','v3_spatial')
                     ORDER BY 1,2''').fetchall(),
        c.execute('''SELECT t.tgrelid::regclass::text,t.tgname,t.tgenabled FROM pg_trigger t
                     JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                     WHERE n.nspname IN ('v3_derived','v3_purge_staging','v3_retired') ORDER BY 1,2''').fetchall(),
        c.execute('''SELECT k.conrelid::regclass::text,k.conname,k.confrelid,k.convalidated FROM pg_constraint k
                     JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                     WHERE n.nspname IN ('v3_derived','v3_purge_staging','v3_retired','v3_spatial')
                     ORDER BY 1,2''').fetchall(),
    )


def test_install_is_capability_only_and_grants_only_the_public_surface(copy_database):
    c = copy_database[0]
    assert _owner(c).execute(
        "SELECT count(*) FROM pg_class WHERE relnamespace IN ('v3_purge_staging'::regnamespace,'v3_retired'::regnamespace)",
    ).fetchone()[0] == 0
    assert _count(c, 'v3_meta.derived_purge_copy_request') == 0
    assert _count(c, 'v3_meta.derived_purge_copy_event') == 0
    assert skip(c) is False
    status = _x(c, 'SELECT v3_meta.purge_copy_status()')
    assert status == {'requests': [], 'staging_relations': [], 'retired_relations': [], 'backup_skip': False}
    c.execute('SET ROLE v3_derived_purge_executor')
    for signature in PUBLIC_FUNCTIONS:
        assert c.execute("SELECT has_function_privilege(current_user,%s,'EXECUTE')",
                         ('v3_meta.' + signature,)).fetchone()[0], signature
    for internal in ('purge_copy_relocate(text,regclass,text)', 'purge_copy_apply_reloptions(regclass,regclass,boolean)',
                     'purge_copy_context(uuid,boolean)', 'purge_copy_state(uuid,text)',
                     'purge_copy_lock_relocation(text,regclass)'):
        assert not c.execute("SELECT has_function_privilege(current_user,%s,'EXECUTE')",
                             ('v3_meta.' + internal,)).fetchone()[0], internal
    assert not c.execute(
        "SELECT has_table_privilege(current_user,'v3_meta.derived_purge_copy_event','INSERT')").fetchone()[0]
    assert c.execute("SELECT has_schema_privilege(current_user,'v3_purge_staging','USAGE')").fetchone()[0]
    assert not c.execute("SELECT has_schema_privilege(current_user,'v3_purge_staging','CREATE')").fetchone()[0]
    c.execute('RESET ROLE')
    kinds = c.execute(
        """SELECT pg_get_constraintdef(oid) FROM pg_constraint
           WHERE conrelid='v3_meta.derived_purge_copy_event'::regclass AND conname LIKE '%event_kind%'""",
    ).fetchone()[0]
    assert set(kinds.split("'")[1::2]) == COPY_KINDS
    # The fingerprint is never vacuous: it carries the live 001-016 shape.
    search = fingerprint(c, 'v3_derived.system_search')
    assert set(search['indexes']) == SEARCH_INDEXES
    assert {'product_insert', 'product_update', 'product_delete', 'product_truncate'} <= set(search['triggers'])
    assert 'guard_purge_delete' in search['triggers']['product_delete']['definition']
    assert len(search['columns']) == 38 and search['relation']['comment']
    assert sum(not item['validated'] for item in search['constraints'].values()) == 18
    assert [item for item in search['acl'] if item[1] == EXECUTOR] == [
        [search['relation']['owner'], EXECUTOR, privilege, False] for privilege in ('MAINTAIN', 'SELECT')]
    vector = fingerprint(c, 'v3_derived.system_rating_vector')
    assert set(vector['indexes']) == {'system_rating_vector_pkey', 'system_rating_chunk_idx'}
    assert {'immutable_insert', 'immutable_delete', 'immutable_truncate'} <= set(vector['triggers'])


def test_install_requires_016():
    with canonical_database() as data:
        connection = data[0]
        for name in CHAIN:
            connection.execute((MIGRATIONS / name).read_text())
        with pytest.raises(psycopg.errors.RaiseException, match='requires the governed purge migration 016'):
            connection.execute((MIGRATIONS / COPY_MIGRATION).read_text())
        connection.rollback()
        assert connection.execute("SELECT to_regnamespace('v3_purge_staging')").fetchone()[0] is None


# A new survivor key, so the statement-level production guard (not the
# primary key) is what refuses the write. FKs are deferred.
NEW_SURVIVOR_ROW = '''INSERT INTO v3_derived.{table}
    SELECT (jsonb_populate_record(NULL::v3_derived.{table},
            to_jsonb(s) || '{{"system_id64": 999999999999}}'::jsonb)).*
    FROM v3_retired.{table} s WHERE derived_generation_id=%s LIMIT 1'''


def _views_read(c):
    _owner(c)
    return (
        c.execute('SELECT count(*), sum(system_id64) FROM v3_app.system_search').fetchone(),
        c.execute('SELECT count(*), sum(potential_score) FROM v3_app.system_economy_rating').fetchone(),
    )


def _child_fks(c, parent):
    return {
        (row[0], row[1], row[2]) for row in _owner(c).execute(
            '''SELECT conrelid::regclass::text,confrelid::regclass::text,convalidated FROM pg_constraint
               WHERE confrelid=%s::regclass AND contype='f' AND conrelid<>confrelid''', (parent,)).fetchall()
    }


def test_full_copy_and_drop_keeps_survivors_and_drops_targets(copy_database):
    c = copy_database[0]
    purge, _ = _authorize(copy_database)
    survivors = {code: _count(c, 'v3_derived.' + code, SURVIVOR) for code in RELATIONS}
    assert all(survivors.values())
    targets = {code: sum(_count(c, 'v3_derived.' + code, target) for _, target in TARGETS) for code in RELATIONS}
    assert all(targets.values())
    before = {code: fingerprint(c, 'v3_derived.' + code) for code in RELATIONS}
    original = {code: oid(c, 'v3_derived.' + code) for code in RELATIONS}
    views = _views_read(c)
    assert views[0][0] == survivors['system_search'] and views[1][0] == 7 * survivors['system_rating_vector']
    for code in RELATIONS:
        assert skip(c) is False
        staged(c, purge, code)
        assert skip(c) is True
        copy_oid = oid(c, 'v3_purge_staging.' + code)
        assert mismatch(c, before[code], fingerprint(c, 'v3_purge_staging.' + code), 'staging') == []
        swap(c, purge, code)
        assert oid(c, 'v3_derived.' + code) == copy_oid
        assert oid(c, 'v3_retired.' + code) == original[code]
        assert skip(c) is True
        # Same catalog shape as the fresh 001-016 table; NOT VALID live checks
        # (010's Search counts) are the only tolerated difference.
        assert mismatch(c, before[code], fingerprint(c, 'v3_derived.' + code)) == []
        assert _views_read(c) == views
        if code == 'system_search':
            assert {row[0] for row in _owner(c).execute(
                "SELECT indexrelid::regclass::text FROM pg_index WHERE indrelid='v3_derived.system_search'::regclass",
            ).fetchall()} == {'v3_derived.' + name for name in SEARCH_INDEXES}
            assert PRIMARY_INDEXES['system_search'] in SEARCH_INDEXES
            assert _owner(c).execute(
                '''SELECT last_vacuum IS NOT NULL AND last_analyze IS NOT NULL FROM pg_stat_user_tables
                   WHERE schemaname='v3_derived' AND relname='system_search' ''').fetchone() == (True,)
            assert not all(value['validated'] for value in before[code]['constraints'].values())
            # The publication-gated view follows the new relation, not the retired one.
            assert c.execute(
                '''SELECT DISTINCT d.refobjid::regclass::text FROM pg_depend d JOIN pg_rewrite r ON r.oid=d.objid
                   WHERE r.ev_class='v3_app.system_search'::regclass AND d.refobjid IN
                   ('v3_derived.system_search'::regclass,'v3_retired.system_search'::regclass)''',
            ).fetchall() == [('v3_derived.system_search',)]
            # Production guards replaced the copy guard: the READY product refuses inserts.
            with pytest.raises(psycopg.errors.RaiseException, match='system_search product .* is not BUILDING'):
                c.execute(NEW_SURVIVOR_ROW.format(table='system_search'), (SURVIVOR,))
            with pytest.raises(psycopg.errors.RaiseException, match='insert-only'):
                c.execute('UPDATE v3_derived.system_search SET name=name')
            # 016's kept guard refuses every DELETE outside v3_derived.
            with pytest.raises(psycopg.errors.RaiseException, match='governed purge function context'):
                c.execute('DELETE FROM v3_retired.system_search')
        if code == 'system_rating_vector':
            assert _child_fks(c, 'v3_derived.system_rating_vector') == {
                (child, 'v3_derived.system_rating_vector', False) for child in VECTOR_CHILDREN}
            assert _child_fks(c, 'v3_retired.system_rating_vector') == set()
            with pytest.raises(psycopg.errors.RaiseException, match='immutable in state PUBLISHED'):
                c.execute(NEW_SURVIVOR_ROW.format(table='system_rating_vector'), (SURVIVOR,))
            with pytest.raises(psycopg.errors.RaiseException, match='retained relation DELETE is forbidden'):
                c.execute('DELETE FROM v3_retired.system_rating_vector')
        validate(c, purge, code)
        if code == 'system_rating_vector':
            assert _child_fks(c, 'v3_derived.system_rating_vector') == {
                (child, 'v3_derived.system_rating_vector', True) for child in VECTOR_CHILDREN}
        if code == 'body_mechanics':
            assert _child_fks(c, 'v3_derived.body_mechanics') == {
                ('v3_derived.economy_opportunity', 'v3_derived.body_mechanics', True)}
        drop(c, purge, code)
        assert oid(c, 'v3_retired.' + code) is None
        assert skip(c) is False
        assert _count(c, 'v3_derived.' + code) == survivors[code]
    assert _views_read(c) == views
    for code in RELATIONS:
        assert sum(_count(c, 'v3_derived.' + code, target) for _, target in TARGETS) == 0
        assert _count(c, 'v3_derived.' + code, SURVIVOR) == survivors[code]
    _x(c, 'SELECT v3_meta.purge_copy_complete(%s)', purge)
    assert events(c)[-1] == 'COMPLETED'
    assert set(events(c)) == COPY_KINDS - {'SWAPPED_BACK', 'FAILED_STOP'}
    status = _x(c, 'SELECT v3_meta.purge_copy_status()')
    assert status['requests'][0]['completed'] is True and status['backup_skip'] is False
    assert {value['copy_position'] for value in status['requests'][0]['relations'].values()} == {'dropped'}
    with pytest.raises(psycopg.errors.RaiseException, match='complete'):
        prepare(c, purge, 'system_search')


def test_copy_guard_refuses_every_write_outside_the_chunk_function(copy_database):
    c = copy_database[0]
    purge, _ = _authorize(copy_database)
    prepare(c, purge, 'system_search')
    assert chunk(c, purge, 'system_search', 1) == 1
    staging = 'v3_purge_staging.system_search'
    c.execute('SET ROLE v3_derived_purge_executor')
    for privilege in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE'):
        assert not c.execute('SELECT has_table_privilege(current_user,%s,%s)', (staging, privilege)).fetchone()[0]
    assert c.execute('SELECT has_table_privilege(current_user,%s,%s)', (staging, 'MAINTAIN')).fetchone()[0]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute('INSERT INTO v3_purge_staging.system_search SELECT * FROM v3_derived.system_search LIMIT 1')
    _owner(c)
    copied = _count(c, staging)
    # The owner, even with the chunk function's GUC spoofed, cannot write.
    for statement in (
        "SELECT set_config('v3.purge_copy_relation','system_search',false)",
    ):
        c.execute(statement)
    for statement, message in (
        ('''INSERT INTO v3_purge_staging.system_search SELECT * FROM v3_derived.system_search
            WHERE derived_generation_id=%s ORDER BY system_id64 DESC LIMIT 1''', 'governed purge copy chunk context'),
        ('UPDATE v3_purge_staging.system_search SET name=name WHERE derived_generation_id=%s', 'only governed chunk inserts'),
        ('DELETE FROM v3_purge_staging.system_search WHERE derived_generation_id=%s', 'only governed chunk inserts'),
    ):
        with pytest.raises(psycopg.errors.RaiseException, match=message):
            c.execute(statement, (SURVIVOR,))
    with pytest.raises(psycopg.errors.RaiseException, match='only governed chunk inserts'):
        c.execute('TRUNCATE v3_purge_staging.system_search')
    c.execute("SELECT set_config('v3.purge_copy_relation','',false)")
    assert _count(c, staging) == copied
    # Chunk bounds are 016's batch bound, and one chunk per transaction.
    for rows in (0, 100_001):
        with pytest.raises(psycopg.errors.RaiseException, match='chunk limit out of range'):
            chunk(c, purge, 'system_search', rows)
    with pytest.raises(psycopg.errors.RaiseException, match='one copy chunk per transaction'):
        with c.transaction():
            chunk(c, purge, 'system_search', 1)
            chunk(c, purge, 'system_search', 1)
    assert events(c, 'system_search') == ['COPY_STARTED', 'CHUNK_COPIED']


def test_wrong_relation_order_and_unknown_relations_are_refused(superuser_database):
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    for code in ('economy_opportunity', 'body_mechanics', 'system_rating_vector'):
        with pytest.raises(psycopg.errors.RaiseException, match='wrong copy-and-drop relation order'):
            prepare(c, purge, code)
    with pytest.raises(psycopg.errors.RaiseException, match='nonallowlisted purge relation'):
        prepare(c, purge, 'system_archetype')
    assert _count(c, 'v3_meta.derived_purge_copy_request') == 0
    staged(c, purge, 'system_search')
    # Search is swapped but not yet dropped: the next relation still waits.
    swap(c, purge, 'system_search')
    with pytest.raises(psycopg.errors.RaiseException, match='wrong copy-and-drop relation order'):
        prepare(c, purge, 'economy_opportunity')
    validate(c, purge, 'system_search')
    drop(c, purge, 'system_search')
    with pytest.raises(psycopg.errors.RaiseException, match='wrong copy-and-drop relation order'):
        prepare(c, purge, 'body_mechanics')
    prepare(c, purge, 'economy_opportunity')
    with pytest.raises(psycopg.errors.RaiseException, match='copy already started'):
        prepare(c, purge, 'economy_opportunity')
    # A dropped earlier relation cannot be copied again once a later one started.
    with pytest.raises(psycopg.errors.RaiseException, match='wrong copy-and-drop relation order'):
        chunk(c, purge, 'system_search', 10)


def test_open_016_event_or_request_drift_refuses_the_copy(superuser_database):
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    record = 'SELECT v3_meta.purge_record_event(%s,%s,NULL,%s)'
    containers = Jsonb({'containers': ['api']})
    _x(c, record, purge, 'SERVICES_QUIESCED', containers)
    with pytest.raises(psycopg.errors.RaiseException, match='open governed purge event'):
        prepare(c, purge, 'system_search')
    _x(c, record, purge, 'SERVICES_RESTORED', containers)
    prepare(c, purge, 'system_search')
    _x(c, record, purge, 'SERVICES_QUIESCED', containers)
    with pytest.raises(psycopg.errors.RaiseException, match='open governed purge event'):
        chunk(c, purge, 'system_search', 10)
    _x(c, record, purge, 'SERVICES_RESTORED', containers)
    assert chunk(c, purge, 'system_search', 1) == 1
    # 016's request assertion: a schema-ledger change after authorization.
    _owner(c).execute("INSERT INTO v3_meta.schema_migration VALUES ('999_drift.sql',%s)", (b'd' * 32,))
    with pytest.raises(psycopg.errors.RaiseException, match='purge schema ledger drift'):
        chunk(c, purge, 'system_search', 1)
    # Undo stays available under drift: recovery authentication only.
    abandon(c, purge, 'system_search')
    assert oid(c, 'v3_purge_staging.system_search') is None
    assert skip(c) is False


def test_drop_requires_verified_swapped_validated_and_no_dependents(superuser_database):
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    code = 'system_search'
    copy_all(c, purge, code)
    build(c, purge, code)
    with pytest.raises(psycopg.errors.RaiseException, match='VERIFIED, SWAPPED and FK_VALIDATED'):
        drop(c, purge, code)
    with pytest.raises(psycopg.errors.RaiseException, match='VACUUM and ANALYZE'):
        verify(c, purge, code)
    with pytest.raises(psycopg.errors.RaiseException, match='verified staging copy required'):
        swap(c, purge, code)
    vacuum(c, code)
    verify(c, purge, code)
    with pytest.raises(psycopg.errors.RaiseException, match='VERIFIED, SWAPPED and FK_VALIDATED'):
        drop(c, purge, code)
    swap(c, purge, code)
    with pytest.raises(psycopg.errors.RaiseException, match='VERIFIED, SWAPPED and FK_VALIDATED'):
        drop(c, purge, code)
    validate(c, purge, code)
    _owner(c).execute('CREATE VIEW v3_meta.retired_reader AS SELECT system_id64 FROM v3_retired.system_search')
    with pytest.raises(psycopg.errors.RaiseException, match='retired relation has dependents: view:v3_meta.retired_reader'):
        drop(c, purge, code)
    _owner(c).execute('DROP VIEW v3_meta.retired_reader')
    drop(c, purge, code)
    assert oid(c, 'v3_retired.system_search') is None
    assert events(c, code)[-4:] == ['VERIFIED', 'SWAPPED', 'FK_VALIDATED', 'DROPPED']
    with pytest.raises(psycopg.errors.RaiseException, match='swapped relation required'):
        swap_back(c, purge, code)


def test_swap_back_is_the_exact_reverse_and_repoints_child_fks(superuser_database):
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    views = _views_read(c)
    original = oid(c, 'v3_derived.system_search')
    before = state(c)
    staged(c, purge, 'system_search')
    copy_oid = oid(c, 'v3_purge_staging.system_search')
    staged_state = state(c)
    swap(c, purge, 'system_search')
    swap_back(c, purge, 'system_search')
    assert oid(c, 'v3_derived.system_search') == original
    assert oid(c, 'v3_purge_staging.system_search') == copy_oid
    assert oid(c, 'v3_retired.system_search') is None
    # Catalog identical to the verified staging state, apart from the ledger.
    assert state(c)[2:] == staged_state[2:]
    assert state(c)[2] != before[2]
    assert _views_read(c) == views
    assert _owner(c).execute(
        '''SELECT DISTINCT d.refobjid FROM pg_depend d JOIN pg_rewrite r ON r.oid=d.objid
           WHERE r.ev_class='v3_app.system_search'::regclass AND d.refclassid='pg_class'::regclass
             AND d.refobjid IN (%s,%s)''', (original, copy_oid)).fetchall() == [(original,)]
    with pytest.raises(psycopg.errors.RaiseException, match='verified staging copy required'):
        swap(c, purge, 'system_search')
    verify(c, purge, 'system_search')
    finish(c, purge, 'system_search')
    staged(c, purge, 'economy_opportunity')
    finish(c, purge, 'economy_opportunity')
    # A parent: its child FK follows the swap and the swap-back, NOT VALID each time.
    body = oid(c, 'v3_derived.body_mechanics')
    staged(c, purge, 'body_mechanics')
    body_copy = oid(c, 'v3_purge_staging.body_mechanics')
    swap(c, purge, 'body_mechanics')
    assert _child_fks(c, 'v3_derived.body_mechanics') == {
        ('v3_derived.economy_opportunity', 'v3_derived.body_mechanics', False)}
    assert oid(c, 'v3_derived.body_mechanics') == body_copy
    swap_back(c, purge, 'body_mechanics')
    assert oid(c, 'v3_derived.body_mechanics') == body
    assert _child_fks(c, 'v3_derived.body_mechanics') == {
        ('v3_derived.economy_opportunity', 'v3_derived.body_mechanics', False)}
    assert _child_fks(c, 'v3_purge_staging.body_mechanics') == set()
    with pytest.raises(psycopg.errors.RaiseException, match='VERIFIED, SWAPPED and FK_VALIDATED'):
        drop(c, purge, 'body_mechanics')
    validate(c, purge, 'body_mechanics')
    assert _child_fks(c, 'v3_derived.body_mechanics') == {
        ('v3_derived.economy_opportunity', 'v3_derived.body_mechanics', True)}
    verify(c, purge, 'body_mechanics')
    finish(c, purge, 'body_mechanics')
    assert oid(c, 'v3_derived.body_mechanics') == body_copy
    assert events(c, 'body_mechanics')[-8:] == [
        'VERIFIED', 'SWAPPED', 'SWAPPED_BACK', 'FK_VALIDATED', 'VERIFIED', 'SWAPPED', 'FK_VALIDATED', 'DROPPED',
    ]


def test_swap_lock_timeout_under_a_concurrent_reader_changes_nothing(superuser_database):
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    staged(c, purge, 'system_search')
    before = state(c)
    reader = psycopg.connect(make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], dbname=c.info.dbname))
    try:
        reader.execute('SELECT count(*) FROM v3_app.system_search').fetchone()
        started = monotonic()
        with pytest.raises(psycopg.errors.LockNotAvailable):
            swap(c, purge, 'system_search')
        elapsed = monotonic() - started
        assert 1.5 <= elapsed < 10
        assert state(c) == before
        # A reader that arrives while a swap waits is delayed at most by the
        # lock timeout, then served by whichever relation is live.
        with ThreadPoolExecutor(1) as pool:
            attempt = pool.submit(lambda: (monotonic(), _swap_in_new_session(c.info.dbname, purge)))
            late = psycopg.connect(make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], dbname=c.info.dbname))
            try:
                late.execute("SET lock_timeout='10s'")
                assert late.execute('SELECT count(*) FROM v3_app.system_search').fetchone()[0] > 0
            finally:
                late.close()
            with pytest.raises(psycopg.errors.LockNotAvailable):
                attempt.result()[1]
        assert state(c) == before
    finally:
        reader.close()
    swap(c, purge, 'system_search')
    assert events(c, 'system_search')[-1] == 'SWAPPED'


def _swap_in_new_session(dbname, purge):
    with psycopg.connect(make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], dbname=dbname),
                         autocommit=True) as other:
        return swap(other, purge, 'system_search')


def test_drop_of_a_child_locks_its_live_parent_only_within_the_lock_timeout(superuser_database):
    """DROP removes the retired table's own FK triggers from the live parent."""
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    staged(c, purge, 'system_search')
    swap(c, purge, 'system_search')
    validate(c, purge, 'system_search')
    before = state(c)
    reader = psycopg.connect(make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], dbname=c.info.dbname))
    try:
        reader.execute('SELECT count(*) FROM v3_derived.system_rating_vector').fetchone()
        started = monotonic()
        with pytest.raises(psycopg.errors.LockNotAvailable):
            drop(c, purge, 'system_search')
        assert monotonic() - started < 10
        assert state(c) == before
    finally:
        reader.close()
    drop(c, purge, 'system_search')


def test_rollback_or_backend_loss_at_every_step_leaves_a_consistent_ledger(superuser_database):
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    code = 'system_search'

    def rolled_back(step, *arguments):
        before = state(c)
        with c.transaction():
            step(c, purge, code, *arguments)
            assert state(c) != before
            raise psycopg.Rollback()
        assert state(c) == before

    rolled_back(prepare)
    prepare(c, purge, code)
    rolled_back(chunk, 2)
    # A backend lost after its chunk but before COMMIT leaves no trace.
    lost = psycopg.connect(make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], dbname=c.info.dbname))
    before = state(c)
    chunk(lost, purge, code, 2)
    _owner(c).execute('SELECT pg_terminate_backend(%s)', (lost.info.backend_pid,))
    lost.close()
    assert state(c) == before
    while chunk(c, purge, code, 2) == 2:
        pass
    rolled_back(build)
    build(c, purge, code)
    vacuum(c, code)
    rolled_back(verify)
    verify(c, purge, code)
    rolled_back(swap)
    swap(c, purge, code)
    rolled_back(swap_back)
    rolled_back(validate)
    validate(c, purge, code)
    rolled_back(drop)
    drop(c, purge, code)
    prepare(c, purge, 'economy_opportunity')
    code = 'economy_opportunity'
    rolled_back(abandon)
    abandon(c, purge, code)
    assert events(c) == [
        'COPY_STARTED', *['CHUNK_COPIED'] * len([e for e in events(c, 'system_search') if e == 'CHUNK_COPIED']),
        'INDEXES_BUILT', 'VERIFIED', 'SWAPPED', 'FK_VALIDATED', 'DROPPED', 'COPY_STARTED', 'FAILED_STOP',
    ]


def test_verify_refuses_catalog_content_and_receipt_drift(superuser_database):
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    code = 'system_search'
    copy_all(c, purge, code)
    build(c, purge, code)
    vacuum(c, code)
    owner = _owner(c)
    owner.execute("COMMENT ON COLUMN v3_purge_staging.system_search.name IS 'tampered'")
    with pytest.raises(psycopg.errors.RaiseException, match='fingerprint mismatch: columns'):
        verify(c, purge, code)
    owner.execute('COMMENT ON COLUMN v3_purge_staging.system_search.name IS NULL')
    owner.execute('ALTER INDEX v3_purge_staging.system_search_region RENAME TO system_search_region_x')
    with pytest.raises(psycopg.errors.RaiseException, match='fingerprint mismatch: indexes'):
        verify(c, purge, code)
    owner.execute('ALTER INDEX v3_purge_staging.system_search_region_x RENAME TO system_search_region')
    owner.execute('ALTER TABLE v3_purge_staging.system_search DISABLE TRIGGER purge_copy_guard')
    with pytest.raises(psycopg.errors.RaiseException, match='copy guard is not exactly installed'):
        verify(c, purge, code)
    owner.execute('ALTER TABLE v3_purge_staging.system_search ENABLE TRIGGER purge_copy_guard')
    # Receipts: a Search chunk receipt that disagrees with the copied rows.
    owner.execute('ALTER TABLE v3_derived.search_build_chunk DISABLE TRIGGER USER')
    owner.execute('UPDATE v3_derived.search_build_chunk SET systems=systems+1 WHERE derived_generation_id=%s',
                  (SURVIVOR,))
    with pytest.raises(psycopg.errors.RaiseException, match='chunk receipt count mismatch'):
        verify(c, purge, code)
    owner.execute('UPDATE v3_derived.search_build_chunk SET systems=systems-1 WHERE derived_generation_id=%s',
                  (SURVIVOR,))
    owner.execute('ALTER TABLE v3_derived.search_build_chunk ENABLE TRIGGER USER')
    # Content: a staged row changed behind the guard's back.
    owner.execute('ALTER TABLE v3_purge_staging.system_search DISABLE TRIGGER purge_copy_guard')
    owner.execute('''UPDATE v3_purge_staging.system_search SET name='tampered'
                     WHERE system_id64=(SELECT min(system_id64) FROM v3_purge_staging.system_search)''')
    owner.execute('ALTER TABLE v3_purge_staging.system_search ENABLE TRIGGER purge_copy_guard')
    vacuum(c, code)
    with pytest.raises(psycopg.errors.RaiseException, match='content mismatch'):
        verify(c, purge, code)
    assert 'VERIFIED' not in events(c, code)
    # The only way forward is to abandon the tainted copy and start again.
    _x(c, 'SELECT v3_meta.purge_copy_record_failure(%s,%s,%s)', purge, code, Jsonb({'integrity': 'content'}))
    with pytest.raises(psycopg.errors.RaiseException, match='index build or swap-back required'):
        verify(c, purge, code)
    assert skip(c) is True
    abandon(c, purge, code)
    assert skip(c) is False
    staged(c, purge, code)
    assert events(c, code)[-1] == 'VERIFIED'


def test_backup_skip_spans_copy_started_to_dropped_or_abandonment(superuser_database):
    c = superuser_database[0]
    assert skip(c) is False
    purge, _ = _authorize(superuser_database)
    assert skip(c) is False
    prepare(c, purge, 'system_search')
    assert skip(c) is True
    abandon(c, purge, 'system_search')
    assert skip(c) is False
    staged(c, purge, 'system_search')
    assert skip(c) is True
    swap(c, purge, 'system_search')
    validate(c, purge, 'system_search')
    assert skip(c) is True
    drop(c, purge, 'system_search')
    assert skip(c) is False
    # A physically present staging or retired table always skips, ledger or not.
    _owner(c).execute('CREATE TABLE v3_retired.stray (x int)')
    assert skip(c) is True
    _owner(c).execute('DROP TABLE v3_retired.stray')
    assert skip(c) is False
    status = _x(c, 'SELECT v3_meta.purge_copy_status()')
    relations = status['requests'][0]['relations']
    assert relations['system_search']['copy_position'] == 'dropped'
    assert relations['economy_opportunity']['copy_position'] == 'none'
    assert {target for target in _owner(c).execute(
        'SELECT unnest(target_generation_ids) FROM v3_meta.derived_purge_copy_request').fetchall()} == {
        (target,) for _, target in TARGETS}


def _column_statistics(c, relation, column):
    return _owner(c).execute(
        'SELECT attstattarget,attoptions FROM pg_attribute WHERE attrelid=%s::regclass AND attname=%s',
        (relation, column)).fetchone()


def test_production_planner_statistics_are_copied_and_the_fingerprint_matches(copy_database):
    """The owner-applied 2026-10-19 statistics (v3-postgres-server-settings.md)."""
    c = copy_database[0]
    purge, _ = _authorize(copy_database)
    owner = _owner(c)
    owner.execute('ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 SET STATISTICS 1000')
    owner.execute('ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 SET (n_distinct = -0.13)')
    owner.execute('ALTER TABLE v3_derived.system_search ALTER COLUMN name SET STATISTICS 500')
    opportunity = ('v3_derived.economy_opportunity', 'system_id64')
    assert _column_statistics(c, *opportunity) == (1000, ['n_distinct=-0.13'])
    before = {code: fingerprint(c, 'v3_derived.' + code) for code in ('system_search', 'economy_opportunity')}
    prepare(c, purge, 'system_search')
    assert _column_statistics(c, 'v3_purge_staging.system_search', 'name') == (500, None)
    staged_after_prepare(c, purge, 'system_search')
    swap(c, purge, 'system_search')
    assert _column_statistics(c, 'v3_derived.system_search', 'name') == (500, None)
    assert mismatch(c, before['system_search'], fingerprint(c, 'v3_derived.system_search')) == []
    validate(c, purge, 'system_search')
    drop(c, purge, 'system_search')
    prepare(c, purge, 'economy_opportunity')
    assert _column_statistics(c, 'v3_purge_staging.economy_opportunity', 'system_id64') == (
        1000, ['n_distinct=-0.13'])
    staged_after_prepare(c, purge, 'economy_opportunity')
    swap(c, purge, 'economy_opportunity')
    # The live value is preserved verbatim; recalibration after the purge is the owner's step.
    assert _column_statistics(c, *opportunity) == (1000, ['n_distinct=-0.13'])
    assert mismatch(c, before['economy_opportunity'], fingerprint(c, 'v3_derived.economy_opportunity')) == []
    validate(c, purge, 'economy_opportunity')
    drop(c, purge, 'economy_opportunity')
    assert events(c, 'economy_opportunity')[-1] == 'DROPPED'


def staged_after_prepare(c, purge, code, rows=2):
    while chunk(c, purge, code, rows) == rows:
        pass
    build(c, purge, code)
    vacuum(c, code)
    return verify(c, purge, code)


SKEW_STAGING = '''
CREATE FUNCTION public.skew_purge_staging() RETURNS event_trigger LANGUAGE plpgsql AS $$
DECLARE c record;
BEGIN
    FOR c IN SELECT objid FROM pg_event_trigger_ddl_commands()
             WHERE schema_name='v3_purge_staging' AND object_type='table' LOOP
        EXECUTE format('ALTER TABLE %s ALTER COLUMN system_id64 SET STATISTICS 7', c.objid::regclass);
    END LOOP;
END $$;
CREATE EVENT TRIGGER skew_purge_staging ON ddl_command_end WHEN TAG IN ('CREATE TABLE')
EXECUTE FUNCTION public.skew_purge_staging();
'''


def test_prepare_refuses_production_only_catalog_differences_before_copying(superuser_database):
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    owner = _owner(c)
    before = state(c)
    # An attribute option outside n_distinct/n_distinct_inherited (catalog
    # injection: PostgreSQL itself accepts no other table attribute option).
    owner.execute('''UPDATE pg_attribute SET attoptions='{bogus=1}'
                     WHERE attrelid='v3_derived.system_search'::regclass AND attname='name' ''')
    with pytest.raises(psycopg.errors.RaiseException, match='unsupported attribute option bogus on name'):
        prepare(c, purge, 'system_search')
    owner.execute('''UPDATE pg_attribute SET attoptions=NULL
                     WHERE attrelid='v3_derived.system_search'::regclass AND attname='name' ''')
    assert state(c) == before
    # A column-level difference the generator cannot reproduce, simulated by
    # skewing the staging column right after CREATE TABLE ... LIKE.
    owner.execute(SKEW_STAGING)
    try:
        with pytest.raises(psycopg.errors.RaiseException,
                           match='prepared staging catalog fingerprint mismatch: columns'):
            prepare(c, purge, 'system_search')
    finally:
        _owner(c).execute('DROP EVENT TRIGGER skew_purge_staging')
        c.execute('DROP FUNCTION public.skew_purge_staging()')
    assert state(c) == before
    # A relation-level production-only attribute that LIKE does not copy.
    owner.execute('ALTER TABLE v3_derived.system_search REPLICA IDENTITY FULL')
    with pytest.raises(psycopg.errors.RaiseException,
                       match='prepared staging catalog fingerprint mismatch: relation'):
        prepare(c, purge, 'system_search')
    owner.execute('ALTER TABLE v3_derived.system_search REPLICA IDENTITY DEFAULT')
    assert state(c) == before
    assert oid(c, 'v3_purge_staging.system_search') is None
    assert _count(c, 'v3_meta.derived_purge_copy_event') == 0
    prepare(c, purge, 'system_search')
    assert events(c) == ['COPY_STARTED']
