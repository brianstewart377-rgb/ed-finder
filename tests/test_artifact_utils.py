import hashlib
import inspect
import json
import math
import os
import re
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import artifact_utils  # noqa: E402


def test_canonical_json_is_stable_independent_of_key_order():
    left = {
        'station': {'name': 'Galileo', 'distanceToArrival': 503.2},
        'services': ['Shipyard', 'Market'],
        'none': None,
    }
    right = {
        'none': None,
        'services': ['Shipyard', 'Market'],
        'station': {'distanceToArrival': 503.2, 'name': 'Galileo'},
    }

    assert artifact_utils.canonical_json(left) == artifact_utils.canonical_json(right)
    assert artifact_utils.canonical_json(left) == (
        '{"none":null,"services":["Shipyard","Market"],'
        '"station":{"distanceToArrival":503.2,"name":"Galileo"}}'
    )


@pytest.mark.parametrize('value', [math.nan, math.inf, -math.inf])
def test_canonical_json_rejects_nan_and_infinity(value):
    with pytest.raises(ValueError):
        artifact_utils.canonical_json({'value': value})


def test_sha256_helpers_match_hashlib(tmp_path):
    data = b'artifact bytes\n'
    text = data.decode('utf-8')
    path = tmp_path / 'artifact.bin'
    path.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()

    assert artifact_utils.sha256_bytes(data) == expected
    assert artifact_utils.sha256_bytes(memoryview(data)) == expected
    assert artifact_utils.sha256_text(text) == expected
    assert artifact_utils.sha256_file(path) == expected


def test_artifact_integrity_excludes_integrity_block():
    payload = {
        'schema_version': 'example/v1',
        'rows': [{'b': 2, 'a': 1}],
    }
    with_integrity = {
        **payload,
        'artifact_integrity': {
            'hash_algorithm': 'sha256',
            'canonical_json_sha256': 'not-the-real-hash',
        },
    }

    assert artifact_utils.artifact_integrity_sha256(payload) == artifact_utils.artifact_integrity_sha256(with_integrity)


def test_attach_artifact_integrity_is_deterministic_and_does_not_mutate_original():
    payload = {
        'schema_version': 'example/v1',
        'nested': {'values': [3, 2, 1]},
        'artifact_integrity': {'canonical_json_sha256': 'stale'},
    }
    original = deepcopy(payload)

    first = artifact_utils.attach_artifact_integrity(payload)
    second = artifact_utils.attach_artifact_integrity(payload)

    assert payload == original
    assert first == second
    assert first['artifact_integrity'] == {
        'hash_algorithm': 'sha256',
        'canonical_json_sha256': artifact_utils.artifact_integrity_sha256(first),
        'canonicalization': artifact_utils.CANONICALIZATION,
    }

    first['nested']['values'].append(4)
    assert payload == original


def test_write_json_artifact_writes_newline_parents_hashes_and_private_mode(tmp_path):
    path = tmp_path / 'nested' / 'artifact.json'
    payload = {
        'schema_version': 'example/v1',
        'station': {'name': 'Galileo', 'distanceToArrival': 503.2},
    }

    record = artifact_utils.write_json_artifact(path, payload)
    raw = path.read_bytes()
    loaded = json.loads(raw.decode('utf-8'))

    assert path.exists()
    assert raw.endswith(b'\n')
    assert raw.decode('utf-8') == artifact_utils.canonical_json(loaded) + '\n'
    assert loaded['artifact_integrity']['hash_algorithm'] == 'sha256'
    assert loaded['artifact_integrity']['canonical_json_sha256'] == artifact_utils.artifact_integrity_sha256(loaded)
    assert payload == {
        'schema_version': 'example/v1',
        'station': {'name': 'Galileo', 'distanceToArrival': 503.2},
    }
    assert record == {
        'path': str(path),
        'file_sha256': artifact_utils.sha256_bytes(raw),
        'artifact_integrity_sha256': loaded['artifact_integrity']['canonical_json_sha256'],
        'hash_algorithm': 'sha256',
        'integrity_key': 'artifact_integrity',
        'bytes_written': len(raw),
    }
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600


def test_artifact_utils_has_no_prod_db_or_side_effect_fragments():
    source = inspect.getsource(artifact_utils)
    forbidden_fragments = [
        'DATABASE_URL',
        'postgresql://',
        'postgres://',
        'PASSWORD=',
        'SECRET=',
        'TOKEN=',
        'systemctl',
        '.timer',
        '.service',
        'scheduler',
        'canonical apply',
    ]

    for fragment in forbidden_fragments:
        assert fragment not in source

    canonical_write_patterns = [
        r'\binsert\s+into\s+(systems|stations|colonies|station_external_identity)\b',
        r'\bupdate\s+(systems|stations|colonies|station_external_identity)\b',
        r'\bdelete\s+from\s+(systems|stations|colonies|station_external_identity)\b',
    ]
    for pattern in canonical_write_patterns:
        assert re.search(pattern, source, flags=re.IGNORECASE) is None
