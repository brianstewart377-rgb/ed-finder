from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ratings_v4.canonical_stream import (  # noqa: E402
    RetainedArtifactStream, _system_ids, adapt_retained_chunk, verify_recovered_source,
)
from domain.ratings_v4 import rate_system_facts  # noqa: E402
from domain.ratings_v4_canonical import adapt_canonical_export, load_source_fixture  # noqa: E402
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


def without_provenance(value):
    if isinstance(value, dict):
        return {key: without_provenance(item) for key, item in value.items()
                if key not in {'provenance', 'feature_provenance'}}
    if isinstance(value, (list, tuple)):
        return [without_provenance(item) for item in value]
    return value


def test_recovered_source_matches_the_published_canonical_run():
    manifest = verify_recovered_source()
    _, metadata, _ = load_source_fixture(ROOT / 'tests/fixtures/ratings_v4_sources')
    assert manifest['importer_package_sha256'] == metadata['run']['importer_code_sha256'].removeprefix('\\x')
    assert manifest['normalizer_sha256'] == metadata['run']['normalizer_sha256'].removeprefix('\\x')


def test_retained_source_adapter_preserves_all_84_frozen_ratings_and_unknowns():
    canonical, metadata, payloads = load_source_fixture(ROOT / 'tests/fixtures/ratings_v4_sources')
    expected = adapt_canonical_export(canonical, metadata, payloads)
    actual = adapt_retained_chunk(canonical, metadata, [payload['system'] for payload in payloads])
    assert len(actual) == 12
    for identifier, facts in actual.items():
        assert without_provenance(asdict(facts)) == without_provenance(asdict(expected[identifier]))
        for economy, rating in rate_system_facts(facts).items():
            assert without_provenance(asdict(rating)) == without_provenance(
                asdict(rate_system_facts(expected[identifier])[economy]))
        for body in facts.bodies:
            lineage = json.loads(body.feature_provenance['body_class'])
            assert lineage['source'] == 'Retained Spansh galaxy artifact'
            assert lineage['artifact_sha256'] == metadata['artifact']['content_sha256'].removeprefix('\\x')
            assert 'source_projection_sha256' in lineage
            assert body.reserve_scope == 'body'
            assert body.usable_ground_opportunity is None


@pytest.mark.parametrize('mutation', ['missing_system', 'missing_body', 'duplicate_body', 'wrong_frontier'])
def test_retained_source_requires_exact_canonical_inventory(mutation):
    canonical, metadata, payloads = deepcopy(load_source_fixture(ROOT / 'tests/fixtures/ratings_v4_sources'))
    records = [payload['system'] for payload in payloads]
    if mutation == 'missing_system':
        records.pop()
    elif mutation == 'missing_body':
        records[0]['bodies'].pop()
    elif mutation == 'duplicate_body':
        records[0]['bodies'].append(records[0]['bodies'][0])
    else:
        records[0]['bodies'][0]['bodyId'] += 1
    with pytest.raises(ValueError, match='inventory mismatch'):
        adapt_retained_chunk(canonical, metadata, records)


def artifact(tmp_path, records):
    data = gzip.compress(json.dumps(records).encode(), mtime=0)
    path = tmp_path / 'galaxy.json.gz'
    path.write_bytes(data)
    return RetainedArtifactStream(path, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))


def test_stream_seals_only_after_complete_consumption(tmp_path):
    stream = artifact(tmp_path, [{'id64': value, 'bodies': []} for value in range(7)])
    chunks = stream.chunks(3)
    assert len(next(chunks)) == 3
    assert stream.receipt is None
    assert [len(chunk) for chunk in chunks] == [3, 1]
    assert stream.receipt['systems'] == 7
    assert stream.receipt['consumed_to_eof'] is True
    with pytest.raises(ValueError, match='single use'):
        list(stream.chunks())


@pytest.mark.parametrize('fault', ['hash', 'size', 'truncated', 'empty', 'object'])
def test_bad_artifact_never_receives_a_completion_receipt(tmp_path, fault):
    records = [] if fault == 'empty' else {} if fault == 'object' else [{'id64': 1}]
    stream = artifact(tmp_path, records)
    if fault == 'hash':
        stream.expected_sha256 = '0' * 64
    elif fault == 'size':
        stream.expected_size += 1
    elif fault == 'truncated':
        stream.path.write_bytes(stream.path.read_bytes()[:-4])
    with pytest.raises((ValueError, EOFError)):
        list(stream.chunks())
    assert stream.receipt is None


@pytest.mark.parametrize('values', [[], [True], [-1], [2**63], [1, 1], list(range(1001))])
def test_reader_rejects_ambiguous_or_unbounded_identity_lists(values):
    with pytest.raises(ValueError):
        _system_ids(values)


def test_postgres_reader_replays_real_canonical_relations_and_stays_pinned():
    from scripts.ratings_v4.canonical_stream import CanonicalSnapshot

    with canonical_database() as (connection, canonical, metadata, payloads):
        snapshot = CanonicalSnapshot.pin(connection)
        assert snapshot.expected_systems == 12
        assert snapshot.expected_bodies == 389
        assert snapshot.metadata['artifact']['content_sha256'] == metadata['artifact']['content_sha256']
        identifiers = [row['id64'] for row in canonical['systems']]
        exported = snapshot.export_chunk(connection, identifiers)
        actual = adapt_retained_chunk(exported, snapshot.metadata, [payload['system'] for payload in payloads])
        expected = adapt_canonical_export(canonical, metadata, payloads)
        for identifier in identifiers:
            assert without_provenance(asdict(actual[identifier])) == without_provenance(asdict(expected[identifier]))
        # An absent current pointer cannot redirect this reader to some other
        # canonical generation. It is already pinned to immutable relations.
        connection.execute('DELETE FROM v3_meta.current_canonical_generation')
        assert snapshot.export_chunk(connection, identifiers)['canonical_schema'] == snapshot.schema
        with pytest.raises(ValueError, match='no valid published'):
            CanonicalSnapshot.pin(connection)
