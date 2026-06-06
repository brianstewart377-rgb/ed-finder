import ast
import inspect
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
OPERATOR_SCRIPTS = ROOT / 'scripts' / 'operator'
if str(OPERATOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATOR_SCRIPTS))

import stage19anr_warehouse_derived_staging_rehearsal as rehearsal  # noqa: E402


NOW = datetime(2026, 6, 6, 10, 30, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.closed = False
        self.fetchone_result = None
        self.fetchall_result = []
        self.description = None

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.conn.statements.append((sql, params))
        compact = ' '.join(sql.lower().split())

        if 'from information_schema.tables' in compact:
            self.fetchall_result = [
                {'table_name': table_name}
                for table_name in sorted(self.conn.present_tables)
            ]
            self.fetchone_result = None
            return

        if 'as source_runs' in compact and 'marked_staging_rows' in compact:
            self.fetchone_result = dict(self.conn.existing_stage19anr_counts)
            self.fetchall_result = []
            return

        if compact.startswith('select s.id') and 'from staging_edsm_stations s' in compact:
            limit = int(params[-1])
            self.fetchall_result = [dict(row) for row in self.conn.sample_rows[:limit]]
            self.fetchone_result = None
            return

        if compact.startswith('insert into source_runs'):
            self.conn.next_source_run_id += 1
            row = {
                'id': self.conn.next_source_run_id,
                'source_run_key': params[0],
                'status': params[5],
                'artifact_path': None,
                'artifact_sha256': None,
                'artifact_integrity_sha256': None,
            }
            self.conn.source_runs[params[0]] = row
            self.fetchone_result = {
                'id': row['id'],
                'source_run_key': row['source_run_key'],
                'status': row['status'],
            }
            self.fetchall_result = []
            return

        if compact.startswith('update source_runs'):
            source_run_key = params[13]
            row = self.conn.source_runs[source_run_key]
            row.update({
                'status': params[0],
                'artifact_path': params[7],
                'artifact_sha256': params[8],
                'artifact_integrity_sha256': params[9],
            })
            self.fetchone_result = {
                'id': row['id'],
                'source_run_key': row['source_run_key'],
                'status': row['status'],
            }
            self.fetchall_result = []
            return

        if compact.startswith('select') and 'from enrichment_source_runs' in compact and 'where source_run_key = %s' in compact:
            row = self.conn.legacy_rows.get(params[0])
            self.fetchone_result = dict(row) if row is not None else None
            self.fetchall_result = []
            return

        if compact.startswith('insert into enrichment_source_runs'):
            self.conn.next_legacy_id += 1
            row = {
                'id': self.conn.next_legacy_id,
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
            self.conn.legacy_rows[params[0]] = row
            self.fetchone_result = dict(row)
            self.fetchall_result = []
            return

        if compact.startswith('insert into staging_edsm_stations'):
            self.conn.next_staging_id += 1
            row = {
                'id': self.conn.next_staging_id,
                'source_run_id': params[0],
                'source_record_key': params[1],
                'source_record_hash': params[2],
                'system_id64': params[3],
                'system_name': params[4],
                'market_id': params[5],
                'edsm_station_id': params[6],
                'station_name': params[7],
                'station_type': params[8],
                'distance_to_arrival': params[9],
                'body_name': params[10],
                'services': json.loads(params[11]),
                'economies': json.loads(params[12]),
                'controlling_faction': params[13],
                'allegiance': params[14],
                'government': params[15],
                'source_class': params[16],
                'confidence': params[17],
                'freshness_class': params[18],
                'source_updated_at': params[19],
                'raw_payload': json.loads(params[20]),
                'provenance': json.loads(params[21]),
            }
            self.conn.staging_rows[row['id']] = row
            self.fetchone_result = {'id': row['id']}
            self.fetchall_result = []
            return

        if compact.startswith('update staging_edsm_stations'):
            marker = json.loads(params[2])
            row_ids = set(params[3])
            legacy_source_run_id = params[4]
            rows = []
            for row_id in row_ids:
                row = self.conn.staging_rows[row_id]
                if row['source_run_id'] != legacy_source_run_id:
                    continue
                row['source_class'] = params[0]
                row['confidence'] = params[1]
                row['provenance'].update(marker)
                rows.append({
                    'id': row['id'],
                    'source_class': row['source_class'],
                    'confidence': row['confidence'],
                    'provenance': dict(row['provenance']),
                })
            self.fetchall_result = rows
            self.fetchone_result = None
            return

        if compact.startswith('select id, source_run_key, status') and 'from source_runs' in compact:
            row = self.conn.source_runs.get(params[0])
            self.fetchone_result = dict(row) if row is not None else None
            self.fetchall_result = []
            return

        if compact.startswith('select count(*)::int as rows_inserted'):
            row_ids = set(params[6])
            rows = [row for row_id, row in self.conn.staging_rows.items() if row_id in row_ids]
            legacy_source_run_id = params[2]
            source_run_id = params[3]
            marker_key = params[4]
            canonical_key = params[5]
            self.fetchone_result = {
                'rows_inserted': len(rows),
                'rows_marked_diagnostic': sum(
                    1
                    for row in rows
                    if row['source_class'] == params[0] and row['confidence'] == params[1]
                ),
                'rows_using_legacy_bridge_id': sum(1 for row in rows if row['source_run_id'] == legacy_source_run_id),
                'rows_using_source_runs_id': sum(1 for row in rows if row['source_run_id'] == source_run_id),
                'rows_with_stage19anr_marker': sum(1 for row in rows if marker_key in row['provenance']),
                'rows_with_canonical_write_blocked': sum(
                    1
                    for row in rows
                    if row['provenance'].get(canonical_key) is False
                ),
            }
            self.fetchall_result = []
            return

        raise AssertionError(f'unexpected SQL: {sql}')

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return list(self.fetchall_result)

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self, *, sample_rows=None, existing_stage19anr_counts=None, present_tables=None):
        self.sample_rows = list(sample_rows or [])
        self.existing_stage19anr_counts = existing_stage19anr_counts or {
            'source_runs': 0,
            'legacy_source_runs': 0,
            'marked_staging_rows': 0,
        }
        self.present_tables = set(present_tables or rehearsal.REQUIRED_TABLES)
        self.statements = []
        self.source_runs = {}
        self.legacy_rows = {}
        self.staging_rows = {}
        self.next_source_run_id = 100
        self.next_legacy_id = 700
        self.next_staging_id = 900
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def sample_staging_row(index=1, **overrides):
    row = {
        'id': 1000 + index,
        'system_id64': 10477373803 + index,
        'system_name': f'Sample System {index}',
        'market_id': 700000 + index,
        'edsm_station_id': 800000 + index,
        'station_name': f'Sample Port {index}',
        'station_type': 'Coriolis Starport',
        'distance_to_arrival': 503.2,
        'body_name': f'Sample Body {index}',
        'services': ['Dock', 'Market'],
        'economies': [{'name': 'High Tech'}, {'name': 'Service'}],
        'controlling_faction': f'Faction {index}',
        'allegiance': 'Independent',
        'government': 'Corporate',
        'source_updated_at': '2026-06-06T08:00:00Z',
        'raw_payload': {'source': 'warehouse', 'row': index},
        'provenance': {'canonical_write_allowed': False},
    }
    row.update(overrides)
    return row


def normalised_import_row(index=1, **overrides):
    row = {
        'source_record_key': f'source-record-key-{index}',
        'source_record_hash': f'hash-{index}',
        'system_id64': 10477373803 + index,
        'system_name': f'Sample System {index}',
        'market_id': 700000 + index,
        'edsm_station_id': 800000 + index,
        'station_name': f'Sample Port {index}',
        'station_type': 'Coriolis Starport',
        'distance_to_arrival': 503.2,
        'body_name': f'Sample Body {index}',
        'services': ['Dock', 'Market'],
        'economies': ['High Tech', 'Service'],
        'controlling_faction': f'Faction {index}',
        'allegiance': 'Independent',
        'government': 'Corporate',
        'source_class': 'semi-stable',
        'confidence': 'source_station_snapshot',
        'freshness_class': 'source_updated_at',
        'source_updated_at': '2026-06-06T08:00:00Z',
        'raw_payload': {'source': 'fixture', 'row': index},
        'provenance': {'canonical_write_allowed': False},
    }
    row.update(overrides)
    return row


def test_cli_defaults_to_read_only_and_does_not_commit_without_flag(tmp_path):
    args = rehearsal.parse_args([
        '--limit',
        '2',
        '--artifact-dir',
        str(tmp_path),
        '--git-head',
        'abc1234',
    ])
    assert args.commit is False

    conn = FakeConn(sample_rows=[sample_staging_row(1), sample_staging_row(2)])
    result = rehearsal.run_rehearsal(
        conn,
        limit=2,
        artifact_dir=tmp_path,
        git_head='abc1234',
        trigger_context='unit_test',
        commit=False,
        generated_at=NOW,
    )

    assert result['commit_requested'] is False
    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert conn.source_runs == {}
    assert conn.legacy_rows == {}
    assert conn.staging_rows == {}
    assert not any('insert into source_runs' in sql.lower() for sql, _params in conn.statements)


def test_preflight_detects_existing_stage19anr_rows_and_stops():
    conn = FakeConn(existing_stage19anr_counts={
        'source_runs': 1,
        'legacy_source_runs': 0,
        'marked_staging_rows': 0,
    })

    with pytest.raises(rehearsal.Stage19AnrRehearsalError, match='existing Stage 19AN-R rows found'):
        rehearsal.preflight_rehearsal(conn)


def test_sample_conversion_from_staging_row_to_edsm_like_json():
    converted = rehearsal.staging_row_to_edsm_fixture_record(sample_staging_row())

    assert converted == {
        'allegiance': 'Independent',
        'bodyName': 'Sample Body 1',
        'controllingFaction': {'name': 'Faction 1'},
        'distanceToArrival': 503.2,
        'economy': 'High Tech',
        'government': 'Corporate',
        'id': 800001,
        'marketId': 700001,
        'name': 'Sample Port 1',
        'secondEconomy': 'Service',
        'services': ['Dock', 'Market'],
        'systemId64': 10477373804,
        'systemName': 'Sample System 1',
        'type': 'Coriolis Starport',
        'updatedAt': '2026-06-06T08:00:00Z',
    }


def test_explicit_compatible_stager_uses_legacy_bridge_id_for_staging():
    conn = FakeConn()
    stager = rehearsal.CompatibleWarehouseDerivedStationStager(generated_at=NOW)
    source_run = {'id': 101, 'source_run_key': 'stage19anr-test', 'status': 'running'}

    rows_written = stager(conn, source_run=source_run, rows=[normalised_import_row()])

    assert rows_written == 1
    assert stager.legacy_source_run_id == 701
    assert stager.bridge_key == 'source_runs:stage19anr-test'
    staged = conn.staging_rows[901]
    assert staged['source_run_id'] == 701
    assert staged['source_run_id'] != source_run['id']
    assert conn.legacy_rows['source_runs:stage19anr-test']['dry_run'] is False


def test_inserted_rows_are_marked_diagnostic_only_and_preserve_no_canonical_write():
    conn = FakeConn()
    stager = rehearsal.CompatibleWarehouseDerivedStationStager(generated_at=NOW)
    stager(conn, source_run={'id': 101, 'source_run_key': 'stage19anr-test', 'status': 'running'}, rows=[
        normalised_import_row(),
    ])

    marked = rehearsal.mark_inserted_rows_diagnostic(
        conn,
        row_ids=stager.inserted_row_ids,
        legacy_source_run_id=stager.legacy_source_run_id,
        source_run_key='stage19anr-test',
        generated_at=NOW,
    )

    assert len(marked) == 1
    staged = conn.staging_rows[901]
    assert staged['source_class'] == 'diagnostic-only'
    assert staged['confidence'] == 'diagnostic-only'
    assert staged['provenance']['canonical_write_allowed'] is False
    assert staged['provenance']['stage19anr_diagnostic_mark']['source_run_key'] == 'stage19anr-test'


def test_validation_passes_for_exactly_n_marked_rows(tmp_path):
    conn = FakeConn()
    import_record = rehearsal.artifact_utils.write_json_artifact(
        tmp_path / 'import.json',
        {'schema_version': 'unit/v1', 'summary': {'rows': 2}},
    )
    import_artifact_record = {
        'artifact_path': import_record['path'],
        'artifact_sha256': import_record['file_sha256'],
        'artifact_integrity_sha256': import_record['artifact_integrity_sha256'],
    }
    conn.source_runs['stage19anr-test'] = {
        'id': 101,
        'source_run_key': 'stage19anr-test',
        'status': 'succeeded',
        **import_artifact_record,
    }
    conn.legacy_rows['source_runs:stage19anr-test'] = {
        'id': 701,
        'source_run_key': 'source_runs:stage19anr-test',
        'dry_run': False,
        'metadata': {},
    }
    conn.staging_rows[901] = {
        **normalised_import_row(1),
        'id': 901,
        'source_run_id': 701,
        'source_class': 'diagnostic-only',
        'confidence': 'diagnostic-only',
        'provenance': {
            'canonical_write_allowed': False,
            'stage19anr_diagnostic_mark': {'source_run_key': 'stage19anr-test'},
        },
    }
    conn.staging_rows[902] = {
        **normalised_import_row(2),
        'id': 902,
        'source_run_id': 701,
        'source_class': 'diagnostic-only',
        'confidence': 'diagnostic-only',
        'provenance': {
            'canonical_write_allowed': False,
            'stage19anr_diagnostic_mark': {'source_run_key': 'stage19anr-test'},
        },
    }

    checks = rehearsal.validate_rehearsal(
        conn,
        limit=2,
        source_run_key='stage19anr-test',
        bridge_key='source_runs:stage19anr-test',
        source_run_id=101,
        legacy_source_run_id=701,
        inserted_row_ids=[901, 902],
        import_artifact_record=import_artifact_record,
    )

    assert checks['one_source_run_inserted'] is True
    assert checks['one_legacy_bridge_inserted'] is True
    assert checks['exactly_limit_staging_rows_inserted'] is True
    assert checks['exactly_limit_staging_rows_marked_diagnostic'] is True
    assert checks['staging_rows_use_legacy_bridge_id'] is True
    assert checks['staging_rows_do_not_use_source_runs_id'] is True
    assert checks['staging_rows_preserve_canonical_write_block'] is True
    assert checks['source_run_artifact_hash_matches'] is True
    assert checks['source_run_artifact_integrity_matches'] is True
    rehearsal.assert_validation_passes(checks)


def test_committed_rehearsal_runs_import_marks_rows_validates_and_writes_artifact(tmp_path):
    conn = FakeConn(sample_rows=[sample_staging_row(1), sample_staging_row(2)])

    result = rehearsal.run_rehearsal(
        conn,
        limit=2,
        artifact_dir=tmp_path,
        git_head='abc1234',
        trigger_context='unit_test',
        commit=True,
        generated_at=NOW,
    )

    assert result['commit_requested'] is True
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert len(conn.source_runs) == 1
    assert len(conn.legacy_rows) == 1
    assert len(conn.staging_rows) == 2
    assert all(row['source_run_id'] == 701 for row in conn.staging_rows.values())
    assert all(row['source_class'] == 'diagnostic-only' for row in conn.staging_rows.values())
    assert all(row['confidence'] == 'diagnostic-only' for row in conn.staging_rows.values())
    assert all(row['provenance']['canonical_write_allowed'] is False for row in conn.staging_rows.values())
    assert all('stage19anr_diagnostic_mark' in row['provenance'] for row in conn.staging_rows.values())
    assert Path(result['sample_record']['path']).is_file()
    assert Path(result['import_result']['artifact_record']['artifact_path']).is_file()
    assert Path(result['operator_artifact_record']['record']['artifact_path']).is_file()


def test_static_guardrails_no_scheduler_canonical_apply_canonical_writes_or_secrets():
    source = inspect.getsource(rehearsal)
    source_upper = source.upper()

    forbidden_fragments = (
        'SYSTEMCTL',
        'RUN_IMPORT',
        'RUN_IMPORT.SH',
        'DATABASE' + '_URL',
        'POSTGRESQL' + '://',
        'POSTGRES' + '://',
        'PASSWORD' + '=',
        'SECRET' + '=',
        'TOKEN' + '=',
    )
    for fragment in forbidden_fragments:
        assert fragment not in source_upper
    assert re.search(r'(?<![a-z0-9_])\.timer(?![a-z0-9_])', source, flags=re.IGNORECASE) is None
    assert re.search(r'(?<![a-z0-9_])\.service(?![a-z0-9_])', source, flags=re.IGNORECASE) is None
    assert 'canonical_apply' not in source.lower()

    canonical_write_patterns = (
        r'\binsert\s+into\s+(stations|systems|bodies|body_rings|station_body_links|station_external_identity)\b',
        r'\bupdate\s+(stations|systems|bodies|body_rings|station_body_links|station_external_identity)\b',
        r'\bdelete\s+from\s+(stations|systems|bodies|body_rings|station_body_links|station_external_identity)\b',
    )
    for pattern in canonical_write_patterns:
        assert re.search(pattern, source, flags=re.IGNORECASE) is None


def test_static_import_call_does_not_override_finished_at():
    tree = ast.parse(inspect.getsource(rehearsal))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'run_edsm_station_import'
    ]

    assert calls
    assert all(
        keyword.arg != 'finished_at'
        for call in calls
        for keyword in call.keywords
    )
