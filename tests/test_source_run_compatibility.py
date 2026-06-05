import inspect
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import source_run_compatibility as compat  # noqa: E402


STARTED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
FINISHED = datetime(2026, 1, 2, 3, 5, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.closed = False
        self.last_result = None

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.conn.statements.append((sql, params))
        compact = ' '.join(sql.lower().split())

        if compact.startswith('select') and 'from enrichment_source_runs' in compact:
            self.last_result = self.conn.existing_rows.get(params[0])
            return

        if compact.startswith('insert into enrichment_source_runs'):
            self.conn.next_id += 1
            row = {
                'id': self.conn.next_id,
                'source_run_key': params[0],
                'source': params[1],
                'adapter_name': params[2],
                'adapter_version': params[3],
                'source_kind': params[4],
                'source_class': params[5],
                'run_label': params[6],
                'dry_run': params[7],
                'source_started_at': params[8],
                'source_completed_at': params[9],
                'metadata': json.loads(params[10]),
            }
            self.conn.existing_rows[params[0]] = row
            self.last_result = row
            return

        raise AssertionError(f'unexpected SQL: {sql}')

    def fetchone(self):
        return self.last_result

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self, *, existing_rows=None):
        self.statements = []
        self.cursors = []
        self.next_id = 700
        self.existing_rows = dict(existing_rows or {})

    def cursor(self):
        cur = FakeCursor(self)
        self.cursors.append(cur)
        return cur


def source_run_row(**overrides):
    row = {
        'id': 101,
        'source_run_key': 'stage-19t-run',
        'source_name': 'edsm',
        'source_category': 'source_of_evidence',
        'domain': 'stations',
        'import_scope': 'staging_only',
        'status': 'succeeded',
        'source_uri': 'file:///tmp/edsm-stations.json',
        'source_input_sha256': 'a' * 64,
        'source_manifest_sha256': None,
        'started_at': STARTED,
        'finished_at': FINISHED,
        'git_commit_sha': 'abc1234',
        'importer_name': 'stage_19t_edsm_station_import_mvp',
        'importer_version': 'v1',
        'trigger_context': 'unit_test',
        'artifact_path': 'artifacts/stage-19t.json',
        'artifact_sha256': 'b' * 64,
        'artifact_integrity_sha256': 'c' * 64,
        'safety_boundary': {
            'canonical_writes_planned': 0,
            'canonical_apply_enabled': False,
        },
        'metadata': {
            'stage': '19t',
            'source_adapter': 'edsm_nightly_stations',
        },
    }
    row.update(overrides)
    return row


def test_build_enrichment_source_run_key_is_deterministic_and_namespaced():
    assert compat.build_enrichment_source_run_key('stage-19t-run') == 'source_runs:stage-19t-run'
    assert compat.build_enrichment_source_run_key(source_run_row()) == 'source_runs:stage-19t-run'

    with pytest.raises(compat.SourceRunCompatibilityError, match='source_run_key is required'):
        compat.build_enrichment_source_run_key('')


def test_build_enrichment_source_run_row_maps_source_runs_metadata_to_legacy_columns():
    row = compat.build_enrichment_source_run_row(source_run_row())

    assert row['source_run_key'] == 'source_runs:stage-19t-run'
    assert row['source'] == 'edsm'
    assert row['adapter_name'] == 'stage_19t_edsm_station_import_mvp'
    assert row['adapter_version'] == 'v1'
    assert row['source_kind'] == 'offline_snapshot'
    assert row['source_class'] == 'semi-stable'
    assert row['run_label'] == 'stage-19t-run'
    assert row['dry_run'] is True
    assert row['source_started_at'] == STARTED
    assert row['source_completed_at'] == FINISHED

    metadata = row['metadata']
    assert metadata['schema_version'] == compat.BRIDGE_SCHEMA_VERSION
    assert metadata['compatibility_bridge'] is True
    assert metadata['new_source_run_table'] == 'source_runs'
    assert metadata['legacy_source_run_table'] == 'enrichment_source_runs'
    assert metadata['target_staging_fk'] == 'enrichment_source_runs(id)'
    assert metadata['source_runs_provenance']['id'] == 101
    assert metadata['source_runs_provenance']['source_run_key'] == 'stage-19t-run'
    assert metadata['source_runs_provenance']['source_uri'] == 'file:///tmp/edsm-stations.json'
    assert metadata['source_runs_provenance']['source_input_sha256'] == 'a' * 64
    assert metadata['source_runs_provenance']['artifact_path'] == 'artifacts/stage-19t.json'
    assert metadata['source_runs_provenance']['artifact_sha256'] == 'b' * 64
    assert metadata['source_runs_provenance']['artifact_integrity_sha256'] == 'c' * 64
    assert metadata['source_runs_provenance']['trigger_context'] == 'unit_test'
    assert metadata['source_runs_provenance']['domain'] == 'stations'
    assert metadata['source_runs_provenance']['import_scope'] == 'staging_only'
    assert metadata['source_runs_provenance']['safety_boundary']['canonical_writes_planned'] == 0
    assert metadata['staging_policy']['do_not_pass_source_runs_id_to_legacy_staging_source_run_id'] is True
    assert metadata['staging_policy']['staging_rows_written_by_this_helper'] is False


def test_build_enrichment_source_run_row_allows_explicit_staging_write_overrides():
    row = compat.build_enrichment_source_run_row(
        source_run_row(),
        source='edsm_nightly_stations',
        adapter_name='explicit_compatible_stager',
        adapter_version='v2',
        source_kind='offline_snapshot',
        source_class='volatile',
        run_label='operator-run-label',
        dry_run=False,
        metadata={'operator_note': 'real staging write approved elsewhere'},
    )

    assert row['source'] == 'edsm_nightly_stations'
    assert row['adapter_name'] == 'explicit_compatible_stager'
    assert row['adapter_version'] == 'v2'
    assert row['source_class'] == 'volatile'
    assert row['run_label'] == 'operator-run-label'
    assert row['dry_run'] is False
    assert row['metadata']['operator_note'] == 'real staging write approved elsewhere'


def test_create_enrichment_source_run_for_source_run_upserts_legacy_row():
    conn = FakeConn()

    row = compat.create_enrichment_source_run_for_source_run(conn, source_run_row())

    assert row['id'] == 701
    assert row['source_run_key'] == 'source_runs:stage-19t-run'
    assert row['source'] == 'edsm'
    assert row['adapter_name'] == 'stage_19t_edsm_station_import_mvp'
    assert row['metadata']['compatibility_bridge'] is True
    sql, params = conn.statements[0]
    assert 'INSERT INTO enrichment_source_runs' in sql
    assert 'ON CONFLICT (source_run_key)' in sql
    assert 'RETURNING' in sql
    assert params[:8] == (
        'source_runs:stage-19t-run',
        'edsm',
        'stage_19t_edsm_station_import_mvp',
        'v1',
        'offline_snapshot',
        'semi-stable',
        'stage-19t-run',
        True,
    )
    assert params[8] == STARTED
    assert params[9] == FINISHED
    metadata = json.loads(params[10])
    assert metadata['target_staging_fk'] == 'enrichment_source_runs(id)'
    assert_only_compat_sql(conn)


def test_get_or_create_returns_existing_row_without_insert_for_idempotency():
    existing = {
        'id': 777,
        'source_run_key': 'source_runs:stage-19t-run',
        'source': 'edsm',
        'adapter_name': 'stage_19t_edsm_station_import_mvp',
        'adapter_version': 'v1',
        'source_kind': 'offline_snapshot',
        'source_class': 'semi-stable',
        'run_label': 'stage-19t-run',
        'dry_run': True,
        'source_started_at': STARTED,
        'source_completed_at': FINISHED,
        'metadata': {'compatibility_bridge': True},
    }
    conn = FakeConn(existing_rows={'source_runs:stage-19t-run': existing})

    row = compat.get_or_create_enrichment_source_run_for_source_run(conn, source_run_row())

    assert row == existing
    assert len(conn.statements) == 1
    assert 'SELECT' in conn.statements[0][0]
    assert 'FROM enrichment_source_runs' in conn.statements[0][0]
    assert_only_compat_sql(conn)


def test_get_or_create_inserts_when_bridge_row_is_absent():
    conn = FakeConn()

    row = compat.get_or_create_enrichment_source_run_for_source_run(conn, source_run_row())

    assert row['id'] == 701
    assert [statement[0].lstrip().split()[0].upper() for statement in conn.statements] == ['SELECT', 'INSERT']
    assert_only_compat_sql(conn)


def test_build_legacy_staging_context_exposes_legacy_fk_id():
    source_run = source_run_row()
    enrichment_source_run = {
        'id': 888,
        'source_run_key': 'source_runs:stage-19t-run',
        'source': 'edsm',
    }

    context = compat.build_legacy_staging_context(
        source_run=source_run,
        enrichment_source_run=enrichment_source_run,
    )

    assert context['source_run'] == source_run
    assert context['enrichment_source_run'] == enrichment_source_run
    assert context['legacy_source_run_id'] == 888
    assert context['target_staging_fk'] == 'enrichment_source_runs(id)'


def test_get_or_create_legacy_staging_context_creates_row_and_returns_fk_context():
    conn = FakeConn()

    context = compat.get_or_create_legacy_staging_context(conn, source_run_row())

    assert context['legacy_source_run_id'] == 701
    assert context['target_staging_fk'] == 'enrichment_source_runs(id)'
    assert context['enrichment_source_run']['source_run_key'] == 'source_runs:stage-19t-run'
    assert_only_compat_sql(conn)


def test_helper_rejects_invalid_source_class_before_db_write():
    conn = FakeConn()

    with pytest.raises(compat.SourceRunCompatibilityError, match='invalid source_class'):
        compat.create_enrichment_source_run_for_source_run(
            conn,
            source_run_row(),
            source_class='canonical',
        )

    assert conn.statements == []


def test_source_run_compatibility_helper_has_no_prod_db_scheduler_import_or_canonical_fragments():
    source = inspect.getsource(compat)
    source_upper = source.upper()
    forbidden_fragments = (
        'PSYCOPG2.CONNECT',
        'ASYNCPG.CONNECT',
        'SUBPROCESS',
        'OS.SYSTEM',
        'SYSTEMCTL',
        'RUN_IMPORT',
        'RUN_IMPORT.SH',
        'DATABASE' + '_URL',
        'POSTGRESQL' + '://',
        'POSTGRES' + '://',
        'PASSWORD' + '=',
        'SECRET',
        'TOKEN' + '=',
        'CANONICAL APPLY',
    )
    for fragment in forbidden_fragments:
        assert fragment not in source_upper
    assert re.search(r'(?<![a-z0-9_])\.timer(?![a-z0-9_])', source, flags=re.IGNORECASE) is None
    assert re.search(r'(?<![a-z0-9_])\.service(?![a-z0-9_])', source, flags=re.IGNORECASE) is None

    forbidden_write_patterns = (
        r'\binsert\s+into\s+staging_[a-z0-9_]+\b',
        r'\bupdate\s+staging_[a-z0-9_]+\b',
        r'\bdelete\s+from\s+staging_[a-z0-9_]+\b',
        r'\binsert\s+into\s+(stations|systems|bodies|body_rings|station_body_links|station_external_identity)\b',
        r'\bupdate\s+(stations|systems|bodies|body_rings|station_body_links|station_external_identity)\b',
        r'\bdelete\s+from\s+(stations|systems|bodies|body_rings|station_body_links|station_external_identity)\b',
    )
    for pattern in forbidden_write_patterns:
        assert re.search(pattern, source, flags=re.IGNORECASE) is None


def assert_only_compat_sql(conn):
    assert conn.statements
    allowed = {'enrichment_source_runs'}
    forbidden_write_tables = (
        'stations',
        'systems',
        'bodies',
        'body_rings',
        'station_body_links',
        'station_external_identity',
    )
    for sql, _params in conn.statements:
        compact = ' '.join(sql.lower().split())
        referenced = {
            match.group(1).replace('"', '').split('.')[-1].lower()
            for match in re.finditer(
                r'\b(?:from|into|update)\s+(?:only\s+)?("?[\w]+"?(?:\."?[\w]+"?)?)',
                sql,
                flags=re.IGNORECASE,
            )
        }
        referenced.discard('set')
        assert referenced <= allowed
        assert re.search(
            r'\b(insert\s+into|update|delete\s+from)\s+staging_[a-z0-9_]+\b',
            compact,
        ) is None
        for table in forbidden_write_tables:
            assert re.search(rf'\b(insert\s+into|update|delete\s+from)\s+{table}\b', compact) is None
