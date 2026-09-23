"""Range workers, using only freshly created local disposable databases.

The retained twelve-system fixture supplies body/source relationships; synthetic
system names and positions make a deterministic Search projection dataset.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from queue import Queue
import sys
from threading import Barrier, Event, Lock
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import v3_system_search as serial  # noqa: E402
from scripts import v3_system_search_parallel as parallel  # noqa: E402
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402
from tests.test_ratings_v4_system_search import (  # noqa: E402
    _ratings_generation, _ready_ratings,
)


def _synthetic_systems(canonical, metadata):
    for index, row in enumerate(canonical['systems']):
        row.update(
            name=f'Parallel Search Fixture {index:02d}',
            x_ly=float(index * 10), y_ly=float(-index * 10), z_ly=0.0,
            grid_x=index, grid_y=-index, grid_z=0,
        )
    return ()


@pytest.fixture(scope='module')
def database():
    # canonical_database rejects non-loopback hosts and any base database except
    # ratings_v4_validation; it creates and drops its own random v4_test_* DB.
    with canonical_database(prepare=_synthetic_systems) as fixture:
        connection, _, _, _ = fixture
        for migration in (
            '003_ratings_v4_derived.sql',
            '004_v3_search_spatial_clusters.sql',
            '006_v3_derived_product_lifecycle.sql',
            '010_v3_system_search_body_type_counts.sql',
            '013_v3_system_search_parallel.sql',
        ):
            connection.execute((ROOT / 'sql/v3/migrations' / migration).read_text())
        yield fixture


def _ready_generation(database, *, chunk_size=4):
    key, generation_id, _, _ = _ratings_generation(database, chunk_size=chunk_size)
    _ready_ratings(database, generation_id)
    return key, generation_id


def _search_rows(connection, generation_id):
    # Compare every projection column, including cube position and all F1 counts;
    # the independently allocated generation identity is intentionally excluded.
    return connection.execute(
        '''SELECT to_jsonb(s)-'derived_generation_id'
             FROM v3_derived.system_search s
            WHERE derived_generation_id=%s ORDER BY system_id64''',
        (generation_id,),
    ).fetchall()


def _receipts(connection, generation_id):
    # Source seals incorporate the generation identity, while content hashes do
    # not. Compare those content hashes and exact chunk coverage across builders.
    return connection.execute(
        '''SELECT chunk_ordinal,content_sha256,systems
             FROM v3_derived.search_build_chunk
            WHERE derived_generation_id=%s ORDER BY chunk_ordinal''',
        (generation_id,),
    ).fetchall()


def _ranges(connection, generation_id):
    return connection.execute(
        '''SELECT range_id,first_chunk,end_chunk,next_chunk
             FROM v3_meta.search_rebuild_range
            WHERE derived_generation_id=%s ORDER BY range_id''',
        (generation_id,),
    ).fetchall()


def _assert_complete_counts(connection, generation_id, *, chunks):
    counts = connection.execute(
        '''SELECT
               (SELECT count(*) FROM v3_derived.system_search
                 WHERE derived_generation_id=%s),
               (SELECT count(DISTINCT system_id64) FROM v3_derived.system_search
                 WHERE derived_generation_id=%s),
               (SELECT count(*) FROM v3_derived.search_build_chunk
                 WHERE derived_generation_id=%s)''',
        (generation_id, generation_id, generation_id),
    ).fetchone()
    assert counts == (12, 12, chunks)
    assert all(next_chunk == end for _, _, end, next_chunk in _ranges(connection, generation_id))


def _fixture_dsn(connection):
    from psycopg.conninfo import make_conninfo

    # Psycopg's public DSN omits the password; preserve the fixture connection's
    # credential without logging it or consulting another database authority.
    return make_conninfo(connection.info.dsn, password=connection.info.password)


def _thread_worker(dsn, key, range_id, *, start=None, pids=None):
    import psycopg

    # The DSN comes from the fixture's already-created random local test DB.
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("SET statement_timeout='20s'")
        if pids is not None:
            pids.put(connection.info.backend_pid)
        if start is not None:
            start.wait(timeout=10)
        return parallel.run_worker(connection, key, range_id=range_id)


def _wait_for_worker_lock(connection, worker_pids):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        blocked = connection.execute(
            '''SELECT EXISTS (SELECT 1 FROM pg_stat_activity
                 WHERE pid=ANY(%s) AND wait_event_type='Lock')''',
            (worker_pids,),
        ).fetchone()[0]
        if blocked:
            return True
        Event().wait(0.01)
    return False


@pytest.mark.parametrize('total,workers', [(1, 1), (2, 2), (3, 2), (17, 4), (101, 64)])
def test_partition_ranges_cover_every_chunk_exactly_once(total, workers):
    ranges = parallel.partition_ranges(total, workers)
    assert len(ranges) == workers
    assert ranges[0][0] == 0
    assert ranges[-1][1] == total
    assert all(first < end for first, end in ranges)
    assert all(left[1] == right[0] for left, right in zip(ranges, ranges[1:], strict=False))
    assert [chunk for first, end in ranges for chunk in range(first, end)] == list(range(total))
    sizes = [end - first for first, end in ranges]
    assert max(sizes) - min(sizes) <= 1


@pytest.mark.parametrize('total,workers', [
    (0, 1), (-1, 1), (True, 1), (1.5, 1), ('3', 1),
    (2**31, 1), (3, 0), (3, -1), (3, True), (3, 1.5), (3, '2'), (3, 4), (100, 65),
])
def test_partition_ranges_reject_unbounded_or_invalid_inputs(total, workers):
    with pytest.raises(ValueError):
        parallel.partition_ranges(total, workers)


def test_disjoint_ranges_match_serial_rows_and_content_hashes(database):
    connection, _, _, _ = database
    serial_key, serial_id = _ready_generation(database, chunk_size=2)
    generation, _, manifest_sha = serial.register_product(connection, serial_key)
    assert serial.build_available(connection, generation, manifest_sha)['chunks_written'] == 6
    assert serial.validate_product(connection, generation, manifest_sha)['status'] == 'VERIFIED'

    key, generation_id = _ready_generation(database, chunk_size=2)
    parallel.prepare(connection, key, workers=3)
    assert _ranges(connection, generation_id) == [(0, 0, 2, 0), (1, 2, 4, 2), (2, 4, 6, 4)]
    # Out-of-order completion must not impose any global ordinal assumption.
    for range_id in (2, 0, 1):
        result = parallel.run_worker(connection, key, range_id=range_id)
        assert result['status'] == 'RANGE_COMPLETE'
        assert result['chunks_written'] == 2
    _assert_complete_counts(connection, generation_id, chunks=6)
    assert _search_rows(connection, generation_id) == _search_rows(connection, serial_id)
    assert _receipts(connection, generation_id) == _receipts(connection, serial_id)
    receipt = parallel.finalize(connection, key)
    assert receipt['status'] == 'VERIFIED'
    assert receipt['coverage_complete'] is True
    assert parallel.finalize(connection, key) == receipt
    replay = parallel.run_worker(connection, key, range_id=0)
    assert replay['status'] == 'RANGE_COMPLETE'
    assert replay['chunks_seen'] == replay['chunks_written'] == 0
    _assert_complete_counts(connection, generation_id, chunks=6)


def test_parallel_resume_skips_compatible_serial_receipts(database):
    connection, _, _, _ = database
    key, generation_id = _ready_generation(database)
    generation, _, manifest_sha = serial.register_product(connection, key)
    assert serial.build_available(
        connection, generation, manifest_sha, max_chunks=1,
    )['chunks_written'] == 1
    first_receipt = _receipts(connection, generation_id)[0]

    parallel.prepare(connection, key, workers=2)
    results = [parallel.run_worker(connection, key, range_id=index) for index in (0, 1)]
    assert sum(result['chunks_seen'] for result in results) == 3
    assert sum(result['chunks_written'] for result in results) == 2
    assert _receipts(connection, generation_id)[0] == first_receipt
    _assert_complete_counts(connection, generation_id, chunks=3)
    assert parallel.finalize(connection, key)['status'] == 'VERIFIED'


def test_disjoint_workers_write_concurrently(database, monkeypatch):
    connection, _, _, _ = database
    key, generation_id = _ready_generation(database, chunk_size=2)
    parallel.prepare(connection, key, workers=2)
    rendezvous = Barrier(2)
    original = serial._chunk_content_sha

    def checksum(connection, generation_id, ordinal):
        if ordinal in {0, 3}:
            # This runs after each INSERT, while its chunk transaction is open.
            # A product-wide FOR UPDATE lock makes this barrier time out.
            rendezvous.wait(timeout=10)
        return original(connection, generation_id, ordinal)

    monkeypatch.setattr(serial, '_chunk_content_sha', checksum)
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = [executor.submit(_thread_worker, _fixture_dsn(connection), key, index) for index in (0, 1)]
        results = [job.result(timeout=30) for job in jobs]
    assert [result['chunks_written'] for result in results] == [3, 3]
    _assert_complete_counts(connection, generation_id, chunks=6)
    assert parallel.finalize(connection, key)['status'] == 'VERIFIED'


def test_duplicate_range_workers_serialize_and_never_double_write(database, monkeypatch):
    connection, _, _, _ = database
    key, generation_id = _ready_generation(database)
    parallel.prepare(connection, key, workers=1)
    start = Barrier(3)
    entered, release = Event(), Event()
    pids = Queue()
    calls = Counter()
    calls_lock = Lock()
    original = serial._chunk_content_sha

    def checksum(connection, generation_id, ordinal):
        with calls_lock:
            calls[ordinal] += 1
        if ordinal == 0:
            entered.set()
            assert release.wait(timeout=15), 'test did not release first chunk'
        return original(connection, generation_id, ordinal)

    monkeypatch.setattr(serial, '_chunk_content_sha', checksum)
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = [executor.submit(
            _thread_worker, _fixture_dsn(connection), key, 0, start=start, pids=pids,
        ) for _ in range(2)]
        worker_pids = [pids.get(timeout=10) for _ in range(2)]
        start.wait(timeout=10)
        try:
            assert entered.wait(timeout=10), 'first worker did not enter its chunk'
            assert _wait_for_worker_lock(connection, worker_pids), (
                'duplicate range worker did not wait for the in-flight chunk'
            )
        finally:
            release.set()
        results = [job.result(timeout=30) for job in jobs]
    assert all(result['status'] == 'RANGE_COMPLETE' for result in results)
    assert sum(result['chunks_written'] for result in results) == 3
    assert calls == Counter({0: 1, 1: 1, 2: 1})
    _assert_complete_counts(connection, generation_id, chunks=3)


def test_source_chunk_mutex_prevents_direct_duplicate_inserts(database, monkeypatch):
    import psycopg

    connection, _, _, _ = database
    key, generation_id = _ready_generation(database)
    generation, _, manifest_sha = serial.register_product(connection, key)
    chunk = serial._rating_chunks(connection, generation.identifier)[0]
    start = Barrier(3)
    entered, release = Event(), Event()
    pids = Queue()
    calls = []
    original = serial._chunk_content_sha

    def checksum(connection, generation_id, ordinal):
        calls.append(ordinal)
        entered.set()
        assert release.wait(timeout=15), 'test did not release the source chunk'
        return original(connection, generation_id, ordinal)

    def insert_chunk():
        with psycopg.connect(_fixture_dsn(connection), autocommit=True) as worker:
            worker.execute("SET statement_timeout='20s'")
            pids.put(worker.info.backend_pid)
            start.wait(timeout=10)
            return serial._insert_chunk(worker, generation, manifest_sha, chunk)

    monkeypatch.setattr(serial, '_chunk_content_sha', checksum)
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = [executor.submit(insert_chunk) for _ in range(2)]
        worker_pids = [pids.get(timeout=10) for _ in range(2)]
        start.wait(timeout=10)
        try:
            assert entered.wait(timeout=10), 'source chunk INSERT was not reached'
            assert _wait_for_worker_lock(connection, worker_pids), (
                'duplicate source chunk writer did not wait for its row lock'
            )
        finally:
            release.set()
        assert sorted(job.result(timeout=30) for job in jobs) == [False, True]
    assert calls == [0]
    assert len(_search_rows(connection, generation_id)) == 4
    assert len(_receipts(connection, generation_id)) == 1


def test_finalizer_waits_for_last_chunk_and_checks_committed_checkpoint(database, monkeypatch):
    import psycopg

    connection, _, _, _ = database
    key, generation_id = _ready_generation(database)
    parallel.prepare(connection, key, workers=1)
    assert parallel.run_worker(connection, key, range_id=0, max_chunks=2)['status'] == 'PAUSED'
    entered, release = Event(), Event()
    finalizer_pids = Queue()
    original = serial._chunk_content_sha

    def checksum(connection, generation_id, ordinal):
        assert ordinal == 2
        entered.set()
        assert release.wait(timeout=15), 'test did not release the final chunk'
        return original(connection, generation_id, ordinal)

    def finalize():
        with psycopg.connect(_fixture_dsn(connection), autocommit=True) as finalizer:
            finalizer_pids.put(finalizer.info.backend_pid)
            return parallel.finalize(finalizer, key)

    monkeypatch.setattr(serial, '_chunk_content_sha', checksum)
    with ThreadPoolExecutor(max_workers=2) as executor:
        worker_job = executor.submit(_thread_worker, _fixture_dsn(connection), key, 0)
        try:
            assert entered.wait(timeout=10), 'last chunk INSERT was not reached'
            finalize_job = executor.submit(finalize)
            pid = finalizer_pids.get(timeout=10)
            assert _wait_for_worker_lock(connection, [pid]), 'finalizer did not wait for the writer'
        finally:
            release.set()
        assert worker_job.result(timeout=30)['status'] == 'RANGE_COMPLETE'
        assert finalize_job.result(timeout=30)['status'] == 'VERIFIED'
    _assert_complete_counts(connection, generation_id, chunks=3)


@pytest.mark.parametrize('failure_location', ['during_checksum', 'before_checkpoint'])
def test_interrupted_chunk_rolls_back_rows_receipt_and_checkpoint(database, monkeypatch, failure_location):
    connection, _, _, _ = database
    key, generation_id = _ready_generation(database)
    parallel.prepare(connection, key, workers=1)
    first = parallel.run_worker(connection, key, range_id=0, max_chunks=1)
    assert first['status'] == 'PAUSED'
    before = (_search_rows(connection, generation_id), _receipts(connection, generation_id), _ranges(connection, generation_id))

    with monkeypatch.context() as patch:
        if failure_location == 'during_checksum':
            def fail_checksum(*args):
                raise RuntimeError('simulated worker interruption')
            patch.setattr(serial, '_chunk_content_sha', fail_checksum)
        else:
            original = serial._insert_chunk

            def fail_before_checkpoint(*args, **kwargs):
                original(*args, **kwargs)
                raise RuntimeError('simulated worker interruption')
            patch.setattr(serial, '_insert_chunk', fail_before_checkpoint)
        with pytest.raises(RuntimeError, match='simulated worker interruption'):
            parallel.run_worker(connection, key, range_id=0)

    after = (_search_rows(connection, generation_id), _receipts(connection, generation_id), _ranges(connection, generation_id))
    assert after == before
    assert _ranges(connection, generation_id) == [(0, 0, 3, 1)]
    resumed = parallel.run_worker(connection, key, range_id=0)
    assert resumed['status'] == 'RANGE_COMPLETE'
    assert resumed['chunks_written'] == 2
    _assert_complete_counts(connection, generation_id, chunks=3)
    assert parallel.finalize(connection, key)['status'] == 'VERIFIED'


def test_prepare_resume_and_bounded_worker_preserve_progress(database):
    connection, _, _, _ = database
    key, generation_id = _ready_generation(database)
    parallel.prepare(connection, key, workers=1)
    result = parallel.run_worker(connection, key, range_id=0, max_chunks=1)
    assert result['status'] == 'PAUSED'
    assert result['chunks_written'] == 1
    assert result['chunks_seen'] == 1
    assert _ranges(connection, generation_id) == [(0, 0, 3, 1)]
    assert parallel.finalize(connection, key)['status'] == 'INCOMPLETE'

    parallel.prepare(connection, key, workers=1)
    assert _ranges(connection, generation_id) == [(0, 0, 3, 1)]
    with pytest.raises(ValueError):
        parallel.prepare(connection, key, workers=2)
    result = parallel.run_worker(connection, key, range_id=0, max_chunks=2)
    assert result['status'] == 'RANGE_COMPLETE'
    assert result['chunks_written'] == 2
    rows, receipts = _search_rows(connection, generation_id), _receipts(connection, generation_id)
    replay = parallel.run_worker(connection, key, range_id=0)
    assert replay['status'] == 'RANGE_COMPLETE'
    assert replay['chunks_written'] == 0
    assert _search_rows(connection, generation_id) == rows
    assert _receipts(connection, generation_id) == receipts
    _assert_complete_counts(connection, generation_id, chunks=3)


def test_prepare_requires_ready_ratings(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    with pytest.raises(ValueError, match='READY'):
        parallel.prepare(connection, key, workers=1)
    assert connection.execute(
        'SELECT count(*) FROM v3_meta.search_rebuild_plan WHERE derived_generation_id=%s',
        (generation_id,),
    ).fetchone()[0] == 0


def test_invalid_worker_inputs_fail_before_writes(database):
    connection, _, _, _ = database
    key, generation_id = _ready_generation(database)
    with pytest.raises(ValueError):
        parallel.prepare(connection, key, workers=4)
    parallel.prepare(connection, key, workers=2)
    for range_id in (-1, 2, True, 0.5, '0'):
        with pytest.raises(ValueError):
            parallel.run_worker(connection, key, range_id=range_id)
    for max_chunks in (0, -1, True, 0.5, '1', 1_000_001):
        with pytest.raises(ValueError):
            parallel.run_worker(connection, key, range_id=0, max_chunks=max_chunks)
    assert _search_rows(connection, generation_id) == []
    assert _receipts(connection, generation_id) == []


def test_unsafe_connection_modes_fail_closed(database):
    connection, _, _, _ = database
    key, generation_id = _ready_generation(database)
    parallel.prepare(connection, key, workers=1)
    actions = (
        lambda: parallel.prepare(connection, key, workers=1),
        lambda: parallel.run_worker(connection, key, range_id=0),
        lambda: parallel.finalize(connection, key),
    )

    connection.autocommit = False
    try:
        for action in actions:
            with pytest.raises(ValueError, match='autocommit'):
                action()
    finally:
        connection.rollback()
        connection.autocommit = True

    # Deliberately unsafe modes are exercised only on the random disposable DB;
    # all actions must reject before writing, and the modes are always restored.
    connection.execute('SET session_replication_role=replica')
    try:
        for action in actions:
            with pytest.raises(ValueError, match='origin'):
                action()
    finally:
        connection.execute('SET session_replication_role=origin')

    connection.execute("SET default_transaction_isolation='repeatable read'")
    try:
        for action in actions:
            with pytest.raises(ValueError, match='read committed'):
                action()
    finally:
        connection.execute("SET default_transaction_isolation='read committed'")
    assert _search_rows(connection, generation_id) == []
    assert _receipts(connection, generation_id) == []
    assert _ranges(connection, generation_id) == [(0, 0, 3, 0)]


def test_worker_rejects_changed_product_manifest(database, monkeypatch):
    connection, _, _, _ = database
    key, generation_id = _ready_generation(database)
    parallel.prepare(connection, key, workers=1)
    changed = dict(serial.code_identity())
    changed['scripts/v3_system_search.py'] = '0' * 64
    monkeypatch.setattr(serial, 'code_identity', lambda: changed)
    with pytest.raises(ValueError, match='manifest'):
        parallel.run_worker(connection, key, range_id=0)
    with pytest.raises(ValueError, match='manifest'):
        parallel.finalize(connection, key)
    assert _search_rows(connection, generation_id) == []
    assert _ranges(connection, generation_id) == [(0, 0, 3, 0)]


def test_workers_and_finalizer_reject_scheduler_drift(database, monkeypatch):
    connection, _, _, _ = database
    key, generation_id = _ready_generation(database)
    parallel.prepare(connection, key, workers=1)
    monkeypatch.setattr(parallel, 'scheduler_identity', lambda: bytes(32))
    with pytest.raises(ValueError, match='scheduler'):
        parallel.prepare(connection, key, workers=1)
    with pytest.raises(ValueError, match='scheduler'):
        parallel.run_worker(connection, key, range_id=0)
    with pytest.raises(ValueError, match='scheduler'):
        parallel.finalize(connection, key)
    assert _search_rows(connection, generation_id) == []
    assert _ranges(connection, generation_id) == [(0, 0, 3, 0)]


def test_cli_runs_workers_and_checks_database_authority(database, monkeypatch, capsys):
    connection, _, _, _ = database
    key, generation_id = _ready_generation(database)
    monkeypatch.setenv('V3_SYSTEM_SEARCH_DATABASE_URL', _fixture_dsn(connection))
    common = ['run', '--generation-key', key, '--workers', '2', '--expected-database']
    assert parallel.main([*common, 'wrong_disposable_database']) == 1
    assert _search_rows(connection, generation_id) == []
    assert parallel.main([*common, connection.info.dbname]) == 0
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result['status'] == 'VERIFIED'
    assert sum(worker['chunks_written'] for worker in result['workers']) == 3
    _assert_complete_counts(connection, generation_id, chunks=3)
