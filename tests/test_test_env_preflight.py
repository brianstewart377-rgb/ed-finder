import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_PATH = ROOT / 'scripts' / 'dev' / 'test_env_preflight.py'

spec = importlib.util.spec_from_file_location('test_env_preflight', PREFLIGHT_PATH)
preflight = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = preflight
spec.loader.exec_module(preflight)


pytestmark = pytest.mark.unit


def successful_runner(args, timeout):
    del timeout
    stdout = ''
    if tuple(args[:2]) == ('docker', 'ps'):
        stdout = 'ed-postgres\n'
    if tuple(args[:1]) == ('pg_isready',):
        stdout = '127.0.0.1:55432 - accepting connections\n'
    return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr='')


def test_preflight_fails_closed_without_credentials_and_never_prints_secret():
    result = preflight.run_preflight(env={}, runner=successful_runner)
    encoded = json.dumps(result, sort_keys=True)

    assert result['ok'] is False
    assert result['failure_category'] == 'credentials_missing'
    assert result['writes_performed'] is False
    assert result['secrets_printed'] is False
    assert result['checks']['db_read_only_select_1']['detail']['attempted'] is False
    assert 'POSTGRES_PASSWORD=' not in encoded
    assert 'PGPASSWORD=' not in encoded
    assert 'postgresql://' not in encoded


def test_preflight_runs_read_only_select_when_credentials_are_present_without_printing_secret():
    def db_probe(env, database):
        assert env['POSTGRES_PASSWORD'] == 'do-not-print-this'
        assert database['password_value_printed'] is False
        return preflight.CheckResult(
            'db_read_only_select_1',
            True,
            None,
            {'attempted': True, 'transaction_read_only': True},
        )

    result = preflight.run_preflight(
        env={'POSTGRES_PASSWORD': 'do-not-print-this'},
        runner=successful_runner,
        db_probe=db_probe,
    )
    encoded = json.dumps(result, sort_keys=True)

    assert result['ok'] is True
    assert result['db_read_only_select_1_passed'] is True
    assert result['writes_performed'] is False
    assert result['checks']['db_credentials']['detail']['present_without_printing'] is True
    assert 'do-not-print-this' not in encoded


def test_preflight_uses_isolated_project_postgres_port_by_default():
    config = preflight.resolve_db_config({})

    assert config['host'] == '127.0.0.1'
    assert config['port'] == '55432'
    assert config['host_postgres_5432_targeted'] is False


def test_command_failures_are_classified_without_secret_material():
    def failing_pg_isready(args, timeout):
        del timeout
        if args[0] == 'pg_isready':
            return subprocess.CompletedProcess(args, 2, stdout='', stderr='no response')
        return successful_runner(args, timeout=5)

    result = preflight.run_preflight(
        env={'PGPASSWORD': 'hidden-password'},
        runner=failing_pg_isready,
        db_probe=lambda _env, _database: preflight.CheckResult('db_read_only_select_1', True),
    )
    encoded = json.dumps(result, sort_keys=True)

    assert result['checks']['pg_isready']['failure_category'] == 'postgres_unavailable'
    assert 'hidden-password' not in encoded
