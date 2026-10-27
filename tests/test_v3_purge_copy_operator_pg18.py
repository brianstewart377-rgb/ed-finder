"""Copy-and-drop operator SQL on disposable PostgreSQL 18, never production.

Proves the two timeout facts the operator layer is built on (F5, F4), the
shared fence's 019 reads, the backup wrapper's 019 query, the preflight
observations and the per-phase wrappers end to end on one relation.
The canonical_database import also makes CI's PG18 discovery select this file.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
import threading
from time import monotonic

import psycopg
from psycopg.conninfo import make_conninfo
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402
from tests.test_v3_governed_derived_purge import installed_purge  # noqa: E402
from tests import test_v3_purge_copy_and_drop as copy_tests  # noqa: E402
from tests.test_v3_purge_copy_and_drop import _authorize, _owner, abandon, prepare  # noqa: E402

copy_database = copy_tests.copy_database  # fixtures: per-test database, 001-016 chain, 019, 020
superuser_database = copy_tests.superuser_database


def _load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


copy = _load('scripts/operator/lib/v3_purge_copy.py', 'purge_copy_pg18')
fence = _load('scripts/operator/lib/v3_purge_state.py', 'purge_fence_pg18')


def _bind(sql, params=None):
    """The action binds psql variables; here the same values become literals."""
    for key, value in (params or {}).items():
        literal = "'" + str(value).replace("'", "''") + "'"
        sql = sql.replace('%(' + key + ')s', literal)
    assert '%(' not in sql
    return sql


def _json(connection, sql, params=None):
    """Run a fixed multi-statement script and return its one JSON row."""
    cursor = connection.execute(_bind(sql, params))
    while cursor.pgresult is not None and cursor.pgresult.status != psycopg.pq.ExecStatus.TUPLES_OK:
        if not cursor.nextset():
            raise AssertionError('no result set')
    row = cursor.fetchone()
    while cursor.nextset():
        pass
    return row[0]


def _reset(connection):
    connection.execute('RESET ROLE')


class _temp_file_limit_grant:
    """GRANT SET ON PARAMETER temp_file_limit TO the executor through the test
    administrator (pg_parameter_acl is cluster-wide), revoked afterwards. This is
    the reviewed production prerequisite the runbook names; 019 does not grant it."""

    def __init__(self, connection):
        import os
        self.admin = psycopg.connect(make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'],
                                                  dbname=connection.info.dbname), autocommit=True)

    def __enter__(self):
        self.admin.execute('GRANT SET ON PARAMETER temp_file_limit TO v3_derived_purge_executor')
        return self

    def __exit__(self, *exc):
        try:
            self.admin.execute('REVOKE SET ON PARAMETER temp_file_limit FROM v3_derived_purge_executor')
        finally:
            self.admin.close()
        return False


# --- F5 / F4 on PostgreSQL 18 ---------------------------------------------------------

def test_function_level_statement_timeout_never_bounds_its_own_call(superuser_database):
    c = _owner(superuser_database[0])
    c.execute("CREATE FUNCTION public.copy_test_sleep() RETURNS void LANGUAGE plpgsql "
              "SET statement_timeout='100ms' AS $$ BEGIN PERFORM pg_sleep(0.6); END $$")
    started = monotonic()
    c.execute('SELECT public.copy_test_sleep()')
    assert monotonic() - started >= 0.5, 'the function-level SET did not bound the call (expected on PG 18)'
    # The operator pattern: SET LOCAL in the same transaction, before the call.
    with pytest.raises(psycopg.errors.QueryCanceled):
        c.execute("BEGIN; SET LOCAL statement_timeout='100ms'; SELECT public.copy_test_sleep(); COMMIT;")
    c.execute('ROLLBACK')
    assert c.execute('SELECT current_setting(%s)', ('statement_timeout',)).fetchone()[0] in ('0', '0ms')


def test_function_level_lock_timeout_wins_but_the_caller_statement_timeout_caps_the_attempt(superuser_database):
    """F4: 019 pins lock_timeout='2s' on swap/swap-back/drop/abandon and that
    value wins over the caller's SET LOCAL; the caller's statement_timeout is
    what bounds one attempt. Measured here with small values."""
    c = _owner(superuser_database[0])
    c.execute('CREATE TABLE public.copy_test_locked (x int)')
    c.execute("CREATE FUNCTION public.copy_test_lock() RETURNS void LANGUAGE plpgsql SET lock_timeout='900ms' "
              "AS $$ BEGIN LOCK TABLE public.copy_test_locked IN ACCESS EXCLUSIVE MODE; END $$")
    holder = psycopg.connect(make_conninfo(c.info.dsn, password=c.info.password))
    try:
        holder.execute('LOCK TABLE public.copy_test_locked IN ACCESS EXCLUSIVE MODE')
        started = monotonic()
        with pytest.raises(psycopg.errors.LockNotAvailable):
            c.execute("BEGIN; SET LOCAL lock_timeout='100ms'; SELECT public.copy_test_lock(); COMMIT;")
        c.execute('ROLLBACK')
        assert monotonic() - started >= 0.8, 'the caller lock_timeout won; update v3_purge_copy and the runbook'
        started = monotonic()
        with pytest.raises(psycopg.errors.QueryCanceled):
            c.execute("BEGIN; SET LOCAL lock_timeout='100ms'; SET LOCAL statement_timeout='300ms'; "
                      'SELECT public.copy_test_lock(); COMMIT;')
        c.execute('ROLLBACK')
        assert monotonic() - started < 0.8
    finally:
        holder.rollback()
        holder.close()
    # The swap wrapper therefore carries both: the (currently ineffective)
    # sub-second lock_timeout and the 8 s statement cap per attempt.
    assert "SET LOCAL lock_timeout='400ms';" in copy.SWAP_SQL and "SET LOCAL statement_timeout='8000ms';" in copy.SWAP_SQL


# --- the shared fence ----------------------------------------------------------------

def _fence_executor(connection, monkeypatch):
    # The fence pins production's database name; the disposable database has a
    # random one, so only that identity constant is substituted here.
    monkeypatch.setattr(fence, 'DATABASE_NAME', connection.info.dbname)
    def execute(sql):
        return json.dumps(_json(connection, sql))
    return execute


def test_fence_reads_follow_the_copy_ledger(copy_database, monkeypatch):
    c = _owner(copy_database[0])
    executor = _fence_executor(c, monkeypatch)
    presence = _json(c, fence.PRESENCE_SQL)
    assert presence['ledger_present'] is True and presence['copy_ledger_present'] is True
    state = _json(c, fence.STATE_SQL)
    assert state['copy_backup_skip'] is False and state['copy_relations'] == [] and state['unresolved'] == []
    report = fence.check(executor, lease_held_by_caller=True)
    assert report['status'] == 'clear' and report['copy_ledger_present'] is True
    purge, _plan = _authorize(copy_database)
    prepare(c, purge, 'system_search')
    _reset(c)
    state = _json(c, fence.STATE_SQL)
    assert state['copy_backup_skip'] is True
    assert state['copy_relations'] == [{'relation_code': 'system_search', 'copy_position': 'staged', 'phase': 'COPY_STARTED'}]
    with pytest.raises(fence.PurgeStateError) as refused:
        fence.check(executor, lease_held_by_caller=True)
    assert refused.value.report['failures'] == ['purge_copy_backup_skip', 'purge_copy_relation_staged']
    abandon(c, purge, 'system_search')
    _reset(c)
    assert fence.check(executor, lease_held_by_caller=True)['status'] == 'clear'


def test_fence_refuses_an_installed_016_without_019_except_the_copy_bootstrap(monkeypatch):
    with canonical_database() as data:
        with installed_purge(data[0], apply_chain=True) as c:
            executor = _fence_executor(c, monkeypatch)
            presence = _json(c, fence.PRESENCE_SQL)
            assert presence['ledger_present'] is True and presence['copy_ledger_present'] is False
            with pytest.raises(fence.PurgeStateError, match='purge_copy_ledger_absent'):
                fence.check(executor, lease_held_by_caller=True)
            report = fence.check(executor, lease_held_by_caller=True, copy_bootstrap=True)
            assert report['copy_bootstrap'] is True and report['status'] == 'clear'
            # The copy-aware read itself fails closed without 019.
            with pytest.raises(psycopg.errors.UndefinedFunction):
                _json(c, fence.STATE_SQL)
            c.execute('ROLLBACK')


# --- the installed backup wrapper's 019 query -------------------------------------------

def _wrapper_copy_query():
    source = (ROOT / 'deploy/v3-production/backup/pgbackrest-operation.sh').read_text()
    blocks = re.findall(r"<<'SQL'\n(.*?)\nSQL\n", source, re.S)
    assert len(blocks) == 2
    assert 'v3_meta.purge_copy_backup_skip()' in blocks[1] and 'purge_open_event' in blocks[0]
    return blocks[1]


def test_backup_wrapper_019_query_returns_exactly_the_boolean_the_wrapper_parses(copy_database):
    c = _owner(copy_database[0])
    query = _wrapper_copy_query()
    assert _json(c, query) is False
    purge, _plan = _authorize(copy_database)
    prepare(c, purge, 'system_search')
    _reset(c)
    assert _json(c, query) is True
    wrapper = (ROOT / 'deploy/v3-production/backup/pgbackrest-operation.sh').read_text()
    assert 'case "$copy_skip" in\n  t)' in wrapper and '  f) ;;' in wrapper and 'exit 65' in wrapper
    # The pinned psql identity is the same as the 016 query's.
    assert wrapper.count('--username edfinder_v3 --dbname edfinder_v3_phase4c_full_20260827_r5') == 2


# --- fixed operator reads on the fixture --------------------------------------------------

def test_operator_reads_execute_and_preflight_passes_on_the_fresh_lineage(copy_database):
    c = copy_database[0]
    purge, plan = _authorize(copy_database)
    _reset(c)
    status = _json(c, copy.STATUS_SQL)
    _reset(c)
    assert status['backup_skip'] is False and status['requests'] == []
    assert _json(c, copy.REQUEST_SQL, {'plan_sha256': plan['plan_sha256']}) is None
    _reset(c)
    staging = _json(c, copy.STAGING_SQL, {'relation': 'system_search'})
    _reset(c)
    assert staging['staging_present'] is False and type(staging['max_wal_size_bytes']) is int
    assert type(staging['live_index_bytes']) is int and type(staging['xid_next']) is int
    lag = _json(c, copy.WAL_LAG_SQL)
    _reset(c)
    assert type(lag['current_segment']) is int
    if lag['archive_mode'] not in ('on', 'always'):
        with pytest.raises(ValueError, match='wal_archive_lag_unknown'):
            copy.archive_lag_segments(lag)
    identity = _json(c, copy.BACKEND_IDENTITY_SQL)
    assert identity['backend_pid'] == c.info.backend_pid and identity['backend_start']
    progress = _json(c, copy.PROGRESS_SQL, {'backend_pid': str(identity['backend_pid']),
                                           'backend_start': identity['backend_start']})
    assert progress['create_index'] is None and progress['vacuum'] is None and progress['activity']['state'] == 'active'
    stats = _json(c, copy.RECALIBRATE_STATS_SQL)
    _reset(c)
    assert type(stats['reltuples']) is int
    plan_json = _json(c, copy.CHUNK_READ_PLAN_SQL)
    _reset(c)
    assert isinstance(plan_json, list) and 'Plan' in plan_json[0]
    # temp_file_limit is SUSET: the executor can only SET LOCAL it after a grant
    # (absent from 019). The probe says so and the long phases refuse without it.
    privilege = _json(c, copy.TEMP_FILE_LIMIT_PRIVILEGE_SQL)
    _reset(c)
    assert privilege['executor'] == 'v3_derived_purge_executor'
    # SET ROLE drops superuser powers too: without the grant no session can
    # bound its temp files, so the long-phase wrapper refuses up front.
    assert privilege['can_set_temp_file_limit'] is False
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _json(c, copy.BUILD_INDEXES_SQL, {'purge_id': purge, 'relation': 'system_search'})
    c.execute('ROLLBACK')
    _reset(c)
    with _temp_file_limit_grant(c):
        assert _json(c, copy.TEMP_FILE_LIMIT_PRIVILEGE_SQL)['can_set_temp_file_limit'] is True
        _reset(c)
    for relation in copy.RELATIONS:
        observed = _json(c, copy.PREFLIGHT_SQL, {'relation': relation})
        violations = _json(c, copy.SEARCH_VIOLATIONS_SQL) if relation == 'system_search' else None
        result = copy.evaluate_preflight(observed, violations=violations, relation=relation)
        assert result['passed'] is True, relation
        if relation == 'system_search':
            assert violations['constraints'] == len(observed['not_valid_checks'])
            assert set(violations['violations']) == set(observed['not_valid_checks'])
    # A survivor row violating a live NOT VALID check is counted, not hidden.
    checks = _json(c, copy.PREFLIGHT_SQL, {'relation': 'system_search'})['not_valid_checks']
    if checks:
        expression = c.execute('SELECT pg_get_expr(conbin,conrelid) FROM pg_constraint WHERE conname=%s', (checks[0],)).fetchone()[0]
        assert isinstance(expression, str) and expression
    # Freeze-age evidence names all four live heaps.
    ages = {(a['relation_code'], a['scope']) for a in observed['ages']}
    assert {(code, 'heap') for code in copy.RELATIONS} <= ages


def test_phase_wrappers_drive_one_relation_through_019_with_their_set_local_bounds(copy_database):
    with _temp_file_limit_grant(copy_database[0]):
        _phase_wrapper_journey(copy_database)


def _phase_wrapper_journey(copy_database):
    c = copy_database[0]
    purge, plan = _authorize(copy_database)
    params = {'purge_id': purge, 'relation': 'system_search'}
    _reset(c)
    assert type(_json(c, copy.PREPARE_SQL, params)['event']) is int
    _reset(c)
    request = _json(c, copy.REQUEST_SQL, {'plan_sha256': plan['plan_sha256']})
    _reset(c)
    frozen = request['frozen_survivors']['system_search']
    total = 0
    while True:
        result = _json(c, copy.CHUNK_SQL, {**params, 'max_rows': '2'})
        _reset(c)
        assert type(result['staging_bytes']) is int and re.fullmatch('[0-9A-F]+/[0-9A-F]+', result['wal_lsn'])
        if result['rows'] == 0:
            break
        total += result['rows']
    assert total == frozen
    assert type(_json(c, copy.BUILD_INDEXES_SQL, params)['event']) is int
    _reset(c)
    before = _json(c, copy.STAGING_SQL, {'relation': 'system_search'})
    _reset(c)
    assert copy.next_step(copy.relation_state(_json(c, copy.STATUS_SQL), plan['plan_sha256'], 'system_search'),
                          frozen, before) == 'vacuum_freeze'
    _reset(c)
    # psql sends each statement on its own (no transaction block); do the same.
    for statement in copy.vacuum_sql('system_search').split(';\n'):
        if statement.strip():
            c.execute(statement)
    _reset(c)
    after = _json(c, copy.STAGING_SQL, {'relation': 'system_search'})
    _reset(c)
    assert after['last_vacuum'] is not None and after['last_analyze'] is not None
    evidence = copy.staging_frozen(after, xid_before=before['xid_next'])
    assert evidence['staging_xid_age'] <= (after['xid_next'] - before['xid_next']) + copy.FREEZE_SLACK_XIDS
    with pytest.raises(ValueError, match='staging_relfrozenxid_not_frozen'):
        copy.staging_frozen({**after, 'staging_xid_age': copy.MAX_STAGING_FROZEN_AGE + 1}, xid_before=before['xid_next'])
    with pytest.raises(ValueError, match='staging_relfrozenxid_not_frozen'):
        copy.staging_frozen({**after, 'staging_xid_age': copy.FREEZE_SLACK_XIDS + 100}, xid_before=after['xid_next'])
    assert copy.next_step(copy.relation_state(_json(c, copy.STATUS_SQL), plan['plan_sha256'], 'system_search'),
                          frozen, after) == 'verify'
    _reset(c)
    assert type(_json(c, copy.VERIFY_SQL, params)['event']) is int
    _reset(c)
    assert type(_json(c, copy.SWAP_SQL, params)['event']) is int
    _reset(c)
    assert type(_json(c, copy.VALIDATE_FKS_SQL, params)['event']) is int
    _reset(c)
    state = copy.relation_state(_json(c, copy.STATUS_SQL), plan['plan_sha256'], 'system_search')
    _reset(c)
    assert state['copy_position'] == 'swapped' and state['fk_validated'] is not None
    assert type(_json(c, copy.DROP_SQL, params)['event']) is int
    _reset(c)
    status = _json(c, copy.STATUS_SQL)
    _reset(c)
    assert copy.relation_state(status, plan['plan_sha256'], 'system_search')['copy_position'] == 'dropped'
    detail = _json(c, copy.REQUEST_SQL, {'plan_sha256': plan['plan_sha256']})
    _reset(c)
    assert detail['latest_events']['system_search']['event_kind'] == 'DROPPED'
    # record_failure and complete refuse here exactly as 019 defines them.
    with pytest.raises(psycopg.errors.RaiseException):
        _json(c, copy.RECORD_FAILURE_SQL, {**params, 'evidence': json.dumps({'condition': 'x', 'integrity_failed': True})})
    c.execute('ROLLBACK')
    _reset(c)
    with pytest.raises(psycopg.errors.RaiseException):
        _json(c, copy.COMPLETE_SQL, {'purge_id': purge})
    c.execute('ROLLBACK')
    _reset(c)


def test_cancel_statement_signals_only_the_authenticated_owner_phase_backend(superuser_database):
    c = _owner(superuser_database[0])
    worker = psycopg.connect(make_conninfo(c.info.dsn, password=c.info.password), autocommit=True)
    outcome = {}
    def run():
        try:
            worker.execute("SELECT pg_sleep(20) /* v3_meta.purge_copy_verify( */")
            outcome['result'] = 'completed'
        except psycopg.errors.QueryCanceled:
            outcome['result'] = 'cancelled'
    thread = threading.Thread(target=run)
    thread.start()
    try:
        deadline = monotonic() + 10
        start = None
        while monotonic() < deadline and start is None:
            row = c.execute("SELECT backend_start FROM pg_stat_activity WHERE pid=%s AND state='active'",
                            (worker.info.backend_pid,)).fetchone()
            start = row[0].isoformat() if row else None
        assert start is not None
        wrong = _json(c, copy.CANCEL_SQL, {'backend_pid': str(worker.info.backend_pid),
                                           'backend_start': '2000-01-01T00:00:00+00:00'})
        assert wrong['cancelled'] is False and thread.is_alive()
        own = _json(c, copy.CANCEL_SQL, {'backend_pid': str(c.info.backend_pid), 'backend_start': start})
        assert own['cancelled'] is False
        right = _json(c, copy.CANCEL_SQL, {'backend_pid': str(worker.info.backend_pid), 'backend_start': start})
        assert right['cancelled'] is True
        thread.join(timeout=10)
        assert outcome == {'result': 'cancelled'}
    finally:
        thread.join(timeout=1)
        worker.close()


# --- the dispatcher's own phases on PG18 (Codex 4379797609/637/650) ------------------------

from types import SimpleNamespace  # noqa: E402

from tests.test_v3_purge_copy_and_drop import (  # noqa: E402
    build, chunk, drop, oid, staged, swap, validate, vacuum, verify,
)


def _controller_module(name):
    module = _load('scripts/operator/lib/v3_generation_purge.py', name)
    return module


def _dispatch_module(name):
    return _load('scripts/operator/lib/v3_purge_copy_dispatch.py', name)


class _PGRuntime:
    """The dispatcher's runtime over the disposable fixture: each fixed
    multi-statement script runs on the owner connection, as psql would."""

    def __init__(self, connection):
        self.c = connection
        self.deadline = float('inf')
        self.report = {}
        self.statements = []
        self.lease_fd = self.backup_lock_fd = None
        import os
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
        self.env['PGPASSWORD'] = connection.info.password or ''

    def query(self, sql, params=None, *, write=False):
        self.statements.append(sql)
        try:
            return _json(self.c, sql, params)
        except psycopg.errors.LockNotAvailable:
            self.c.execute('ROLLBACK')
            raise RuntimeError('database_lock_timeout') from None
        except psycopg.errors.QueryCanceled:
            self.c.execute('ROLLBACK')
            raise RuntimeError('database_statement_timeout') from None
        finally:
            if self.c.info.transaction_status == psycopg.pq.TransactionStatus.INERROR:
                self.c.execute('ROLLBACK')
            _reset(self.c)

    def workers(self):
        return True


def _phase_harness(monkeypatch, connection, *, name, real_long_phase=False):
    """Dispatcher + controller wired to the fixture; host facilities are fakes."""
    c = _controller_module('copy_pg18_controller_' + name)
    dispatch = _dispatch_module('copy_pg18_dispatch_' + name)
    copy_module = c._load('v3_purge_copy')
    runtime = _PGRuntime(connection)
    saved = []
    original = c._load
    monitor = SimpleNamespace(start_copy=lambda *a, **k: 'unit', copy_condition=lambda unit: None)
    delete = SimpleNamespace(save_host_state=lambda value, path=None: saved.append((value, str(path))))
    cache = {}
    def load(module, path=None):
        if module == 'v3_purge_rewrite_monitor':
            return monitor
        if module == 'v3_purge_delete':
            return delete
        if module == 'v3_purge_copy':
            return copy_module
        if module not in cache:
            cache[module] = original(module, path) if path else original(module)
        return cache[module]
    monkeypatch.setattr(c, '_load', load)
    monkeypatch.setattr(dispatch, '_wait', lambda *a, **k: None)
    monkeypatch.setattr(dispatch, '_measure', lambda *a, **k: {'filesystem_free_bytes': 1})
    monkeypatch.setattr(copy_module, 'finder_smoke', lambda *a, **k: {'passed': True, 'origin': 'pg18-fixture'})
    if not real_long_phase:
        def long_phase(c_, cp, rt, rep, *, phase, sql, params, **kwargs):
            # The same fixed statement, run once on the owner connection.
            result = rt.query(sql, params, write=kwargs.get('write', True))
            rep.setdefault('long_phases', []).append(phase)
            return result
        monkeypatch.setattr(dispatch, '_long_phase', long_phase)
    # Without the local psql transport the dispatcher would use docker exec.
    dsn = connection.info.dsn
    monkeypatch.setattr(dispatch, 'psql_argv', lambda _c: [
        'psql', '-X', '--no-psqlrc', '--no-password', '--dbname', dsn,
        '--tuples-only', '--no-align', '--quiet', '--set', 'ON_ERROR_STOP=1',
        '--set', 'VERBOSITY=sqlstate', '--file=-'])
    return c, dispatch, copy_module, runtime, saved


def _state_now(copy_module, runtime, plan, relation):
    return copy_module.relation_state(runtime.query(copy_module.STATUS_SQL), plan['plan_sha256'], relation)


def _attoptions(c, relation):
    row = _owner(c).execute("SELECT attoptions FROM pg_attribute WHERE attrelid=to_regclass(%s) AND attname='system_id64'",
                            (relation,)).fetchone()
    return None if row is None else row[0]


def test_long_phase_runs_its_watch_callback_on_a_real_psql_backend(superuser_database, monkeypatch):
    """Codex 4379797609: the long-phase callback must not touch the backend
    before phase_backend has set it up. Drives _long_phase end to end over a
    real psql login (identity, executor session, the fixed verify call with a
    short fault pause), polling progress every callback, then cancels a second
    paused verify through the authenticated cancel statement."""
    import shutil
    assert shutil.which('psql'), 'the real-backend long-phase test needs a psql client (GitHub ubuntu images ship one)'
    c = superuser_database[0]
    purge, plan = _authorize(superuser_database)
    purge = str(purge)
    controller, dispatch, copy_module, runtime, _saved = _phase_harness(
        monkeypatch, c, name='long_phase', real_long_phase=True)
    monkeypatch.setattr(dispatch, 'PROGRESS_INTERVAL_SECONDS', 0)
    params = {'purge_id': purge, 'relation': 'system_search'}
    with _temp_file_limit_grant(c):
        prepare(c, purge, 'system_search')
        while chunk(c, purge, 'system_search', 2) == 2:
            pass
        build(c, purge, 'system_search')
        vacuum(c, 'system_search')
        _reset(c)
        anchor = '%(purge_id)s::uuid,%(relation)s))'
        assert copy_module.VERIFY_SQL.count(anchor) == 1
        paused = copy_module.VERIFY_SQL.replace(anchor, "%(purge_id)s::uuid,%(relation)s),'pause',(pg_sleep(1.2) IS NULL))")
        report = {'runner_state': {}}
        stop = threading.Event()
        result = dispatch._long_phase(controller, copy_module, runtime, report, phase='verify', sql=paused,
                                      params=params, relation='system_search', ids=[purge, purge],
                                      identity={'data_directory': '/unused'}, controller_alive=lambda: None,
                                      stop=stop, required_bytes=1, max_wal_size=1)
        assert type(result['event']) is int and result['pause'] is False
        progress = report['copy_progress']
        assert progress['phase'] == 'verify' and progress['samples'] >= 2
        assert progress['last'].get('unavailable') is None and progress['last']['activity'] is not None
        assert report['copy_steps'][-1]['phase'] == 'verify' and report['copy_steps'][-1]['seconds'] >= 1.2
        assert type(report['wal_phase_bytes']['verify']) is int
        assert _state_now(copy_module, runtime, plan, 'system_search')['phase'] == 'VERIFIED'
        # A stop request cancels the authenticated phase backend; nothing commits.
        swap(c, purge, 'system_search')
        _reset(c)
        validate(c, purge, 'system_search')
        _reset(c)
        long_validate = copy_module.VALIDATE_FKS_SQL.replace(
            anchor, "%(purge_id)s::uuid,%(relation)s),'pause',(pg_sleep(30) IS NULL))")
        timer = threading.Timer(1.0, stop.set)
        timer.start()
        started = monotonic()
        try:
            with pytest.raises(ValueError, match='copy_validate_fks_interrupted'):
                dispatch._long_phase(controller, copy_module, runtime, report, phase='validate_fks', sql=long_validate,
                                     params=params, relation='system_search', ids=[purge, purge],
                                     identity={'data_directory': '/unused'}, controller_alive=lambda: None,
                                     stop=stop, required_bytes=1, max_wal_size=1)
        finally:
            timer.cancel()
        assert monotonic() - started < 25
        failure = report['copy_phase_failures'][-1]
        assert failure['phase'] == 'validate_fks' and failure['sqlstate'] == '57014'
        assert failure['classification'] == 'retryable'


def test_opportunity_swap_back_restores_its_statistics_in_both_directions(copy_database, monkeypatch):
    """Codex 4379797637: swap-R recalibrates n_distinct on the copy; 019's
    swap-back compares attribute options with the retired table. swap-back-R
    restores the retired value in its own transaction, then a re-verified copy
    swaps forward and back again, as the owner or as the non-superuser app owner."""
    with _temp_file_limit_grant(copy_database[0]):
        _statistics_journey(copy_database, monkeypatch)


def _statistics_journey(copy_database, monkeypatch):
    c = copy_database[0]
    purge, plan = _authorize(copy_database)
    purge = str(purge)
    owner = _owner(c)
    owner.execute('ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 SET STATISTICS 1000')
    owner.execute('ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 SET (n_distinct = -0.13)')
    controller, dispatch, copy_module, runtime, saved = _phase_harness(monkeypatch, c, name='statistics')
    # The fixture's planner choice for the chunk read is not under test here.
    monkeypatch.setattr(copy_module, 'chunk_read_plan_ok', lambda plan_: True)
    staged(c, purge, 'system_search')
    _reset(c)
    swap(c, purge, 'system_search')
    validate(c, purge, 'system_search')
    drop(c, purge, 'system_search')
    original = oid(c, 'v3_derived.economy_opportunity')
    staged(c, purge, 'economy_opportunity')
    _reset(c)
    copy_oid = oid(c, 'v3_purge_staging.economy_opportunity')
    assert _attoptions(c, 'v3_purge_staging.economy_opportunity') == ['n_distinct=-0.13']
    ids = [purge, purge]
    identity = {'data_directory': '/unused'}
    stop = threading.Event()
    def swap_forward():
        report = {'reviewed_plan_sha256': plan['plan_sha256']}
        dispatch._swap(controller, copy_module, runtime, report, ids, identity, 'economy_opportunity',
                       _state_now(copy_module, runtime, plan, 'economy_opportunity'),
                       controller_alive=lambda: None, stop=stop, max_wal_size=1)
        return report
    def swap_backward():
        report = {'reviewed_plan_sha256': plan['plan_sha256']}
        dispatch._swap_back(controller, copy_module, runtime, report, ids, identity, 'economy_opportunity',
                            _state_now(copy_module, runtime, plan, 'economy_opportunity'),
                            controller_alive=lambda: None, stop=stop, max_wal_size=1)
        return report
    for direction in (1, 2):
        report = swap_forward()
        assert report['result'] == 'swap_verified' and report['long_phases'] == ['validate_fks', 'recalibrate_count', 'recalibrate_analyze']
        recalibration = report['n_distinct_recalibration']
        wanted = copy_module.n_distinct_option(-recalibration['n_distinct'])
        assert oid(c, 'v3_derived.economy_opportunity') == copy_oid and oid(c, 'v3_retired.economy_opportunity') == original
        assert _attoptions(c, 'v3_derived.economy_opportunity') == [wanted] != ['n_distinct=-0.13']
        assert _attoptions(c, 'v3_retired.economy_opportunity') == ['n_distinct=-0.13']
        # The restore value was recorded before the ALTER, retired table included.
        record, path = saved[-1]
        assert path.endswith('derived-purge-copy-statistics.json') and len(saved) == direction
        assert record['live_attoptions_before'] == ['n_distinct=-0.13'] == record['retired_attoptions']
        # 019's own swap-back refuses the recalibrated copy: this is the defect.
        with pytest.raises(psycopg.errors.RaiseException):
            _json(c, copy_module.SWAP_BACK_SQL, {'purge_id': purge, 'relation': 'economy_opportunity'})
        c.execute('ROLLBACK')
        _reset(c)
        back = swap_backward()
        assert back['result'] == 'swapped_back_live_restored' and back['long_phases'] == ['validate_fks']
        assert copy_module.SWAP_BACK_OPPORTUNITY_SQL in runtime.statements
        assert back['n_distinct_restore']['before']['attoptions'] == [wanted]
        assert back['n_distinct_restore']['after']['attoptions'] == ['n_distinct=-0.13']
        assert oid(c, 'v3_derived.economy_opportunity') == original
        assert oid(c, 'v3_purge_staging.economy_opportunity') == copy_oid
        assert _attoptions(c, 'v3_derived.economy_opportunity') == ['n_distinct=-0.13']
        assert _attoptions(c, 'v3_purge_staging.economy_opportunity') == ['n_distinct=-0.13']
        state = _state_now(copy_module, runtime, plan, 'economy_opportunity')
        assert state['phase'] == 'SWAPPED_BACK' and state['fk_validated'] is not None
        assert copy_module.next_step(state, 10, None) == 'verify'
        # copy-R re-verifies the staged copy (019 allows SWAPPED_BACK).
        assert type(_json(c, copy_module.VERIFY_SQL, {'purge_id': purge, 'relation': 'economy_opportunity'})['event']) is int
        _reset(c)
    # A third forward swap, then an idempotent re-dispatch: no second ALTER.
    swap_forward()
    assert len(saved) == 3
    again = swap_forward()
    assert again['result'] == 'swap_already_verified' and again['n_distinct_recalibration']['host_state'] is None
    assert len(saved) == 3
    drop(c, purge, 'economy_opportunity')
    assert oid(c, 'v3_retired.economy_opportunity') is None


def test_committed_swap_back_and_swap_resume_without_a_second_relocation(superuser_database, monkeypatch):
    """Codex 4379797650: staged + SWAPPED_BACK with NOT VALID child FKs is
    resumable (validate + smoke only), and so is a committed forward swap.
    The vector has four child relations, so its child FKs are re-pointed."""
    with _temp_file_limit_grant(superuser_database[0]):
        _resume_journey(superuser_database, monkeypatch)


def _resume_journey(superuser_database, monkeypatch):
    c = superuser_database[0]
    purge, plan = _authorize(superuser_database)
    purge = str(purge)
    controller, dispatch, copy_module, runtime, _saved = _phase_harness(monkeypatch, c, name='resume')
    for code in ('system_search', 'economy_opportunity', 'body_mechanics'):
        staged(c, purge, code)
        _reset(c)
        swap(c, purge, code)
        validate(c, purge, code)
        drop(c, purge, code)
    staged(c, purge, 'system_rating_vector')
    _reset(c)
    original = oid(c, 'v3_derived.system_rating_vector')
    swap(c, purge, 'system_rating_vector')
    validate(c, purge, 'system_rating_vector')
    # The swap-back commits; its FK validation never runs (the job was lost).
    assert type(_json(c, copy_module.SWAP_BACK_SQL, {'purge_id': purge, 'relation': 'system_rating_vector'})['event']) is int
    _reset(c)
    assert oid(c, 'v3_derived.system_rating_vector') == original
    not_valid = "SELECT count(*) FROM pg_constraint WHERE confrelid='v3_derived.system_rating_vector'::regclass AND NOT convalidated"
    assert _owner(c).execute(not_valid).fetchone()[0] == 4
    state = _state_now(copy_module, runtime, plan, 'system_rating_vector')
    assert state['copy_position'] == 'staged' and state['phase'] == 'SWAPPED_BACK' and state['fk_validated'] is None
    assert copy_module.next_step(state, 10, None) == 'refuse:swap_back_fk_validation_pending'
    runtime.statements.clear()
    report = {'reviewed_plan_sha256': plan['plan_sha256']}
    stop = threading.Event()
    dispatch._swap_back(controller, copy_module, runtime, report, [purge, purge], {'data_directory': '/unused'},
                        'system_rating_vector', state, controller_alive=lambda: None, stop=stop, max_wal_size=1)
    assert report['swap_back_resumed'] is True and report['result'] == 'swapped_back_live_restored'
    assert copy_module.SWAP_BACK_SQL not in runtime.statements and report['long_phases'] == ['validate_fks']
    assert _owner(c).execute(not_valid).fetchone()[0] == 0
    assert oid(c, 'v3_derived.system_rating_vector') == original
    # A re-dispatch after that changes nothing physical either.
    again = {'reviewed_plan_sha256': plan['plan_sha256']}
    dispatch._swap_back(controller, copy_module, runtime, again, [purge, purge], {'data_directory': '/unused'},
                        'system_rating_vector', _state_now(copy_module, runtime, plan, 'system_rating_vector'),
                        controller_alive=lambda: None, stop=stop, max_wal_size=1)
    assert again['result'] == 'swap_back_already_verified' and 'long_phases' not in again
    # Forward again: re-verify, the swap commits, its validation is lost.
    verify(c, purge, 'system_rating_vector')
    swap(c, purge, 'system_rating_vector')
    _reset(c)
    copy_oid = oid(c, 'v3_derived.system_rating_vector')
    assert _owner(c).execute(not_valid).fetchone()[0] == 4
    runtime.statements.clear()
    forward = {'reviewed_plan_sha256': plan['plan_sha256']}
    dispatch._swap(controller, copy_module, runtime, forward, [purge, purge], {'data_directory': '/unused'},
                   'system_rating_vector', _state_now(copy_module, runtime, plan, 'system_rating_vector'),
                   controller_alive=lambda: None, stop=stop, max_wal_size=1)
    assert forward['swap_resumed'] is True and forward['result'] == 'swap_verified'
    assert copy_module.SWAP_SQL not in runtime.statements and forward['long_phases'] == ['validate_fks']
    assert oid(c, 'v3_derived.system_rating_vector') == copy_oid
    assert _owner(c).execute(not_valid).fetchone()[0] == 0
    drop(c, purge, 'system_rating_vector')
    assert type(_json(c, copy_module.COMPLETE_SQL, {'purge_id': purge})['event']) is int


def test_competing_copy_lock_or_statement_is_observed(superuser_database):
    c = superuser_database[0]
    _authorize(superuser_database)
    assert _json(c, copy.COMPETING_COPY_SQL) == {'lock_holders': 0, 'copy_statements': 0}
    other = psycopg.connect(make_conninfo(c.info.dsn, password=c.info.password))
    try:
        # 019's own lock call, held by an open transaction elsewhere.
        other.execute('SELECT pg_try_advisory_xact_lock(764019001)')
        assert _json(c, copy.COMPETING_COPY_SQL)['lock_holders'] == 1
        other.rollback()
        assert _json(c, copy.COMPETING_COPY_SQL) == {'lock_holders': 0, 'copy_statements': 0}
    finally:
        other.close()
    sleeper = psycopg.connect(make_conninfo(c.info.dsn, password=c.info.password), autocommit=True)
    thread = threading.Thread(target=lambda: sleeper.execute(
        "SELECT pg_sleep(2) /* v3_meta.purge_copy_chunk( */"))
    thread.start()
    try:
        deadline = monotonic() + 5
        seen = 0
        while monotonic() < deadline and not seen:
            seen = _json(c, copy.COMPETING_COPY_SQL)['copy_statements']
        assert seen == 1
    finally:
        thread.join(timeout=10)
        sleeper.close()



def test_cancel_allowlist_matches_the_recalibration_analyze_and_nothing_wider(superuser_database):
    """PR #894 review 4383773090: the recalibration ANALYZE now runs as a long
    phase, so the watchdog's fixed cancel allowlist must match it, evaluated by
    PostgreSQL's own regex engine, and still refuse other ANALYZE statements."""
    pattern = r"^\s*analyze v3_derived[.]economy_opportunity [(]system_id64[)]"
    assert "lower(a.query) ~ '" + pattern + "'" in copy.CANCEL_SQL
    statement = [line for line in copy.RECALIBRATE_ANALYZE_SQL.splitlines() if line.startswith('ANALYZE ')]
    assert statement == ['ANALYZE v3_derived.economy_opportunity (system_id64);']
    c = _owner(superuser_database[0])
    for text, expected in ((statement[0], True), ('  ' + statement[0], True),
                           ('ANALYZE v3_derived.system_search;', False),
                           ('ANALYZE v3_derived.economy_opportunity;', False),
                           ('SELECT 1; ' + statement[0], False)):
        matched = c.execute('SELECT lower(%s) ~ %s', (text, pattern)).fetchone()[0]
        assert matched is expected, text
