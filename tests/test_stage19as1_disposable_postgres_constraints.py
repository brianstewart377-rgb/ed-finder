import json
import re
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from tests.helpers import db_isolation


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = ROOT / 'docs' / 'colonisation-redesign' / 'stage-19-state-authority.json'
SOURCE_RUNS_MIGRATION = ROOT / 'sql' / '029_create_source_runs.sql'
STAGING_MIGRATION = ROOT / 'sql' / '026_enrichment_staging_foundation.sql'
STAGE19AR_SCRIPT = ROOT / 'scripts' / 'operator' / 'stage19ar_edsm_25_row_staging_pilot.py'
STAGE19AS_AU_SCRIPT = ROOT / 'scripts' / 'operator' / 'stage19as_au_edsm_100_row_controlled_expansion.py'

APPROVED_STAGE19AR_SOURCE_RUN_KEY = 'stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034'
APPROVED_STAGE19AR_BRIDGE_KEY = f'source_runs:{APPROVED_STAGE19AR_SOURCE_RUN_KEY}'
APPROVED_STAGE19AR_ARTIFACT_SHA256 = 'b617d0239b7458b5b881895b564d091c771394b555c88a5bae942fd9d2c10e5e'
STAGE19AS_AU_SOURCE_RUN_KEY = 'stage19as-au-edsm-100-row-controlled-expansion-1843ccf903dfa6c9'
STAGE19AS_AU_BRIDGE_KEY = f'source_runs:{STAGE19AS_AU_SOURCE_RUN_KEY}'
STAGE19AS_AU_ARTIFACT_SHA256 = '7f6f20a4d01b543d8ef12072891d8fda749bcc1b6633c26bc9ec178a40b8f84e'
STAGE19AS_AU_MARKER = 'stage19as_au_controlled_100_row_expansion'
HEX_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _normalise_sql(sql: str) -> str:
    return re.sub(r'\s+', ' ', sql).strip()


def _table_sql(migration: str, table_name: str) -> str:
    match = re.search(
        rf'CREATE TABLE IF NOT EXISTS {re.escape(table_name)} \((.*?)\n\);',
        migration,
        flags=re.DOTALL,
    )
    assert match is not None, f'{table_name} table definition missing'
    return match.group(1)


@pytest.mark.unit
def test_stage19as1_authority_keeps_asau_recorded_and_stage19_paused():
    authority = json.loads(_read(AUTHORITY_PATH))

    assert authority['stage19'] == {
        'status': 'paused',
        'stage19as_au_status': 'completed',
    }
    assert authority['approved_stage19ar_baseline'] == {
        'source_run_key': APPROVED_STAGE19AR_SOURCE_RUN_KEY,
        'bridge_key': APPROVED_STAGE19AR_BRIDGE_KEY,
        'artifact': APPROVED_STAGE19AR_ARTIFACT_SHA256,
        'rows': 25,
    }

    checkpoint = authority['stage19as_au_completed_checkpoint']
    assert checkpoint['status'] == 'completed'
    assert checkpoint['safe_db_target'] == '127.0.0.1:55432'
    assert checkpoint['source_run_key'] == STAGE19AS_AU_SOURCE_RUN_KEY
    assert checkpoint['bridge_key'] == STAGE19AS_AU_BRIDGE_KEY
    assert checkpoint['artifact'] == STAGE19AS_AU_ARTIFACT_SHA256
    assert checkpoint['rows_read'] == 100
    assert checkpoint['rows_staged'] == 100
    assert checkpoint['rows_rejected'] == 0
    assert checkpoint['rows_skipped'] == 0
    assert checkpoint['canonical_writes_performed'] is False
    assert checkpoint['approved_stage19ar_baseline_preserved'] is True
    assert checkpoint['stage19_remains_paused'] is True


@pytest.mark.unit
def test_stage19as1_invalid_stage19_states_remain_denylisted():
    authority = json.loads(_read(AUTHORITY_PATH))

    invalid_states = {state['id']: state['status'] for state in authority['invalid_states']}
    assert invalid_states == {
        '45e2d58': 'invalid_partial_rebaseline_never_authority',
        'f72812a': 'docs_only_stopped_checkpoint_not_successful_expansion',
        '8509171250b1449832a7fe3227d87acc02fb015e': 'wrong_branch_unavailable_never_authority',
    }
    assert 'superseded_states' not in authority


@pytest.mark.unit
def test_source_runs_schema_has_stage19as1_required_constraints():
    table = _table_sql(_read(SOURCE_RUNS_MIGRATION), 'source_runs')
    normalised = _normalise_sql(table)

    assert 'source_run_key TEXT NOT NULL UNIQUE' in normalised
    assert 'started_at TIMESTAMPTZ NOT NULL' in normalised
    assert 'artifact_sha256 TEXT DEFAULT NULL' in normalised
    assert 'artifact_integrity_sha256 TEXT DEFAULT NULL' in normalised
    assert "safety_boundary JSONB NOT NULL DEFAULT '{}'::jsonb" in normalised
    assert "metadata JSONB NOT NULL DEFAULT '{}'::jsonb" in normalised

    for constraint_name in (
        'chk_source_runs_source_name',
        'chk_source_runs_source_category',
        'chk_source_runs_domain',
        'chk_source_runs_import_scope',
        'chk_source_runs_status',
        'chk_source_runs_finished_window',
    ):
        assert f'CONSTRAINT {constraint_name}' in table

    for counter in ('rows_read', 'rows_staged', 'rows_rejected', 'rows_skipped'):
        assert f'{counter} BIGINT NOT NULL DEFAULT 0' in normalised
        assert f'CHECK ({counter} >= 0)' in normalised

    assert 'CHECK (finished_at IS NULL OR finished_at >= started_at)' in normalised
    assert "'staging_only'" in table
    assert "'canonical_apply'" in table
    assert "'complete'" not in table
    assert "'done'" not in table
    assert "'error'" not in table


@pytest.mark.unit
def test_staging_schema_keeps_stage19as1_rows_on_legacy_bridge_fk():
    table = _table_sql(_read(STAGING_MIGRATION), 'staging_edsm_stations')
    normalised = _normalise_sql(table)
    migration = _read(STAGING_MIGRATION)

    assert 'source_run_id BIGINT NOT NULL REFERENCES enrichment_source_runs(id) ON DELETE CASCADE' in normalised
    assert 'source_run_id BIGINT NOT NULL REFERENCES source_runs(id)' not in normalised
    assert "'diagnostic-only'" in table
    assert "provenance JSONB NOT NULL DEFAULT '{}'::jsonb" in normalised
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_edsm_stations_run_hash' in migration


@pytest.mark.unit
def test_operator_validation_contract_covers_stage19as1_pilot_path():
    stage19ar_source = _read(STAGE19AR_SCRIPT)
    stage19as_au_source = _read(STAGE19AS_AU_SCRIPT)

    for fragment in (
        'staging_rows_use_legacy_bridge_id',
        'staging_rows_do_not_use_source_runs_id',
        'staging_rows_preserve_canonical_write_block',
        'source_run_artifact_hash_matches',
        'source_run_artifact_integrity_matches',
        "'canonical_table_writes_performed_by_script': False",
    ):
        assert fragment in stage19ar_source

    assert 'allowed_false = {\'canonical_table_writes_performed_by_script\'}' in stage19ar_source
    assert 'if checks.get(\'canonical_table_writes_performed_by_script\') is not False' in stage19ar_source
    assert "source_run_prefixes=('stage19as-au-', 'stage-19as-au-')" in stage19as_au_source
    assert "provenance_marker_key='stage19as_au_controlled_100_row_expansion'" in stage19as_au_source
    assert "hard_max_limit=100" in stage19as_au_source


def _db_config(env: Mapping[str, str]) -> dict[str, object]:
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
def readonly_stage19as1_conn() -> Iterator[object]:
    import os

    try:
        config = _db_config(os.environ)
    except db_isolation.DbIsolationError as exc:
        pytest.skip(f'Stage 19AS.1 disposable Postgres checks skipped: unsafe_target:{exc}')

    try:
        import psycopg2  # noqa: PLC0415
        import psycopg2.extras  # noqa: PLC0415
    except Exception:
        pytest.skip('Stage 19AS.1 disposable Postgres checks skipped: psycopg2_missing')

    conn = None
    try:
        conn = psycopg2.connect(str(config['database_url']), cursor_factory=psycopg2.extras.RealDictCursor)
        conn.set_session(readonly=True, autocommit=False)
    except Exception as exc:
        if conn is not None:
            conn.close()
        pytest.skip(f'Stage 19AS.1 disposable Postgres checks skipped: {type(exc).__name__}')

    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.operator
@pytest.mark.requires_postgres
def test_stage19as1_real_local_postgres_checkpoint_is_readonly_and_isolated(readonly_stage19as1_conn):
    with readonly_stage19as1_conn.cursor() as cur:
        cur.execute('SHOW transaction_read_only')
        assert cur.fetchone()['transaction_read_only'] == 'on'

        cur.execute(
            """
            SELECT
              id,
              source_run_key,
              status,
              artifact_sha256,
              artifact_integrity_sha256,
              rows_read,
              rows_staged,
              rows_rejected,
              rows_skipped
            FROM source_runs
            WHERE source_run_key = %s
            """,
            (STAGE19AS_AU_SOURCE_RUN_KEY,),
        )
        source_run = cur.fetchone()
        assert source_run is not None
        assert source_run['status'] == 'succeeded'
        assert source_run['artifact_sha256'] == STAGE19AS_AU_ARTIFACT_SHA256
        assert HEX_SHA256_RE.match(source_run['artifact_integrity_sha256'])
        assert source_run['rows_read'] == 100
        assert source_run['rows_staged'] == 100
        assert source_run['rows_rejected'] == 0
        assert source_run['rows_skipped'] == 0

        cur.execute(
            """
            SELECT id, source_run_key
            FROM enrichment_source_runs
            WHERE source_run_key = %s
            """,
            (STAGE19AS_AU_BRIDGE_KEY,),
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
              COUNT(*) FILTER (WHERE provenance ? %s)::int AS rows_with_stage19as_au_marker,
              COUNT(*) FILTER (WHERE provenance->>%s = 'false')::int AS rows_with_canonical_write_blocked
            FROM staging_edsm_stations
            WHERE source_run_id = %s
            """,
            (
                'diagnostic-only',
                'diagnostic-only',
                bridge['id'],
                source_run['id'],
                STAGE19AS_AU_MARKER,
                'canonical_write_allowed',
                bridge['id'],
            ),
        )
        counts = cur.fetchone()

    readonly_stage19as1_conn.rollback()
    assert counts == {
        'rows_total': 100,
        'rows_diagnostic_only': 100,
        'rows_using_legacy_bridge_id': 100,
        'rows_using_source_runs_id': 0,
        'rows_with_stage19as_au_marker': 100,
        'rows_with_canonical_write_blocked': 100,
    }
