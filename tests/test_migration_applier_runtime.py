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
APPLY_MIGRATIONS = ROOT / 'scripts' / 'apply_migrations.sh'
MANIFEST = ROOT / 'sql' / 'migration-manifest.txt'
MANUAL_MIGRATION = '019_nullable_coords.sql'


def test_apply_migrations_uses_ledger_to_skip_replay_on_second_run():
    psycopg2 = pytest.importorskip('psycopg2')
    bash = shutil.which('bash')
    if bash is None:
        pytest.skip('bash is required to execute scripts/apply_migrations.sh')

    try:
        db_isolation.require_destructive_reset_opt_in(os.environ)
        db_target = db_isolation.target_from_env(os.environ)
    except db_isolation.DbIsolationError as exc:
        pytest.skip(str(exc))

    auto_migrations = _manifest_entries(include_manual=False)
    expected_auto_count = len(auto_migrations)
    rehearsal_db = f'migration_ledger_{uuid.uuid4().hex[:12]}'
    rehearsal_dsn = _dsn_for_database(db_target.dsn, rehearsal_db)

    try:
        admin_conn = psycopg2.connect(db_target.dsn)
    except Exception as exc:  # pragma: no cover - explicit local skip path
        pytest.skip(f'disposable Postgres unavailable for migration runtime test: {exc}')

    admin_conn.autocommit = True
    try:
        with admin_conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{rehearsal_db}"')
            cur.execute(f'CREATE DATABASE "{rehearsal_db}"')

        first_run = _run_applier(bash, rehearsal_dsn)
        assert first_run.returncode == 0, first_run.stderr or first_run.stdout
        assert f'[INFO] skipping manual migration {MANUAL_MIGRATION}' in first_run.stdout
        assert _schema_migration_count(rehearsal_dsn) == expected_auto_count
        assert _has_migration(rehearsal_dsn, MANUAL_MIGRATION) is False

        second_run = _run_applier(bash, rehearsal_dsn)
        assert second_run.returncode == 0, second_run.stderr or second_run.stdout
        assert '[INFO] already applied 001_schema.sql' in second_run.stdout
        assert _schema_migration_count(rehearsal_dsn) == expected_auto_count
        assert _has_migration(rehearsal_dsn, MANUAL_MIGRATION) is False

        manual_run = _run_applier(bash, rehearsal_dsn, '--include-manual')
        assert manual_run.returncode == 0, manual_run.stderr or manual_run.stdout
        assert f'[INFO] applying {MANUAL_MIGRATION}' in manual_run.stdout
        assert _schema_migration_count(rehearsal_dsn) == expected_auto_count + 1
        assert _has_migration(rehearsal_dsn, MANUAL_MIGRATION) is True
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(
                'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                'WHERE datname = %s AND pid <> pg_backend_pid()',
                (rehearsal_db,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{rehearsal_db}"')
        admin_conn.close()


def _run_applier(bash: str, database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env['DATABASE_URL'] = database_url
    return subprocess.run(
        [bash, str(APPLY_MIGRATIONS), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _manifest_entries(*, include_manual: bool) -> list[str]:
    entries: list[str] = []
    for raw_line in MANIFEST.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        filename, _, mode = line.partition('|')
        if mode.strip() == 'manual' and not include_manual:
            continue
        entries.append(filename.strip())
    return entries


def _schema_migration_count(database_url: str) -> int:
    psycopg2 = pytest.importorskip('psycopg2')
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM schema_migrations')
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def _has_migration(database_url: str, filename: str) -> bool:
    psycopg2 = pytest.importorskip('psycopg2')
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE filename = %s)',
                (filename,),
            )
            return bool(cur.fetchone()[0])
    finally:
        conn.close()


def _dsn_for_database(dsn: str, database: str) -> str:
    parsed = urlsplit(dsn)
    return urlunsplit((parsed.scheme, parsed.netloc, f'/{database}', parsed.query, parsed.fragment))
