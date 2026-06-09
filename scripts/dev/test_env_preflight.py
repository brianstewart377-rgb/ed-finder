#!/usr/bin/env python3
"""Local test environment preflight with no writes and no secret output."""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_HOST = '127.0.0.1'
DEFAULT_DB_PORT = '55432'
DEFAULT_DB_NAME = 'edfinder'
DEFAULT_DB_USER = 'edfinder'


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    failure_category: str | None = None
    detail: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'ok': self.ok,
            'failure_category': self.failure_category,
            'detail': dict(self.detail or {}),
        }


CommandRunner = Callable[[Sequence[str], int], subprocess.CompletedProcess[str]]
DbProbe = Callable[[Mapping[str, str], Mapping[str, Any]], CheckResult]


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_preflight(env=os.environ, timeout=args.timeout_seconds)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['ok'] else 2


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Check the local test environment without writes.')
    parser.add_argument('--timeout-seconds', type=int, default=5)
    return parser.parse_args(argv)


def run_preflight(
    *,
    env: Mapping[str, str],
    runner: CommandRunner | None = None,
    db_probe: DbProbe | None = None,
    timeout: int = 5,
) -> dict[str, Any]:
    command_runner = runner or run_command
    database = resolve_db_config(env)
    checks = [
        check_pytest_available(),
        check_project_imports(),
        check_docker_cli(command_runner, timeout),
        check_docker_compose(command_runner, timeout),
        check_postgres_container(command_runner, timeout),
        check_pg_isready(command_runner, database, timeout),
        check_db_credentials(env),
    ]
    if database['password_present']:
        checks.append((db_probe or run_read_only_select_one)(env, database))
    else:
        checks.append(CheckResult(
            'db_read_only_select_1',
            False,
            'credentials_missing',
            {'attempted': False},
        ))

    failure_category = next((check.failure_category for check in checks if not check.ok), None)
    return {
        'ok': all(check.ok for check in checks),
        'failure_category': failure_category,
        'writes_performed': False,
        'secrets_printed': False,
        'db_read_only_select_1_passed': any(
            check.name == 'db_read_only_select_1' and check.ok for check in checks
        ),
        'credentials': {
            'postgres_password_present': bool(env.get('POSTGRES_PASSWORD')),
            'pgpassword_present': bool(env.get('PGPASSWORD')),
            'database_url_present': bool(env.get('DATABASE_URL')),
            'password_value_printed': False,
        },
        'database': database,
        'checks': {check.name: check.to_dict() for check in checks},
    }


def run_command(args: Sequence[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def check_pytest_available() -> CheckResult:
    return CheckResult(
        'pytest_available',
        importlib.util.find_spec('pytest') is not None,
        None if importlib.util.find_spec('pytest') is not None else 'pytest_missing',
    )


def check_project_imports() -> CheckResult:
    try:
        import_file('stage19ar_preflight_import', ROOT / 'scripts/operator/stage19ar_edsm_25_row_staging_pilot.py')
        import_file('stage19as_au_preflight_import', ROOT / 'scripts/operator/stage19as_au_edsm_100_row_controlled_expansion.py')
        with sys_path(ROOT / 'apps/api/src', ROOT / 'apps/api/src/routers'):
            importlib.import_module('operator_visibility')
            import_file('operator_router_preflight_import', ROOT / 'apps/api/src/routers/operator.py')
    except Exception as exc:
        return CheckResult('project_imports', False, classify_exception(exc))
    return CheckResult('project_imports', True)


def import_file(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f'cannot load {path.relative_to(ROOT)}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class sys_path:
    def __init__(self, *paths: Path):
        self.paths = [str(path) for path in paths]

    def __enter__(self) -> None:
        for path in reversed(self.paths):
            if path not in sys.path:
                sys.path.insert(0, path)

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        for path in self.paths:
            try:
                sys.path.remove(path)
            except ValueError:
                pass


def check_docker_cli(runner: CommandRunner, timeout: int) -> CheckResult:
    if shutil.which('docker') is None:
        return CheckResult('docker_cli', False, 'docker_cli_missing')
    completed = runner(('docker', 'version', '--format', '{{.Server.Version}}'), timeout)
    return command_result('docker_cli', completed, failure='docker_unavailable')


def check_docker_compose(runner: CommandRunner, timeout: int) -> CheckResult:
    if shutil.which('docker') is None:
        return CheckResult('docker_compose', False, 'docker_cli_missing')
    completed = runner(('docker', 'compose', 'version'), timeout)
    return command_result('docker_compose', completed, failure='docker_compose_unavailable')


def check_postgres_container(runner: CommandRunner, timeout: int) -> CheckResult:
    if shutil.which('docker') is None:
        return CheckResult('postgres_container', False, 'docker_cli_missing')
    completed = runner(('docker', 'ps', '--filter', 'name=ed-postgres', '--format', '{{.Names}}'), timeout)
    if completed.returncode != 0:
        return command_result('postgres_container', completed, failure='docker_unavailable')
    names = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return CheckResult(
        'postgres_container',
        'ed-postgres' in names,
        None if 'ed-postgres' in names else 'postgres_container_not_running',
        {'container_name_present': 'ed-postgres' in names},
    )


def check_pg_isready(runner: CommandRunner, database: Mapping[str, Any], timeout: int) -> CheckResult:
    if shutil.which('pg_isready') is None:
        return CheckResult('pg_isready', False, 'pg_isready_missing')
    completed = runner(('pg_isready', '-h', str(database['host']), '-p', str(database['port'])), timeout)
    return command_result('pg_isready', completed, failure='postgres_unavailable')


def command_result(name: str, completed: subprocess.CompletedProcess[str], *, failure: str) -> CheckResult:
    return CheckResult(
        name,
        completed.returncode == 0,
        None if completed.returncode == 0 else failure,
        {
            'returncode': completed.returncode,
            'stdout': completed.stdout.strip()[:300],
            'stderr': completed.stderr.strip()[:300],
        },
    )


def check_db_credentials(env: Mapping[str, str]) -> CheckResult:
    present = bool(env.get('POSTGRES_PASSWORD') or env.get('PGPASSWORD') or env.get('DATABASE_URL'))
    return CheckResult(
        'db_credentials',
        present,
        None if present else 'credentials_missing',
        {'present_without_printing': present},
    )


def resolve_db_config(env: Mapping[str, str]) -> dict[str, Any]:
    parsed = parse_database_url(env.get('DATABASE_URL'))
    return {
        'host': first_text(env.get('PGHOST'), parsed.get('host'), DEFAULT_DB_HOST),
        'port': first_text(env.get('PGPORT'), parsed.get('port'), DEFAULT_DB_PORT),
        'database': first_text(env.get('PGDATABASE'), parsed.get('database'), DEFAULT_DB_NAME),
        'user': first_text(env.get('PGUSER'), parsed.get('user'), DEFAULT_DB_USER),
        'database_url_present': bool(env.get('DATABASE_URL')),
        'password_present': bool(
            env.get('PGPASSWORD')
            or env.get('POSTGRES_PASSWORD')
            or parsed.get('password_present')
        ),
        'password_value_printed': False,
        'default_isolated_port': DEFAULT_DB_PORT,
        'host_postgres_5432_targeted': first_text(env.get('PGPORT'), parsed.get('port'), DEFAULT_DB_PORT) == '5432',
    }


def run_read_only_select_one(env: Mapping[str, str], database: Mapping[str, Any]) -> CheckResult:
    try:
        import psycopg2  # noqa: PLC0415
        import psycopg2.extras  # noqa: PLC0415
    except Exception as exc:
        return CheckResult('db_read_only_select_1', False, classify_exception(exc), {'attempted': False})

    conn = None
    try:
        conn = psycopg2.connect(build_db_dsn(env, database), cursor_factory=psycopg2.extras.RealDictCursor)
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute('SHOW transaction_read_only')
            read_only = cur.fetchone()['transaction_read_only'] == 'on'
            cur.execute('SELECT 1 AS db_preflight_ok')
            selected = cur.fetchone()['db_preflight_ok'] == 1
        conn.rollback()
        return CheckResult(
            'db_read_only_select_1',
            read_only and selected,
            None if read_only and selected else 'read_only_select_failed',
            {'attempted': True, 'transaction_read_only': read_only},
        )
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        return CheckResult('db_read_only_select_1', False, classify_exception(exc), {'attempted': True})
    finally:
        if conn is not None:
            conn.close()


def build_db_dsn(env: Mapping[str, str], database: Mapping[str, Any]) -> str:
    if env.get('DATABASE_URL'):
        return str(env['DATABASE_URL'])
    password = env.get('PGPASSWORD') or env.get('POSTGRES_PASSWORD')
    if not password:
        raise RuntimeError('credentials_missing')
    return ' '.join((
        f'host={database["host"]}',
        f'port={database["port"]}',
        f'dbname={database["database"]}',
        f'user={database["user"]}',
        f'password={password}',
        'sslmode=disable',
    ))


def parse_database_url(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = urlsplit(value)
    return {
        'host': parsed.hostname,
        'port': str(parsed.port) if parsed.port is not None else None,
        'database': parsed.path.lstrip('/') or None,
        'user': parsed.username,
        'password_present': parsed.password is not None,
    }


def first_text(*values: Any) -> str:
    for value in values:
        if value is not None and str(value):
            return str(value)
    return 'unknown'


def classify_exception(exc: Exception) -> str:
    text = str(exc).lower()
    if 'password authentication failed' in text:
        return 'password_authentication_failed'
    if 'connection refused' in text:
        return 'connection_refused'
    if 'could not translate host name' in text or 'name or service not known' in text:
        return 'host_resolution_failed'
    if 'timeout' in text:
        return 'connection_timeout'
    if 'credentials_missing' in text:
        return 'credentials_missing'
    return type(exc).__name__


if __name__ == '__main__':
    raise SystemExit(main())
