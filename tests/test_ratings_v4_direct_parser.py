from contextlib import nullcontext
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
from uuid import UUID

import ijson
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ratings_v4 import production_generation  # noqa: E402
from scripts.ratings_v4.benchmark_source_parser import legacy_event_parser  # noqa: E402
from scripts.ratings_v4.canonical_stream import RetainedArtifactStream, _ArrayRootReader  # noqa: E402
from scripts.ratings_v4.run_generation import build_generation  # noqa: E402
from domain.ratings_v4_canonical import load_source_fixture  # noqa: E402
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


def stream_for(tmp_path, raw):
    compressed = gzip.compress(raw, mtime=0)
    path = tmp_path / 'galaxy.json.gz'
    path.write_bytes(compressed)
    return RetainedArtifactStream(path, sha256=hashlib.sha256(compressed).hexdigest(),
                                  size_bytes=len(compressed))


def test_root_guard_preserves_bytes_across_reads_and_ignores_read_zero():
    data = b' \t\r\n\v\f' * 20 + b'[{"id64":1}]  \n'
    source = io.BytesIO(data)
    reader = _ArrayRootReader(source)
    assert reader.read(0) == b''
    assert source.tell() == 0 and reader.checked is False
    pieces = []
    while piece := reader.read(3):
        pieces.append(piece)
    assert b''.join(pieces) == data
    assert reader.checked is True


@pytest.mark.parametrize('raw', [
    b'', b' \t\r\n', b'{"item":{"id64":1}}', b'null', b'1',
    b'"array"', b'\xef\xbb\xbf[{"id64":1}]',
    b'[{"id64":1}', b'[{"id64":1}] {}', b'[{"id64":1}] []',
    b'[{"id64":1,"bad":NaN}]', b'[{"id64":1,"bad":1e400}]',
    b'[{"id64":1,"name":"\xff"}]',
])
@pytest.mark.parametrize('legacy', [False, True], ids=['direct', 'legacy'])
def test_invalid_or_incomplete_json_never_produces_an_eof_receipt(tmp_path, raw, legacy):
    stream = stream_for(tmp_path, raw)
    with legacy_event_parser() if legacy else nullcontext():
        with pytest.raises((ValueError, ijson.JSONError, EOFError)):
            list(stream.chunks())
    assert stream.receipt is None


@pytest.mark.parametrize('prefix', [b'', b' \t\r\n\v\f'])
def test_direct_parser_preserves_numeric_unicode_and_backend_whitespace(tmp_path, prefix):
    raw = prefix + ('[{"id64":9223372036854775807,"bodies":[],"n":1.25,"z":-0.0,'
           '"name":"Étoile 🌟","nested":[true,null,{"s":"\\\\\\\""}]}]').encode()
    direct = stream_for(tmp_path, raw)
    actual = list(direct.chunks())
    legacy = stream_for(tmp_path, raw)
    with legacy_event_parser():
        expected = list(legacy.chunks())
    assert json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert direct.receipt == legacy.receipt


def test_complete_parallel_build_has_identical_rows_and_chunk_hashes_for_both_parsers(tmp_path, monkeypatch):
    _, _, payloads = load_source_fixture(ROOT / 'tests/fixtures/ratings_v4_sources')
    records = [payload['system'] for payload in payloads]
    compressed = gzip.compress(json.dumps(records).encode(), mtime=0)
    source = tmp_path / 'galaxy.json.gz'
    source.write_bytes(compressed)

    def retained_fixture(_canonical, metadata):
        metadata['artifact']['content_sha256'] = '\\x' + hashlib.sha256(compressed).hexdigest()
        metadata['artifact']['size_bytes'] = len(compressed)
        return ()

    identifier = UUID('6842309d-9775-448d-b8c7-44f081c11563')
    monkeypatch.setattr(production_generation, 'uuid4', lambda: identifier)
    results = []
    for legacy in (True, False):
        with canonical_database(prepare=retained_fixture) as (connection, _, _, _):
            connection.execute((ROOT / 'sql/v3/migrations/003_ratings_v4_derived.sql').read_text())
            with legacy_event_parser() if legacy else nullcontext():
                receipt = build_generation(connection, connection, source, 'parser_parity',
                                           chunk_size=3, workers=2)
            assert receipt['status'] == 'VERIFIED'
            assert receipt['lifecycle_state'] == 'READY'
            assert receipt['publication_performed'] is False
            rows = {}
            for table, columns, order in (
                ('system_rating_vector', production_generation.VECTOR_COLUMNS, 'system_id64'),
                ('body_mechanics', production_generation.BODY_COLUMNS, 'system_id64,body_pk'),
                ('economy_opportunity', production_generation.OPPORTUNITY_COLUMNS,
                 'system_id64,body_pk,economy_ordinal'),
            ):
                from psycopg import sql
                query = sql.SQL('SELECT {} FROM v3_derived.{} ORDER BY {}').format(
                    sql.SQL(',').join(map(sql.Identifier, columns)),
                    sql.Identifier(table), sql.SQL(order))
                rows[table] = connection.execute(query).fetchall()
            rows['chunks'] = connection.execute('''SELECT chunk_ordinal,
                source_projection_sha256,canonical_input_sha256,content_sha256,systems,
                canonical_bodies,physical_bodies,eligible_opportunities
                FROM v3_derived.build_chunk ORDER BY chunk_ordinal''').fetchall()
            # A completed resume must retain the already committed output.
            resumed = build_generation(connection, connection, source, 'parser_parity',
                                       chunk_size=3, workers=2)
            assert resumed['resumed'] is True
            assert resumed['chunks_written'] == 0
            results.append(rows)
    assert results[0] == results[1]
