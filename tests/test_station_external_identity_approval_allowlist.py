import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import station_external_identity_approval_allowlist as allowlist  # noqa: E402
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
    packet = {
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
    packet['artifact_integrity'] = {
        'hash_algorithm': 'sha256',
        'canonical_json_sha256': 'review-packet-integrity',
    }
    return packet


def write_json(tmp_path: Path, name: str, payload: dict) -> tuple[Path, str]:
    path = tmp_path / name
    text = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    path.write_text(text + '\n', encoding='utf-8', newline='\n')
    return path, hashlib.sha256((text + '\n').encode('utf-8')).hexdigest()


def build_allowlist(packet, *, max_rows=20, reviewer_decision='approve_selected_identity_rows'):
    return allowlist.build_allowlist(
        packet,
        source_review_packet_basename='review-packet.json',
        source_review_packet_sha256='packet-sha',
        source_review_packet_size_bytes=123,
        max_rows=max_rows,
        reviewer='Synthetic Reviewer',
        reviewer_decision=reviewer_decision,
        generated_at=GENERATED_AT,
    )


def test_allowlist_verifies_review_packet_sha(tmp_path):
    path, packet_sha = write_json(tmp_path, 'packet.json', review_packet([planned_row(1)]))

    artifact = allowlist.build_allowlist_from_file(
        path,
        expected_review_packet_sha256=packet_sha,
        max_rows=1,
        reviewer='Synthetic Reviewer',
        generated_at=GENERATED_AT,
    )

    assert artifact['source_review_packet_sha256'] == packet_sha
    assert artifact['review_packet_sha256'] == packet_sha
    assert artifact['approved_review_item_ids'] == ['review-item-1']
    assert artifact['approved_plan_row_ids'] == ['plan-row-1']


def test_checksum_mismatch_fails(tmp_path):
    path, _packet_sha = write_json(tmp_path, 'packet.json', review_packet([planned_row(1)]))

    with pytest.raises(allowlist.IdentityApprovalAllowlistError, match='checksum mismatch'):
        allowlist.build_allowlist_from_file(
            path,
            expected_review_packet_sha256='0' * 64,
            max_rows=1,
            reviewer='Synthetic Reviewer',
            generated_at=GENERATED_AT,
        )


def test_missing_review_packet_fails(tmp_path):
    with pytest.raises(allowlist.IdentityApprovalAllowlistError, match='review packet is missing'):
        allowlist.build_allowlist_from_file(
            tmp_path / 'missing.json',
            expected_review_packet_sha256='0' * 64,
            max_rows=1,
            reviewer='Synthetic Reviewer',
            generated_at=GENERATED_AT,
        )


def test_missing_review_packet_integrity_fails():
    packet = review_packet([planned_row(1)])
    packet.pop('artifact_integrity')

    with pytest.raises(allowlist.IdentityApprovalAllowlistError, match='artifact_integrity'):
        build_allowlist(packet)


def test_missing_explicit_confirmation_fails():
    with pytest.raises(SystemExit):
        allowlist.parse_args([
            '--review-packet',
            'packet.json',
            '--expected-review-packet-sha256',
            'a' * 64,
            '--output',
            'out.json',
            '--reviewer-decision',
            'approve_selected_identity_rows',
            '--max-rows',
            '20',
        ])


def test_wrong_reviewer_decision_fails():
    with pytest.raises(SystemExit):
        allowlist.parse_args([
            '--review-packet',
            'packet.json',
            '--expected-review-packet-sha256',
            'a' * 64,
            '--output',
            'out.json',
            '--confirm-reviewed',
            '--reviewer-decision',
            'approve_canonical_apply',
            '--max-rows',
            '20',
        ])


def test_max_rows_over_20_fails():
    with pytest.raises(SystemExit):
        allowlist.parse_args([
            '--review-packet',
            'packet.json',
            '--expected-review-packet-sha256',
            'a' * 64,
            '--output',
            'out.json',
            '--confirm-reviewed',
            '--reviewer-decision',
            'approve_selected_identity_rows',
            '--max-rows',
            '21',
        ])


def test_dsn_is_rejected():
    with pytest.raises(SystemExit):
        allowlist.parse_args([
            '--review-packet',
            'packet.json',
            '--expected-review-packet-sha256',
            'a' * 64,
            '--output',
            'out.json',
            '--confirm-reviewed',
            '--reviewer-decision',
            'approve_selected_identity_rows',
            '--max-rows',
            '20',
            '--dsn',
            'not-accepted',
        ])


@pytest.mark.parametrize(
    'flag',
    [
        '--write',
        '--apply',
        '--load',
        '--commit',
        '--reconciliation',
        '--import',
        '--station-type',
        '--station-type-dry-run',
        '--canonical',
        '--canonical-apply',
        '--summarizer',
    ],
)
def test_forbidden_flags_are_rejected(flag):
    with pytest.raises(SystemExit):
        allowlist.parse_args([
            '--review-packet',
            'packet.json',
            '--expected-review-packet-sha256',
            'a' * 64,
            '--output',
            'out.json',
            '--confirm-reviewed',
            '--reviewer-decision',
            'approve_selected_identity_rows',
            '--max-rows',
            '20',
            flag,
        ])


def test_rows_are_capped_by_max_rows():
    packet = review_packet([planned_row(1), planned_row(2), planned_row(3)])

    artifact = build_allowlist(packet, max_rows=2)

    assert artifact['approved_rows_count'] == 2
    assert artifact['approved_review_item_ids'] == ['review-item-1', 'review-item-2']
    assert artifact['approved_plan_row_ids'] == ['plan-row-1', 'plan-row-2']


def test_planned_row_missing_fails():
    packet = review_packet([planned_row(1)])
    packet['manual_review_items'][0]['planned_row'] = None

    with pytest.raises(allowlist.IdentityApprovalAllowlistError, match='missing planned_row'):
        build_allowlist(packet)


def test_failed_item_checks_fail():
    packet = review_packet([planned_row(1)])
    packet['manual_review_items'][0]['checks']['external_id_present'] = False

    with pytest.raises(allowlist.IdentityApprovalAllowlistError, match='failed required checks'):
        build_allowlist(packet)


def test_missing_source_provenance_fails():
    row = planned_row(1, source_record_hash='')

    with pytest.raises(allowlist.IdentityApprovalAllowlistError, match='source_record_hash'):
        build_allowlist(review_packet([row]))


def test_missing_external_id_fails():
    row = planned_row(1, market_id=None, edsm_station_id=None)

    with pytest.raises(allowlist.IdentityApprovalAllowlistError, match='market_id or edsm_station_id'):
        build_allowlist(review_packet([row]))


def test_identity_status_not_confirmed_fails():
    row = planned_row(1, identity_status='proposed')

    with pytest.raises(allowlist.IdentityApprovalAllowlistError, match='identity_status must be confirmed'):
        build_allowlist(review_packet([row]))


def test_conflict_reason_non_null_fails():
    row = planned_row(1, conflict_reason='ambiguous_canonical_station_match')

    with pytest.raises(allowlist.IdentityApprovalAllowlistError, match='conflict_reason must be null'):
        build_allowlist(review_packet([row]))


def test_allowlist_emits_required_safety_fields():
    artifact = build_allowlist(review_packet([planned_row(1), planned_row(2)]), max_rows=2)

    assert artifact['schema_version'] == 'station_external_identity_load_approval_allowlist/v1'
    assert artifact['offline'] is True
    assert artifact['read_only'] is True
    assert artifact['approval_record_created'] is False
    assert artifact['identity_rows_written'] == 0
    assert artifact['canonical_writes_planned'] == 0
    assert artifact['station_type_writes_planned'] == 0
    assert artifact['approved_review_item_ids'] == ['review-item-1', 'review-item-2']
    assert artifact['approved_plan_row_ids'] == ['plan-row-1', 'plan-row-2']
    assert artifact['reviewer_attestation']['decision_scope'] == 'external_identity_evidence_load_only'
    assert artifact['reviewer_attestation']['does_not_approve_station_type_writes'] is True
    assert artifact['reviewer_attestation']['does_not_approve_canonical_apply'] is True
    assert artifact['safety_summary']['db_write_statements_included'] is False


def test_loader_accepts_allowlist_for_synthetic_write():
    packet_sha = 'packet-sha'
    packet = review_packet([planned_row(1)])
    approval = build_allowlist(packet, max_rows=1)

    artifact = loader.build_execution_plan(
        packet,
        review_packet_basename='packet.json',
        review_packet_sha256=packet_sha,
        review_packet_size_bytes=123,
        max_rows=1,
        dry_run=False,
        write_reviewed=True,
        approval_allowlist=approval,
        approval_allowlist_sha256='approval-sha',
        conn=_FakeConn(),
        generated_at=GENERATED_AT,
    )

    assert artifact['identity_rows_selected'] == 1
    assert artifact['identity_rows_written'] == 1


def test_deterministic_json_output():
    packet = review_packet([planned_row(1)])
    first = build_allowlist(packet)
    second = build_allowlist(packet)

    assert allowlist.json_dumps_artifact(first) == allowlist.json_dumps_artifact(second)
    assert first['artifact_integrity']['canonical_json_sha256']


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.last_result = None

    def execute(self, _sql, _params=None):
        self.last_result = self.conn.next_result()

    def fetchone(self):
        return self.last_result

    def close(self):
        pass


class _FakeConn:
    def __init__(self):
        self.next_id = 100

    def cursor(self):
        return _FakeCursor(self)

    def next_result(self):
        row_id = self.next_id
        self.next_id += 1
        return (row_id,)

    def commit(self):
        pass

    def rollback(self):
        pass
