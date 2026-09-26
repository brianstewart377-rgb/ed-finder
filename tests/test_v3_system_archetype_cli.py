"""F2b Task 5: CLI + follow loop + code-identity test.

Mirrors tests/test_v3_system_search_parallel.py's CLI test pattern (real
disposable database, DSN via monkeypatch.setenv on the same
`V3_..._DATABASE_URL` convention the builder's `main` already reads -- no
`--dsn` flag exists on either builder) and
tests/test_v3_system_archetype_build.py's fixture/harness. `builder.main`
without `--validate` registers + builds to full chunk coverage; `--validate`
runs `validate_product`, which promotes the product to READY on VERIFIED and
prints the receipt.
"""
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation, seal_source, validate_generation, write_chunk,
)
import scripts.v3_system_archetype as builder  # noqa: E402
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


@pytest.fixture
def database():
    with canonical_database() as (connection, canonical, metadata, payloads):
        for name in (
            '003_ratings_v4_derived.sql',
            '004_v3_search_spatial_clusters.sql',
            '006_v3_derived_product_lifecycle.sql',
            '011_v3_system_archetype.sql',
        ):
            connection.execute((ROOT / 'sql/v3/migrations' / name).read_text())
        yield connection, canonical, metadata, payloads


def _ratings_generation(database, *, chunk_size=4):
    connection, _, _, payloads = database
    snapshot = CanonicalSnapshot.pin(connection)
    key = 'archetype_cli_test_' + uuid4().hex
    generation_id = create_generation(connection, snapshot, key)
    records = [payload['system'] for payload in payloads]
    for ordinal, start in enumerate(range(0, len(records), chunk_size)):
        chunk = records[start:start + chunk_size]
        canonical = snapshot.export_chunk(
            connection, [record['id64'] for record in chunk],
        )
        assert write_chunk(
            connection, generation_id, ordinal, canonical,
            snapshot.metadata, chunk,
        )
    return key, generation_id


def _eof_receipt(database):
    _, canonical, metadata, _ = database
    return {
        'consumed_to_eof': True,
        'artifact_sha256': metadata['artifact']['content_sha256'].removeprefix('\\x'),
        'size_bytes': metadata['artifact']['size_bytes'],
        'systems': len(canonical['systems']),
        'bodies': len(canonical['bodies']),
    }


def _ready_ratings(database, generation_id):
    connection, _, _, _ = database
    seal_source(connection, generation_id, _eof_receipt(database))
    receipt = validate_generation(connection, generation_id)
    assert receipt['status'] == 'VERIFIED'
    return receipt


def _fixture_dsn(connection):
    from psycopg.conninfo import make_conninfo

    # Psycopg's public DSN omits the password; preserve the fixture connection's
    # credential without logging it or consulting another database authority.
    return make_conninfo(connection.info.dsn, password=connection.info.password)


def test_cli_build_then_validate(database, monkeypatch, capsys):
    connection, _, _, _ = database
    key, generation_id = _ratings_generation(database)
    _ready_ratings(database, generation_id)
    monkeypatch.setenv('V3_SYSTEM_ARCHETYPE_DATABASE_URL', _fixture_dsn(connection))

    assert builder.main(['--generation-key', key]) == 0
    built = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert built['status'] == 'BUILT'
    assert built['chunks_written'] == 3

    assert builder.main(['--generation-key', key, '--validate']) == 0
    receipt = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert receipt['status'] == 'VERIFIED'

    row = connection.execute(
        '''SELECT lifecycle_state FROM v3_meta.derived_product
            WHERE derived_generation_id=%s AND product_code=%s''',
        (generation_id, builder.PRODUCT_CODE),
    ).fetchone()
    assert row[0] == 'READY'

    # Idempotent: re-running --validate after promotion just re-prints the
    # stored receipt, no double-promotion / no error.
    assert builder.main(['--generation-key', key, '--validate']) == 0
    again = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert again == receipt


def test_cli_missing_database_authority_fails_closed(monkeypatch, capsys):
    monkeypatch.delenv('V3_SYSTEM_ARCHETYPE_DATABASE_URL', raising=False)
    assert builder.main(['--generation-key', 'whatever']) == 64
    error = json.loads(capsys.readouterr().err.strip())
    assert error == {'status': 'FAILED', 'error': 'database_authority_missing'}


def test_run_follow_stops_once_max_chunks_reached(database, monkeypatch):
    connection, _, _, _ = database
    key, generation_id = _ratings_generation(database)

    result = builder.run(connection, key, follow=True, max_chunks=1)
    assert result['status'] == 'INCOMPLETE'
    assert result['chunks_written'] == 1


def test_code_identity_lists_model_and_migration():
    ident = builder.code_identity()
    assert 'scripts/v3_system_archetype_model.py' in ident
    assert 'sql/v3/migrations/011_v3_system_archetype.sql' in ident
