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
        # Statement index at which each commit happened, for ordering checks.
        self.commit_marks: list[int] = []

    def execute(self, statement, parameters=None):
        self.statements.append(str(statement))
        return _Cursor()

    def commit(self):
        self.commits += 1
        self.commit_marks.append(len(self.statements))


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

    # A torn append past the checkpointed length is truncated, then the run
    # resumes from the checkpoint and seals the same receipt.
    torn_state = tmp_path / 'torn'
    exit_code, _ = complete.run_complete(
        _Connection(), _args(torn_state, stop_after_chunks=1), f2d_identity=identity,
    )
    assert exit_code == 75
    torn_log = torn_state / complete.PER_CHUNK_FILE
    pinned = json.loads((torn_state / 'checkpoint.json').read_text())['per_chunk_bytes']
    assert torn_log.stat().st_size == pinned
    with torn_log.open('ab') as handle:
        handle.write(b'{"chunk_ordinal":1,"row_count":1,"per_arch')
    reads.clear()
    exit_code, after_torn = complete.run_complete(
        _Connection(), _args(torn_state), f2d_identity=identity,
    )
    assert exit_code == 0
    assert reads == [1]
    assert after_torn == fresh

    # A log whose checkpointed prefix was altered is refused, never resumed.
    altered_state = tmp_path / 'altered'
    exit_code, _ = complete.run_complete(
        _Connection(), _args(altered_state, stop_after_chunks=1), f2d_identity=identity,
    )
    assert exit_code == 75
    altered_log = altered_state / complete.PER_CHUNK_FILE
    altered_log.write_bytes(altered_log.read_bytes().replace(b'"S":', b'"s":'))
    with pytest.raises(ValueError, match='digest does not match the checkpoint'):
        complete.run_complete(_Connection(), _args(altered_state), f2d_identity=identity)

    # A log shorter than the checkpoint records is refused.
    altered_log.write_bytes(b'')
    with pytest.raises(ValueError, match='shorter than the checkpoint'):
        complete.run_complete(_Connection(), _args(altered_state), f2d_identity=identity)


def test_resume_writes_this_launch_id_before_scoring_and_receipt_excludes_it(
    tmp_path, monkeypatch,
):
    identity = compute_operator_code_sha256(ROOT)
    monkeypatch.setattr(complete, '_generation', lambda *_args: _generation_row())
    monkeypatch.setattr(complete, 'refuse_unlisted_checkout_modules', lambda: None)
    reads: list[int] = []
    probe = _fake_probe(reads)
    monkeypatch.setattr(complete, '_load_scoring_modules', lambda: (probe, builder, model))

    state = tmp_path / 'state'
    monkeypatch.setenv(complete.LAUNCH_ID_ENV, 'a' * 32)
    exit_code, _ = complete.run_complete(
        _Connection(), _args(state, stop_after_chunks=1), f2d_identity=identity,
    )
    assert exit_code == 75
    assert json.loads((state / 'checkpoint.json').read_text())['launch_id'] == 'a' * 32

    # The resumed launch's identifier is on disk before any further chunk is
    # read, so the start action's proof belongs to this worker, not the file
    # an earlier run left behind.
    monkeypatch.setenv(complete.LAUNCH_ID_ENV, 'b' * 32)
    seen_at_first_read: list[str] = []

    def read_chunk(connection, generation_id, ordinal):
        seen_at_first_read.append(
            json.loads((state / 'checkpoint.json').read_text())['launch_id']
        )
        return _fake_probe([])._read_chunk_rows(connection, generation_id, ordinal)

    monkeypatch.setattr(probe, '_read_chunk_rows', read_chunk)
    exit_code, resumed = complete.run_complete(
        _Connection(), _args(state), f2d_identity=identity,
    )
    assert exit_code == 0
    assert seen_at_first_read and seen_at_first_read[0] == 'b' * 32
    assert 'launch_id' not in json.dumps(resumed)

    monkeypatch.delenv(complete.LAUNCH_ID_ENV)
    monkeypatch.setattr(probe, '_read_chunk_rows', _fake_probe([])._read_chunk_rows)
    exit_code, fresh = complete.run_complete(
        _Connection(), _args(tmp_path / 'fresh'), f2d_identity=identity,
    )
    assert exit_code == 0
    assert resumed == fresh


def test_start_proves_this_launch_and_moves_a_stale_failure_receipt_aside():
    action = (
        ROOT / 'scripts/operator/actions/v3-archetype-calibration-complete.sh'
    ).read_text()
    start = action[action.index('start_operation()'):action.index('status_operation()')]
    launch = start.index('V3_ARCHETYPE_COMPLETE_LAUNCH_ID=%s')
    rotate = start.index('mv -- "$STATE_ROOT/failure-receipt.json"')
    run = start.index('docker run -d')
    # The old failure receipt is preserved under a new name before the new
    # worker launches, so status reports the live run instead of it.
    assert rotate < run and launch < run
    proof = start[start.index('local proof=false'):]
    # Existence of a checkpoint is not proof: it must carry this launch's id.
    assert "checkpoint.get('launch_id') == sys.argv[2]" in proof
    assert '"$launch_id"' in proof


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

    # Per-chunk counts live in the append-only log bound to the receipt by
    # digest and byte length; the receipt itself stays small for ~200k chunks.
    log_path = tmp_path / complete.PER_CHUNK_FILE
    log_bytes = log_path.read_bytes()
    assert receipt['per_chunk'] == {
        'file': complete.PER_CHUNK_FILE,
        'schema_version': complete.PER_CHUNK_SCHEMA,
        'chunk_count': 2,
        'bytes': len(log_bytes),
        'sha256': hashlib.sha256(log_bytes).hexdigest(),
    }
    assert receipt['chunk_plan'] == {
        'chunk_count': 2,
        'first_chunk_ordinal': 0,
        'last_chunk_ordinal': 1,
        'sha256': complete.canonical_sha256([[0, 2], [1, 1]]),
    }
    chunks = complete.validate_per_chunk_log(receipt, log_path)
    assert [chunk['chunk_ordinal'] for chunk in chunks] == [0, 1]
    assert [chunk['row_count'] for chunk in chunks] == [2, 1]
    assert 'per_chunk' not in receipt['per_archetype']['paradise']

    sigma = 0.0
    for key in model.ARCHETYPE_KEYS:
        entry = receipt['per_archetype'][key]
        histogram = entry['tier_histogram']
        assert sum(histogram.values()) == receipt['system_count']
        assert sum(chunk['row_count'] for chunk in chunks) == 3
        combined = {tier: 0 for tier in complete.TIERS}
        for chunk in chunks:
            for tier, count in chunk['per_archetype'][key]['tier_histogram'].items():
                combined[tier] += count
        assert combined == histogram
        total = sum(histogram.values())
        sigma += (histogram['S'] + histogram['A'] + histogram['B']) / total
        sigma += (histogram['S'] + histogram['A']) / total
        sigma += histogram['S'] / total
    assert receipt['sigma_all'] == pytest.approx(sigma)
    for field in ('started_at', 'updated_at', 'chunk_count'):
        assert field not in receipt
    checkpoint = json.loads((tmp_path / 'checkpoint.json').read_text())
    assert checkpoint['chunk_count'] == 2
    assert checkpoint['next_chunk_index'] == 2
    assert checkpoint['per_chunk_sha256'] == receipt['per_chunk']['sha256']

    # A log that does not match the receipt binding is refused by the consumer.
    tampered = tmp_path / 'tampered.jsonl'
    tampered.write_bytes(log_bytes.replace(b'"row_count":1', b'"row_count":2'))
    with pytest.raises(ValueError, match='does not match the receipt binding'):
        complete.validate_per_chunk_log(receipt, tampered)
    forged = dict(receipt)
    forged['per_chunk'] = {
        **receipt['per_chunk'],
        'bytes': tampered.stat().st_size,
        'sha256': hashlib.sha256(tampered.read_bytes()).hexdigest(),
    }
    forged.pop('content_sha256')
    forged = complete.seal_receipt(forged)
    with pytest.raises(ValueError, match='histogram total is invalid'):
        complete.validate_per_chunk_log(forged, tampered)

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
    assert '--require-hashes -r /work/deploy/v3-production/f2d-wheels.txt' in action
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


def _scoring_fixture(monkeypatch, reads):
    identity = compute_operator_code_sha256(ROOT)
    monkeypatch.setattr(complete, '_generation', lambda *_args: _generation_row())
    monkeypatch.setattr(complete, 'refuse_unlisted_checkout_modules', lambda: None)
    probe = _fake_probe(reads)
    monkeypatch.setattr(complete, '_load_scoring_modules', lambda: (probe, builder, model))
    return identity, probe


def test_resume_survives_a_stale_temporary_left_by_a_hard_kill(tmp_path, monkeypatch):
    # The worker is PID 1 in its container, so the old `.checkpoint.json.tmp-1`
    # name was identical on every run and O_EXCL refused every later resume.
    reads: list[int] = []
    identity, _ = _scoring_fixture(monkeypatch, reads)
    state = tmp_path / 'state'
    exit_code, _ = complete.run_complete(
        _Connection(), _args(state, stop_after_chunks=1), f2d_identity=identity,
    )
    assert exit_code == 75
    stale = state / '.checkpoint.json.tmp-1'
    stale.write_text('{"torn":', encoding='utf-8')
    (state / '.failure-receipt.json.tmp-1').write_text('', encoding='utf-8')
    exit_code, receipt = complete.run_complete(
        _Connection(), _args(state), f2d_identity=identity,
    )
    assert exit_code == 0
    assert complete.validate_complete_receipt(receipt) is receipt
    assert not stale.exists()
    assert not list(state.glob('.checkpoint.json.tmp-*'))
    # The failure-receipt writer is also unblocked by a stale temporary.
    complete._failure_receipt(state, 'x', identity)
    assert json.loads((state / 'failure-receipt.json').read_text())['status'] == 'failed'
    assert not list(state.glob('.failure-receipt.json.tmp-*'))


import psycopg  # noqa: E402


class _FlakyConnectionFactory:
    '''Produces connections whose chunk reads fail a scripted number of times.'''

    def __init__(self, failures_by_ordinal: dict[int, list[BaseException]]):
        self.failures = failures_by_ordinal
        self.created: list[_Connection] = []
        self.rollbacks = 0
        self.closed = 0
        self.events: list[tuple[int, str]] = []  # (connection index, commit|rollback)

    def connect(self):
        connection = _Connection()
        factory = self
        inner_commit = connection.commit
        index = len(self.created)

        def commit():
            inner_commit()
            factory.events.append((index, 'commit'))

        def rollback():
            factory.rollbacks += 1
            factory.events.append((index, 'rollback'))

        connection.commit = commit

        def close():
            factory.closed += 1

        connection.rollback = rollback
        connection.close = close
        self.created.append(connection)
        return connection

    def wrap_probe(self, probe):
        inner = probe._read_chunk_rows

        def read(connection, generation_id, ordinal):
            pending = self.failures.get(ordinal)
            if pending:
                error = pending.pop(0)
                if isinstance(error, psycopg.OperationalError) and not isinstance(
                    error, psycopg.errors.QueryCanceled,
                ):
                    connection.broken = True  # the server link is gone
                raise error
            return inner(connection, generation_id, ordinal)

        probe._read_chunk_rows = read


def test_chunk_read_retries_then_succeeds_and_reconnects_on_connection_loss(
    tmp_path, monkeypatch,
):
    import psycopg

    reads: list[int] = []
    identity, probe = _scoring_fixture(monkeypatch, reads)
    cancelled = psycopg.errors.QueryCanceled('canceling statement due to statement timeout')
    dropped = psycopg.OperationalError('server closed the connection unexpectedly')
    factory = _FlakyConnectionFactory({0: [cancelled], 1: [dropped]})
    factory.wrap_probe(probe)
    sleeps: list[float] = []
    first = factory.connect()
    exit_code, receipt = complete.run_complete(
        first, _args(tmp_path), f2d_identity=identity,
        reconnect=factory.connect, sleep=sleeps.append,
    )
    assert exit_code == 0
    assert complete.validate_complete_receipt(receipt) is receipt
    # Chunk 0: one statement cancel, rolled back on the same connection.
    # Chunk 1: one dropped connection, replaced by a fresh configured one.
    assert factory.rollbacks == 1
    assert factory.closed == 1
    assert len(factory.created) == 2
    replacement = factory.created[1]
    assert replacement.read_only is True
    assert any("'plan_cache_mode','force_custom_plan'" in s for s in replacement.statements)
    assert any("'statement_timeout'" in s for s in replacement.statements)
    assert sleeps == [complete.CHUNK_RETRY_BACKOFF_SECONDS[0]] * 2
    # Each chunk is checkpointed exactly once.
    log = (tmp_path / complete.PER_CHUNK_FILE).read_bytes().splitlines()
    assert [json.loads(line)['chunk_ordinal'] for line in log] == [0, 1]
    assert reads == [0, 1]


def test_chunk_read_retry_exhaustion_leaves_a_detailed_failure_receipt(
    tmp_path, monkeypatch,
):
    import psycopg

    reads: list[int] = []
    identity, probe = _scoring_fixture(monkeypatch, reads)
    errors = [
        psycopg.errors.QueryCanceled('canceling statement due to statement timeout')
        for _ in range(complete.CHUNK_RETRY_ATTEMPTS)
    ]
    for error in errors:
        error.sqlstate = '57014'
    first_error = errors[0]
    factory = _FlakyConnectionFactory({1: list(errors)})
    factory.wrap_probe(probe)
    connection = factory.connect()
    with pytest.raises(complete.ChunkReadError) as caught:
        complete.run_complete(
            connection, _args(tmp_path), f2d_identity=identity,
            reconnect=factory.connect, sleep=lambda _seconds: None,
        )
    assert caught.value.ordinal == 1
    assert factory.rollbacks == complete.CHUNK_RETRY_ATTEMPTS - 1
    # Chunk 0 was checkpointed; chunk 1 never was, so a later resume rescans it.
    checkpoint = json.loads((tmp_path / 'checkpoint.json').read_text())
    assert checkpoint['next_chunk_index'] == 1

    # main() turns it into a sealed failure receipt with the detail an
    # operator needs: class, message, SQLSTATE and the chunk in flight.
    monkeypatch.setenv(complete.DEFAULT_IDENTITY_ENV, identity)
    monkeypatch.setenv(complete.DEFAULT_DATABASE_URL_ENV, 'postgresql://unused/unused')
    monkeypatch.setattr(complete, 'require_image_model_match', lambda _path: 'f' * 64)
    monkeypatch.setattr(
        complete.f2d_operator_identity, 'require_operator_code_identity',
        lambda _root, _attested: identity,
    )

    def run_complete(*_args, **_kwargs):
        raise complete.ChunkReadError(1, first_error)

    monkeypatch.setattr(complete, 'run_complete', run_complete)
    monkeypatch.setattr(psycopg, 'connect', lambda *_a, **_k: _ContextConnection())
    assert complete.main([
        '--generation-key', 'g', '--generation-id', 'i', '--publication-sequence', '1',
        '--state-dir', str(tmp_path / 'main'),
    ]) == 4
    receipt = json.loads((tmp_path / 'main' / 'failure-receipt.json').read_text())
    assert complete.validate_complete_receipt(receipt) is receipt
    assert receipt['failures'] == ['database error: QueryCanceled']
    assert receipt['error'].startswith('QueryCanceled: canceling statement')
    assert receipt['sqlstate'] == '57014'
    assert receipt['chunk_ordinal'] == 1


class _ContextConnection(_Connection):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_main_writes_a_failure_receipt_for_any_exception(tmp_path, monkeypatch):
    import psycopg

    identity = 'a' * 64
    monkeypatch.setenv(complete.DEFAULT_IDENTITY_ENV, identity)
    monkeypatch.setenv(complete.DEFAULT_DATABASE_URL_ENV, 'postgresql://unused/unused')
    monkeypatch.setattr(complete, 'require_image_model_match', lambda _path: 'f' * 64)
    monkeypatch.setattr(
        complete.f2d_operator_identity, 'require_operator_code_identity',
        lambda _root, _attested: identity,
    )
    monkeypatch.setattr(psycopg, 'connect', lambda *_a, **_k: _ContextConnection())

    def run_complete(*_args, **_kwargs):
        raise TypeError("int() argument must be a string, not 'NoneType'")

    monkeypatch.setattr(complete, 'run_complete', run_complete)
    assert complete.main([
        '--generation-key', 'g', '--generation-id', 'i', '--publication-sequence', '1',
        '--state-dir', str(tmp_path),
    ]) == 5
    receipt = json.loads((tmp_path / 'failure-receipt.json').read_text())
    assert complete.validate_complete_receipt(receipt) is receipt
    assert receipt['failures'] == ['internal error: TypeError']
    assert receipt['error'] == "TypeError: int() argument must be a string, not 'NoneType'"
    assert 'postgresql://' not in json.dumps(receipt)


def test_complete_default_statement_timeout_is_five_minutes():
    args = complete.parse_args([
        '--generation-key', 'g', '--generation-id', 'i', '--publication-sequence', '1',
    ])
    assert args.statement_timeout_ms == 300_000


def test_action_refusals_print_a_result_line_on_stdout():
    import os
    import subprocess

    action = ROOT / 'scripts/operator/actions/v3-archetype-calibration-complete.sh'
    environment = os.environ.copy()
    environment.pop('F2D_OPERATOR_CODE_SHA256_ATTESTED', None)
    result = subprocess.run(
        ['bash', str(action), 'start', str(ROOT), '0' * 40],
        cwd=ROOT, env=environment, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 64
    line = json.loads(result.stdout.strip().splitlines()[-1])
    assert line['status'] == 'stopped'
    assert line['failures'] == ['attested_identity_refused']
    assert line['operation'] == 'v3-archetype-calibration-complete-start'
    # A generic fail() refusal also leaves a parseable line.
    result = subprocess.run(
        ['bash', str(action), 'status', '/nonexistent-bundle', '0' * 40],
        cwd=ROOT, env=environment, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 64
    line = json.loads(result.stdout.strip().splitlines()[-1])
    assert line['failures'] == ['trusted_main_bundle_path_is_required']
    assert 'trusted main bundle path is required' in result.stderr


def test_action_keeps_worker_logs_and_uses_init_with_a_ten_minute_proof_window():
    action = (
        ROOT / 'scripts/operator/actions/v3-archetype-calibration-complete.sh'
    ).read_text()
    start = action[action.index('start_operation()'):action.index('status_operation()')]
    # A stopped worker's logs are saved before `docker rm` discards them.
    assert start.index('save_worker_logs') < start.index('docker rm "$WORKER"')
    assert 'docker logs --tail 200 "$WORKER" > "$destination" 2>&1' in action
    assert '--init \\' in start
    assert 'for _ in $(seq 1 300); do' in start
    assert "'log_tail': os.environ.get('WORKER_LOGS') or None" in action


def test_workflow_routes_action_stderr_into_the_receipt_artifact():
    workflow = (ROOT / '.github/workflows/chatgpt-ed-new-ops.yml').read_text()
    for script in (
        'v3-archetype-calibration-complete.sh',
        'v3-archetype-calibration-probe.sh',
        'v3-system-search-f1.sh',
        'v3-system-archetype.sh',
        'v3-finder-capacity-gate.sh',
        'v3-archetype-plan-probe.sh',
    ):
        for line in workflow.splitlines():
            if f'actions/{script} | tee' in line or f'actions/{script} 2>&1 | tee' in line:
                assert '2>&1 | tee "$RECEIPT"' in line, line


def test_configure_session_commits_so_a_later_rollback_keeps_the_settings():
    # autocommit is off: without the commit, the first rollback after a
    # reconnect would discard statement_timeout and force_custom_plan.
    connection = _Connection()
    complete.configure_session(connection, 1234)
    assert connection.read_only is True
    assert connection.commits == 1
    assert any("'statement_timeout'" in s for s in connection.statements)
    assert any("'plan_cache_mode','force_custom_plan'" in s for s in connection.statements)


def test_settings_survive_a_rollback_after_reconnect(tmp_path, monkeypatch):
    # After the reconnect for chunk 1, the replacement connection sees a
    # statement cancel on the next attempt and is rolled back; its session
    # configuration was committed, so it is still in force for the retry.
    reads: list[int] = []
    identity, probe = _scoring_fixture(monkeypatch, reads)
    dropped = psycopg.OperationalError('server closed the connection unexpectedly')
    cancelled = psycopg.errors.QueryCanceled('canceling statement due to statement timeout')
    factory = _FlakyConnectionFactory({1: [dropped, cancelled]})
    factory.wrap_probe(probe)
    exit_code, receipt = complete.run_complete(
        factory.connect(), _args(tmp_path), f2d_identity=identity,
        reconnect=factory.connect, sleep=lambda _s: None,
    )
    assert exit_code == 0
    assert complete.validate_complete_receipt(receipt) is receipt
    replacement = factory.created[1]
    configured_at = next(
        i for i, s in enumerate(replacement.statements)
        if "'plan_cache_mode','force_custom_plan'" in s
    )
    # The configuration commit happened before any chunk statement and before
    # the rollback that followed the cancel: commit (configure), rollback
    # (cancel), commit (chunk 1 scored).
    assert replacement.commit_marks[0] == configured_at + 1
    assert [kind for index, kind in factory.events if index == 1] == ['commit', 'rollback', 'commit']
    assert factory.rollbacks == 1
    assert reads == [0, 1]


def test_reconnect_failures_count_against_the_chunk_retry_budget(tmp_path, monkeypatch):
    reads: list[int] = []
    identity, probe = _scoring_fixture(monkeypatch, reads)
    dropped = psycopg.OperationalError('server closed the connection unexpectedly')
    factory = _FlakyConnectionFactory({1: [dropped]})
    factory.wrap_probe(probe)
    connect_errors = [psycopg.OperationalError('connection refused')]
    real_connect = factory.connect

    def reconnect():
        if connect_errors:
            raise connect_errors.pop(0)
        return real_connect()

    # One failed reconnect, then success: the run completes.
    exit_code, receipt = complete.run_complete(
        factory.connect(), _args(tmp_path / 'ok'), f2d_identity=identity,
        reconnect=reconnect, sleep=lambda _s: None,
    )
    assert exit_code == 0
    assert complete.validate_complete_receipt(receipt) is receipt

    # Every reconnect failing exhausts the per-chunk budget and keeps the
    # chunk ordinal, instead of escaping as a bare connection error.
    reads.clear()
    factory = _FlakyConnectionFactory({1: [psycopg.OperationalError('dropped')]})
    factory.wrap_probe(probe)

    def always_refused():
        raise psycopg.OperationalError('connection refused')

    with pytest.raises(complete.ChunkReadError) as caught:
        complete.run_complete(
            factory.connect(), _args(tmp_path / 'refused'), f2d_identity=identity,
            reconnect=always_refused, sleep=lambda _s: None,
        )
    assert caught.value.ordinal == 1
    assert 'connection refused' in str(caught.value.cause)


def _run_action_with_fake_docker(tmp_path, action_name, *, ps_names, prepare_state=None):
    '''Run the action against a staged manifest tree and a fake docker.'''
    import os
    import shutil
    import subprocess
    import textwrap

    from scripts.operator.lib import f2d_operator_identity

    source_sha = hashlib.sha1(str(tmp_path).encode()).hexdigest()
    stage = Path(f'/var/tmp/edfinder-v3-archetype-complete-{source_sha}')
    stage.mkdir(mode=0o700)
    try:
        for entry in f2d_operator_identity.manifest_entries(ROOT):
            if entry.startswith('requirement:'):
                continue
            destination = stage / entry
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / entry, destination)
        (stage / '.v3-archetype-complete-source-sha').write_text(f'{source_sha}\n')
        (stage / '.v3-probe-wheelhouse').mkdir()
        identity = compute_operator_code_sha256(stage)

        fake_bin = tmp_path / 'bin'
        fake_bin.mkdir()
        (fake_bin / 'hostname').write_text(
            '#!/bin/sh\nif [ "${1:-}" = "-f" ]; then echo nb79a3d.mevnode.com; else echo ed-finder-prod; fi\n'
        )
        (fake_bin / 'python3.14').write_text('#!/bin/sh\nexec "$TEST_PYTHON_BIN" "$@"\n')
        (fake_bin / 'docker').write_text(textwrap.dedent(f'''\
            #!/usr/bin/env python3
            import json, sys
            args = sys.argv[1:]
            joined = " ".join(args)
            if "derived_generation_purge_event" in joined:
                print(json.dumps({{"database": "edfinder_v3_phase4c_full_20260827_r5",
                    "read_only": "on", "ledger_present": True, "unresolved": []}}))
                raise SystemExit(0)
            if args[:2] == ["context", "show"]:
                print("default"); raise SystemExit(0)
            if args[:3] == ["context", "inspect", "default"]:
                print('{{"Endpoints":{{"docker":{{"Host":"unix:///var/run/docker.sock"}}}}}}'); raise SystemExit(0)
            if args[:1] == ["inspect"]:
                if "edfinder-v3-archetype-calibration-complete" in joined:
                    raise SystemExit(1)  # no worker container
                if "State.Running" in joined:
                    print("true")
                elif "com.docker.compose.service" in joined:
                    print("api-blue" if "api-active" in joined else "api-green")
                else:
                    print("{{}}")
                raise SystemExit(0)
            if args[:1] == ["ps"]:
                for name in {ps_names!r}:
                    print(name)
                raise SystemExit(0)
            if args[:1] == ["exec"] and "current_derived_generation" in joined:
                print("ratings_v4_prod_p4_parallel_v1\\tcfc25d36-3bc7-4011-a465-d6460eaaf826\\tPUBLISHED\\t1\\ttrue")
                raise SystemExit(0)
            raise SystemExit(2)
        '''))
        for name in ('hostname', 'python3.14', 'docker'):
            (fake_bin / name).chmod(0o755)
        home = tmp_path / 'home'
        home.mkdir()
        state_root = home / '.local/state/ed-finder/v3-archetype-calibration-complete'
        if prepare_state is not None:
            state_root.mkdir(parents=True)
            prepare_state(state_root)
        env = os.environ.copy()
        env.update({
            'PATH': f'{fake_bin}{os.pathsep}{env.get("PATH", "")}',
            'HOME': str(home),
            'TEST_PYTHON_BIN': sys.executable,
            'F2D_OPERATOR_CODE_SHA256_ATTESTED': identity,
        })
        result = subprocess.run(
            ['bash', str(stage / 'scripts/operator/actions/v3-archetype-calibration-complete.sh'),
             action_name, str(stage), source_sha],
            cwd=stage, env=env, capture_output=True, text=True, check=False,
        )
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return result, state_root


def test_action_refusal_inside_a_command_substitution_still_prints_its_line(tmp_path):
    '''The "two API slots" refusal is raised inside api="$(active_api_container)".'''
    result, _ = _run_action_with_fake_docker(
        tmp_path, 'start', ps_names=['api-active', 'api-other'],
    )
    assert result.returncode == 64, result.stderr
    assert 'expected exactly one running production API slot, found 2' in result.stderr
    line = json.loads(result.stdout.strip().splitlines()[-1])
    assert line['status'] == 'stopped'
    assert line['failures'] == ['expected_exactly_one_running_production_API_slot_found_2']


def test_status_reports_the_archived_crash_log_from_a_later_process(tmp_path):
    # start archived the crashed worker's logs and removed the container; a
    # later status call is a different process and must still find them.
    def prepare(state_root):
        archive = state_root / 'worker-logs.20261018T200000Z.123.txt'
        archive.write_text('pip ok\ndatabase error: OperationalError\n')
        (state_root / 'worker-logs.latest').write_text(f'{archive}\n')

    result, state_root = _run_action_with_fake_docker(
        tmp_path, 'status', ps_names=['api-active'], prepare_state=prepare,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload['status'] == 'stopped'
    assert payload['worker']['status'] == 'missing'
    assert payload['worker']['log_tail'].endswith('database error: OperationalError')
    assert payload['worker']['archived_log_file'] == str(
        state_root / 'worker-logs.20261018T200000Z.123.txt'
    )


def test_status_ignores_a_pointer_outside_the_state_directory(tmp_path):
    def prepare(state_root):
        (state_root / 'worker-logs.latest').write_text('/etc/passwd\n')

    result, _ = _run_action_with_fake_docker(
        tmp_path, 'status', ps_names=['api-active'], prepare_state=prepare,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload['worker']['log_tail'] is None
    assert payload['worker']['archived_log_file'] is None


def test_a_failed_session_configuration_discards_the_reconnected_connection(
    tmp_path, monkeypatch,
):
    reads: list[int] = []
    identity, probe = _scoring_fixture(monkeypatch, reads)
    factory = _FlakyConnectionFactory({1: [psycopg.OperationalError('dropped')]})
    factory.wrap_probe(probe)
    real_configure = complete.configure_session
    configure_failures = [psycopg.OperationalError('SET failed')]
    configured: list[int] = []

    def configure(connection, timeout):
        if connection is not factory.created[0] and configure_failures:
            raise configure_failures.pop(0)
        configured.append(factory.created.index(connection))
        real_configure(connection, timeout)

    monkeypatch.setattr(complete, 'configure_session', configure)
    exit_code, receipt = complete.run_complete(
        factory.connect(), _args(tmp_path), f2d_identity=identity,
        reconnect=factory.connect, sleep=lambda _s: None,
    )
    assert exit_code == 0
    assert complete.validate_complete_receipt(receipt) is receipt
    # Three connections: the original, the one whose configuration failed
    # (closed, never used for a read) and the configured replacement.
    assert len(factory.created) == 3
    assert configured == [0, 2]
    assert factory.closed == 2
    assert factory.created[1].statements == []
