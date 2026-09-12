"""Read-only, bounded prefix timing inside the existing Ratings container.

This separate process never patches/imports into the running builder process.
It uses the old builder's checkpoint projection and a transparent direct parser.
Only complete verified chunks count toward timing; a partial scan is not an EOF
receipt and extrapolation is explicitly conditional on the sampled data mix.
"""
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import signal
import sys
import time

GENERATION_KEY = 'ratings_v4_prod_p4_opt1'
GENERATION_ID = '403b2d43-820c-414a-ad57-0d4de0ca3e82'
DATABASE = 'edfinder_v3_phase4c_full_20260827_r5'
DURATION_SECONDS = 120
CHUNK_SIZE = 1000
MAX_CHUNK_BODIES = 100_000
LEGACY_CODE = {
    'scripts/ratings_v4/production_generation.py': 'd47815984c257261c6e306f7a842f24fd8a0e7732633e47c9e013fb3a007f7b5',
    'scripts/ratings_v4/run_generation.py': '43c4554e83545560bb4fceb2cb3b889c1eebc1f9bbb53c0a97423f8511c8b361',
    'scripts/ratings_v4/canonical_stream.py': '160322dbeac52908a1dddf41efa5d5f97e1cb7b6bfa46ab4bc658671108ca738',
    'sql/v3/migrations/003_ratings_v4_derived.sql': 'c7818f98ad00b4b99b7ce0f7c3fa12ece555e59e761b7b1ca15d437a39c499cb',
}


class ArrayRootReader:
    """Same bounded transparent root check as the reviewed PR #707 parser."""
    def __init__(self, stream):
        self.stream = stream
        self.checked = False

    def read(self, size=-1):
        data = self.stream.read(size)
        if size != 0 and not self.checked:
            prefix = data.lstrip(b' \t\r\n\v\f')
            if prefix:
                if prefix[:1] != b'[':
                    raise ValueError('Spansh artifact must be a JSON array')
                self.checked = True
            elif not data:
                raise ValueError('Spansh artifact must be a JSON array')
        return data


def direct_chunks(decoded, chunk_size=CHUNK_SIZE):
    import ijson
    from scripts.ratings_v4.canonical_stream import _system_ids

    chunk, bodies = [], 0
    for record in ijson.items(ArrayRootReader(decoded), 'item', use_float=True):
        if not isinstance(record, dict) or not isinstance(record.get('bodies', []), list):
            raise ValueError('invalid Spansh system record')
        _system_ids([record.get('id64')])
        count = len(record.get('bodies', []))
        if count > MAX_CHUNK_BODIES:
            raise ValueError('system exceeds bounded body inventory')
        if chunk and (len(chunk) >= chunk_size or bodies + count > MAX_CHUNK_BODIES):
            yield chunk
            chunk, bodies = [], 0
        chunk.append(record)
        bodies += count
    if chunk:
        yield chunk


def verify_chunk(checkpoint, ordinal, records):
    from scripts.ratings_v4.production_generation import _digest, _projection

    if (checkpoint[0] != ordinal or checkpoint[2] != len(records) or
            checkpoint[3] != sum(len(record.get('bodies', [])) for record in records) or
            bytes(checkpoint[1]) != _digest([_projection(record) for record in records])):
        raise ValueError('source/checkpoint prefix mismatch')


def emit(kind, **data):
    print(json.dumps({'kind': kind, 'utc': datetime.now(timezone.utc).isoformat(), **data},
                     sort_keys=True), flush=True)


def main():
    import psycopg
    import resource
    from scripts.ratings_v4.canonical_stream import _HashedReader
    from scripts.ratings_v4.production_generation import _digest, code_identity

    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (150, 160))
    os.nice(10)

    class Deadline(Exception):
        pass

    def deadline(_signum, _frame):
        raise Deadline

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(150)
    if code_identity() != LEGACY_CODE:
        raise ValueError('unexpected production builder identity')
    source = Path('/source/galaxy.json.gz')
    if not source.is_file() or source.is_symlink():
        raise ValueError('retained artifact must be a regular source mount')
    dsn = os.environ['RATINGS_V4_DERIVED_DATABASE_URL']
    with psycopg.connect(dsn, autocommit=True,
                         options='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000') as connection:
        if connection.execute('SELECT current_database()').fetchone()[0] != DATABASE:
            raise ValueError('unexpected database')
        if connection.execute('SHOW transaction_read_only').fetchone()[0] != 'on':
            raise ValueError('read-only connection required')
        row = connection.execute('''SELECT derived_generation_id,lifecycle_state,manifest,manifest_sha256
            FROM v3_meta.derived_generation WHERE generation_key=%s''', (GENERATION_KEY,)).fetchone()
        if (row is None or str(row[0]) != GENERATION_ID or row[1] != 'BUILDING' or
                row[2]['code_sha256_lf'] != LEGACY_CODE or _digest(row[2]) != bytes(row[3])):
            raise ValueError('unexpected generation identity/state')
        manifest = row[2]
        if source.stat().st_size != manifest['source_metadata']['artifact']['size_bytes']:
            raise ValueError('source size differs from manifest')
        checkpoints = connection.execute('''SELECT chunk_ordinal,source_projection_sha256,systems,canonical_bodies
            FROM v3_derived.build_chunk WHERE derived_generation_id=%s ORDER BY chunk_ordinal''', (GENERATION_ID,)).fetchall()
        if not checkpoints or any(row[0] != i for i, row in enumerate(checkpoints)):
            raise ValueError('committed prefix is empty or noncontiguous')
        before = sum(row[2] for row in checkpoints)
        emit('start', generation_id=GENERATION_ID, committed_systems=before,
             committed_chunks=len(checkpoints), expected_systems=manifest['expected_systems'],
             database_read_only=True, duration_seconds=DURATION_SECONDS)
        started = last_complete = time.monotonic()
        verified_systems = verified_chunks = 0
        deadline_reached = False
        with source.open('rb') as raw:
            reader = _HashedReader(raw)
            try:
                with gzip.GzipFile(fileobj=reader, mode='rb') as decoded:
                    for ordinal, records in enumerate(direct_chunks(decoded)):
                        if ordinal >= len(checkpoints):
                            break
                        verify_chunk(checkpoints[ordinal], ordinal, records)
                        verified_chunks += 1
                        verified_systems += len(records)
                        last_complete = time.monotonic()
                        if verified_chunks % 1000 == 0:
                            emit('progress', verified_chunks=verified_chunks,
                                 verified_systems=verified_systems, elapsed_seconds=last_complete-started)
                        if last_complete - started >= DURATION_SECONDS:
                            break
            except Deadline:
                deadline_reached = True
            signal.alarm(15)
            elapsed = time.monotonic() - started
            after = connection.execute('''SELECT COALESCE(sum(systems),0) FROM v3_derived.build_chunk
                WHERE derived_generation_id=%s''', (GENERATION_ID,)).fetchone()[0]
            sample_seconds = last_complete - started
            rate = verified_systems / sample_seconds if verified_systems and sample_seconds else None
            emit('summary', generation_id=GENERATION_ID, database_read_only=True,
                 ratings_writes_performed=False, worker_restarted=False,
                 elapsed_seconds=elapsed, completed_chunk_seconds=sample_seconds,
                 verified_chunks=verified_chunks, verified_systems=verified_systems,
                 prefix_systems_at_start=before, compressed_bytes_read=reader.bytes_read,
                 compressed_prefix_sha256=reader.digest.hexdigest(), source_eof_verified=False,
                 all_initial_checkpoints_verified=verified_chunks == len(checkpoints),
                 verified_systems_per_second=rate,
                 projected_prefix_seconds_if_same_mix=before / rate if rate else None,
                 projection_is_not_a_production_eta=True, deadline_reached=deadline_reached,
                 builder_systems_committed_during_sample=after-before,
                 builder_systems_per_second=(after-before)/elapsed)
    signal.alarm(0)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Never emit DSNs or raw database errors into an artifact.
        emit('failed', error_type=type(exc).__name__)
        sys.exit(1)
