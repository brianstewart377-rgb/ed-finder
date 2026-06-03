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

import station_external_identity_candidates as candidates  # noqa: E402


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
        'market_id': 1001,
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


def build_artifact(rows, *, sample_limit=100):
    return candidates.build_candidate_artifact_from_rows(
        rows,
        source_run_key='run-stations',
        source_file_key='file-stations',
        sample_limit=sample_limit,
        generated_at=GENERATED_AT,
    )


def test_single_canonical_match_yields_reviewable_confirmed_candidate():
    artifact = build_artifact([station_candidate_row()])

    assert artifact['schema_version'] == 'station_external_identity_candidates/v1'
    assert artifact['dry_run'] is True
    assert artifact['read_only'] is True
    assert artifact['canonical_writes_planned'] == 0
    assert artifact['station_type_writes_planned'] == 0
    assert artifact['identity_rows_written'] == 0
    assert artifact['summary']['candidate_status_counts']['confirmed_candidate'] == 1
    assert artifact['summary']['canonical_match_coverage']['canonical_station_match_count_1'] == 1

    sample = artifact['sample_candidates'][0]
    assert sample['candidate_status'] == 'confirmed_candidate'
    assert sample['proposed_identity_status'] == 'confirmed'
    assert sample['match_basis'] == 'system_id64_normalized_station_name'
    assert sample['canonical_match']['canonical_station_id'] == 2001
    assert sample['match_proof']['internal_station_id_not_used_as_external_proof'] is True
    assert sample['match_proof']['station_body_links_not_used_as_identity_proof'] is True


def test_zero_canonical_matches_yields_rejected_source_only_candidate():
    artifact = build_artifact([
        station_candidate_row(
            canonical_station_id=None,
            canonical_station_name=None,
            canonical_station_type=None,
            canonical_station_match_count=0,
        ),
    ])

    sample = artifact['sample_candidates'][0]
    assert sample['candidate_status'] == 'rejected'
    assert sample['proposed_identity_status'] == 'rejected'
    assert sample['rejection_reason'] == 'source_only_no_canonical_station_match'
    assert artifact['summary']['candidate_status_counts']['rejected'] == 1
    assert artifact['summary']['canonical_match_coverage']['canonical_station_match_count_0'] == 1


def test_multiple_canonical_matches_yields_conflicting_ambiguous_candidate():
    rows = [
        station_candidate_row(staging_station_id=1, canonical_station_id=2001, canonical_station_name='Test Port'),
        station_candidate_row(staging_station_id=1, canonical_station_id=2002, canonical_station_name='Test Port'),
    ]

    artifact = build_artifact(rows)

    sample = artifact['sample_candidates'][0]
    assert sample['candidate_status'] == 'conflicting'
    assert sample['proposed_identity_status'] == 'conflicting'
    assert sample['conflict_reason'] == 'ambiguous_canonical_station_match'
    assert len(sample['canonical_matches']) == 2
    assert artifact['summary']['candidate_status_counts']['conflicting'] == 1
    assert artifact['summary']['conflict_reason_counts'] == {'ambiguous_canonical_station_match': 1}
    assert artifact['summary']['canonical_match_coverage']['canonical_station_match_count_multiple'] == 1


def test_source_external_ids_and_provenance_are_preserved():
    artifact = build_artifact([
        station_candidate_row(
            market_id=987654,
            edsm_station_id=123456,
            source_record_hash='stable-hash',
            source_updated_at='2026-02-03T00:00:00Z',
        ),
    ])

    source = artifact['sample_candidates'][0]['source_identity']
    assert source['market_id'] == 987654
    assert source['edsm_station_id'] == 123456
    assert source['source_run_key'] == 'run-stations'
    assert source['source_file_key'] == 'file-stations'
    assert source['source_record_hash'] == 'stable-hash'
    assert source['source_updated_at'] == '2026-02-03T00:00:00Z'
    assert artifact['summary']['source_identity_coverage']['source_market_id_present'] == 1
    assert artifact['summary']['source_identity_coverage']['source_edsm_station_id_present'] == 1
    assert artifact['summary']['source_identity_coverage']['source_station_name_present'] == 1
    assert artifact['summary']['source_identity_coverage']['source_system_id64_present'] == 1


def test_build_candidate_artifact_from_db_is_read_only():
    conn = FakeConn([station_candidate_row()])

    artifact = candidates.build_candidate_artifact_from_db(
        conn,
        source_run_key='run-stations',
        source_file_key='file-stations',
        generated_at=GENERATED_AT,
    )

    assert artifact['summary']['candidate_status_counts']['confirmed_candidate'] == 1
    assert conn.statements
    for sql, _params in conn.statements:
        assert WRITE_SQL_RE.search(sql) is None
        assert 'station_external_identity' not in sql


def test_sample_candidates_are_capped():
    rows = [
        station_candidate_row(staging_station_id=1, source_record_hash='hash-1', canonical_station_id=2001),
        station_candidate_row(staging_station_id=2, source_record_hash='hash-2', canonical_station_id=2002),
        station_candidate_row(staging_station_id=3, source_record_hash='hash-3', canonical_station_id=2003),
    ]

    artifact = build_artifact(rows, sample_limit=2)

    assert artifact['summary']['total_staged_rows_inspected'] == 3
    assert artifact['summary']['sample_candidates_included'] == 2
    assert len(artifact['sample_candidates']) == 2


def test_candidate_json_is_deterministic_and_compact():
    rows = [station_candidate_row()]

    first = build_artifact(rows)
    second = build_artifact(rows)
    first_json = candidates.json_dumps_artifact(first)
    second_json = candidates.json_dumps_artifact(second)

    assert first_json == second_json
    assert json.loads(first_json) == first
    assert '\n' not in first_json
    assert 'artifact_integrity' in first
    assert first['artifact_integrity']['canonical_json_sha256']


@pytest.mark.parametrize('flag', ['--apply', '--write', '--write-staging', '--commit', '--load'])
def test_cli_rejects_write_apply_commit_aliases(flag):
    with pytest.raises(SystemExit):
        candidates.parse_args([
            '--dsn',
            'read-only-dsn',
            '--source-run-key',
            'run-stations',
            flag,
        ])


def test_synthetic_read_only_artifact_build_does_not_require_production_credentials():
    artifact = build_artifact([station_candidate_row()])

    assert artifact['filters']['source_run_key'] == 'run-stations'
    assert artifact['summary']['canonical_writes_planned'] == 0
    assert artifact['summary']['station_type_writes_planned'] == 0
    assert artifact['summary']['identity_rows_written'] == 0
