import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', '/dev/null')

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import station_external_identity_load_plan as load_plan  # noqa: E402


WRITE_SQL_RE = re.compile(r'\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER)\b', re.IGNORECASE)
GENERATED_AT = '2026-01-02T00:00:00Z'


class FakeCursor:
    def __init__(self, conn) -> None:
        self.conn = conn

    def execute(self, sql, params=None):
        self.conn.statements.append((sql, tuple(params or ())))

    def fetchall(self):
        return list(self.conn.rows)

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows) -> None:
        self.rows = list(rows)
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def cursor(self):
        return FakeCursor(self)


def station_candidate_row(**overrides):
    row = {
        'staging_station_id': 1,
        'source_run_key': 'run-stations',
        'source_file_key': 'file-stations',
        'source_record_key': 'station-record-key',
        'source_record_hash': 'station-hash',
        'system_id64': 42,
        'system_name': 'Test System',
        'market_id': None,
        'edsm_station_id': 1001,
        'station_name': 'Test Port',
        'source': 'edsm_nightly_stations',
        'source_class': 'semi-stable',
        'confidence': 'source_station_snapshot',
        'freshness_class': 'source_updated_at',
        'source_updated_at': datetime(2026, 1, 2, 0, 0, tzinfo=timezone.utc),
        'canonical_system_id64': 42,
        'canonical_system_name': 'Test System',
        'canonical_station_id': 2001,
        'canonical_station_name': 'Test Port',
        'canonical_station_type': 'Orbis',
        'canonical_station_match_count': 1,
    }
    row.update(overrides)
    return row


def build_plan(rows, *, max_rows=20, sample_limit=20, candidate_sha='candidate-sha'):
    return load_plan.build_load_plan_artifact_from_rows(
        rows,
        source_run_key='run-stations',
        source_file_key='file-stations',
        max_rows=max_rows,
        sample_limit=sample_limit,
        input_candidate_artifact_sha256=candidate_sha,
        generated_at=GENERATED_AT,
    )


def test_confirmed_candidate_becomes_planned_identity_row():
    artifact = build_plan([station_candidate_row()], max_rows=1)

    assert artifact['schema_version'] == 'station_external_identity_load_plan/v1'
    assert artifact['dry_run'] is True
    assert artifact['read_only'] is True
    assert artifact['report_only'] is True
    assert artifact['canonical_writes_planned'] == 0
    assert artifact['station_type_writes_planned'] == 0
    assert artifact['identity_rows_planned'] == 1
    assert artifact['identity_rows_written'] == 0
    assert artifact['summary']['eligible_confirmed_candidates_seen'] == 1
    assert artifact['summary']['planned_rows_count'] == 1

    row = artifact['planned_rows'][0]
    assert row['canonical_station_id'] == 2001
    assert row['system_id64'] == 42
    assert row['station_name'] == 'Test Port'
    assert row['source'] == 'edsm_nightly_stations'
    assert row['identity_status'] == 'confirmed'
    assert row['conflict_reason'] is None
    assert row['canonical_writes_planned'] == 0
    assert row['station_type_writes_planned'] == 0
    assert row['identity_rows_written'] == 0


def test_rejected_source_only_candidate_is_skipped():
    artifact = build_plan([
        station_candidate_row(
            canonical_station_id=None,
            canonical_station_name=None,
            canonical_station_type=None,
            canonical_station_match_count=0,
        ),
    ])

    assert artifact['identity_rows_planned'] == 0
    assert artifact['planned_rows'] == []
    assert artifact['summary']['candidate_status_counts']['rejected'] == 1
    assert artifact['summary']['skipped_reason_counts'] == {'source_only_no_canonical_station_match': 1}
    assert artifact['summary']['rejected_reason_counts'] == {'source_only_no_canonical_station_match': 1}
    assert artifact['sample_rejected_candidates'][0]['skip_reason'] == 'source_only_no_canonical_station_match'


def test_conflicting_ambiguous_candidate_is_skipped():
    rows = [
        station_candidate_row(staging_station_id=1, canonical_station_id=2001, canonical_station_name='Test Port'),
        station_candidate_row(staging_station_id=1, canonical_station_id=2002, canonical_station_name='Test Port'),
    ]

    artifact = build_plan(rows)

    assert artifact['identity_rows_planned'] == 0
    assert artifact['summary']['candidate_status_counts']['conflicting'] == 1
    assert artifact['summary']['skipped_reason_counts'] == {'ambiguous_canonical_station_match': 1}
    assert artifact['summary']['conflicting_reason_counts'] == {'ambiguous_canonical_station_match': 1}
    assert artifact['sample_conflicting_candidates'][0]['skip_reason'] == 'ambiguous_canonical_station_match'


def test_proposed_candidate_is_skipped_for_first_bounded_load_plan():
    artifact = build_plan([station_candidate_row(confidence='medium')])

    assert artifact['identity_rows_planned'] == 0
    assert artifact['summary']['candidate_status_counts']['proposed'] == 1
    assert artifact['summary']['skipped_reason_counts'] == {'proposed_candidate_not_planned': 1}


def test_planned_row_preserves_provenance_and_edsm_station_id():
    artifact = build_plan([
        station_candidate_row(
            market_id=None,
            edsm_station_id=123456,
            source_record_hash='stable-hash',
            source_updated_at='2026-02-03T00:00:00Z',
        ),
    ])

    row = artifact['planned_rows'][0]
    assert row['source_run_key'] == 'run-stations'
    assert row['source_file_key'] == 'file-stations'
    assert row['source_record_hash'] == 'stable-hash'
    assert row['source_updated_at'] == '2026-02-03T00:00:00Z'
    assert row['market_id'] is None
    assert row['edsm_station_id'] == 123456
    assert row['confidence'] == 'source_station_snapshot'
    assert row['freshness_class'] == 'source_updated_at'


def test_planned_row_includes_market_id_when_present():
    artifact = build_plan([station_candidate_row(market_id=987654, edsm_station_id=None)])

    row = artifact['planned_rows'][0]
    assert row['market_id'] == 987654
    assert row['edsm_station_id'] is None


def test_max_rows_is_required_by_cli():
    with pytest.raises(SystemExit):
        load_plan.parse_args([
            '--dsn',
            'read-only-dsn',
            '--source-run-key',
            'run-stations',
        ])


def test_max_rows_above_first_run_cap_is_rejected():
    with pytest.raises(SystemExit):
        load_plan.parse_args([
            '--dsn',
            'read-only-dsn',
            '--source-run-key',
            'run-stations',
            '--max-rows',
            str(load_plan.MAX_ROWS_CAP + 1),
        ])


def test_max_rows_bounds_planned_rows_without_writes():
    rows = [
        station_candidate_row(staging_station_id=1, source_record_hash='hash-1', canonical_station_id=2001),
        station_candidate_row(staging_station_id=2, source_record_hash='hash-2', canonical_station_id=2002),
        station_candidate_row(staging_station_id=3, source_record_hash='hash-3', canonical_station_id=2003),
    ]

    artifact = build_plan(rows, max_rows=2)

    assert artifact['summary']['eligible_confirmed_candidates_seen'] == 3
    assert artifact['identity_rows_planned'] == 2
    assert len(artifact['planned_rows']) == 2
    assert artifact['summary']['skipped_reason_counts']['eligible_beyond_max_rows'] == 1
    assert artifact['identity_rows_written'] == 0


def test_build_load_plan_artifact_from_db_is_read_only_and_does_not_target_identity_table():
    conn = FakeConn([station_candidate_row()])

    artifact = load_plan.build_load_plan_artifact_from_db(
        conn,
        source_run_key='run-stations',
        source_file_key='file-stations',
        max_rows=1,
        generated_at=GENERATED_AT,
    )

    assert artifact['identity_rows_planned'] == 1
    assert conn.statements
    for sql, _params in conn.statements:
        assert WRITE_SQL_RE.search(sql) is None
        assert 'station_external_identity' not in sql


@pytest.mark.parametrize('flag', ['--apply', '--write', '--write-staging', '--commit', '--load'])
def test_cli_rejects_write_apply_load_commit_aliases(flag):
    with pytest.raises(SystemExit):
        load_plan.parse_args([
            '--dsn',
            'read-only-dsn',
            '--source-run-key',
            'run-stations',
            '--max-rows',
            '1',
            flag,
        ])


def test_load_plan_json_is_deterministic_and_compact():
    rows = [station_candidate_row()]

    first = build_plan(rows)
    second = build_plan(rows)
    first_json = load_plan.json_dumps_artifact(first)
    second_json = load_plan.json_dumps_artifact(second)

    assert first_json == second_json
    assert json.loads(first_json) == first
    assert '\n' not in first_json
    assert first['artifact_integrity']['canonical_json_sha256']


def test_rejected_and_conflicting_samples_are_capped():
    rows = [
        station_candidate_row(staging_station_id=1, canonical_station_id=None, canonical_station_name=None),
        station_candidate_row(staging_station_id=2, canonical_station_id=None, canonical_station_name=None),
        station_candidate_row(staging_station_id=3, canonical_station_id=3001),
        station_candidate_row(staging_station_id=3, canonical_station_id=3002),
        station_candidate_row(staging_station_id=4, canonical_station_id=4001),
        station_candidate_row(staging_station_id=4, canonical_station_id=4002),
    ]

    artifact = build_plan(rows, sample_limit=1)

    assert artifact['summary']['sample_rejected_candidates_included'] == 1
    assert artifact['summary']['sample_conflicting_candidates_included'] == 1
    assert len(artifact['sample_rejected_candidates']) == 1
    assert len(artifact['sample_conflicting_candidates']) == 1
