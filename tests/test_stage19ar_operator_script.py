import ast
import importlib.util
import inspect
import json
import re
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
OPERATOR_SCRIPTS = ROOT / 'scripts' / 'operator'
if str(OPERATOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATOR_SCRIPTS))

import stage19ar_edsm_25_row_staging_pilot as rehearsal  # noqa: E402
import stage19as_au_edsm_100_row_controlled_expansion as expansion  # noqa: E402


NOW = datetime(2026, 6, 6, 10, 30, 0, tzinfo=timezone.utc)
SUBSTITUTE_SOURCE_RUN_KEY = 'stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034'
SUBSTITUTE_ARTIFACT_SHA256 = 'b617d0239b7458b5b881895b564d091c771394b555c88a5bae942fd9d2c10e5e'


def noncanonical_stage19ar_profile():
    return replace(
        rehearsal.STAGE19AR_PROFILE,
        expected_source_run_key=None,
        expected_artifact_sha256=None,
    )


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

        if 'from information_schema.table_constraints' in compact:
            self.fetchall_result = [dict(row) for row in self.conn.fk_rows]
            self.fetchone_result = None
            return

        if 'as source_runs' in compact and 'marked_staging_rows' in compact:
            self.fetchone_result = dict(self.conn.existing_stage19ar_counts)
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
                'rows_read': 0,
                'rows_staged': 0,
                'rows_rejected': 0,
                'rows_skipped': 0,
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
                'rows_read': params[3],
                'rows_staged': params[4],
                'rows_rejected': params[5],
                'rows_skipped': params[6],
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
                'rows_with_stage_marker': sum(1 for row in rows if marker_key in row['provenance']),
                'rows_with_canonical_write_blocked': sum(
                    1
                    for row in rows
                    if row['provenance'].get(canonical_key) is False
                ),
            }
            self.fetchall_result = []
            return

        if compact.startswith('select count(*)::int as rows_total'):
            legacy_source_run_id = params[2]
            source_run_id = params[3]
            marker_key = params[4]
            rows = [
                row for row in self.conn.staging_rows.values()
                if row['source_run_id'] == params[5]
            ]
            self.fetchone_result = {
                'rows_total': len(rows),
                'rows_diagnostic_only': sum(
                    1
                    for row in rows
                    if row['source_class'] == params[0] and row['confidence'] == params[1]
                ),
                'rows_using_legacy_bridge_id': sum(1 for row in rows if row['source_run_id'] == legacy_source_run_id),
                'rows_using_source_runs_id': sum(1 for row in rows if row['source_run_id'] == source_run_id),
                'rows_with_marker': sum(1 for row in rows if marker_key in row['provenance']),
            }
            self.fetchall_result = []
            return

        if compact == 'select 1 as db_preflight_ok':
            self.fetchone_result = {'db_preflight_ok': 1}
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
    def __init__(
        self,
        *,
        sample_rows=None,
        existing_stage19ar_counts=None,
        present_tables=None,
        fk_rows=None,
    ):
        self.sample_rows = list(sample_rows or [])
        self.existing_stage19ar_counts = existing_stage19ar_counts or {
            'source_runs': 0,
            'running_source_runs': 0,
            'legacy_source_runs': 0,
            'marked_staging_rows': 0,
        }
        self.fk_rows = list(fk_rows or [{
            'constraint_name': 'staging_edsm_stations_source_run_id_fkey',
            'foreign_table_name': 'enrichment_source_runs',
            'foreign_column_name': 'id',
        }])
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


def sample_staging_rows(count):
    return [sample_staging_row(index) for index in range(1, count + 1)]


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


def test_cli_defaults_to_25_row_read_only_and_does_not_commit_without_flag(tmp_path):
    args = rehearsal.parse_args([
        '--artifact-dir',
        str(tmp_path),
        '--git-head',
        'abc1234',
    ])
    assert args.commit is False
    assert args.limit == 25
    assert args.trigger_context == 'stage19ar_bounded_25_row_pilot'

    conn = FakeConn(sample_rows=sample_staging_rows(25))
    result = rehearsal.run_pilot(
        conn,
        limit=25,
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
    assert result['validation_checks']['db_writes_attempted'] is False
    assert result['validation_checks']['selected_sample_count'] == 25
    assert result['validation_checks']['ready_for_commit'] is True
    assert result['inserted_row_count'] == 0
    assert result['inserted_row_ids'] == []
    payload = result['operator_artifact_record']['payload']
    assert payload['inserted_row_count'] == 0
    assert payload['inserted_row_ids'] == []
    written_payload = json.loads(Path(result['operator_artifact_record']['record']['artifact_path']).read_text())
    assert written_payload['inserted_row_count'] == 0
    assert written_payload['inserted_row_ids'] == []
    summary = rehearsal._summary_for_stdout(result)
    assert summary['inserted_row_count'] == 0
    assert summary['inserted_row_ids'] == []


def test_limit_hard_max_is_25(tmp_path):
    with pytest.raises(SystemExit):
        rehearsal.parse_args(['--limit', '26', '--artifact-dir', str(tmp_path)])

    with pytest.raises(rehearsal.Stage19ArPilotError, match='limit must be <= 25'):
        rehearsal.run_pilot(
            FakeConn(sample_rows=sample_staging_rows(25)),
            limit=26,
            artifact_dir=tmp_path,
            git_head='abc1234',
            trigger_context='unit_test',
            commit=False,
            generated_at=NOW,
        )


def test_commit_mode_refuses_limit_other_than_25(tmp_path):
    conn = FakeConn(sample_rows=sample_staging_rows(2))

    with pytest.raises(rehearsal.Stage19ArPilotError, match='commit mode requires exactly 25 rows'):
        rehearsal.run_pilot(
            conn,
            limit=2,
            artifact_dir=tmp_path,
            git_head='abc1234',
            trigger_context='unit_test',
            commit=True,
            generated_at=NOW,
        )

    assert conn.commits == 0
    assert conn.source_runs == {}


def test_preflight_detects_existing_stage19ar_rows_and_stops():
    conn = FakeConn(existing_stage19ar_counts={
        'source_runs': 1,
        'running_source_runs': 0,
        'legacy_source_runs': 0,
        'marked_staging_rows': 0,
    })

    with pytest.raises(rehearsal.Stage19ArPilotError, match='existing Stage 19AR rows found'):
        rehearsal.preflight_pilot(conn)


def test_preflight_detects_running_stage19ar_source_run_first():
    conn = FakeConn(existing_stage19ar_counts={
        'source_runs': 1,
        'running_source_runs': 1,
        'legacy_source_runs': 0,
        'marked_staging_rows': 0,
    })

    with pytest.raises(rehearsal.Stage19ArPilotError, match='running Stage 19AR source run found'):
        rehearsal.preflight_pilot(conn)


def test_existing_stage19anr_rows_do_not_block_stage19ar_preflight():
    conn = FakeConn()

    preflight = rehearsal.preflight_pilot(conn)

    assert preflight['existing_stage19ar_rows'] == {
        'source_runs': 0,
        'running_source_runs': 0,
        'legacy_source_runs': 0,
        'marked_staging_rows': 0,
    }
    params_text = json.dumps([params for _sql, params in conn.statements], default=str)
    assert 'stage19ar' in params_text
    assert 'stage19anr' not in params_text


def test_preflight_requires_staging_fk_to_legacy_bridge():
    conn = FakeConn(fk_rows=[{
        'constraint_name': 'bad_fk',
        'foreign_table_name': 'source_runs',
        'foreign_column_name': 'id',
    }])

    with pytest.raises(rehearsal.Stage19ArPilotError, match='must target enrichment_source_runs'):
        rehearsal.preflight_pilot(conn)


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
    stager = rehearsal.CompatibleStage19ArStationStager(generated_at=NOW)
    source_run = {'id': 101, 'source_run_key': 'stage19ar-test', 'status': 'running'}

    rows_written = stager(conn, source_run=source_run, rows=[normalised_import_row()])

    assert rows_written == 1
    assert stager.legacy_source_run_id == 701
    assert stager.bridge_key == 'source_runs:stage19ar-test'
    staged = conn.staging_rows[901]
    assert staged['source_run_id'] == 701
    assert staged['source_run_id'] != source_run['id']
    assert conn.legacy_rows['source_runs:stage19ar-test']['dry_run'] is False


def test_inserted_rows_are_marked_diagnostic_only_and_preserve_no_canonical_write():
    conn = FakeConn()
    stager = rehearsal.CompatibleStage19ArStationStager(generated_at=NOW)
    stager(conn, source_run={'id': 101, 'source_run_key': 'stage19ar-test', 'status': 'running'}, rows=[
        normalised_import_row(),
    ])

    marked = rehearsal.mark_inserted_rows_diagnostic(
        conn,
        row_ids=stager.inserted_row_ids,
        legacy_source_run_id=stager.legacy_source_run_id,
        source_run_key='stage19ar-test',
        generated_at=NOW,
    )

    assert len(marked) == 1
    staged = conn.staging_rows[901]
    assert staged['source_class'] == 'diagnostic-only'
    assert staged['confidence'] == 'diagnostic-only'
    assert staged['provenance']['canonical_write_allowed'] is False
    assert staged['provenance']['stage19ar_bounded_25_row_pilot']['source_run_key'] == 'stage19ar-test'


def test_validation_passes_for_exactly_n_marked_rows(tmp_path):
    conn = FakeConn()
    import_record = rehearsal.artifact_utils.write_json_artifact(
        tmp_path / 'import.json',
        {'schema_version': 'unit/v1', 'summary': {'rows': 25}},
    )
    import_artifact_record = {
        'artifact_path': import_record['path'],
        'artifact_sha256': import_record['file_sha256'],
        'artifact_integrity_sha256': import_record['artifact_integrity_sha256'],
    }
    conn.source_runs['stage19ar-test'] = {
        'id': 101,
        'source_run_key': 'stage19ar-test',
        'status': 'succeeded',
        'rows_read': 25,
        'rows_staged': 25,
        'rows_rejected': 0,
        'rows_skipped': 0,
        **import_artifact_record,
    }
    conn.legacy_rows['source_runs:stage19ar-test'] = {
        'id': 701,
        'source_run_key': 'source_runs:stage19ar-test',
        'dry_run': False,
        'metadata': {},
    }
    for index in range(1, 26):
        conn.staging_rows[900 + index] = {
            **normalised_import_row(index),
            'id': 900 + index,
            'source_run_id': 701,
            'source_class': 'diagnostic-only',
            'confidence': 'diagnostic-only',
            'provenance': {
                'canonical_write_allowed': False,
                'stage19ar_bounded_25_row_pilot': {'source_run_key': 'stage19ar-test'},
            },
        }

    checks = rehearsal.validate_pilot(
        conn,
        limit=25,
        source_run_key='stage19ar-test',
        bridge_key='source_runs:stage19ar-test',
        source_run_id=101,
        legacy_source_run_id=701,
        inserted_row_ids=list(range(901, 926)),
        import_artifact_record=import_artifact_record,
        profile=noncanonical_stage19ar_profile(),
    )

    assert checks['one_source_run_inserted'] is True
    assert checks['source_run_rows_read_matches_limit'] is True
    assert checks['source_run_rows_staged_matches_inserted_rows'] is True
    assert checks['source_run_rows_rejected_is_zero'] is True
    assert checks['source_run_rows_skipped_is_zero'] is True
    assert checks['one_legacy_bridge_inserted'] is True
    assert checks['exactly_25_staging_rows_inserted'] is True
    assert checks['exactly_25_staging_rows_marked_diagnostic'] is True
    assert checks['staging_rows_use_legacy_bridge_id'] is True
    assert checks['staging_rows_do_not_use_source_runs_id'] is True
    assert checks['staging_rows_have_stage19ar_marker'] is True
    assert checks['staging_rows_preserve_canonical_write_block'] is True
    assert checks['source_run_artifact_hash_matches'] is True
    assert checks['source_run_artifact_integrity_matches'] is True
    rehearsal.assert_validation_passes(checks)


def test_committed_pilot_runs_import_marks_rows_validates_and_writes_artifact(tmp_path):
    conn = FakeConn(sample_rows=sample_staging_rows(25))

    result = rehearsal.run_pilot(
        conn,
        limit=25,
        artifact_dir=tmp_path,
        git_head='abc1234',
        trigger_context='unit_test',
        commit=True,
        generated_at=NOW,
        profile=noncanonical_stage19ar_profile(),
    )

    assert result['commit_requested'] is True
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert len(conn.source_runs) == 1
    assert len(conn.legacy_rows) == 1
    assert len(conn.staging_rows) == 25
    assert all(row['source_run_id'] == 701 for row in conn.staging_rows.values())
    assert all(row['source_class'] == 'diagnostic-only' for row in conn.staging_rows.values())
    assert all(row['confidence'] == 'diagnostic-only' for row in conn.staging_rows.values())
    assert all(row['provenance']['canonical_write_allowed'] is False for row in conn.staging_rows.values())
    assert all('stage19ar_bounded_25_row_pilot' in row['provenance'] for row in conn.staging_rows.values())
    assert Path(result['sample_record']['path']).is_file()
    assert Path(result['import_result']['artifact_record']['artifact_path']).is_file()
    assert Path(result['operator_artifact_record']['record']['artifact_path']).is_file()
    assert result['inserted_row_count'] == 25
    assert result['inserted_row_ids'] == list(range(901, 926))
    assert result['source_run_key'].startswith('stage19ar-edsm-25-row-staging-pilot-')
    assert not result['source_run_key'].startswith('stage19anr-')
    assert result['bridge_key'].startswith('source_runs:stage19ar-edsm-25-row-staging-pilot-')
    assert result['validation_checks']['source_run_rows_read_matches_limit'] is True
    assert result['validation_checks']['source_run_rows_staged_matches_inserted_rows'] is True
    assert result['validation_checks']['source_run_rows_rejected_is_zero'] is True
    assert result['validation_checks']['source_run_rows_skipped_is_zero'] is True
    assert result['validation_checks']['exactly_25_staging_rows_inserted'] is True
    assert result['validation_checks']['exactly_25_staging_rows_marked_diagnostic'] is True
    assert result['validation_checks']['canonical_table_writes_performed_by_script'] is False
    assert result['validation_checks']['no_scheduler_or_service_invoked'] is True
    payload = result['operator_artifact_record']['payload']
    assert payload['inserted_row_count'] == 25
    assert payload['inserted_row_ids'] == list(range(901, 926))
    written_payload = json.loads(Path(result['operator_artifact_record']['record']['artifact_path']).read_text())
    assert written_payload['inserted_row_count'] == 25
    assert written_payload['inserted_row_ids'] == list(range(901, 926))
    summary = rehearsal._summary_for_stdout(result)
    assert summary['inserted_row_count'] == 25
    assert summary['inserted_row_ids'] == list(range(901, 926))


def test_default_stage19ar_profile_uses_exact_canonical_source_run_key():
    assert rehearsal.CANONICAL_SOURCE_RUN_KEY == 'stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd'
    assert rehearsal.CANONICAL_BRIDGE_KEY == 'source_runs:stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd'
    assert rehearsal.CANONICAL_ARTIFACT_SHA256 == (
        '418bc0db66978623c460aa8cc46a8ab14811098f39cb99a16274d9d181f19417'
    )
    assert rehearsal.build_source_run_key('5f777958b81bd034') == rehearsal.CANONICAL_SOURCE_RUN_KEY


def test_substitute_stage19ar_run_fails_canonical_validation(tmp_path):
    conn = FakeConn()
    import_record = rehearsal.artifact_utils.write_json_artifact(
        tmp_path / 'import.json',
        {'schema_version': 'unit/v1', 'summary': {'rows': 25}},
    )
    import_artifact_record = {
        'artifact_path': import_record['path'],
        'artifact_sha256': import_record['file_sha256'],
        'artifact_integrity_sha256': import_record['artifact_integrity_sha256'],
    }
    conn.source_runs[SUBSTITUTE_SOURCE_RUN_KEY] = {
        'id': 101,
        'source_run_key': SUBSTITUTE_SOURCE_RUN_KEY,
        'status': 'succeeded',
        'rows_read': 25,
        'rows_staged': 25,
        'rows_rejected': 0,
        'rows_skipped': 0,
        **import_artifact_record,
    }
    conn.legacy_rows[f'source_runs:{SUBSTITUTE_SOURCE_RUN_KEY}'] = {
        'id': 701,
        'source_run_key': f'source_runs:{SUBSTITUTE_SOURCE_RUN_KEY}',
        'dry_run': False,
        'metadata': {},
    }
    for index in range(1, 26):
        conn.staging_rows[900 + index] = {
            **normalised_import_row(index),
            'id': 900 + index,
            'source_run_id': 701,
            'source_class': 'diagnostic-only',
            'confidence': 'diagnostic-only',
            'provenance': {
                'canonical_write_allowed': False,
                'stage19ar_bounded_25_row_pilot': {'source_run_key': SUBSTITUTE_SOURCE_RUN_KEY},
            },
        }

    checks = rehearsal.validate_pilot(
        conn,
        limit=25,
        source_run_key=SUBSTITUTE_SOURCE_RUN_KEY,
        bridge_key=f'source_runs:{SUBSTITUTE_SOURCE_RUN_KEY}',
        source_run_id=101,
        legacy_source_run_id=701,
        inserted_row_ids=list(range(901, 926)),
        import_artifact_record=import_artifact_record,
    )

    assert checks['canonical_source_run_key_matches'] is False
    assert checks['canonical_bridge_key_matches'] is False
    assert checks['canonical_artifact_hash_matches'] is False
    with pytest.raises(rehearsal.Stage19ArPilotError, match='canonical_'):
        rehearsal.assert_validation_passes(checks)


def test_stage19as_au_defaults_to_100_row_profile(tmp_path):
    args = expansion.parse_args([
        '--artifact-dir',
        str(tmp_path),
        '--git-head',
        'abc1234',
    ])

    assert args.commit is False
    assert args.limit == 100
    assert args.trigger_context == 'stage19as_au_controlled_100_row_expansion'
    assert expansion.STAGE19AS_AU_PROFILE.default_limit == 100
    assert expansion.STAGE19AS_AU_PROFILE.hard_max_limit == 100


def test_stage19as_au_rejects_substitute_stage19ar_baseline():
    conn = FakeConn()
    conn.source_runs[SUBSTITUTE_SOURCE_RUN_KEY] = {
        'id': 101,
        'source_run_key': SUBSTITUTE_SOURCE_RUN_KEY,
        'status': 'succeeded',
        'rows_read': 25,
        'rows_staged': 25,
        'rows_rejected': 0,
        'rows_skipped': 0,
        'artifact_path': 'stage19ar_edsm_import.json',
        'artifact_sha256': SUBSTITUTE_ARTIFACT_SHA256,
        'artifact_integrity_sha256': 'integrity',
    }
    conn.legacy_rows[f'source_runs:{SUBSTITUTE_SOURCE_RUN_KEY}'] = {
        'id': 701,
        'source_run_key': f'source_runs:{SUBSTITUTE_SOURCE_RUN_KEY}',
        'dry_run': False,
        'metadata': {},
    }
    for index in range(1, 26):
        conn.staging_rows[900 + index] = {
            **normalised_import_row(index),
            'id': 900 + index,
            'source_run_id': 701,
            'source_class': 'diagnostic-only',
            'confidence': 'diagnostic-only',
            'provenance': {
                'canonical_write_allowed': False,
                'stage19ar_bounded_25_row_pilot': {'source_run_key': SUBSTITUTE_SOURCE_RUN_KEY},
            },
        }

    baseline = expansion.verify_canonical_stage19ar_baseline(conn)

    assert baseline['checks']['canonical_source_run_key_present'] is False
    assert baseline['checks']['canonical_bridge_key_present'] is False
    assert baseline['checks']['canonical_artifact_present'] is False
    with pytest.raises(rehearsal.Stage19ArPilotError, match='canonical Stage 19AR baseline is required'):
        expansion.assert_canonical_stage19ar_baseline(baseline)


def test_stage19as_au_db_preflight_redacts_config_and_performs_no_writes(monkeypatch):
    conn = FakeConn()
    args = expansion.parse_args([
        '--preflight-db',
        '--db-host',
        '127.0.0.1',
        '--db-port',
        '5432',
        '--db-name',
        'edfinder',
        '--db-user',
        'edfinder',
    ])
    env = {
        'POSTGRES_PASSWORD': 'do-not-print-this',
        'DATABASE_URL': 'postgresql://edfinder:do-not-print-this@127.0.0.1:5432/edfinder',
    }

    monkeypatch.setattr(expansion.pilot, 'connect_operator_db', lambda _dsn: conn)

    result = expansion.run_db_preflight(args, env=env)
    encoded = json.dumps(result, sort_keys=True)

    assert result['auth_success'] is True
    assert result['performed_no_writes'] is True
    assert result['secrets_redacted'] is True
    assert result['db_config'] == {
        'database_url_present': True,
        'host': '127.0.0.1',
        'port': '5432',
        'database': 'edfinder',
        'user': 'edfinder',
        'password_present': True,
        'password_value_printed': False,
        'secrets_file_detected': False,
        'secrets_file_used': False,
        'secrets_file_path': 'not reported',
        'secrets_file_tracked_by_git': False,
    }
    assert 'do-not-print-this' not in encoded
    assert 'postgresql://' not in encoded
    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert conn.source_runs == {}
    assert conn.legacy_rows == {}
    assert conn.staging_rows == {}


def test_stage19as_au_loads_untracked_secrets_file_without_printing_values(tmp_path, monkeypatch):
    secrets_path = tmp_path / 'stage19.env'
    secrets_path.write_text(
        'POSTGRES_PASSWORD=from-secret-file\n'
        'PGHOST=127.0.0.1\n'
        'PGPORT=5432\n'
        'PGDATABASE=edfinder\n'
        'PGUSER=edfinder\n',
        encoding='utf-8',
    )
    args = expansion.parse_args(['--secrets-file', str(secrets_path)])
    monkeypatch.delenv('POSTGRES_PASSWORD', raising=False)
    monkeypatch.delenv('PGHOST', raising=False)
    monkeypatch.delenv('PGPORT', raising=False)
    monkeypatch.delenv('PGDATABASE', raising=False)
    monkeypatch.delenv('PGUSER', raising=False)

    loaded = expansion.load_secrets_for_args(args)
    config = expansion.redacted_db_config(args, secrets=loaded)
    encoded = json.dumps({'loaded': loaded, 'config': config}, sort_keys=True)

    assert loaded['detected'] is True
    assert loaded['used'] is True
    assert loaded['tracked_by_git'] is False
    assert loaded['path'] == 'not reported'
    assert sorted(loaded['keys']) == ['PGDATABASE', 'PGHOST', 'PGPORT', 'PGUSER', 'POSTGRES_PASSWORD']
    assert config['password_present'] is True
    assert config['password_value_printed'] is False
    assert 'from-secret-file' not in encoded


def test_stage19as_au_db_preflight_reports_auth_failure_without_secret(monkeypatch):
    args = expansion.parse_args(['--preflight-db'])
    env = {'POSTGRES_PASSWORD': 'do-not-print-this'}

    def fail_connect(_dsn):
        raise RuntimeError('password authentication failed for user "edfinder"')

    monkeypatch.setattr(expansion.pilot, 'connect_operator_db', fail_connect)

    result = expansion.run_db_preflight(args, env=env)
    encoded = json.dumps(result, sort_keys=True)

    assert result['auth_success'] is False
    assert result['failure_category'] == 'password_authentication_failed'
    assert result['performed_no_writes'] is True
    assert result['secrets_redacted'] is True
    assert 'do-not-print-this' not in encoded


def test_stage19as_au_preflight_flag_exits_before_commit_path(monkeypatch, capsys):
    def fake_preflight(_args):
        return {
            'db_config': {
                'database_url_present': False,
                'host': '127.0.0.1',
                'port': '5432',
                'database': 'edfinder',
                'user': 'edfinder',
                'password_present': True,
                'password_value_printed': False,
            },
            'db_config_loaded': True,
            'auth_success': False,
            'performed_no_writes': True,
            'secrets_redacted': True,
            'failure_category': 'password_authentication_failed',
        }

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError('commit path must not run during DB preflight')

    monkeypatch.setattr(expansion, 'run_db_preflight', fake_preflight)
    monkeypatch.setattr(expansion.pilot, 'run_pilot', fail_if_called)

    exit_code = expansion.main(['--preflight-db', '--commit'])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert 'password_authentication_failed' in output
    assert 'password_value_printed' in output


def test_stage19as_au_committed_expansion_reuses_stage19ar_path_with_100_rows(tmp_path):
    conn = FakeConn(sample_rows=sample_staging_rows(100))

    result = rehearsal.run_pilot(
        conn,
        limit=100,
        artifact_dir=tmp_path,
        git_head='abc1234',
        trigger_context=expansion.STAGE19AS_AU_PROFILE.trigger_context,
        commit=True,
        generated_at=NOW,
        profile=expansion.STAGE19AS_AU_PROFILE,
    )

    assert result['commit_requested'] is True
    assert conn.commits == 1
    assert len(conn.source_runs) == 1
    assert len(conn.legacy_rows) == 1
    assert len(conn.staging_rows) == 100
    assert result['inserted_row_count'] == 100
    assert result['inserted_row_ids'] == list(range(901, 1001))
    assert result['source_run_key'].startswith('stage19as-au-edsm-100-row-controlled-expansion-')
    assert result['source_run_key'] != expansion.BASELINE_SOURCE_RUN_KEY
    assert result['bridge_key'] == f'source_runs:{result["source_run_key"]}'
    assert result['validation_checks']['exactly_100_staging_rows_inserted'] is True
    assert result['validation_checks']['exactly_100_staging_rows_marked_diagnostic'] is True
    assert result['validation_checks']['staging_rows_have_stage19as_au_marker'] is True
    assert result['validation_checks']['canonical_table_writes_performed_by_script'] is False
    assert all(row['source_run_id'] == 701 for row in conn.staging_rows.values())
    assert all(row['source_class'] == 'diagnostic-only' for row in conn.staging_rows.values())
    assert all(row['confidence'] == 'diagnostic-only' for row in conn.staging_rows.values())
    assert all(
        row['provenance']['stage19as_au_controlled_100_row_expansion']['source_run_key']
        == result['source_run_key']
        for row in conn.staging_rows.values()
    )
    bridge_metadata = next(iter(conn.legacy_rows.values()))['metadata']
    assert bridge_metadata['controlled_100_row_expansion'] is True
    assert bridge_metadata['baseline_source_run_key'] == expansion.BASELINE_SOURCE_RUN_KEY
    payload = result['operator_artifact_record']['payload']
    assert payload['schema_version'] == 'stage19as_au_edsm_100_row_controlled_expansion/v1'
    assert payload['inserted_row_count'] == 100


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


def test_static_import_call_uses_explicit_stage19ar_stager():
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
        any(keyword.arg == 'station_stager' for keyword in call.keywords)
        for call in calls
    )
    assert 'CompatibleStage19ArStationStager' in inspect.getsource(rehearsal)


def test_stage19_operator_modules_load_from_py_source_not_only_bytecode():
    for module in (rehearsal, expansion):
        module_file = Path(module.__file__)
        assert module_file.suffix == '.py'
        assert module_file.is_file()
    expansion_dsn_source = inspect.getsource(expansion.build_db_dsn)
    assert "source_env.get('PGPORT')" in expansion_dsn_source
    rehearsal_dsn_source = inspect.getsource(rehearsal.build_operator_dsn)
    assert "source_env.get('PGPORT')" in rehearsal_dsn_source


def test_stage19_preflight_reloaded_from_source_authenticates_without_bytecode(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        'stage19as_au_reloaded_from_source',
        Path(expansion.__file__),
    )
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)

    captured = {}

    class _Cursor:
        def execute(self, sql, params=None):
            captured['sql'] = ' '.join(sql.lower().split())

        def fetchone(self):
            return {'db_preflight_ok': 1}

        def close(self):
            pass

    class _Conn:
        def __init__(self):
            self.rollbacks = 0
            self.closed = False

        def cursor(self):
            return _Cursor()

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    conn = _Conn()
    monkeypatch.setattr(fresh.pilot, 'connect_operator_db', lambda _dsn: conn)
    args = fresh.parse_args(['--preflight-db', '--db-port', '55432'])
    env = {
        'PGPASSWORD': 'do-not-print-this',
        'PGHOST': '127.0.0.1',
        'PGPORT': '55432',
    }

    result = fresh.run_db_preflight(args, env=env)
    encoded = json.dumps(result, sort_keys=True)

    assert Path(fresh.__file__).suffix == '.py'
    assert result['auth_success'] is True
    assert result['performed_no_writes'] is True
    assert result['db_config']['host'] == '127.0.0.1'
    assert result['db_config']['port'] == '55432'
    assert captured['sql'] == 'select 1 as db_preflight_ok'
    assert conn.rollbacks == 1
    assert 'do-not-print-this' not in encoded


def test_stage19as_au_rejects_missing_canonical_baseline():
    conn = FakeConn()

    baseline = expansion.verify_canonical_stage19ar_baseline(conn)

    assert baseline['source_run'] is None
    assert baseline['bridge'] is None
    assert baseline['checks']['canonical_source_run_key_present'] is False
    assert baseline['checks']['canonical_bridge_key_present'] is False
    assert baseline['checks']['canonical_artifact_present'] is False
    assert baseline['checks']['canonical_25_rows_present'] is False
    with pytest.raises(rehearsal.Stage19ArPilotError, match='canonical Stage 19AR baseline is required'):
        expansion.assert_canonical_stage19ar_baseline(baseline)


def test_stage19ar_operator_dsn_honors_pg_env_for_isolated_db_port():
    args = rehearsal.parse_args([])
    assert args.db_port == '5432'
    env = {
        'PGPASSWORD': 'do-not-print-this',
        'PGHOST': '127.0.0.1',
        'PGPORT': '55432',
        'PGDATABASE': 'edfinder',
        'PGUSER': 'edfinder',
    }

    dsn = rehearsal.build_operator_dsn(args, env=env)

    assert 'host=127.0.0.1' in dsn
    assert 'port=55432' in dsn
    assert 'port=5432' not in dsn
    assert 'dbname=edfinder' in dsn


def test_stage19ar_operator_dsn_requires_a_password():
    args = rehearsal.parse_args([])
    with pytest.raises(
        rehearsal.Stage19ArPilotError,
        match='POSTGRES_PASSWORD or PGPASSWORD is required',
    ):
        rehearsal.build_operator_dsn(args, env={})
