from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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
APPLY_SCRIPT = ROOT / 'scripts' / 'apply_migrations.sh'
REPAIR_BODY_CONTRACT = ROOT / 'scripts' / 'repair_body_contract.py'
RECONCILE_NO_BODY_RATINGS = ROOT / 'scripts' / 'reconcile_no_body_ratings.py'
REPAIR_STATION_BODY_LINKS = ROOT / 'scripts' / 'repair_station_body_links.py'
DATA_INVARIANTS = ROOT / 'scripts' / 'checks' / 'data_invariants.py'
DATA_TRUST_HEALTH_SNAPSHOT = ROOT / 'scripts' / 'checks' / 'data_trust_health_snapshot.py'


def test_body_contract_repair_and_reconcile_restore_clean_invariants():
    psycopg2 = pytest.importorskip('psycopg2')
    bash = shutil.which('bash')
    psql = shutil.which('psql')
    if bash is None or psql is None:
        pytest.skip('bash and psql are required to apply schema migrations for runtime trust tests')

    try:
        db_isolation.require_destructive_reset_opt_in(os.environ)
        db_target = db_isolation.target_from_env(os.environ)
    except db_isolation.DbIsolationError as exc:
        pytest.skip(str(exc))

    runtime_db = f'data_trust_body_{uuid.uuid4().hex[:12]}'
    runtime_dsn = _dsn_for_database(db_target.dsn, runtime_db)

    try:
        admin_conn = psycopg2.connect(db_target.dsn)
    except Exception as exc:  # pragma: no cover - explicit local skip path
        pytest.skip(f'disposable Postgres unavailable for data trust runtime test: {exc}')

    admin_conn.autocommit = True
    try:
        with admin_conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{runtime_db}"')
            cur.execute(f'CREATE DATABASE "{runtime_db}"')

        _apply_schema_via_migrations(bash, runtime_dsn)
        _exec_sql(
            runtime_dsn,
            """
            INSERT INTO systems (
              id64, name, x, y, z, population,
              has_body_data, body_count, rating_dirty, cluster_dirty
            )
            VALUES (4201, 'Runtime Body Drift', 1, 2, 3, NULL, TRUE, 0, FALSE, FALSE);

            INSERT INTO ratings (system_id64, score, rating_version)
            VALUES (4201, 77, '3.4');
            """,
        )

        before = _run_python(
            DATA_INVARIANTS,
            '--database-url',
            runtime_dsn,
            '--target-rating-version',
            '3.4',
        )
        assert before.returncode == 1
        assert 'FAIL: stored systems body-data flags/counts drift from actual bodies rows' in before.stderr

        repair = _run_python(
            REPAIR_BODY_CONTRACT,
            '--dsn',
            runtime_dsn,
            '--apply',
            '--skip-summary',
            '--focus',
            'missing-bodies-only',
            '--json',
        )
        assert repair.returncode == 0, repair.stderr
        repair_report = json.loads(repair.stdout)
        assert repair_report['summary_skipped'] is True
        assert repair_report['before']['total_mismatches'] is None
        assert repair_report['after']['total_mismatches'] is None
        assert repair_report['updated'] == 1

        reconcile = _run_python(
            RECONCILE_NO_BODY_RATINGS,
            '--dsn',
            runtime_dsn,
            '--apply',
            '--batch-size',
            '100',
            '--json',
        )
        assert reconcile.returncode == 0, reconcile.stderr
        reconcile_report = json.loads(reconcile.stdout)
        assert reconcile_report['reconciled'] == 1
        assert reconcile_report['deleted_ratings'] == 1
        assert reconcile_report['cleared_dirty'] == 1
        assert reconcile_report['after']['total_candidates'] == 0

        after = _run_python(
            DATA_INVARIANTS,
            '--database-url',
            runtime_dsn,
            '--target-rating-version',
            '3.4',
        )
        assert after.returncode == 0, after.stderr
        assert 'PASS: checked invariants satisfied' in after.stdout

        with psycopg2.connect(runtime_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT has_body_data, body_count, rating_dirty, cluster_dirty
                FROM systems
                WHERE id64 = 4201
                """
            )
            assert cur.fetchone() == (False, 0, False, True)
            cur.execute('SELECT COUNT(*) FROM ratings WHERE system_id64 = 4201')
            assert cur.fetchone()[0] == 0
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(
                'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                'WHERE datname = %s AND pid <> pg_backend_pid()',
                (runtime_db,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{runtime_db}"')
        admin_conn.close()


def test_body_contract_skip_summary_requires_apply():
    result = _run_python(REPAIR_BODY_CONTRACT, '--dsn', 'postgresql://example.invalid/db', '--skip-summary')
    assert result.returncode != 0
    assert '--skip-summary requires --apply' in result.stderr


def test_data_invariants_production_safe_mode_skips_heavy_scans_but_catches_drift():
    psycopg2 = pytest.importorskip('psycopg2')
    bash = shutil.which('bash')
    psql = shutil.which('psql')
    if bash is None or psql is None:
        pytest.skip('bash and psql are required to apply schema migrations for runtime trust tests')

    try:
        db_isolation.require_destructive_reset_opt_in(os.environ)
        db_target = db_isolation.target_from_env(os.environ)
    except db_isolation.DbIsolationError as exc:
        pytest.skip(str(exc))

    runtime_db = f'data_trust_safe_{uuid.uuid4().hex[:12]}'
    runtime_dsn = _dsn_for_database(db_target.dsn, runtime_db)

    try:
        admin_conn = psycopg2.connect(db_target.dsn)
    except Exception as exc:  # pragma: no cover - explicit local skip path
        pytest.skip(f'disposable Postgres unavailable for production-safe invariant test: {exc}')

    admin_conn.autocommit = True
    try:
        with admin_conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{runtime_db}"')
            cur.execute(f'CREATE DATABASE "{runtime_db}"')

        _apply_schema_via_migrations(bash, runtime_dsn)
        _exec_sql(
            runtime_dsn,
            """
            INSERT INTO systems (
              id64, name, x, y, z, population,
              has_body_data, body_count, rating_dirty, cluster_dirty
            )
            VALUES (4301, 'Runtime Safe Drift', 1, 2, 3, NULL, FALSE, 1, FALSE, FALSE);
            """,
        )

        result = _run_python(
            DATA_INVARIANTS,
            '--database-url',
            runtime_dsn,
            '--production-safe',
            '--allow-stale-noneligible',
        )
        assert result.returncode == 1
        assert 'FAIL: stored systems body-data flags/counts drift from actual bodies rows' in result.stderr
        assert 'Query profile             : production-safe' in result.stdout
        assert 'Eligible systems rated    : skipped' in result.stdout
        assert 'Body count mismatches     : skipped' in result.stdout
        assert 'Stale clean ratings       : skipped' in result.stdout
        assert 'Missing body flag rows    : 1' in result.stdout
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(
                'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                'WHERE datname = %s AND pid <> pg_backend_pid()',
                (runtime_db,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{runtime_db}"')
        admin_conn.close()


def test_station_body_link_repair_restores_clean_invariants():
    psycopg2 = pytest.importorskip('psycopg2')
    bash = shutil.which('bash')
    psql = shutil.which('psql')
    if bash is None or psql is None:
        pytest.skip('bash and psql are required to apply schema migrations for runtime trust tests')

    try:
        db_isolation.require_destructive_reset_opt_in(os.environ)
        db_target = db_isolation.target_from_env(os.environ)
    except db_isolation.DbIsolationError as exc:
        pytest.skip(str(exc))

    runtime_db = f'data_trust_link_{uuid.uuid4().hex[:12]}'
    runtime_dsn = _dsn_for_database(db_target.dsn, runtime_db)

    try:
        admin_conn = psycopg2.connect(db_target.dsn)
    except Exception as exc:  # pragma: no cover - explicit local skip path
        pytest.skip(f'disposable Postgres unavailable for data trust runtime test: {exc}')

    admin_conn.autocommit = True
    try:
        with admin_conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{runtime_db}"')
            cur.execute(f'CREATE DATABASE "{runtime_db}"')

        _apply_schema_via_migrations(bash, runtime_dsn)
        _exec_sql(
            runtime_dsn,
            """
            INSERT INTO systems (
              id64, name, x, y, z, population,
              has_body_data, body_count, rating_dirty, cluster_dirty
            )
            VALUES
              (5201, 'Runtime Link Drift', 1, 2, 3, NULL, TRUE, 1, FALSE, FALSE),
              (9999, 'Wrong System', 9, 9, 9, NULL, FALSE, 0, FALSE, FALSE);

            INSERT INTO bodies (id, system_id64, name, body_type)
            VALUES (6201, 5201, 'Runtime Link Drift 1', 'Planet');

            INSERT INTO stations (id, system_id64, name, station_type)
            VALUES (7201, 5201, 'Runtime Port', 'Coriolis');

            -- Seed legacy drift past migration 034's write-time repair guard.
            SET LOCAL session_replication_role = replica;

            INSERT INTO station_body_links (
              station_id,
              market_id,
              system_id64,
              body_id,
              body_name,
              lane,
              association_status,
              association_confidence,
              association_source,
              resolver_notes
            )
            VALUES (
              7201,
              7201,
              9999,
              6201,
              'Stale Body Name',
              'orbital',
              'confirmed',
              'strong_inference',
              'manual',
              'curated'
            );
            """,
        )

        before = _run_python(
            DATA_INVARIANTS,
            '--database-url',
            runtime_dsn,
            '--allow-unrated-eligible',
        )
        assert before.returncode == 1
        assert 'FAIL: stored station_body_links rows drift from canonical station/body truth' in before.stderr

        repair = _run_python(
            REPAIR_STATION_BODY_LINKS,
            '--dsn',
            runtime_dsn,
            '--apply',
            '--json',
        )
        assert repair.returncode == 0, repair.stderr
        repair_report = json.loads(repair.stdout)
        assert repair_report['updated'] == 1
        assert repair_report['after']['total_mismatches'] == 0

        after = _run_python(
            DATA_INVARIANTS,
            '--database-url',
            runtime_dsn,
            '--allow-unrated-eligible',
        )
        assert after.returncode == 0, after.stderr
        assert 'PASS: checked invariants satisfied' in after.stdout

        with psycopg2.connect(runtime_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT system_id64, body_id, body_name, association_status,
                       association_confidence, association_source
                FROM station_body_links
                WHERE station_id = 7201
                """
            )
            assert cur.fetchone() == (
                5201,
                6201,
                'Runtime Link Drift 1',
                'confirmed',
                'exact',
                'manual',
            )
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(
                'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                'WHERE datname = %s AND pid <> pg_backend_pid()',
                (runtime_db,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{runtime_db}"')
        admin_conn.close()


def test_data_trust_health_snapshot_reports_runtime_drift_buckets():
    psycopg2 = pytest.importorskip('psycopg2')
    bash = shutil.which('bash')
    psql = shutil.which('psql')
    if bash is None or psql is None:
        pytest.skip('bash and psql are required to apply schema migrations for runtime trust tests')

    try:
        db_isolation.require_destructive_reset_opt_in(os.environ)
        db_target = db_isolation.target_from_env(os.environ)
    except db_isolation.DbIsolationError as exc:
        pytest.skip(str(exc))

    runtime_db = f'data_trust_snapshot_{uuid.uuid4().hex[:12]}'
    runtime_dsn = _dsn_for_database(db_target.dsn, runtime_db)

    try:
        admin_conn = psycopg2.connect(db_target.dsn)
    except Exception as exc:  # pragma: no cover - explicit local skip path
        pytest.skip(f'disposable Postgres unavailable for health snapshot runtime test: {exc}')

    admin_conn.autocommit = True
    try:
        with admin_conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{runtime_db}"')
            cur.execute(f'CREATE DATABASE "{runtime_db}"')

        _apply_schema_via_migrations(bash, runtime_dsn)
        _exec_sql(
            runtime_dsn,
            """
            INSERT INTO systems (
              id64, name, x, y, z, population,
              has_body_data, body_count, rating_dirty, cluster_dirty
            )
            VALUES
              (6101, 'Snapshot Flagged Zero', 1, 2, 3, NULL, TRUE, 0, TRUE, FALSE),
              (6102, 'Snapshot Unflagged Positive', 4, 5, 6, NULL, FALSE, 2, TRUE, FALSE),
              (6103, 'Snapshot Truthful No Body', 7, 8, 9, NULL, FALSE, 0, TRUE, FALSE),
              (6104, 'Snapshot Eligible', 10, 11, 12, NULL, TRUE, 1, TRUE, FALSE),
              (6999, 'Snapshot Wrong Link System', 13, 14, 15, NULL, FALSE, 0, FALSE, FALSE);

            INSERT INTO bodies (id, system_id64, name, body_type)
            VALUES
              (7102, 6102, 'Snapshot Unflagged Positive 1', 'Planet'),
              (7104, 6104, 'Snapshot Eligible 1', 'Planet');

            -- Recreate legacy systems/body drift after the body trigger repairs it.
            UPDATE systems
               SET has_body_data = FALSE,
                   body_count = 2
             WHERE id64 = 6102;

            INSERT INTO ratings (system_id64, score, rating_version)
            VALUES
              (6101, 11, '3.4'),
              (6104, 44, '3.4');

            INSERT INTO body_rings (
              system_id64,
              body_id,
              source_body_id,
              body_name,
              ring_name,
              ring_type,
              ring_class,
              source,
              confidence,
              association_status
            )
            VALUES (
              6104,
              7104,
              9104,
              'Wrong Snapshot Body Name',
              'Snapshot Eligible 1 A Ring',
              'Metal Rich',
              'A',
              'eddn_scan',
              'measured',
              'local_matched'
            );

            INSERT INTO stations (id, system_id64, name, station_type)
            VALUES (8104, 6104, 'Snapshot Port', 'Coriolis');

            -- The snapshot must observe impossible legacy drift that new writes reject.
            SET LOCAL session_replication_role = replica;

            INSERT INTO station_body_links (
              station_id,
              market_id,
              system_id64,
              body_id,
              body_name,
              lane,
              association_status,
              association_confidence,
              association_source,
              resolver_notes
            )
            VALUES (
              8104,
              8104,
              6999,
              7104,
              'Wrong Snapshot Body Name',
              'unknown',
              'confirmed',
              'strong_inference',
              'manual',
              'runtime drift fixture'
            );
            """,
        )

        result = _run_python(
            DATA_TRUST_HEALTH_SNAPSHOT,
            '--database-url',
            runtime_dsn,
            '--json',
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)

        assert report['body_contract_and_dirty_tail'] == {
            'dirty_eligible_body_backed': 1,
            'dirty_rows': 4,
            'dirty_truthful_no_bodies': 1,
            'dirty_with_rating': 2,
            'dirty_without_rating': 2,
            'flagged_but_zero_count': 1,
            'unflagged_but_positive_count': 1,
        }
        assert report['ring_status'] == {'ring_status_drift': 1}
        assert report['station_links'] == {
            'confirmed_links_no_body': 0,
            'confirmed_nonexact': 1,
            'confirmed_unknown_lane': 1,
            'link_body_name_drift': 1,
            'link_body_system_drift': 1,
            'link_station_system_drift': 1,
        }
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(
                'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                'WHERE datname = %s AND pid <> pg_backend_pid()',
                (runtime_db,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{runtime_db}"')
        admin_conn.close()


def _apply_schema_via_migrations(bash: str, database_url: str) -> None:
    env = os.environ.copy()
    env['DATABASE_URL'] = database_url
    result = subprocess.run(
        [bash, str(APPLY_SCRIPT), '--include-manual'],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)


def _exec_sql(database_url: str, sql: str) -> None:
    psycopg2 = pytest.importorskip('psycopg2')
    with psycopg2.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(sql)


def _run_python(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _dsn_for_database(dsn: str, database: str) -> str:
    parsed = urlsplit(dsn)
    return urlunsplit((parsed.scheme, parsed.netloc, f'/{database}', parsed.query, parsed.fragment))
