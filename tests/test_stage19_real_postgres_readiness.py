import os
from collections.abc import Iterator, Mapping

import pytest

from tests.helpers import db_isolation


pytestmark = [
    pytest.mark.integration,
    pytest.mark.db,
    pytest.mark.operator,
    pytest.mark.requires_postgres,
]

APPROVED_SOURCE_RUN_KEY = 'stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034'
APPROVED_BRIDGE_KEY = f'source_runs:{APPROVED_SOURCE_RUN_KEY}'
APPROVED_ARTIFACT_SHA256 = 'b617d0239b7458b5b881895b564d091c771394b555c88a5bae942fd9d2c10e5e'
PROVENANCE_MARKER_KEY = 'stage19ar_bounded_25_row_pilot'


def db_config(env: Mapping[str, str]) -> dict[str, object]:
    target = db_isolation.target_from_env(env)
    return {
        'database_url': target.dsn,
        'redacted_database_url': target.redacted_dsn,
        'host': target.host,
        'port': target.port,
        'database': target.database,
        'user': target.user,
        'password_present': target.password_present,
        'host_postgres_5432_targeted': target.host_postgres_5432_targeted,
    }


@pytest.fixture(scope='module')
def real_stage19_conn() -> Iterator[object]:
    try:
        config = db_config(os.environ)
    except db_isolation.DbIsolationError as exc:
        pytest.skip(f'real Stage 19 DB readiness skipped explicitly: unsafe_target:{exc}')

    try:
        import psycopg2  # noqa: PLC0415
        import psycopg2.extras  # noqa: PLC0415
    except Exception:
        pytest.skip('real Stage 19 DB readiness skipped explicitly: psycopg2_missing')

    conn = None
    try:
        conn = psycopg2.connect(str(config['database_url']), cursor_factory=psycopg2.extras.RealDictCursor)
        conn.set_session(readonly=True, autocommit=False)
    except Exception as exc:
        if conn is not None:
            conn.close()
        pytest.skip(f'real Stage 19 DB readiness skipped explicitly: {connection_skip_reason(exc)}')

    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_real_stage19_db_readiness_uses_no_fake_fallbacks():
    source = __import__('pathlib').Path(__file__).read_text(encoding='utf-8')

    assert 'Fake' + 'Conn' not in source
    assert 'Fake' + 'Cursor' not in source
    assert '-' + '-commit' not in source
    assert 'psycopg2.connect' in source


def test_real_stage19_db_readiness_select_1_is_read_only(real_stage19_conn):
    with real_stage19_conn.cursor() as cur:
        cur.execute('SHOW transaction_read_only')
        assert cur.fetchone()['transaction_read_only'] == 'on'
        cur.execute('SELECT 1 AS db_readiness_ok')
        assert cur.fetchone()['db_readiness_ok'] == 1
    real_stage19_conn.rollback()


def test_approved_stage19ar_baseline_is_present_in_real_local_postgres(real_stage19_conn):
    with real_stage19_conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, source_run_key, status, artifact_sha256, rows_read, rows_staged, rows_rejected, rows_skipped
            FROM source_runs
            WHERE source_run_key = %s
            """,
            (APPROVED_SOURCE_RUN_KEY,),
        )
        source_run = cur.fetchone()
        if source_run is None:
            pytest.skip(
                'real Stage 19 DB readiness skipped explicitly: '
                'approved_stage19ar_baseline_missing',
            )
        assert source_run['artifact_sha256'] == APPROVED_ARTIFACT_SHA256
        assert source_run['rows_read'] == 25
        assert source_run['rows_staged'] == 25
        assert source_run['rows_rejected'] == 0
        assert source_run['rows_skipped'] == 0

        cur.execute(
            """
            SELECT id, source_run_key
            FROM enrichment_source_runs
            WHERE source_run_key = %s
            """,
            (APPROVED_BRIDGE_KEY,),
        )
        bridge = cur.fetchone()
        assert bridge is not None

        cur.execute(
            """
            SELECT
              COUNT(*)::int AS rows_total,
              COUNT(*) FILTER (WHERE source_class = %s AND confidence = %s)::int AS rows_diagnostic_only,
              COUNT(*) FILTER (WHERE source_run_id = %s)::int AS rows_using_legacy_bridge_id,
              COUNT(*) FILTER (WHERE source_run_id = %s)::int AS rows_using_source_runs_id,
              COUNT(*) FILTER (WHERE provenance ? %s)::int AS rows_with_marker,
              COUNT(*) FILTER (WHERE provenance->>%s = 'false')::int AS rows_with_canonical_write_blocked
            FROM staging_edsm_stations
            WHERE source_run_id = %s
            """,
            (
                'diagnostic-only',
                'diagnostic-only',
                bridge['id'],
                source_run['id'],
                PROVENANCE_MARKER_KEY,
                'canonical_write_allowed',
                bridge['id'],
            ),
        )
        counts = cur.fetchone()

    real_stage19_conn.rollback()
    assert counts == {
        'rows_total': 25,
        'rows_diagnostic_only': 25,
        'rows_using_legacy_bridge_id': 25,
        'rows_using_source_runs_id': 0,
        'rows_with_marker': 25,
        'rows_with_canonical_write_blocked': 25,
    }


def connection_skip_reason(exc: Exception) -> str:
    text = str(exc).lower()
    if 'password authentication failed' in text:
        return 'password_authentication_failed'
    if 'connection refused' in text:
        return 'postgres_unavailable'
    if 'timeout' in text:
        return 'postgres_unavailable'
    if 'could not translate host name' in text or 'name or service not known' in text:
        return 'postgres_unavailable'
    return 'postgres_unavailable'
