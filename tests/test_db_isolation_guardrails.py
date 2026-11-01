import pytest

from tests.helpers import db_isolation


def test_default_target_uses_isolated_port_not_host_5432():
    target = db_isolation.default_target({})

    assert target.host == '127.0.0.1'
    assert target.port == '55432'
    assert target.host_postgres_5432_targeted is False
    assert 'edfinder' in target.redacted_dsn
    assert '***' in target.redacted_dsn


@pytest.mark.parametrize(
    'dsn,match',
    [
        ('postgresql://edfinder:secret@db.example.com:55432/edfinder', 'unsafe test DB host'),
        ('postgresql://edfinder:secret@127.0.0.1:55432/edfinder_prod', 'production-like marker'),
        ('postgresql://edfinder:secret@prod-db:55432/edfinder', 'unsafe test DB host'),
        ('postgresql://edfinder@127.0.0.1:55432/edfinder', 'must include credentials'),
        ('postgresql://edfinder:@127.0.0.1:55432/edfinder', 'must include credentials'),
        ('postgresql://edfinder:secret@127.0.0.1:5432/edfinder', 'localhost:5432'),
    ],
)
def test_unsafe_targets_fail_closed(dsn, match):
    with pytest.raises(db_isolation.DbIsolationError, match=match):
        db_isolation.validate_test_db_target(dsn, env={})


def test_explicit_opt_in_allows_localhost_5432_for_disposable_db():
    target = db_isolation.validate_test_db_target(
        'postgresql://edfinder:secret@127.0.0.1:5432/edfinder',
        env={db_isolation.HOST_5432_OPT_IN_ENV: 'yes'},
    )

    assert target.host_postgres_5432_targeted is True
    assert target.host_5432_allowed is True


def test_ci_allows_localhost_5432_service_container():
    target = db_isolation.validate_test_db_target(
        'postgresql://edfinder:secret@localhost:5432/edfinder',
        env={'CI': 'true'},
    )

    assert target.host_postgres_5432_targeted is True
    assert target.host_5432_allowed is True


def test_secrets_are_redacted_from_url_and_keyword_dsns():
    assert db_isolation.redact_dsn(
        'postgresql://edfinder:super-secret@127.0.0.1:55432/edfinder'
    ) == 'postgresql://edfinder:***@127.0.0.1:55432/edfinder'
    assert db_isolation.redact_dsn(
        'host=127.0.0.1 port=55432 dbname=edfinder user=edfinder password=super-secret'
    ) == 'host=127.0.0.1 port=55432 dbname=edfinder user=edfinder password=***'


def test_safe_summary_never_prints_secret():
    target = db_isolation.validate_test_db_target(
        'postgresql://edfinder:do-not-print@127.0.0.1:55432/edfinder',
        env={},
    )

    summary = target.safe_summary()
    assert 'do-not-print' not in repr(summary)
    assert summary['dsn'] == 'postgresql://edfinder:***@127.0.0.1:55432/edfinder'


def test_destructive_reset_requires_explicit_opt_in():
    with pytest.raises(db_isolation.DbIsolationError, match='destructive reset requires'):
        db_isolation.require_destructive_reset_opt_in({})

    db_isolation.require_destructive_reset_opt_in({
        db_isolation.DESTRUCTIVE_RESET_OPT_IN_ENV: 'yes',
    })


def test_explicit_empty_env_does_not_inherit_ambient_ci(monkeypatch):
    monkeypatch.setenv('CI', 'true')

    with pytest.raises(db_isolation.DbIsolationError, match='localhost:5432'):
        db_isolation.validate_test_db_target(
            'postgresql://edfinder:secret@127.0.0.1:5432/edfinder',
            env={},
        )

    assert db_isolation.host_5432_is_allowed({}) is False


def test_explicit_empty_env_does_not_inherit_ambient_destructive_reset_opt_in(monkeypatch):
    monkeypatch.setenv(db_isolation.DESTRUCTIVE_RESET_OPT_IN_ENV, 'yes')

    with pytest.raises(db_isolation.DbIsolationError, match='destructive reset requires'):
        db_isolation.require_destructive_reset_opt_in({})


def test_explicit_ci_mapping_preserves_documented_ci_behavior():
    target = db_isolation.validate_test_db_target(
        'postgresql://edfinder:secret@127.0.0.1:5432/edfinder',
        env={'CI': 'true'},
    )

    assert target.host_postgres_5432_targeted is True
    assert target.host_5432_allowed is True
    assert db_isolation.host_5432_is_allowed({'CI': 'true'}) is True


def test_custom_mapping_does_not_inherit_unrelated_ambient_values(monkeypatch):
    monkeypatch.setenv('CI', 'true')
    monkeypatch.setenv(db_isolation.HOST_5432_OPT_IN_ENV, 'yes')
    monkeypatch.setenv(db_isolation.DESTRUCTIVE_RESET_OPT_IN_ENV, 'yes')

    with pytest.raises(db_isolation.DbIsolationError, match='localhost:5432'):
        db_isolation.validate_test_db_target(
            'postgresql://edfinder:secret@127.0.0.1:5432/edfinder',
            env={'UNRELATED': '1'},
        )

    with pytest.raises(db_isolation.DbIsolationError, match='destructive reset requires'):
        db_isolation.require_destructive_reset_opt_in({'UNRELATED': '1'})

    assert db_isolation.host_5432_is_allowed({'UNRELATED': '1'}) is False


def test_none_env_still_uses_ambient_environment(monkeypatch):
    monkeypatch.setenv('CI', 'true')
    monkeypatch.delenv(db_isolation.HOST_5432_OPT_IN_ENV, raising=False)

    target = db_isolation.validate_test_db_target(
        'postgresql://edfinder:secret@localhost:5432/edfinder',
        env=None,
    )

    assert target.host_postgres_5432_targeted is True
    assert target.host_5432_allowed is True
    assert db_isolation.host_5432_is_allowed(None) is True


def test_none_env_uses_ambient_destructive_reset_opt_in(monkeypatch):
    monkeypatch.setenv(db_isolation.DESTRUCTIVE_RESET_OPT_IN_ENV, 'yes')
    db_isolation.require_destructive_reset_opt_in(None)


def test_target_from_env_and_pg_env_respect_explicit_empty_mapping(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://edfinder:secret@localhost:5432/edfinder')
    monkeypatch.setenv('PGHOST', 'localhost')
    monkeypatch.setenv('PGPORT', '5432')
    monkeypatch.setenv('PGDATABASE', 'edfinder')
    monkeypatch.setenv('PGUSER', 'edfinder')
    monkeypatch.setenv('PGPASSWORD', 'secret')
    monkeypatch.setenv('CI', 'true')

    target = db_isolation.target_from_env({})
    assert target.host == '127.0.0.1'
    assert target.port == '55432'
    assert target.host_5432_allowed is False

    target = db_isolation.target_from_pg_env({})
    assert target.host == '127.0.0.1'
    assert target.port == '55432'
    assert target.host_5432_allowed is False


def test_default_target_remains_isolated_from_ambient_ci(monkeypatch):
    monkeypatch.setenv('CI', 'true')

    target = db_isolation.default_target()

    assert target.host == '127.0.0.1'
    assert target.port == '55432'
    assert target.host_postgres_5432_targeted is False
    assert target.host_5432_allowed is False


def test_safe_schema_names_are_generated_and_validated():
    schema = db_isolation.safe_schema_name('Stage 19 AR', token='abc123')

    assert schema == 'stage_19_ar_abc123'
    assert db_isolation.validate_schema_name(schema) == schema
    with pytest.raises(db_isolation.DbIsolationError):
        db_isolation.validate_schema_name('unsafe-name;drop')


def test_rollback_transaction_rolls_back_and_closes():
    class FakeConn:
        def __init__(self):
            self.read_only = None
            self.autocommit = None
            self.rollbacks = 0
            self.closed = False

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    fake = FakeConn()

    def connect(dsn):
        assert dsn == 'postgresql://edfinder:secret@127.0.0.1:55432/edfinder'
        return fake

    with db_isolation.rollback_transaction(
        connect,
        'postgresql://edfinder:secret@127.0.0.1:55432/edfinder',
        readonly=True,
    ) as conn:
        assert conn is fake
        assert fake.read_only is True
        assert fake.autocommit is False

    assert fake.rollbacks == 1
    assert fake.closed is True


def test_database_unavailable_skips_by_default():
    with pytest.raises(pytest.skip.Exception, match='no server'):
        db_isolation.database_unavailable('no server', env={})


def test_database_unavailable_fails_when_db_tests_are_required():
    with pytest.raises(pytest.fail.Exception, match='EDF_DB_TESTS_REQUIRED=1 .* no server'):
        db_isolation.database_unavailable('no server', env={db_isolation.DB_TESTS_REQUIRED_ENV: '1'})

    # Only the exact value "1" arms the gate; other values keep the skip.
    with pytest.raises(pytest.skip.Exception):
        db_isolation.database_unavailable('no server', env={db_isolation.DB_TESTS_REQUIRED_ENV: 'yes'})


def test_import_db_module_honours_required_gate():
    assert db_isolation.import_db_module('json', env={}) is not None
    with pytest.raises(pytest.skip.Exception, match='not importable'):
        db_isolation.import_db_module('edf_no_such_driver_module', env={})
    with pytest.raises(pytest.fail.Exception, match='not importable'):
        db_isolation.import_db_module(
            'edf_no_such_driver_module', env={db_isolation.DB_TESTS_REQUIRED_ENV: '1'},
        )


def test_confirmed_target_or_skip_fails_without_opt_in_when_db_tests_are_required():
    with pytest.raises(pytest.fail.Exception, match='requires DSN and CONFIRM=yes'):
        db_isolation.confirmed_target_or_skip(
            dsn_env='DSN', confirm_env='CONFIRM', purpose='probe',
            env={db_isolation.DB_TESTS_REQUIRED_ENV: '1'},
        )


def test_ci_database_lanes_require_db_tests_to_run():
    import yaml
    from pathlib import Path

    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / '.github/workflows/ci.yml').read_text(encoding='utf-8')
    )
    expected = {
        'importer-tooling': 'Run importer and synchronous tooling unit and PostgreSQL tests',
        'journal-flows': 'Run V3 journal research and import flows',
        'integration': 'Run integration test suite',
        'finder-derived-data': 'Run every validation-fixture-backed Finder test module',
    }
    for job_id, step_name in expected.items():
        job = workflow['jobs'][job_id]
        assert 'postgres' in job['services'], job_id
        step = next(step for step in job['steps'] if step.get('name') == step_name)
        assert step['env'][db_isolation.DB_TESTS_REQUIRED_ENV] == '1', (job_id, step_name)
