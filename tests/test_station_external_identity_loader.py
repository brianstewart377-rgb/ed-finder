import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import station_external_identity_loader as loader  # noqa: E402


GENERATED_AT = '2026-01-02T00:00:00Z'


def planned_row(index: int, **overrides):
    row = {
        'plan_row_id': f'plan-row-{index}',
        'candidate_id': f'candidate-{index}',
        'canonical_station_id': 2000 + index,
        'system_id64': 420000 + index,
        'station_name': f'Test Port {index}',
        'source': 'edsm_nightly_stations',
        'market_id': None,
        'edsm_station_id': 1000 + index,
        'source_run_key': 'run-key',
        'source_file_key': 'file-key',
        'source_record_hash': f'source-hash-{index}',
        'source_updated_at': '2026-01-02T00:00:00Z',
        'confidence': 'source_station_snapshot',
        'freshness_class': 'source_updated_at',
        'identity_status': 'confirmed',
        'conflict_reason': None,
        'match_basis': 'system_id64_normalized_station_name',
        'canonical_writes_planned': 0,
        'station_type_writes_planned': 0,
        'identity_rows_written': 0,
    }
    row.update(overrides)
    return row


def checks(**overrides):
    result = {
        'canonical_station_id_present': True,
        'system_id64_present': True,
        'station_name_present': True,
        'source_run_key_present': True,
        'source_file_key_present': True,
        'source_record_hash_present': True,
        'external_id_present': True,
        'identity_status_is_confirmed': True,
        'conflict_reason_is_null': True,
        'station_type_write_not_planned': True,
    }
    result.update(overrides)
    return result


def review_packet(rows):
    return {
        'schema_version': 'station_external_identity_review_packet/v1',
        'dry_run': True,
        'read_only': True,
        'report_only': True,
        'canonical_writes_planned': 0,
        'station_type_writes_planned': 0,
        'identity_rows_planned': len(rows),
        'identity_rows_written': 0,
        'approval_record_created': False,
        'max_planned_rows': 20,
        'source_artifact': {
            'artifact_type': 'station_external_identity_load_plan/v1',
            'basename': 'load-plan.json',
            'sha256': 'load-plan-sha',
        },
        'summary': {
            'planned_rows_count': len(rows),
            'manual_review_items_count': len(rows),
            'manual_review_status_counts': {'needs_manual_review': len(rows)},
            'canonical_writes_planned': 0,
            'station_type_writes_planned': 0,
            'identity_rows_written': 0,
            'approval_record_created': False,
        },
        'planned_rows': list(rows),
        'manual_review_items': [
            {
                'review_item_id': f'review-item-{index}',
                'planned_row_index': index,
                'review_status': 'needs_manual_review',
                'planned_row': row,
                'checks': checks(),
                'reviewer_notes': None,
            }
            for index, row in enumerate(rows, start=1)
        ],
    }


def approval_allowlist(packet_sha, *, review_item_ids=None, plan_row_ids=None):
    return {
        'schema_version': 'station_external_identity_load_approval_allowlist/v1',
        'review_packet_sha256': packet_sha,
        'approved_review_item_ids': list(review_item_ids or []),
        'approved_plan_row_ids': list(plan_row_ids or []),
        'reviewer': 'Synthetic Reviewer',
        'reviewed_at': '2026-01-02T00:00:00Z',
        'declaration': 'Synthetic fixture approval for station_external_identity rows only.',
    }


def write_json(tmp_path: Path, name: str, payload: dict) -> tuple[Path, str]:
    path = tmp_path / name
    text = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    path.write_text(text + '\n', encoding='utf-8')
    return path, hashlib.sha256((text + '\n').encode('utf-8')).hexdigest()


def build_plan(packet, *, max_rows=20, approval=None, write_reviewed=False, conn=None, packet_sha='packet-sha'):
    return loader.build_execution_plan(
        packet,
        review_packet_basename='packet.json',
        review_packet_sha256=packet_sha,
        review_packet_size_bytes=123,
        max_rows=max_rows,
        dry_run=not write_reviewed,
        write_reviewed=write_reviewed,
        approval_allowlist=approval,
        approval_allowlist_sha256='approval-sha' if approval else None,
        conn=conn,
        generated_at=GENERATED_AT,
    )


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.last_result = None

    def execute(self, sql, params=None):
        self.conn.statements.append((sql, tuple(params or ())))
        self.last_result = self.conn.insert_identity(tuple(params or ()))

    def fetchone(self):
        return self.last_result

    def close(self):
        self.conn.cursor_closed = True


class FakeConn:
    def __init__(self, *, existing_external_ids=None):
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.cursor_closed = False
        self.next_id = 100
        self.existing_external_ids = set(existing_external_ids or ())
        self.station_type_updates = []
        self.stations_updates = []

    def cursor(self):
        return FakeCursor(self)

    def insert_identity(self, params):
        source = params[3]
        market_id = params[4]
        edsm_station_id = params[5]
        key = (source, market_id, edsm_station_id)
        if key in self.existing_external_ids:
            return None
        self.existing_external_ids.add(key)
        row_id = self.next_id
        self.next_id += 1
        return (row_id,)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_dry_run_validates_good_review_packet():
    artifact = build_plan(review_packet([planned_row(1), planned_row(2)]))

    assert artifact['schema_version'] == 'station_external_identity_load_execution_plan/v1'
    assert artifact['dry_run'] is True
    assert artifact['write_reviewed'] is False
    assert artifact['identity_rows_selected'] == 2
    assert artifact['identity_rows_written'] == 0
    assert artifact['selected_review_item_ids'] == ['review-item-1', 'review-item-2']
    assert artifact['selected_plan_row_ids'] == ['plan-row-1', 'plan-row-2']


def test_dry_run_refuses_checksum_mismatch(tmp_path):
    path, _actual_sha = write_json(tmp_path, 'packet.json', review_packet([planned_row(1)]))

    with pytest.raises(loader.IdentityLoaderError, match='checksum mismatch'):
        loader.build_execution_plan_from_files(
            review_packet_path=path,
            expected_review_packet_sha256='0' * 64,
            max_rows=1,
            dry_run=True,
            write_reviewed=False,
            generated_at=GENERATED_AT,
        )


def test_dry_run_refuses_missing_planned_row():
    packet = review_packet([planned_row(1)])
    packet['manual_review_items'][0]['planned_row'] = None

    with pytest.raises(loader.IdentityLoaderError, match='missing planned_row'):
        build_plan(packet)


def test_dry_run_refuses_missing_checks():
    packet = review_packet([planned_row(1)])
    packet['manual_review_items'][0]['checks'] = {}

    with pytest.raises(loader.IdentityLoaderError, match='missing checks'):
        build_plan(packet)


def test_dry_run_refuses_failed_checks():
    packet = review_packet([planned_row(1)])
    packet['manual_review_items'][0]['checks']['external_id_present'] = False

    with pytest.raises(loader.IdentityLoaderError, match='failed required checks'):
        build_plan(packet)


def test_dry_run_refuses_non_confirmed_identity_status():
    row = planned_row(1, identity_status='proposed')
    packet = review_packet([row])

    with pytest.raises(loader.IdentityLoaderError, match='identity_status must be confirmed'):
        build_plan(packet)


def test_dry_run_refuses_non_null_conflict_reason():
    row = planned_row(1, conflict_reason='ambiguous_canonical_station_match')
    packet = review_packet([row])

    with pytest.raises(loader.IdentityLoaderError, match='conflict_reason must be null'):
        build_plan(packet)


def test_dry_run_refuses_missing_source_provenance():
    row = planned_row(1, source_record_hash='')
    packet = review_packet([row])

    with pytest.raises(loader.IdentityLoaderError, match='source_record_hash'):
        build_plan(packet)


def test_dry_run_refuses_missing_external_id():
    row = planned_row(1, market_id=None, edsm_station_id=None)
    packet = review_packet([row])

    with pytest.raises(loader.IdentityLoaderError, match='market_id or edsm_station_id'):
        build_plan(packet)


def test_parse_args_refuses_missing_max_rows():
    with pytest.raises(SystemExit):
        loader.parse_args([
            '--review-packet',
            'packet.json',
            '--expected-review-packet-sha256',
            'a' * 64,
            '--dsn',
            'dry-run-dsn',
            '--dry-run',
            '--output',
            'out.json',
        ])


def test_parse_args_refuses_max_rows_over_20():
    with pytest.raises(SystemExit):
        loader.parse_args([
            '--review-packet',
            'packet.json',
            '--expected-review-packet-sha256',
            'a' * 64,
            '--dsn',
            'dry-run-dsn',
            '--max-rows',
            '21',
            '--dry-run',
            '--output',
            'out.json',
        ])


@pytest.mark.parametrize(
    'flag',
    ['--write', '--apply', '--canonical-apply', '--station-type-dry-run', '--reconciliation', '--import', '--summarizer', '--commit'],
)
def test_forbidden_flags_are_rejected(flag):
    with pytest.raises(SystemExit):
        loader.parse_args([
            '--review-packet',
            'packet.json',
            '--expected-review-packet-sha256',
            'a' * 64,
            '--dsn',
            'dry-run-dsn',
            '--max-rows',
            '1',
            '--dry-run',
            '--output',
            'out.json',
            flag,
        ])


def test_dry_run_selects_only_up_to_max_rows():
    rows = [planned_row(1), planned_row(2), planned_row(3)]
    artifact = build_plan(review_packet(rows), max_rows=2)

    assert artifact['identity_rows_selected'] == 2
    assert artifact['selected_plan_row_ids'] == ['plan-row-1', 'plan-row-2']


def test_dry_run_output_keeps_write_counts_zero():
    artifact = build_plan(review_packet([planned_row(1)]))

    assert artifact['canonical_writes_planned'] == 0
    assert artifact['station_type_writes_planned'] == 0
    assert artifact['identity_rows_written'] == 0
    assert artifact['approval_record_created'] is False
    assert artifact['validation_summary']['canonical_writes_planned'] == 0
    assert artifact['validation_summary']['station_type_writes_planned'] == 0
    assert artifact['validation_summary']['identity_rows_written'] == 0
    assert artifact['validation_summary']['approval_record_created'] is False


def test_write_reviewed_requires_approval_allowlist():
    with pytest.raises(loader.IdentityLoaderError, match='approval allowlist'):
        build_plan(review_packet([planned_row(1)]), write_reviewed=True, conn=FakeConn())


def test_synthetic_local_write_inserts_only_selected_approved_rows():
    packet_sha = 'packet-sha'
    rows = [planned_row(1), planned_row(2)]
    approval = approval_allowlist(packet_sha, review_item_ids=['review-item-2'])
    conn = FakeConn()

    artifact = build_plan(
        review_packet(rows),
        write_reviewed=True,
        approval=approval,
        conn=conn,
        packet_sha=packet_sha,
    )

    assert artifact['dry_run'] is False
    assert artifact['write_reviewed'] is True
    assert artifact['identity_rows_selected'] == 1
    assert artifact['identity_rows_written'] == 1
    assert artifact['approval_record_created'] is False
    assert artifact['validation_summary']['approval_record_created'] is False
    assert artifact['selected_review_item_ids'] == ['review-item-2']
    assert artifact['selected_plan_row_ids'] == ['plan-row-2']
    assert artifact['inserted_row_ids'] == [100]
    assert conn.commits == 1


def test_synthetic_local_write_never_updates_stations_or_station_type():
    packet_sha = 'packet-sha'
    approval = approval_allowlist(packet_sha, review_item_ids=['review-item-1'])
    conn = FakeConn()

    build_plan(review_packet([planned_row(1)]), write_reviewed=True, approval=approval, conn=conn, packet_sha=packet_sha)

    assert conn.statements
    for sql, _params in conn.statements:
        normalized = ' '.join(sql.lower().split())
        assert normalized.startswith('insert into station_external_identity')
        assert 'update stations' not in normalized
        assert ' station_type' not in normalized
    assert conn.stations_updates == []
    assert conn.station_type_updates == []


def test_duplicate_insert_behavior_is_idempotent_skip():
    packet_sha = 'packet-sha'
    approval = approval_allowlist(packet_sha, review_item_ids=['review-item-1'])
    existing_key = ('edsm_nightly_stations', None, 1001)
    conn = FakeConn(existing_external_ids={existing_key})

    artifact = build_plan(review_packet([planned_row(1)]), write_reviewed=True, approval=approval, conn=conn, packet_sha=packet_sha)

    assert artifact['identity_rows_selected'] == 1
    assert artifact['identity_rows_written'] == 0
    assert artifact['validation_summary']['duplicate_rows_skipped'] == 1
    assert artifact['insert_results'][0]['inserted'] is False


def test_deterministic_json_output():
    packet = review_packet([planned_row(1)])
    first = build_plan(packet)
    second = build_plan(packet)

    assert loader.json_dumps_artifact(first) == loader.json_dumps_artifact(second)
    assert first['artifact_integrity']['canonical_json_sha256']
