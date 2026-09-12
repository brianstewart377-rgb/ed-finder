import gzip
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from domain.ratings_v4_canonical import load_source_fixture  # noqa: E402
from scripts.ratings_v4.run_generation import (  # noqa: E402
    MAX_ENCODER_WORKERS, build_generation,
)
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


def _retained_source(tmp_path):
    _, _, payloads = load_source_fixture(ROOT / 'tests/fixtures/ratings_v4_sources')
    records = [payload['system'] for payload in payloads]
    compressed = gzip.compress(json.dumps(records).encode(), mtime=0)
    source = tmp_path / 'galaxy.json.gz'
    source.write_bytes(compressed)
    return source, compressed


def test_parallel_runner_builds_ordered_atomic_chunks(tmp_path):
    source, compressed = _retained_source(tmp_path)

    def retained_fixture(_canonical, metadata):
        metadata['artifact']['content_sha256'] = '\\x' + hashlib.sha256(compressed).hexdigest()
        metadata['artifact']['size_bytes'] = len(compressed)
        return ()

    with canonical_database(prepare=retained_fixture) as (connection, _, _, _):
        connection.execute((ROOT / 'sql/v3/migrations/003_ratings_v4_derived.sql').read_text())
        receipt = build_generation(
            connection, connection, source, 'parallel_runner_fixture',
            chunk_size=3, workers=2,
        )
        assert receipt['status'] == 'VERIFIED'
        assert receipt['lifecycle_state'] == 'READY'
        assert receipt['chunks_seen'] == 4
        assert receipt['chunks_written'] == 4
        assert receipt['publication_performed'] is False
        chunks = connection.execute('''SELECT chunk_ordinal,systems FROM v3_derived.build_chunk
            WHERE derived_generation_id=%s ORDER BY chunk_ordinal''',
            (receipt['derived_generation_id'],)).fetchall()
        assert chunks == [(0, 3), (1, 3), (2, 3), (3, 3)]
        assert connection.execute('''SELECT published_at FROM v3_meta.derived_generation
            WHERE derived_generation_id=%s''',
            (receipt['derived_generation_id'],)).fetchone()[0] is None


@pytest.mark.parametrize('workers', [0, MAX_ENCODER_WORKERS + 1, True])
def test_parallel_worker_count_is_bounded_before_io(workers):
    with pytest.raises(ValueError, match='worker count'):
        build_generation(None, None, Path('/does/not/exist'), 'bounded_workers', workers=workers)
