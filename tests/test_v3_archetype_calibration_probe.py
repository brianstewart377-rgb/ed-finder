'''Tests for the read-only V3 archetype coefficient-calibration probe.'''
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation,
    write_chunk,
)
from scripts import v3_archetype_calibration_probe as probe  # noqa: E402
from shared_contracts.v3_system_archetype_model import (  # noqa: E402
    ARCHETYPE_KEYS,
    SystemVectorRow,
    archetype_model_sha256,
    score_raw_system,
)
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
    key = 'archetype_probe_test_' + uuid4().hex
    generation_id = create_generation(connection, snapshot, key)
    records = [payload['system'] for payload in payloads]
    for ordinal, start in enumerate(range(0, len(records), chunk_size)):
        chunk = records[start:start + chunk_size]
        canonical = snapshot.export_chunk(
            connection, [record['id64'] for record in chunk],
        )
        assert write_chunk(
            connection,
            generation_id,
            ordinal,
            canonical,
            snapshot.metadata,
            chunk,
        )
    return key, generation_id, snapshot, records


def _raw_row(**overrides) -> SystemVectorRow:
    values = {
        'system_id64': 1,
        'potential': (0,) * 7,
        'quality': (None,) * 7,
        'quality_min': (0,) * 7,
        'quality_max': (0,) * 7,
        'completeness': (10_000,) * 7,
        'confidence': (10_000,) * 7,
    }
    values.update(overrides)
    return SystemVectorRow(**values)


@pytest.mark.parametrize(
    ('values', 'percentile', 'expected'),
    [
        ([4, 1, 3, 2], 0, 1),
        ([4, 1, 3, 2], 10, 1),
        ([4, 1, 3, 2], 50, 2),
        ([4, 1, 3, 2], 90, 4),
        ([4, 1, 3, 2], 100, 4),
        ([], 50, None),
    ],
)
def test_nearest_rank(values, percentile, expected):
    assert probe.nearest_rank(values, percentile) == expected


def test_nearest_rank_rejects_invalid_percentile():
    with pytest.raises(ValueError, match='percentile'):
        probe.nearest_rank([1], 101)


def test_chunk_selection_is_strided_bounded_and_starts_at_first_chunk():
    rows = [(0, 4), (1, 4), (2, 4), (3, 4), (4, 4)]
    assert probe.select_chunk_ordinals(rows, max_systems=12, stride=2) == [0, 2, 4]
    assert probe.select_chunk_ordinals(rows, max_systems=9, stride=1) == [0, 1]


def test_chunk_selection_is_empty_when_bound_is_smaller_than_smallest_chunk():
    rows = [(0, 4), (1, 6), (2, 5)]
    assert probe.select_chunk_ordinals(rows, max_systems=3, stride=1) == []


def test_chunk_selection_uses_ordinals_when_completed_chunks_have_gaps():
    rows = [(4, 3), (0, 3), (3, 3), (1, 3)]
    assert probe.select_chunk_ordinals(rows, max_systems=6, stride=2) == [0, 4]


def test_default_stride_targets_one_thousand_system_chunks():
    assert probe.default_stride(500, 200_000) == 3
    assert probe.default_stride(3, 200_000) == 1


def test_raw_score_aggregation_matches_shared_score_raw_system():
    rows = [
        (
            _raw_row(
                potential=(90, 20, 15, 75, 30, 90, 10),
                quality=(80, 40, 40, 70, 50, 85, 30),
            ),
            ((1, 9, 720), (6, 10, 850)),
        ),
        (
            _raw_row(
                system_id64=2,
                potential=(20, 90, 85, 30, 20, 10, 92),
                quality=(30, 80, 85, 40, 30, 20, 90),
            ),
            ((2, 10, 800), (3, 10, 850), (7, 9, 792)),
        ),
        (
            _raw_row(
                system_id64=3,
                potential=(70,) * 7,
                quality=(60,) * 7,
                confidence=(9_000,) * 7,
                completeness=(8_000,) * 7,
            ),
            (),
        ),
    ]
    result = probe.aggregate_vectors(rows)

    for key in ARCHETYPE_KEYS:
        expected = [score_raw_system(*row) for row in rows]
        expected_scores = [scored[f'{key}_score'] for scored in expected]
        expected_tiers = {
            tier: sum(scored[f'{key}_tier'] == tier for scored in expected)
            for tier in probe.TIERS
        }
        observed = result['per_archetype'][key]
        assert observed['count'] == len(rows)
        assert observed['score_min'] == min(expected_scores)
        assert observed['score_max'] == max(expected_scores)
        assert observed['tier_histogram'] == expected_tiers
    assert sum(result['primary_counts'].values()) == len(rows)
    assert sum(result['secondary_counts'].values()) == len(rows)
    assert sum(result['best_tier_histogram'].values()) == len(rows)


def test_probe_source_has_no_private_scaling_or_model_fit_or_sql_average():
    source = (ROOT / 'scripts/v3_archetype_calibration_probe.py').read_text()

    assert '/ 10_000' not in source
    assert 'fit_all(' not in source
    assert 'avg(' not in source.lower()
    assert 'model.VECTOR_READ_SQL' in source
    assert 'model.OPPORTUNITY_READ_SQL' in source
    assert 'model.score_raw_system' in source


def _run_probe_subprocess(*arguments: str) -> subprocess.CompletedProcess[str]:
    clean_env = os.environ.copy()
    clean_env.pop('V3_ARCHETYPE_PROBE_DATABASE_URL', None)
    return subprocess.run(
        [sys.executable, str(ROOT / 'scripts/v3_archetype_calibration_probe.py'), *arguments],
        cwd=ROOT,
        env=clean_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_rejects_max_systems_above_hard_cap_without_database():
    result = _run_probe_subprocess(
        '--generation-key', 'test_generation',
        '--max-systems', '1000001',
    )
    assert result.returncode == 2
    assert result.stdout == ''


def test_cli_reports_missing_database_environment_without_printing_dsn():
    result = _run_probe_subprocess('--generation-key', 'test_generation')
    assert result.returncode == 2
    assert result.stdout == ''
    assert 'V3_ARCHETYPE_PROBE_DATABASE_URL' in result.stderr


def test_probe_reads_all_fixture_chunks_without_writing(
    database, monkeypatch, capsys,
):
    connection, _, _, _ = database
    key, generation_id, _, records = _ratings_generation(database)
    assert len(records) == 12

    archetype_count_before = connection.execute(
        '''SELECT count(*) FROM v3_derived.system_archetype
            WHERE derived_generation_id=%s''',
        (generation_id,),
    ).fetchone()[0]
    lifecycle_before = connection.execute(
        '''SELECT lifecycle_state FROM v3_meta.derived_generation
            WHERE derived_generation_id=%s''',
        (generation_id,),
    ).fetchone()[0]
    assert archetype_count_before == 0
    assert lifecycle_before == 'BUILDING'

    monkeypatch.setenv('V3_ARCHETYPE_PROBE_DATABASE_URL', connection.info.dsn)
    assert probe.main(['--generation-key', key]) == 3
    rejected = capsys.readouterr()
    assert rejected.out == ''

    assert probe.main([
        '--generation-key', key,
        '--allow-unpublished',
        '--max-systems', '1000000',
    ]) == 0
    output = capsys.readouterr()
    receipt = json.loads(output.out)

    assert receipt['mode'] == 'sampled'
    assert receipt['row_count'] == 12
    assert receipt['sample']['systems_sampled'] == 12
    assert receipt['sample']['chunks_sampled'] == 3
    assert receipt['sample']['ordinals_first_last'] == [0, 2]
    for key_name in ARCHETYPE_KEYS:
        assert receipt['per_archetype'][key_name]['count'] == 12
        assert sum(
            receipt['per_archetype'][key_name]['tier_histogram'].values()
        ) == receipt['row_count']
    assert sum(receipt['primary_counts'].values()) == 12
    canonical_model = ROOT / 'shared_contracts/v3_system_archetype_model.py'
    assert receipt['archetype_model_sha256'] == archetype_model_sha256()
    assert receipt['model_file_sha256'] == hashlib.sha256(
        canonical_model.read_bytes()
    ).hexdigest()
    assert (
        receipt['expected_product_manifest']['archetype_model_sha256']
        == receipt['archetype_model_sha256']
    )
    assert (
        receipt['expected_product_manifest']['model_file_sha256']
        == receipt['model_file_sha256']
    )
    assert (
        receipt['expected_product_manifest']['code_sha256']
        == receipt['code_identity']
    )
    assert (
        receipt['expected_product_manifest']['coefficients']
        == receipt['coefficients']
    )
    assert receipt['read_only'] is True
    assert receipt['writes_performed'] is False

    archetype_count_after = connection.execute(
        '''SELECT count(*) FROM v3_derived.system_archetype
            WHERE derived_generation_id=%s''',
        (generation_id,),
    ).fetchone()[0]
    lifecycle_after = connection.execute(
        '''SELECT lifecycle_state FROM v3_meta.derived_generation
            WHERE derived_generation_id=%s''',
        (generation_id,),
    ).fetchone()[0]
    assert archetype_count_after == archetype_count_before == 0
    assert lifecycle_after == lifecycle_before == 'BUILDING'


def test_probe_rejects_bound_smaller_than_a_fixture_chunk(
    database, monkeypatch, capsys,
):
    connection, _, _, _ = database
    key, _, _, _ = _ratings_generation(database)
    monkeypatch.setenv('V3_ARCHETYPE_PROBE_DATABASE_URL', connection.info.dsn)

    assert probe.main([
        '--generation-key', key,
        '--allow-unpublished',
        '--max-systems', '1',
    ]) == 5

    output = capsys.readouterr()
    assert output.out == ''
    assert output.err == (
        'calibration sample is empty: raise --max-systems '
        '(at least one full chunk must fit)\n'
    )
