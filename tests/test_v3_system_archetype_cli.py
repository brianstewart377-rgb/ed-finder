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
    _verified_search_product(connection, generation_id, len(records))
    return key, generation_id


def _verified_search_product(connection, generation_id, expected_rows):
    connection.execute(
        '''INSERT INTO v3_meta.derived_product(
               derived_generation_id,product_code,product_version,manifest,
               manifest_sha256,expected_rows)
           VALUES (%s,'system_search','fixture-search-1','{}'::jsonb,%s,%s)''',
        (generation_id, b'\x01' * 32, expected_rows),
    )
    connection.execute(
        '''UPDATE v3_meta.derived_product
              SET lifecycle_state='READY',
                  validation_receipt='{"status":"VERIFIED"}'::jsonb,
                  validation_sha256=%s,validated_at=now()
            WHERE derived_generation_id=%s AND product_code='system_search' ''',
        (b'\x02' * 32, generation_id),
    )


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

    # The worker validates and promotes READY itself once every chunk is
    # sealed (the Search pattern); finalize no longer runs a validate container.
    assert builder.main(['--generation-key', key]) == 0
    built = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert built['status'] == 'VERIFIED'
    assert built['chunks_written'] == 3
    assert built['validation_receipt']['status'] == 'VERIFIED'

    assert builder.main(['--generation-key', key, '--validate']) == 0
    receipt = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert receipt['status'] == 'VERIFIED'
    assert receipt == built['validation_receipt']

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


def test_cli_forces_custom_plans_for_the_whole_session(database, monkeypatch):
    # Shared read SQL selects its branch with parameter NULL tests; a generic
    # plan joins full scans (production probe run 39155668281 cancelled at
    # its statement timeout). main() must set the session mode on connect,
    # before the first chunk read, for build and validate alike.
    connection, _, _, _ = database
    key, generation_id = _ratings_generation(database)
    _ready_ratings(database, generation_id)
    monkeypatch.setenv('V3_SYSTEM_ARCHETYPE_DATABASE_URL', _fixture_dsn(connection))
    observed = []
    import psycopg

    class Observed:
        def __init__(self, inner):
            self._inner = inner

        def __enter__(self):
            self._inner.__enter__()
            return self

        def __exit__(self, *args):
            return self._inner.__exit__(*args)

        def execute(self, sql, *args, **kwargs):
            observed.append(sql)
            return self._inner.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    original = psycopg.connect
    monkeypatch.setattr(psycopg, 'connect', lambda *a, **k: Observed(original(*a, **k)))
    assert builder.main(['--generation-key', key]) == 0
    forced = next(i for i, sql in enumerate(observed)
                  if "'plan_cache_mode','force_custom_plan'" in sql)
    first_read = next(i for i, sql in enumerate(observed)
                      if 'system_rating_vector' in sql)
    assert forced < first_read
    assert connection.execute(
        "SELECT current_setting('plan_cache_mode')"
    ).fetchone()[0] == 'auto'  # the fixture's own session is untouched


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


def test_run_follow_keeps_polling_while_base_is_still_building(database, monkeypatch):
    """Finding #1 (P1): archetype_chunks==rating_chunks can be momentarily
    true while the base Ratings generation is still BUILDING -- run() must not
    treat that as final, or later Ratings chunks would get no archetype rows.
    Build to full (transient) chunk-count parity while the base is BUILDING,
    then seal the base mid-poll and confirm the loop only completes after.
    """
    connection, _, _, _ = database
    key, generation_id = _ratings_generation(database)

    poll_calls = []

    def fake_sleep(seconds):
        poll_calls.append(seconds)
        if len(poll_calls) == 1:
            # Base seals mid-poll -- the loop must have been polling, not
            # already returned BUILT on the first (premature) chunk-count match.
            _ready_ratings(database, generation_id)

    monkeypatch.setattr(builder.time, 'sleep', fake_sleep)

    result = builder.run(connection, key, follow=True, poll_seconds=0.01)
    assert result['status'] == 'VERIFIED'
    assert result['validation_receipt']['status'] == 'VERIFIED'
    assert len(poll_calls) == 1

    row = connection.execute(
        'SELECT lifecycle_state FROM v3_meta.derived_generation WHERE derived_generation_id=%s',
        (generation_id,),
    ).fetchone()
    assert row[0] == 'READY'


def _fail_ratings(database, generation_id):
    connection, _, _, _ = database
    connection.execute(
        '''UPDATE v3_meta.derived_generation
              SET lifecycle_state='FAILED', failed_at=now(), failure=%s
            WHERE derived_generation_id=%s''',
        ('test_induced_failure', generation_id),
    )


def test_run_follow_stops_when_base_generation_fails(database, monkeypatch):
    """P1 finding: FAILED is a legal terminal state for the base Ratings
    generation (BUILDING/VALIDATING -> FAILED). If that transition happens
    while `run(follow=True)` is polling, `base_sealed` never becomes true and
    there is no terminal branch, so the loop must otherwise poll forever.
    Drive one poll, flip the base to FAILED during it, and assert the loop
    stops promptly with a failed signal instead of continuing to poll.
    """
    connection, _, _, _ = database
    key, generation_id = _ratings_generation(database)

    poll_calls = []

    def fake_sleep(seconds):
        poll_calls.append(seconds)
        if len(poll_calls) == 1:
            _fail_ratings(database, generation_id)
        elif len(poll_calls) > 3:
            pytest.fail('run() kept polling after the base generation failed')

    monkeypatch.setattr(builder.time, 'sleep', fake_sleep)

    result = builder.run(connection, key, follow=True, poll_seconds=0.01)
    assert result['status'] == 'FAILED'
    assert result['derived_generation_id'] == str(generation_id)
    assert len(poll_calls) == 1

    row = connection.execute(
        'SELECT lifecycle_state FROM v3_meta.derived_generation WHERE derived_generation_id=%s',
        (generation_id,),
    ).fetchone()
    assert row[0] == 'FAILED'


def test_cli_validate_returns_nonzero_exit_when_not_verified(database, monkeypatch, capsys):
    """Finding #4: --validate must fail closed on exit code (not just the
    printed receipt) whenever the result is not VERIFIED."""
    connection, _, _, _ = database
    key, generation_id = _ratings_generation(database)
    monkeypatch.setenv('V3_SYSTEM_ARCHETYPE_DATABASE_URL', _fixture_dsn(connection))

    # Do not seal/validate the base Ratings generation, so --validate returns
    # INCOMPLETE rather than VERIFIED.
    exit_code = builder.main(['--generation-key', key, '--validate'])
    assert exit_code != 0

    receipt = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert receipt['status'] == 'INCOMPLETE'


def test_cli_follow_returns_nonzero_exit_when_base_generation_fails(database, monkeypatch, capsys):
    """P1 finding: main() only fail-closes the exit code for --validate. A
    --follow run whose run() result is status='FAILED' (base Ratings
    generation went terminal) must ALSO exit nonzero -- otherwise CI/ops
    tooling that only checks the exit code treats a failed generation as
    success, even though the FAILED receipt was printed."""
    connection, _, _, _ = database
    key, generation_id = _ratings_generation(database)
    monkeypatch.setenv('V3_SYSTEM_ARCHETYPE_DATABASE_URL', _fixture_dsn(connection))

    poll_calls = []

    def fake_sleep(seconds):
        poll_calls.append(seconds)
        if len(poll_calls) == 1:
            _fail_ratings(database, generation_id)

    monkeypatch.setattr(builder.time, 'sleep', fake_sleep)

    exit_code = builder.main([
        '--generation-key', key, '--follow', '--poll-seconds', '0.01',
    ])
    assert exit_code != 0

    receipt = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert receipt['status'] == 'FAILED'


def test_code_identity_lists_model_and_migration():
    ident = builder.code_identity()
    assert 'shared_contracts/v3_system_archetype_model.py' in ident
    assert 'scripts/v3_system_archetype_model.py' in ident
    assert 'sql/v3/migrations/011_v3_system_archetype.sql' in ident


def test_code_identity_changes_when_only_canonical_model_changes(tmp_path):
    for path in builder.code_identity():
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / path).read_bytes())
    before = builder.code_identity(tmp_path)
    canonical = tmp_path / 'shared_contracts/v3_system_archetype_model.py'
    canonical.write_text(canonical.read_text() + '\n# identity-only test\n')
    after = builder.code_identity(tmp_path)
    changed = {path for path in before if before[path] != after[path]}
    assert changed == {'shared_contracts/v3_system_archetype_model.py'}


def test_failure_receipt_carries_bounded_detail_and_sqlstate(monkeypatch, capsys):
    import psycopg

    class Boom(psycopg.Error):
        pass

    error = Boom('canceling statement due to statement timeout ' + 'x' * 600)
    error.sqlstate = '57014'
    receipt = builder.failure_receipt(error)
    assert receipt['error'] == 'Boom'
    assert receipt['sqlstate'] == '57014'
    assert len(receipt['error_detail']) == 500
    assert receipt['error_detail'].startswith('Boom: canceling statement')
    assert builder.failure_receipt(ValueError('x')) == {
        'status': 'FAILED', 'error': 'ValueError', 'error_detail': 'ValueError: x',
    }
    # main() writes it to stderr on any unexpected failure.
    monkeypatch.setenv('V3_SYSTEM_ARCHETYPE_DATABASE_URL', 'postgresql://x:y@127.0.0.1:1/z')
    assert builder.main(['--generation-key', 'nothing']) == 1
    written = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert written['status'] == 'FAILED'
    assert 'error_detail' in written
    assert 'x:y@' not in json.dumps(written)


def test_session_settings_are_exactly_plan_mode_and_timeouts(monkeypatch):
    class Connection:
        def __init__(self):
            self.statements = []

        def execute(self, sql, params=None):
            self.statements.append((sql, params))

    connection = Connection()
    builder.configure_session(connection)
    names = [sql.split("'")[1] for sql, _ in connection.statements]
    assert names == ['plan_cache_mode', 'lock_timeout', 'statement_timeout']
    assert connection.statements[1][1] == (builder.LOCK_TIMEOUT,)
    assert connection.statements[2][1] == (builder.STATEMENT_TIMEOUT,)
    assert builder.STATEMENT_TIMEOUT == '30min'


def test_worker_validates_in_process_and_reports_validation_progress(database, monkeypatch):
    # After the last chunk is sealed the worker re-reads and re-scores every
    # chunk and promotes READY itself; finalize never launches a bounded
    # foreground validate container. Progress lines mark the validate phase.
    connection, _, _, _ = database
    key, generation_id = _ratings_generation(database)
    _ready_ratings(database, generation_id)
    events = []
    monkeypatch.setattr(builder, '_validate_rows_and_seals', _progress_spy(events))
    result = builder.run(connection, key, follow=True, progress=events.append)
    assert result['status'] == 'VERIFIED'
    assert result['validation_receipt']['status'] == 'VERIFIED'
    assert [event['phase'] for event in events if event.get('phase')] == ['validate']
    row = connection.execute(
        '''SELECT lifecycle_state FROM v3_meta.derived_product
            WHERE derived_generation_id=%s AND product_code=%s''',
        (generation_id, builder.PRODUCT_CODE),
    ).fetchone()
    assert row[0] == 'READY'
    # A re-run on the READY product re-prints the stored receipt, no rebuild.
    again = builder.run(connection, key, follow=True)
    assert again['status'] == 'VERIFIED' and again['chunks_written'] == 0


def _progress_spy(events):
    real = builder._validate_rows_and_seals

    def spy(connection, generation, manifest_sha, rating_chunks, progress=None):
        assert progress is not None
        progress({'phase': 'validate', 'chunks_total': len(rating_chunks)})
        return real(connection, generation, manifest_sha, rating_chunks)

    return spy
