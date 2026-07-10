from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

from tests.helpers import db_isolation


pytestmark = [
    pytest.mark.integration,
    pytest.mark.db,
    pytest.mark.requires_postgres,
]

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SCRIPT = ROOT / 'scripts' / 'baseline_migration_ledger.sh'
SQL_DIR = ROOT / 'sql'
BASELINE_THROUGH = '003_functions.sql'
PRE_LEDGER_FILES = [
    '001_schema.sql',
    '002_indexes.sql',
    '003_functions.sql',
]


def test_baseline_migration_ledger_records_existing_preledger_state():
    psycopg2 = pytest.importorskip('psycopg2')
    bash = shutil.which('bash')
    if bash is None:
        pytest.skip('bash is required to execute scripts/baseline_migration_ledger.sh')
    psql = shutil.which('psql')
    if psql is None:
        pytest.skip('psql is required to simulate a pre-ledger database')

    try:
        db_isolation.require_destructive_reset_opt_in(os.environ)
        db_target = db_isolation.target_from_env(os.environ)
    except db_isolation.DbIsolationError as exc:
        pytest.skip(str(exc))

    baseline_db = f'migration_baseline_{uuid.uuid4().hex[:12]}'
    baseline_dsn = _dsn_for_database(db_target.dsn, baseline_db)

    try:
        admin_conn = psycopg2.connect(db_target.dsn)
    except Exception as exc:  # pragma: no cover - explicit local skip path
        pytest.skip(f'disposable Postgres unavailable for baseline runtime test: {exc}')

    admin_conn.autocommit = True
    try:
        with admin_conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{baseline_db}"')
            cur.execute(f'CREATE DATABASE "{baseline_db}"')

        _apply_preledger_schema(psql, baseline_dsn)
        first_run = _run_baseline(bash, baseline_dsn)
        assert first_run.returncode == 0, first_run.stderr or first_run.stdout
        assert 'baseline complete through 003_functions.sql' in first_run.stdout
        assert _count_rows(baseline_dsn, 'schema_migrations') == len(PRE_LEDGER_FILES)
        assert _count_rows(baseline_dsn, 'schema_migration_manual_status') == 0

        second_run = _run_baseline(bash, baseline_dsn)
        assert second_run.returncode != 0
        assert 'ledger already contains 3 rows' in (second_run.stderr or second_run.stdout)
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(
                'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                'WHERE datname = %s AND pid <> pg_backend_pid()',
                (baseline_db,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{baseline_db}"')
        admin_conn.close()


def _apply_preledger_schema(psql: str, database_url: str) -> None:
    for migration in PRE_LEDGER_FILES:
        result = subprocess.run(
            [psql, database_url, '-v', 'ON_ERROR_STOP=1', '-f', str(SQL_DIR / migration)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)


def _run_baseline(bash: str, database_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env['DATABASE_URL'] = database_url
    return subprocess.run(
        [bash, str(BASELINE_SCRIPT), '--baseline-through', BASELINE_THROUGH],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _count_rows(database_url: str, table_name: str) -> int:
    psycopg2 = pytest.importorskip('psycopg2')
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM {table_name}')
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def _dsn_for_database(dsn: str, database: str) -> str:
    parsed = urlsplit(dsn)
    return urlunsplit((parsed.scheme, parsed.netloc, f'/{database}', parsed.query, parsed.fragment))
