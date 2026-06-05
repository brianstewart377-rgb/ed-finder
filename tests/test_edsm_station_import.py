import inspect
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import artifact_utils  # noqa: E402
import edsm_station_import as importer  # noqa: E402


NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.closed = False
        self.last_result = None

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.conn.statements.append((sql, params))
        compact = ' '.join(sql.lower().split())

        if compact.startswith('insert into source_runs'):
            self.conn.next_source_run_id += 1
            self.last_result = {
                'id': self.conn.next_source_run_id,
                'source_run_key': params[0],
                'status': params[5],
            }
            self.conn.source_run_key = params[0]
            return

        if compact.startswith('insert into staging_edsm_stations'):
            self.conn.next_staging_id += 1
            self.conn.staging_params.append(params)
            self.last_result = {'id': self.conn.next_staging_id}
            return

        if compact.startswith('update source_runs'):
            self.last_result = {
                'id': self.conn.next_source_run_id,
                'source_run_key': self.conn.source_run_key,
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
        self.staging_params = []
        self.next_source_run_id = 100
        self.next_staging_id = 900
        self.source_run_key = 'stage-19t-test'

    def cursor(self):
        return FakeCursor(self)


def write_source(path, rows):
    path.write_text(json.dumps(rows, sort_keys=True), encoding='utf-8')
    return path


def sample_rows():
    return [
        {
            'systemName': 'Sol',
            'systemId64': 10477373803,
            'id': 322,
            'marketId': 322,
            'name': 'Galileo',
            'type': 'Coriolis Starport',
            'distanceToArrival': 503.2,
            'bodyName': 'Moon',
            'services': ['Dock', 'Market', 'Shipyard'],
            'economy': 'High Tech',
            'secondEconomy': 'Service',
            'updatedAt': '2026-01-02T00:00:00Z',
        },
        {
            'systemName': 'Carrier System',
            'systemId64': 42,
            'id': 7001,
            'marketId': 7001,
            'name': 'BVT-19T',
            'type': 'Drake-Class Carrier',
            'distanceToArrival': 12.5,
            'updatedAt': '2026-01-02T00:00:00Z',
        },
        {
            'systemName': 'Depot System',
            'systemId64': 43,
            'id': 7002,
            'marketId': 7002,
            'name': 'Rackham Depot Works',
            'type': 'Space Construction Depot',
            'distanceToArrival': 2200,
            'updatedAt': '2026-01-02T00:00:00Z',
        },
    ]


def load_artifact(path):
    raw = path.read_bytes()
    loaded = json.loads(raw.decode('utf-8'))
    assert raw.endswith(b'\n')
    assert raw.decode('utf-8') == artifact_utils.canonical_json(loaded) + '\n'
    assert loaded['artifact_integrity']['canonical_json_sha256'] == artifact_utils.artifact_integrity_sha256(loaded)
    return loaded


def compatible_fake_station_stager(conn, *, source_run, rows):
    assert source_run['source_run_key'].startswith('stage-19t')
    cur = conn.cursor()
    try:
        for row in rows:
            cur.execute(
                """
                INSERT INTO staging_edsm_stations (
                    source_run_id,
                    source_record_hash,
                    station_name,
                    station_type,
                    provenance
                )
                VALUES (%s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    'compatible-enrichment-source-run-id',
                    row['source_record_hash'],
                    row['station_name'],
                    row['station_type'],
                    artifact_utils.canonical_json(row['provenance']),
                ),
            )
            cur.fetchone()
        return len(rows)
    finally:
        cur.close()


def test_edsm_station_import_stages_valid_rows_with_injected_stager_and_completes_source_run(tmp_path):
    conn = FakeConn()
    source_file = write_source(tmp_path / 'edsm-stations.json', sample_rows())
    artifact_path = tmp_path / 'artifacts' / 'stage-19t.json'

    result = importer.run_edsm_station_import(
        conn,
        source_file=source_file,
        artifact_path=artifact_path,
        source_run_key='stage-19t-test',
        git_commit_sha='abc1234',
        trigger_context='unit_test',
        generated_at=NOW,
        finished_at=NOW,
        station_stager=compatible_fake_station_stager,
    )

    source_input_sha256 = artifact_utils.sha256_file(source_file)
    assert result['source_run'] == {'id': 101, 'source_run_key': 'stage-19t-test', 'status': 'running'}
    assert result['completion']['status'] == 'succeeded'
    assert len(conn.staging_params) == 3
    assert {params[3] for params in conn.staging_params} == {
        'Coriolis Starport',
        'Drake-Class Carrier',
        'Space Construction Depot',
    }
    assert {params[2] for params in conn.staging_params} == {'Galileo', 'BVT-19T', 'Rackham Depot Works'}
    assert all(json.loads(params[4])['canonical_write_allowed'] is False for params in conn.staging_params)

    create_sql, create_params = conn.statements[0]
    assert 'INSERT INTO source_runs' in create_sql
    assert create_params[:8] == (
        'stage-19t-test',
        'edsm',
        'source_of_evidence',
        'stations',
        'staging_only',
        'running',
        source_file.resolve().as_uri(),
        source_input_sha256,
    )
    assert json.loads(create_params[18])['canonical_writes_planned'] == 0

    loaded = load_artifact(artifact_path)
    assert loaded['schema_version'] == importer.SCHEMA_VERSION
    assert loaded['source']['uri'] == source_file.resolve().as_uri()
    assert loaded['source']['input_sha256'] == source_input_sha256
    assert loaded['summary']['rows_read'] == 3
    assert loaded['summary']['rows_staged'] == 3
    assert loaded['summary']['rows_rejected'] == 0
    assert loaded['summary']['rows_skipped'] == 0
    assert loaded['summary']['source_station_type_counts'] == {
        'Coriolis Starport': 1,
        'Drake-Class Carrier': 1,
        'Space Construction Depot': 1,
    }
    assert loaded['summary']['noisy_transient_station_type_counts'] == {
        'Drake-Class Carrier': 1,
        'Space Construction Depot': 1,
    }
    assert loaded['payload']['station_type_mapping_written'] is False
    assert loaded['summary']['safety_summary']['target_tables'] == ['source_runs', 'staging_edsm_stations']
    assert loaded['summary']['safety_summary']['canonical_writes_planned'] == 0
    assert loaded['summary']['safety_summary']['canonical_apply_enabled'] is False

    update_sql, update_params = conn.statements[-1]
    assert 'UPDATE source_runs' in update_sql
    assert update_params[0] == 'succeeded'
    assert update_params[3:10] == (
        3,
        3,
        0,
        0,
        result['artifact_record']['artifact_path'],
        result['artifact_record']['artifact_sha256'],
        result['artifact_record']['artifact_integrity_sha256'],
    )
    assert_sql_only_touches_allowed_tables(conn)


def test_edsm_station_import_without_explicit_stager_fails_closed_before_staging_write(tmp_path):
    conn = FakeConn()
    source_file = write_source(tmp_path / 'edsm-stations.json', sample_rows())
    artifact_path = tmp_path / 'artifacts' / 'stage-19t-no-default-stager.json'

    result = importer.run_edsm_station_import(
        conn,
        source_file=source_file,
        artifact_path=artifact_path,
        source_run_key='stage-19t-no-default-stager',
        git_commit_sha='abc1234',
        trigger_context='unit_test',
        generated_at=NOW,
        finished_at=NOW,
    )

    assert result['completion']['status'] == 'failed'
    assert conn.staging_params == []
    assert not any('INSERT INTO staging_edsm_stations' in sql for sql, _params in conn.statements)
    update_params = conn.statements[-1][1]
    assert update_params[0] == 'failed'
    assert update_params[3:7] == (3, 0, 0, 0)
    assert update_params[10] == 'edsm_station_import_failed'
    assert 'EdsmStationImportError' in update_params[11]
    assert 'staging_edsm_stations.source_run_id currently expects enrichment_source_runs.id' in update_params[11]
    assert 'not source_runs.id from this wrapper' in update_params[11]
    loaded = load_artifact(artifact_path)
    assert loaded['summary']['status'] == 'failed'
    assert loaded['summary']['rows_read'] == 3
    assert loaded['summary']['rows_staged'] == 0
    assert loaded['summary']['error_summary'] == update_params[11]
    assert_sql_only_touches_allowed_tables(conn)


def test_edsm_station_import_records_failed_completion_when_staging_raises(tmp_path):
    conn = FakeConn()
    source_file = write_source(tmp_path / 'edsm-stations.json', sample_rows()[:1])
    artifact_path = tmp_path / 'artifacts' / 'stage-19t-failed.json'

    def failing_stager(_conn, *, source_run, rows):
        assert source_run['id'] == 101
        assert len(rows) == 1
        raise RuntimeError('staging insert failed')

    result = importer.run_edsm_station_import(
        conn,
        source_file=source_file,
        artifact_path=artifact_path,
        source_run_key='stage-19t-failed',
        git_commit_sha='abc1234',
        trigger_context='unit_test',
        generated_at=NOW,
        finished_at=NOW,
        station_stager=failing_stager,
    )

    assert result['completion']['status'] == 'failed'
    assert conn.staging_params == []
    update_params = conn.statements[-1][1]
    assert update_params[0] == 'failed'
    assert update_params[3:7] == (1, 0, 0, 0)
    assert update_params[10] == 'edsm_station_import_failed'
    assert 'RuntimeError: staging insert failed' in update_params[11]
    loaded = load_artifact(artifact_path)
    assert loaded['summary']['status'] == 'failed'
    assert loaded['summary']['error_code'] == 'edsm_station_import_failed'
    assert_sql_only_touches_allowed_tables(conn)


def test_edsm_station_import_records_rejected_completion_for_invalid_input(tmp_path):
    conn = FakeConn()
    source_file = write_source(
        tmp_path / 'edsm-invalid.json',
        [{
            'systemName': 'Broken Example',
            'marketId': 999,
            'type': 'Drake-Class Carrier',
            'distanceToArrival': 12,
        }],
    )
    artifact_path = tmp_path / 'artifacts' / 'stage-19t-rejected.json'

    result = importer.run_edsm_station_import(
        conn,
        source_file=source_file,
        artifact_path=artifact_path,
        source_run_key='stage-19t-rejected',
        git_commit_sha='abc1234',
        trigger_context='unit_test',
        generated_at=NOW,
        finished_at=NOW,
    )

    assert result['completion']['status'] == 'rejected'
    assert conn.staging_params == []
    update_params = conn.statements[-1][1]
    assert update_params[0] == 'rejected'
    assert update_params[3:7] == (1, 0, 1, 0)
    assert update_params[10] == 'edsm_station_input_rejected'
    assert update_params[11] == 'No valid EDSM station rows were available to stage.'
    loaded = load_artifact(artifact_path)
    assert loaded['summary']['rows_rejected'] == 1
    assert loaded['summary']['source_station_type_counts'] == {'Drake-Class Carrier': 1}
    assert loaded['summary']['noisy_transient_station_type_counts'] == {'Drake-Class Carrier': 1}
    assert loaded['payload']['rejections'][0]['reason'] == 'invalid_station_snapshot_record'
    assert_sql_only_touches_allowed_tables(conn)


def test_edsm_station_import_helper_has_no_prod_db_scheduler_or_canonical_write_fragments():
    source = inspect.getsource(importer)
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
    )
    for fragment in forbidden_fragments:
        assert fragment not in source_upper
    assert re.search(r'(?<![a-z0-9_])\.timer(?![a-z0-9_])', source, flags=re.IGNORECASE) is None
    assert re.search(r'(?<![a-z0-9_])\.service(?![a-z0-9_])', source, flags=re.IGNORECASE) is None

    canonical_write_patterns = (
        r'\binsert\s+into\s+(stations|systems|bodies|body_rings|station_body_links|station_external_identity)\b',
        r'\bupdate\s+(stations|systems|bodies|body_rings|station_body_links|station_external_identity)\b',
        r'\bdelete\s+from\s+(stations|systems|bodies|body_rings|station_body_links|station_external_identity)\b',
    )
    for pattern in canonical_write_patterns:
        assert re.search(pattern, source, flags=re.IGNORECASE) is None


def assert_sql_only_touches_allowed_tables(conn):
    assert conn.statements
    allowed = {'source_runs', 'staging_edsm_stations'}
    canonical_tables = (
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
        for table in canonical_tables:
            assert re.search(rf'\b(insert\s+into|update|delete\s+from)\s+{table}\b', compact) is None
