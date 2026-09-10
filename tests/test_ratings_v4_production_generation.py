from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation, write_chunk, seal_source, validate_generation, explain_system,
)
from scripts.ratings_v4.run_generation import build_generation  # noqa: E402
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


@pytest.fixture(scope='module')
def database():
    with canonical_database() as (connection, canonical, metadata, payloads):
        connection.execute((ROOT / 'sql/v3/migrations/003_ratings_v4_derived.sql').read_text())
        snapshot = CanonicalSnapshot.pin(connection)
        exported = snapshot.export_chunk(connection, [row['id64'] for row in canonical['systems']])
        yield connection, exported, snapshot.metadata, [payload['system'] for payload in payloads], snapshot


def new_generation(database):
    connection, canonical, metadata, records, snapshot = database
    generation = create_generation(connection, snapshot, 'test_' + uuid4().hex)
    return generation


def eof_receipt(database):
    _, canonical, metadata, _, _ = database
    # Simulated receipt for the retained fixture in a disposable database.
    # This is not evidence of a production full-artifact scan.
    return {'consumed_to_eof': True,
            'artifact_sha256': metadata['artifact']['content_sha256'].removeprefix('\\x'),
            'size_bytes': metadata['artifact']['size_bytes'],
            'systems': len(canonical['systems']), 'bodies': len(canonical['bodies'])}


def build_ready(database):
    connection, canonical, metadata, records, _ = database
    generation = new_generation(database)
    assert write_chunk(connection, generation, 0, canonical, metadata, records)
    seal_source(connection, generation, eof_receipt(database))
    return generation, validate_generation(connection, generation)


def test_complete_generation_replays_scores_coverage_opportunities_and_explanations(database):
    connection, canonical, _, _, _ = database
    generation, receipt = build_ready(database)
    assert receipt['status'] == 'VERIFIED'
    assert receipt['systems'] == 12
    assert receipt['ratings'] == 84
    assert receipt['physical_bodies'] == 360
    assert receipt['every_system_replayed']
    assert receipt['unknown_quality']['Refinery'] == 10
    explanation = explain_system(connection, generation, canonical['systems'][0]['id64'])
    assert len(explanation['ratings']) == 7
    assert 'overall_score' not in explanation
    assert explanation['scorer_version'] == '4.0.0'
    assert explain_system(connection, generation, 0) is None


def test_checkpoint_resume_is_idempotent_but_detects_input_changes(database):
    connection, canonical, metadata, records, _ = database
    generation = new_generation(database)
    assert write_chunk(connection, generation, 0, canonical, metadata, records)
    assert write_chunk(connection, generation, 0, canonical, metadata, records) is False
    changed = deepcopy(canonical)
    changed['systems'][0]['name'] += ' changed'
    with pytest.raises(ValueError, match='resumed chunk source/content changed'):
        write_chunk(connection, generation, 0, changed, metadata, records)
    assert connection.execute('SELECT count(*) FROM v3_derived.build_chunk WHERE derived_generation_id=%s',
                              (generation,)).fetchone()[0] == 1


def test_duplicate_systems_across_chunks_roll_back_every_write(database):
    import psycopg
    connection, canonical, metadata, records, _ = database
    generation = new_generation(database)
    write_chunk(connection, generation, 0, canonical, metadata, records)
    with pytest.raises(psycopg.errors.UniqueViolation):
        write_chunk(connection, generation, 1, canonical, metadata, records)
    assert connection.execute('SELECT count(*) FROM v3_derived.build_chunk WHERE derived_generation_id=%s',
                              (generation,)).fetchone()[0] == 1


@pytest.mark.parametrize('fault', ['no_eof', 'bad_hash', 'wrong_size', 'missing_chunks', 'gap'])
def test_incomplete_source_or_chunks_cannot_leave_building(database, fault):
    connection, canonical, metadata, records, _ = database
    generation = new_generation(database)
    receipt = eof_receipt(database)
    if fault != 'missing_chunks':
        write_chunk(connection, generation, 1 if fault == 'gap' else 0, canonical, metadata, records)
    if fault == 'no_eof':
        receipt = None
    elif fault == 'bad_hash':
        receipt['artifact_sha256'] = '0' * 64
    elif fault == 'wrong_size':
        receipt['size_bytes'] += 1
    with pytest.raises(ValueError):
        seal_source(connection, generation, receipt)
    assert connection.execute('SELECT lifecycle_state FROM v3_meta.derived_generation WHERE derived_generation_id=%s',
                              (generation,)).fetchone()[0] == 'BUILDING'


def test_stored_corruption_is_detected_before_ready(database):
    connection, canonical, metadata, records, _ = database
    generation = new_generation(database)
    write_chunk(connection, generation, 0, canonical, metadata, records)
    connection.execute("UPDATE v3_derived.body_mechanics SET body_class='Rocky body' WHERE derived_generation_id=%s", (generation,))
    seal_source(connection, generation, eof_receipt(database))
    with pytest.raises(ValueError, match='content checksum mismatch'):
        validate_generation(connection, generation)


def test_ready_inputs_and_source_manifest_are_immutable(database):
    import psycopg
    connection, _, _, _, _ = database
    generation, _ = build_ready(database)
    for statement in (
        "UPDATE v3_derived.body_mechanics SET rings=false WHERE derived_generation_id=%s",
        'DELETE FROM v3_derived.economy_opportunity WHERE derived_generation_id=%s',
        "UPDATE v3_meta.derived_generation SET lifecycle_state='BUILDING' WHERE derived_generation_id=%s",
        "UPDATE v3_meta.derived_generation SET scorer_version='changed' WHERE derived_generation_id=%s",
    ):
        with pytest.raises(psycopg.errors.RaiseException):
            connection.execute(statement, (generation,))
    with pytest.raises(psycopg.errors.RaiseException):
        connection.execute('TRUNCATE v3_derived.economy_opportunity')


def test_publish_compare_and_swap_and_rollback(database):
    import psycopg
    connection, _, _, _, snapshot = database
    first, _ = build_ready(database)
    second, _ = build_ready(database)

    def publish(target, previous, sequence, canonical=snapshot.generation_id):
        return connection.execute('SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s)',
            (target, previous, sequence, canonical, snapshot.publication_sequence, 'test', 'verified fixture')).fetchone()[0]

    assert publish(first, None, 0) == 1
    with pytest.raises(psycopg.errors.RaiseException, match='derived publication changed'):
        publish(second, None, 0)
    with pytest.raises(psycopg.errors.RaiseException, match='canonical publication changed'):
        publish(second, first, 1, str(uuid4()))
    assert publish(second, first, 1) == 2
    assert publish(first, second, 2) == 3
    assert connection.execute('SELECT count(*) FROM v3_app.system_economy_rating').fetchone()[0] == 84
    assert connection.execute('SELECT count(*) FROM v3_meta.derived_publication_audit').fetchone()[0] == 3


def test_invalid_quality_and_ratio_vectors_are_rejected(database):
    import psycopg
    connection, canonical, metadata, records, _ = database
    generation = new_generation(database)
    write_chunk(connection, generation, 0, canonical, metadata, records)
    for field, value in [('confidence', [10001] * 7), ('potential', [1] * 6), ('quality', [None] * 7)]:
        with pytest.raises(psycopg.errors.CheckViolation):
            from psycopg import sql
            connection.execute(sql.SQL('UPDATE v3_derived.system_rating_vector SET {}=%s WHERE derived_generation_id=%s').format(
                sql.Identifier(field)), (value, generation))


def test_generation_cannot_accept_another_canonical_source(database):
    connection, canonical, metadata, records, snapshot = database
    changed_snapshot = replace(snapshot, metadata={**metadata, 'unregistered': 'different source'})
    generation = create_generation(connection, changed_snapshot, 'test_' + uuid4().hex)
    with pytest.raises(ValueError, match='source differs'):
        write_chunk(connection, generation, 0, canonical, metadata, records)


def test_full_artifact_runner_builds_then_idempotently_resumes(tmp_path):
    import gzip
    import hashlib
    import json
    from domain.ratings_v4_canonical import load_source_fixture

    _, _, payloads = load_source_fixture(ROOT / 'tests/fixtures/ratings_v4_sources')
    records = [payload['system'] for payload in payloads]
    compressed = gzip.compress(json.dumps(records).encode(), mtime=0)
    source = tmp_path / 'galaxy.json.gz'
    source.write_bytes(compressed)

    def retained_fixture(_canonical, metadata):
        metadata['artifact']['content_sha256'] = '\\x' + hashlib.sha256(compressed).hexdigest()
        metadata['artifact']['size_bytes'] = len(compressed)
        return ()

    with canonical_database(prepare=retained_fixture) as (read_connection, _, _, _):
        read_connection.execute((ROOT / 'sql/v3/migrations/003_ratings_v4_derived.sql').read_text())
        # Psycopg intentionally redacts passwords from ``connection.info.dsn``.
        # Reusing the autocommit fixture connection keeps this integration test
        # faithful without manufacturing a credential-less second DSN.
        first = build_generation(
            read_connection, read_connection, source, 'full_runner_fixture'
        )
        second = build_generation(
            read_connection, read_connection, source, 'full_runner_fixture'
        )
        assert first['status'] == 'VERIFIED'
        assert first['lifecycle_state'] == 'READY'
        assert first['publication_performed'] is False
        assert first['chunks_written'] == 1
        assert second['status'] == 'VERIFIED'
        assert second['resumed'] is True
        assert second['chunks_seen'] == 0
        assert second['derived_generation_id'] == first['derived_generation_id']
