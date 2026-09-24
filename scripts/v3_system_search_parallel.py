#!/usr/bin/env python3
"""Bounded, resumable Search chunk-range workers; never publish a generation.

Requires a READY Ratings generation, migration 013, and explicit database
authority. `prepare`, `work`, and `finalize` may run separately; `run` starts
one independent direct Psycopg connection per range and then validates once.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import threading
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import v3_system_search as serial  # noqa: E402

MAX_WORKERS = 64
MAX_CHUNKS = 2_147_483_647
MAX_CHUNKS_PER_INVOCATION = 1_000_000
LOCK_TIMEOUT_MS = 30_000
STATEMENT_TIMEOUT_MS = 900_000


def _bounded(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer between {low} and {high}')
    return value


def partition_ranges(total_chunks: int, workers: int) -> list[tuple[int, int]]:
    _bounded(total_chunks, 'total_chunks', 1, MAX_CHUNKS)
    _bounded(workers, 'workers', 1, min(MAX_WORKERS, total_chunks))
    return [(index * total_chunks // workers, (index + 1) * total_chunks // workers)
            for index in range(workers)]


def scheduler_identity() -> bytes:
    return serial._digest({
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in (
            'scripts/v3_system_search_parallel.py',
            'sql/v3/migrations/013_v3_system_search_parallel.sql',
        )
    })


def _require_connection(connection):
    from psycopg.pq import TransactionStatus

    if not connection.autocommit or connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError('requires an idle, direct autocommit connection with explicit chunk transactions')
    if connection.execute('SHOW session_replication_role').fetchone()[0] != 'origin':
        raise ValueError('Search requires origin triggers')
    if connection.execute('SHOW transaction_isolation').fetchone()[0] != 'read committed':
        raise ValueError('Search requires read committed isolation')


def _timeouts(connection):
    connection.execute("SELECT set_config('lock_timeout',%s,true)", (str(LOCK_TIMEOUT_MS),))
    connection.execute("SELECT set_config('statement_timeout',%s,true)", (str(STATEMENT_TIMEOUT_MS),))


def _lock_base(connection, generation_id):
    row = connection.execute(
        '''SELECT lifecycle_state FROM v3_meta.derived_generation
            WHERE derived_generation_id=%s FOR SHARE''', (generation_id,),
    ).fetchone()
    if row is None or row[0] != 'READY':
        raise ValueError('parallel Search requires a READY Ratings generation')


def _load_plan(connection, generation_key):
    generation = serial._generation(connection, generation_key)
    if generation.state != 'READY':
        raise ValueError('parallel Search requires a READY Ratings generation')
    manifest = serial.product_manifest(generation)
    manifest_sha = serial._digest(manifest)
    product = serial._product(connection, generation.identifier)
    if (product is None or product[0] != serial.PRODUCT_VERSION
            or product[1] not in {'BUILDING', 'READY'} or product[2] != manifest
            or bytes(product[3]) != manifest_sha
            or int(product[4]) != generation.expected_systems):
        raise ValueError('Search product manifest/state differs from current code/input')
    plan = connection.execute(
        '''SELECT manifest_sha256,scheduler_sha256,workers,total_chunks
             FROM v3_meta.search_rebuild_plan WHERE derived_generation_id=%s''',
        (generation.identifier,),
    ).fetchone()
    if plan is None:
        raise ValueError('parallel Search plan is not prepared')
    if bytes(plan[0]) != manifest_sha or bytes(plan[1]) != scheduler_identity():
        raise ValueError('parallel Search manifest/scheduler identity changed')
    workers, total_chunks = int(plan[2]), int(plan[3])
    expected = partition_ranges(total_chunks, workers)
    ranges = connection.execute(
        '''SELECT range_id,first_chunk,end_chunk,next_chunk
             FROM v3_meta.search_rebuild_range WHERE derived_generation_id=%s
            ORDER BY range_id LIMIT 65''', (generation.identifier,),
    ).fetchall()
    if len(ranges) != workers or any(
        row[0] != index or (row[1], row[2]) != expected[index]
        or not row[1] <= row[3] <= row[2]
        for index, row in enumerate(ranges)
    ):
        raise ValueError('parallel Search range partition changed')
    return generation, manifest_sha, workers, ranges


def prepare(connection, generation_key: str, *, workers: int) -> dict:
    """Freeze N disjoint existing-chunk ranges, or verify an identical plan."""
    _bounded(workers, 'workers', 1, MAX_WORKERS)
    _require_connection(connection)
    # Bulk-write safety: this scheduler only writes derived-product metadata.
    # Origin triggers/FKs must remain enabled; no canonical tables are updated.
    with connection.transaction():
        _timeouts(connection)
        # Registration/finalization use the publication guard's advisory lock
        # before base/product locks. Workers never take this global mutex.
        connection.execute('SELECT pg_advisory_xact_lock(764003001)')
        generation = serial._generation(connection, generation_key)
        _lock_base(connection, generation.identifier)
        generation, state, manifest_sha = serial.register_product(connection, generation_key)
        connection.execute(
            '''SELECT 1 FROM v3_meta.derived_product
                WHERE derived_generation_id=%s AND product_code=%s FOR UPDATE''',
            (generation.identifier, serial.PRODUCT_CODE),
        )
        existing = connection.execute(
            'SELECT workers FROM v3_meta.search_rebuild_plan WHERE derived_generation_id=%s',
            (generation.identifier,),
        ).fetchone()
        if existing is None:
            if state != 'BUILDING':
                raise ValueError('a new parallel Search plan requires a BUILDING product')
            count, first, last, systems = connection.execute(
                '''SELECT count(*),min(chunk_ordinal),max(chunk_ordinal),sum(systems)
                     FROM v3_derived.build_chunk WHERE derived_generation_id=%s''',
                (generation.identifier,),
            ).fetchone()
            if not count or first != 0 or last != count - 1 or systems != generation.expected_systems:
                raise ValueError('Ratings chunks do not provide complete contiguous coverage')
            ranges = partition_ranges(int(count), workers)
            connection.execute(
                '''INSERT INTO v3_meta.search_rebuild_plan
                       (derived_generation_id,manifest_sha256,scheduler_sha256,workers,total_chunks)
                   VALUES (%s,%s,%s,%s,%s)''',
                (generation.identifier, manifest_sha, scheduler_identity(), workers, count),
            )
            for index, (first, end) in enumerate(ranges):
                connection.execute(
                    '''INSERT INTO v3_meta.search_rebuild_range
                           (derived_generation_id,range_id,first_chunk,end_chunk,next_chunk)
                       VALUES (%s,%s,%s,%s,%s)''',
                    (generation.identifier, index, first, end, first),
                )
        elif int(existing[0]) != workers:
            raise ValueError('prepared worker count cannot change')
        _, _, _, ranges = _load_plan(connection, generation_key)
    return {'status': 'PREPARED', 'derived_generation_id': generation.identifier,
            'workers': workers, 'ranges': [list(row) for row in ranges]}


def run_worker(connection, generation_key: str, *, range_id: int,
               max_chunks: int | None = None, progress=None,
               stop: threading.Event | None = None) -> dict:
    """Commit one bounded Ratings chunk plus its checkpoint per transaction.

    A repeated invocation safely skips committed receipts. A crash rolls back
    rows, receipt and cursor together; there are no persistent leases to repair.
    """
    _bounded(range_id, 'range_id', 0, MAX_WORKERS - 1)
    if max_chunks is not None:
        _bounded(max_chunks, 'max_chunks', 1, MAX_CHUNKS_PER_INVOCATION)
    _require_connection(connection)
    generation, manifest_sha, workers, _ = _load_plan(connection, generation_key)
    if range_id >= workers:
        raise ValueError('range_id is outside the prepared partition')
    seen = written = 0
    while True:
        with connection.transaction():
            _timeouts(connection)
            _lock_base(connection, generation.identifier)
            # Base -> product -> range -> source chunk: same order for every
            # worker. SHARE excludes READY finalization but allows all ranges.
            product = connection.execute(
                '''SELECT lifecycle_state,manifest_sha256 FROM v3_meta.derived_product
                    WHERE derived_generation_id=%s AND product_code=%s FOR SHARE''',
                (generation.identifier, serial.PRODUCT_CODE),
            ).fetchone()
            if product is None or bytes(product[1]) != manifest_sha:
                raise ValueError('Search product manifest changed')
            row = connection.execute(
                '''SELECT next_chunk,end_chunk FROM v3_meta.search_rebuild_range
                    WHERE derived_generation_id=%s AND range_id=%s FOR UPDATE''',
                (generation.identifier, range_id),
            ).fetchone()
            if row is None:
                raise ValueError('parallel Search range disappeared')
            ordinal, end = map(int, row)
            if product[0] not in {'BUILDING', 'READY'}:
                raise ValueError('Search product cannot resume from current state')
            if ordinal == end:
                break
            if product[0] != 'BUILDING':
                raise ValueError('Search product is not BUILDING')
            if max_chunks is not None and seen >= max_chunks:
                break
            # Cooperative stop: when a peer range fails, the orchestrator sets
            # this event so the remaining workers exit PAUSED at the next chunk
            # boundary instead of running their (possibly multi-day) range to
            # completion. Checked here, ordinal/end are already bound, so the
            # PAUSED return below reports an accurate resume cursor.
            if stop is not None and stop.is_set():
                break
            chunk = connection.execute(
                '''SELECT chunk_ordinal,systems,canonical_input_sha256,content_sha256
                     FROM v3_derived.build_chunk
                    WHERE derived_generation_id=%s AND chunk_ordinal=%s''',
                (generation.identifier, ordinal),
            ).fetchone()
            if chunk is None:
                raise ValueError('prepared Ratings chunk disappeared')
            did_write = serial._insert_chunk(connection, generation, manifest_sha, chunk)
            # This UPDATE touches only scheduler metadata, never canonical data.
            # It MUST share the outer transaction with _insert_chunk's savepoint.
            changed = connection.execute(
                '''UPDATE v3_meta.search_rebuild_range
                      SET next_chunk=%s,updated_at=clock_timestamp()
                    WHERE derived_generation_id=%s AND range_id=%s AND next_chunk=%s''',
                (ordinal + 1, generation.identifier, range_id, ordinal),
            ).rowcount
            if changed != 1:
                raise ValueError('parallel Search checkpoint changed')
        seen += 1
        written += int(did_write)
        if progress is not None:
            progress({'derived_generation_id': generation.identifier, 'range_id': range_id,
                      'chunk_ordinal': ordinal, 'systems': int(chunk[1]), 'written': did_write})
    return {'status': 'RANGE_COMPLETE' if ordinal == end else 'PAUSED',
            'derived_generation_id': generation.identifier, 'range_id': range_id,
            'chunks_seen': seen, 'chunks_written': written, 'next_chunk': ordinal}


def finalize(connection, generation_key: str) -> dict:
    """Validate once after every range is committed; never publish."""
    _require_connection(connection)
    with connection.transaction():
        _timeouts(connection)
        connection.execute('SELECT pg_advisory_xact_lock(764003001)')
        generation, manifest_sha, _, _ = _load_plan(connection, generation_key)
        _lock_base(connection, generation.identifier)
        connection.execute(
            '''SELECT 1 FROM v3_meta.derived_product
                WHERE derived_generation_id=%s AND product_code=%s FOR UPDATE''',
            (generation.identifier, serial.PRODUCT_CODE),
        )
        # Re-read after acquiring the product lock: any active chunk has now
        # committed; subsequent chunks wait until this transaction completes.
        remaining = connection.execute(
            '''SELECT count(*) FROM v3_meta.search_rebuild_range
                WHERE derived_generation_id=%s AND next_chunk<>end_chunk''',
            (generation.identifier,),
        ).fetchone()[0]
        if remaining:
            return {'status': 'INCOMPLETE', 'ranges_remaining': int(remaining)}
        return serial.validate_product(connection, generation, manifest_sha)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'work', 'finalize', 'run'))
    parser.add_argument('--generation-key', required=True)
    parser.add_argument('--expected-database', required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--range-id', type=int)
    parser.add_argument('--max-chunks', type=int)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if platform.python_implementation() != 'CPython' or sys.version_info[:2] != (3, 14):
            raise ValueError('CPython 3.14 is required')
        import psycopg
        if psycopg.__version__ != '3.3.4':
            raise ValueError('locked Psycopg 3.3.4 is required')
        if not serial.GENERATION_KEY.fullmatch(args.generation_key):
            raise ValueError('invalid derived generation key')
        if not 1 <= len(args.expected_database) <= 63:
            raise ValueError('expected database name is out of bounds')
        _bounded(args.workers, 'workers', 1, MAX_WORKERS)
        if args.action == 'work':
            _bounded(args.range_id, 'range_id', 0, MAX_WORKERS - 1)
        elif args.range_id is not None:
            raise ValueError('range-id requires work')
        if args.max_chunks is not None:
            _bounded(args.max_chunks, 'max_chunks', 1, MAX_CHUNKS_PER_INVOCATION)
            if args.action not in {'work', 'run'}:
                raise ValueError('max-chunks requires work or run')
        dsn = os.environ.get('V3_SYSTEM_SEARCH_DATABASE_URL')
        if not dsn:
            raise ValueError('database authority missing')

        def connect():
            connection = psycopg.connect(dsn, autocommit=True, connect_timeout=10,
                                         application_name='v3-system-search-parallel')
            if connection.info.dbname != args.expected_database:
                connection.close()
                raise ValueError('database differs from explicit authority')
            return connection

        def progress(item):
            print(json.dumps({'status': 'PROGRESS', **item}, sort_keys=True), flush=True)

        stop = threading.Event()

        def work(index):
            with connect() as connection:
                return run_worker(connection, args.generation_key, range_id=index,
                                  max_chunks=args.max_chunks, progress=progress, stop=stop)

        if args.action == 'work':
            result = work(args.range_id)
        else:
            with connect() as connection:
                if args.action == 'finalize':
                    result = finalize(connection, args.generation_key)
                else:
                    result = prepare(connection, args.generation_key, workers=args.workers)
                    if args.action == 'run':
                        # Connections belong to individual worker threads. The
                        # frozen plan survives any process/thread failure.
                        # as_completed surfaces the first failing range
                        # immediately (executor.map yields in submission order,
                        # so a late range's failure hides behind earlier
                        # still-running ranges); on failure, signal the peers to
                        # stop at their next chunk boundary rather than run to
                        # completion before this run reports FAILED.
                        with ThreadPoolExecutor(max_workers=args.workers) as executor:
                            futures = [executor.submit(work, index)
                                       for index in range(args.workers)]
                            results = []
                            try:
                                for future in as_completed(futures):
                                    results.append(future.result())
                            except Exception:
                                stop.set()
                                raise
                        results.sort(key=lambda worker: worker['range_id'])
                        result = {'workers': results, **finalize(connection, args.generation_key)}
    except Exception as exc:
        # Do not expose DSNs, credentials or server-supplied text in logs.
        print(json.dumps({'status': 'FAILED', 'error': type(exc).__name__}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
