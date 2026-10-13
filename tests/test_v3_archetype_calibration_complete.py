'''Tests for the complete, resumable V3 archetype calibration read.'''
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import v3_archetype_calibration_complete as complete  # noqa: E402
from scripts import v3_system_archetype as builder  # noqa: E402
from scripts.operator.lib.f2d_operator_identity import (  # noqa: E402
    compute_operator_code_sha256,
)
from shared_contracts import v3_system_archetype_model as model  # noqa: E402
from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation,
    write_chunk,
)
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


class _Cursor:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self):
        self.read_only = False
        self.commits = 0
        self.statements: list[str] = []

    def execute(self, statement, parameters=None):
        self.statements.append(str(statement))
        return _Cursor()

    def commit(self):
        self.commits += 1


def _vector(system_id64: int, potential: int) -> model.SystemVectorRow:
    return model.SystemVectorRow(
        system_id64=system_id64,
        potential=(potential,) * 7,
        quality=(90,) * 7,
        quality_min=(90,) * 7,
        quality_max=(90,) * 7,
        completeness=(10_000,) * 7,
        confidence=(10_000,) * 7,
    )


def _args(state_dir: Path, *, stop_after_chunks: int | None = None):
    return argparse.Namespace(
        generation_key='fixture_generation',
        generation_id='11111111-1111-1111-1111-111111111111',
        publication_sequence=1,
        state_dir=state_dir,
        database_url_env=complete.DEFAULT_DATABASE_URL_ENV,
        statement_timeout_ms=60_000,
        stop_after_chunks=stop_after_chunks,
    )


def _generation_row():
    return (
        '11111111-1111-1111-1111-111111111111',
        'fixture_generation',
        'PUBLISHED',
        3,
        '22222222-2222-2222-2222-222222222222',
        4,
        {'canonical_schema': 'v3_gen_fixture'},
        1,
    )


def _fake_probe(read_ordinals: list[int]) -> SimpleNamespace:
    rows = {
        0: {
            10: (_vector(10, 100), ((1, 8, 800),)),
            11: (_vector(11, 70), ((2, 4, 300),)),
        },
        1: {12: (_vector(12, 20), ())},
    }

    def read_chunk(_connection, _generation_id, ordinal):
        read_ordinals.append(ordinal)
        return rows[ordinal]

    return SimpleNamespace(
        _chunk_rows=lambda _connection, _generation_id: [(0, 2), (1, 1)],
        _read_chunk_rows=read_chunk,
    )


def test_complete_restart_resumes_and_equals_fresh_run(tmp_path, monkeypatch):
    identity = compute_operator_code_sha256(ROOT)
    monkeypatch.setattr(complete, '_generation', lambda *_args: _generation_row())
    monkeypatch.setattr(complete, 'refuse_unlisted_checkout_modules', lambda: None)
    reads: list[int] = []
    probe = _fake_probe(reads)
    monkeypatch.setattr(
        complete,
        '_load_scoring_modules',
        lambda: (probe, builder, model),
    )

    resumed_state = tmp_path / 'resumed'
    exit_code, receipt = complete.run_complete(
        _Connection(), _args(resumed_state, stop_after_chunks=1),
        f2d_identity=identity,
    )
    assert exit_code == 75
    assert receipt is None
    assert reads == [0]

    exit_code, resumed = complete.run_complete(
        _Connection(), _args(resumed_state), f2d_identity=identity,
    )
    assert exit_code == 0
    assert reads == [0, 1]
    assert complete.validate_complete_receipt(resumed) is resumed

    reads.clear()
    exit_code, fresh = complete.run_complete(
        _Connection(), _args(tmp_path / 'fresh'), f2d_identity=identity,
    )
    assert exit_code == 0
    assert reads == [0, 1]
    assert resumed == fresh


def test_complete_receipt_totals_chunks_sigma_and_expected_manifest(
    tmp_path, monkeypatch,
):
    identity = compute_operator_code_sha256(ROOT)
    monkeypatch.setattr(complete, '_generation', lambda *_args: _generation_row())
    monkeypatch.setattr(complete, 'refuse_unlisted_checkout_modules', lambda: None)
    monkeypatch.setattr(
        complete,
        '_load_scoring_modules',
        lambda: (_fake_probe([]), builder, model),
    )
    connection = _Connection()
    exit_code, receipt = complete.run_complete(
        connection, _args(tmp_path), f2d_identity=identity,
    )
    assert exit_code == 0
    assert receipt['system_count'] == 3
    sigma = 0.0
    for key in model.ARCHETYPE_KEYS:
        entry = receipt['per_archetype'][key]
        histogram = entry['tier_histogram']
        assert sum(histogram.values()) == receipt['system_count']
        assert sum(chunk['row_count'] for chunk in entry['per_chunk']) == 3
        combined = {tier: 0 for tier in complete.TIERS}
        for chunk in entry['per_chunk']:
            for tier, count in chunk['tier_histogram'].items():
                combined[tier] += count
        assert combined == histogram
        total = sum(histogram.values())
        sigma += (histogram['S'] + histogram['A'] + histogram['B']) / total
        sigma += (histogram['S'] + histogram['A']) / total
        sigma += histogram['S'] / total
    assert receipt['sigma_all'] == pytest.approx(sigma)

    generation = builder.Generation(
        identifier=_generation_row()[0],
        key=_generation_row()[1],
        state='PUBLISHED',
        canonical_generation_id=_generation_row()[4],
        canonical_publication_sequence=4,
        canonical_schema='v3_gen_fixture',
        expected_systems=3,
    )
    assert receipt['expected_product_manifest'] == builder.product_manifest(generation)
    assert receipt['expected_product_manifest_sha256'] == complete.canonical_sha256(
        receipt['expected_product_manifest']
    )
    assert connection.read_only is True
    assert all(statement.lstrip().startswith('SELECT') for statement in connection.statements)


def test_sampled_receipt_is_distinguishable_from_complete_receipt():
    sampled = complete.seal_receipt({'mode': 'sampled'})
    with pytest.raises(ValueError, match='mode is not complete'):
        complete.validate_complete_receipt(sampled)


def test_checkpoint_for_another_generation_or_identity_is_refused():
    checkpoint = complete._new_checkpoint(
        generation_key='fixture_generation',
        generation_id='11111111-1111-1111-1111-111111111111',
        publication_sequence=1,
        f2d_identity='a' * 64,
        chunk_plan_sha256='b' * 64,
        keys=tuple(model.ARCHETYPE_KEYS),
    )
    with pytest.raises(ValueError, match='derived_generation_id mismatch'):
        complete._require_checkpoint_identity(
            checkpoint,
            generation_key='fixture_generation',
            generation_id='33333333-3333-3333-3333-333333333333',
            publication_sequence=1,
            f2d_identity='a' * 64,
            chunk_plan_sha256='b' * 64,
        )
    with pytest.raises(ValueError, match='f2d_operator_code_sha256 mismatch'):
        complete._require_checkpoint_identity(
            checkpoint,
            generation_key='fixture_generation',
            generation_id='11111111-1111-1111-1111-111111111111',
            publication_sequence=1,
            f2d_identity='c' * 64,
            chunk_plan_sha256='b' * 64,
        )


def test_loaded_checkout_module_outside_manifest_is_refused(monkeypatch):
    rogue = ModuleType('f2d_test_rogue')
    rogue.__file__ = str(ROOT / 'scripts/unlisted_f2d_module.py')
    monkeypatch.setitem(sys.modules, rogue.__name__, rogue)
    with pytest.raises(ValueError, match='scripts/unlisted_f2d_module.py'):
        complete.refuse_unlisted_checkout_modules()


def test_complete_program_and_status_are_read_only_and_start_is_identity_first():
    program = (ROOT / 'scripts/v3_archetype_calibration_complete.py').read_text()
    action = (
        ROOT / 'scripts/operator/actions/v3-archetype-calibration-complete.sh'
    ).read_text()
    for statement in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE'):
        assert statement not in program
    assert "connection.read_only = True" in program
    assert "default_transaction_read_only" in program
    assert '--image-model-file /app/shared_contracts/v3_system_archetype_model.py' in action
    assert action.index('require_f2d_operator_code_identity') < action.index('require_target()')
    status = action[action.index('status_operation()'):]
    assert 'docker rm' not in status
    assert 'docker run' not in status
    assert 'install -d' not in status
    assert "read('checkpoint.json')" in action
    assert "read('receipt.json')" in action


def test_action_pins_target_and_runs_a_bounded_read_only_detached_worker():
    action = (
        ROOT / 'scripts/operator/actions/v3-archetype-calibration-complete.sh'
    ).read_text()
    for declaration in (
        'TARGET_HOSTNAME="ed-finder-prod"',
        'TARGET_FQDN="nb79a3d.mevnode.com"',
        'POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"',
        'DATABASE_USER="edfinder_v3"',
        'DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"',
        'WORKER_NETWORK="edfinder-v3-phase4c-full-20260827_r5-network"',
        'TARGET_GENERATION_KEY="ratings_v4_prod_p4_parallel_v1"',
        'TARGET_GENERATION_ID="cfc25d36-3bc7-4011-a465-d6460eaaf826"',
        'TARGET_PUBLICATION_SEQUENCE="1"',
    ):
        assert declaration in action
    assert 'docker run -d' in action
    assert '--cpus "$TARGET_CPUS"' in action
    assert '--memory "$TARGET_MEMORY"' in action
    assert '--memory-swap "$TARGET_MEMORY"' in action
    assert '--pids-limit 256' in action
    assert '--restart no' in action
    assert '--read-only' in action
    assert '--tmpfs /tmp:rw,nosuid,size=2g' in action
    assert 'dst=/work,readonly' in action
    assert 'dst=/state' in action
    assert '--env-file "$env_file"' in action
    assert 'V3_ARCHETYPE_COMPLETE_DATABASE_URL=%s' in action
    assert 'psycopg[binary]==3.3.4' in action
    assert '--no-index' in action
    assert '--find-links /work/.v3-probe-wheelhouse' in action
    assert "sealed_read('receipt.json')" in action


def test_action_refuses_missing_attested_identity_before_target_checks():
    import os
    import subprocess

    environment = os.environ.copy()
    environment.pop('F2D_OPERATOR_CODE_SHA256_ATTESTED', None)
    result = subprocess.run(
        [
            'bash',
            str(ROOT / 'scripts/operator/actions/v3-archetype-calibration-complete.sh'),
            'start',
            str(ROOT),
            '0' * 40,
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 64
    assert 'attested_identity_missing' in result.stderr
    assert 'unexpected hostname' not in result.stderr


def test_failure_receipt_is_sealed(tmp_path):
    complete._failure_receipt(tmp_path, 'tier total mismatch', 'd' * 64)
    receipt = json.loads((tmp_path / 'failure-receipt.json').read_text())
    assert complete.validate_complete_receipt(receipt) is receipt
    assert receipt['status'] == 'failed'


def test_image_model_must_match_checkout(tmp_path):
    matching = tmp_path / 'model.py'
    matching.write_bytes(
        (ROOT / 'shared_contracts/v3_system_archetype_model.py').read_bytes()
    )
    expected = complete.require_image_model_match(matching)
    assert expected == hashlib.sha256(matching.read_bytes()).hexdigest()
    matching.write_bytes(matching.read_bytes() + b'\n# changed\n')
    with pytest.raises(ValueError, match='files differ'):
        complete.require_image_model_match(matching)


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


def test_complete_read_scores_every_fixture_chunk_without_product_rows(
    database, tmp_path, monkeypatch,
):
    connection, _, _, payloads = database
    snapshot = CanonicalSnapshot.pin(connection)
    generation_key = 'archetype_complete_fixture'
    generation_id = create_generation(connection, snapshot, generation_key)
    records = [payload['system'] for payload in payloads]
    for ordinal, start in enumerate(range(0, len(records), 4)):
        chunk = records[start:start + 4]
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

    stored = connection.execute(
        '''SELECT g.derived_generation_id::text,g.generation_key,
                  g.expected_systems,g.canonical_generation_id::text,
                  g.canonical_publication_sequence,g.manifest
             FROM v3_meta.derived_generation g
            WHERE g.derived_generation_id=%s''',
        (generation_id,),
    ).fetchone()
    monkeypatch.setattr(
        complete,
        '_generation',
        lambda *_args: (
            stored[0], stored[1], 'PUBLISHED', int(stored[2]), stored[3],
            int(stored[4]), stored[5], 1,
        ),
    )
    monkeypatch.setattr(complete, 'refuse_unlisted_checkout_modules', lambda: None)
    identity = compute_operator_code_sha256(ROOT)
    before = connection.execute(
        'SELECT count(*) FROM v3_derived.system_archetype WHERE derived_generation_id=%s',
        (generation_id,),
    ).fetchone()[0]

    exit_code, receipt = complete.run_complete(
        connection,
        argparse.Namespace(
            generation_key=generation_key,
            generation_id=str(generation_id),
            publication_sequence=1,
            state_dir=tmp_path,
            database_url_env=complete.DEFAULT_DATABASE_URL_ENV,
            statement_timeout_ms=60_000,
            stop_after_chunks=None,
        ),
        f2d_identity=identity,
    )
    after = connection.execute(
        'SELECT count(*) FROM v3_derived.system_archetype WHERE derived_generation_id=%s',
        (generation_id,),
    ).fetchone()[0]
    assert exit_code == 0
    assert receipt['system_count'] == len(records)
    assert before == after == 0
