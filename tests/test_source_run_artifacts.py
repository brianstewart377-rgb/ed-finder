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

import artifact_utils  # noqa: E402
import source_run_artifacts as artifacts  # noqa: E402


NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.last_result = None
        self.closed = False

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.conn.statements.append((sql, params))
        normalised = ' '.join(sql.lower().split())

        if normalised.startswith('insert into source_runs'):
            self.conn.next_id += 1
            self.last_result = {
                'id': self.conn.next_id,
                'source_run_key': params[0],
                'status': params[5],
            }
            return

        if normalised.startswith('update source_runs'):
            self.conn.next_id += 1
            self.last_result = {
                'id': self.conn.next_id,
                'source_run_key': self.conn.transition_key,
                'status': params[0],
            }
            return

        raise AssertionError(f'unexpected SQL: {sql}')

    def fetchone(self):
        return self.last_result

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self):
        self.statements = []
        self.cursors = []
        self.next_id = 100
        self.transition_key = 'stage-19r-run'

    def cursor(self):
        cursor = FakeCursor(self)
        self.cursors.append(cursor)
        return cursor


def valid_source_run_kwargs():
    return {
        'source_run_key': 'stage-19r-run',
        'source_name': 'edsm',
        'source_category': 'source_of_evidence',
        'domain': 'stations',
        'import_scope': 'staging_only',
        'git_commit_sha': 'abc1234',
        'importer_name': 'stage_19r_test_helper',
        'importer_version': 'v1',
        'trigger_context': 'manual_test',
        'status': 'running',
        'metadata': {'stage': '19r'},
    }


def assert_sql_only_touches_source_runs(conn):
    canonical_tables = (
        'stations',
        'systems',
        'bodies',
        'body_rings',
        'station_body_links',
    )
    for sql, _params in conn.statements:
        compact = ' '.join(sql.lower().split())
        assert 'source_runs' in compact
        for table in canonical_tables:
            assert re.search(rf'\b(insert\s+into|update|delete\s+from)\s+{table}\b', compact) is None


def payload_shell():
    return artifacts.build_artifact_payload_shell(
        schema_version='stage_19r_artifact/v1',
        source_run_key='stage-19r-run',
        source_name='edsm',
        source_category='source_of_evidence',
        domain='stations',
        import_scope='staging_only',
        git_commit_sha='abc1234',
        importer_name='stage_19r_test_helper',
        importer_version='v1',
        trigger_context='manual_test',
        generated_at=NOW,
        source_uri='file:///tmp/example.jsonl',
        source_input_sha256='a' * 64,
        safety_boundary={'canonical_writes_planned': 0},
        metadata={'dry_run': True},
        summary={'rows_seen': 2},
        payload={'sample_rows': [{'station': 'Galileo'}]},
    )


def test_build_artifact_payload_shell_includes_source_run_metadata():
    payload = payload_shell()

    assert payload['generated_at'] == '2026-01-02T03:04:05Z'
    assert payload['source_run'] == {
        'source_run_key': 'stage-19r-run',
        'source_name': 'edsm',
        'source_category': 'source_of_evidence',
        'domain': 'stations',
        'import_scope': 'staging_only',
        'git_commit_sha': 'abc1234',
        'importer_name': 'stage_19r_test_helper',
        'importer_version': 'v1',
        'trigger_context': 'manual_test',
    }
    assert payload['source']['input_sha256'] == 'a' * 64
    assert payload['safety_boundary']['canonical_writes_planned'] == 0
    assert payload['summary']['rows_seen'] == 2


def test_write_source_run_artifact_writes_canonical_json_and_record_hashes(tmp_path):
    path = tmp_path / 'artifacts' / 'stage-19r.json'

    record = artifacts.write_source_run_artifact(path, payload_shell())
    raw = path.read_bytes()
    loaded = json.loads(raw.decode('utf-8'))

    assert raw.endswith(b'\n')
    assert raw.decode('utf-8') == artifact_utils.canonical_json(loaded) + '\n'
    assert loaded['artifact_integrity']['canonical_json_sha256'] == artifact_utils.artifact_integrity_sha256(loaded)
    assert record['artifact_path'] == str(path)
    assert record['path'] == str(path)
    assert record['file_sha256'] == artifact_utils.sha256_bytes(raw)
    assert record['artifact_sha256'] == record['file_sha256']
    assert record['artifact_integrity_sha256'] == loaded['artifact_integrity']['canonical_json_sha256']
    assert record['bytes_written'] == len(raw)

def test_run_source_run_artifact_flow_creates_writes_and_completes_success(tmp_path):
    conn = FakeConn()
    artifact_path = tmp_path / 'runs' / 'stage-19r-success.json'
    seen_source_runs = []

    def operation(source_run):
        seen_source_runs.append(dict(source_run))
        payload = payload_shell()
        return artifacts.SourceRunArtifactOutcome(
            payload=payload,
            rows_read=2,
            rows_staged=2,
            rows_rejected=0,
            rows_skipped=0,
            metadata={'operation': 'fake_success'},
            finished_at=NOW,
            duration_ms=42,
        )

    result = artifacts.run_source_run_artifact_flow(
        conn,
        source_run_kwargs=valid_source_run_kwargs(),
        artifact_path=artifact_path,
        operation=operation,
    )

    assert seen_source_runs == [{'id': 101, 'source_run_key': 'stage-19r-run', 'status': 'running'}]
    assert result['completion']['status'] == 'succeeded'
    assert artifact_path.exists()
    assert len(conn.statements) == 2
    update_sql, update_params = conn.statements[1]
    assert 'UPDATE source_runs' in update_sql
    assert update_params[:13] == (
        'succeeded',
        NOW,
        42,
        2,
        2,
        0,
        0,
        result['artifact_record']['artifact_path'],
        result['artifact_record']['artifact_sha256'],
        result['artifact_record']['artifact_integrity_sha256'],
        None,
        None,
        update_params[12],
    )
    metadata = json.loads(update_params[12])
    assert metadata['operation'] == 'fake_success'
    assert metadata['artifact_record']['file_sha256'] == result['artifact_record']['file_sha256']
    assert update_params[13] == 'stage-19r-run'
    assert update_params[14] == ['planned', 'running']
    assert_sql_only_touches_source_runs(conn)


@pytest.mark.parametrize('status,complete_error_code', [
    ('failed', 'source_read_failed'),
    ('rejected', 'source_schema_mismatch'),
])
def test_complete_source_run_with_artifact_records_failure_and_rejection_errors(
    tmp_path,
    status,
    complete_error_code,
):
    conn = FakeConn()
    record = artifacts.write_source_run_artifact(tmp_path / f'{status}.json', payload_shell())

    row = artifacts.complete_source_run_with_artifact(
        conn,
        'stage-19r-run',
        status=status,
        artifact_record=record,
        rows_read=3,
        rows_rejected=3,
        error_code=complete_error_code,
        error_summary='fake operation stopped before staging',
        finished_at=NOW,
        metadata={'operation': f'fake_{status}'},
    )

    assert row['status'] == status
    sql, params = conn.statements[0]
    assert 'UPDATE source_runs' in sql
    assert params[0] == status
    assert params[3] == 3
    assert params[5] == 3
    assert params[7:10] == (
        record['artifact_path'],
        record['artifact_sha256'],
        record['artifact_integrity_sha256'],
    )
    assert params[10:12] == (
        complete_error_code,
        'fake operation stopped before staging',
    )
    metadata = json.loads(params[12])
    assert metadata['operation'] == f'fake_{status}'
    assert metadata['artifact_record']['artifact_integrity_sha256'] == record['artifact_integrity_sha256']
    assert_sql_only_touches_source_runs(conn)


def test_run_source_run_artifact_flow_rejects_unknown_completion_status(tmp_path):
    conn = FakeConn()

    def operation(_source_run):
        return artifacts.SourceRunArtifactOutcome(payload=payload_shell(), status='waiting')

    with pytest.raises(
        artifacts.source_run_ledger.SourceRunLedgerError,
        match='unsupported artifact completion status',
    ):
        artifacts.run_source_run_artifact_flow(
            conn,
            source_run_kwargs=valid_source_run_kwargs(),
            artifact_path=tmp_path / 'unsupported.json',
            operation=operation,
        )

    assert len(conn.statements) == 1
    assert not (tmp_path / 'unsupported.json').exists()
    assert_sql_only_touches_source_runs(conn)


def test_source_run_artifacts_has_no_prod_db_import_scheduler_or_canonical_write_fragments():
    source = inspect.getsource(artifacts)
    source_upper = source.upper()
    forbidden_fragments = (
        'PSYCOPG2.CONNECT',
        'ASYNCPG.CONNECT',
        'SUBPROCESS',
        'OS.SYSTEM',
        'SYSTEMCTL',
        '.TIMER',
        '.SERVICE',
        'SCHEDULER',
        'RUN_IMPORT',
        'RUN_IMPORT.SH',
        'CANONICAL APPLY',
        'DATABASE' + '_URL',
        'POSTGRESQL' + '://',
        'POSTGRES' + '://',
        'PASSWORD' + '=',
        'SECRET',
        'TOKEN' + '=',
    )
    for fragment in forbidden_fragments:
        assert fragment not in source_upper

    canonical_write_patterns = (
        r'\binsert\s+into\s+(stations|systems|bodies|body_rings|station_body_links)\b',
        r'\bupdate\s+(stations|systems|bodies|body_rings|station_body_links)\b',
        r'\bdelete\s+from\s+(stations|systems|bodies|body_rings|station_body_links)\b',
    )
    for pattern in canonical_write_patterns:
        assert re.search(pattern, source, flags=re.IGNORECASE) is None
