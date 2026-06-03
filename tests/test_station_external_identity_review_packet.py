import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import station_external_identity_review_packet as review_packet  # noqa: E402


REQUIRED_PLANNED_ROW_FIELDS = {
    'canonical_station_id',
    'system_id64',
    'station_name',
    'source',
    'market_id',
    'edsm_station_id',
    'source_run_key',
    'source_file_key',
    'source_record_hash',
    'source_updated_at',
    'confidence',
    'freshness_class',
    'identity_status',
    'conflict_reason',
}

REQUIRED_CHECK_FIELDS = {
    'canonical_station_id_present',
    'system_id64_present',
    'station_name_present',
    'source_run_key_present',
    'source_file_key_present',
    'source_record_hash_present',
    'external_id_present',
    'identity_status_is_confirmed',
    'conflict_reason_is_null',
    'station_type_write_not_planned',
}


def planned_row(index: int) -> dict[str, object]:
    return {
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


def load_plan_artifact(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        'schema_version': 'station_external_identity_load_plan/v1',
        'generated_at': '2026-01-02T00:00:00Z',
        'tool': {
            'name': 'station_external_identity_load_plan',
            'version': 'v1',
        },
        'dry_run': True,
        'read_only': True,
        'report_only': True,
        'canonical_writes_planned': 0,
        'station_type_writes_planned': 0,
        'identity_rows_planned': len(rows),
        'identity_rows_written': 0,
        'max_rows': 20,
        'filters': {
            'source': 'edsm_nightly_stations',
            'source_run_key': 'run-key',
            'source_file_key': 'file-key',
            'sample_limit': 20,
        },
        'summary': {
            'total_candidates_seen': 298177,
            'eligible_confirmed_candidates_seen': 261938,
            'planned_rows_count': len(rows),
            'candidate_status_counts': {
                'proposed': 0,
                'confirmed_candidate': 261938,
                'conflicting': 258,
                'rejected': 35981,
            },
            'skipped_reason_counts': {
                'eligible_beyond_max_rows': 261918,
                'source_only_no_canonical_station_match': 35981,
                'ambiguous_canonical_station_match': 258,
            },
            'rejected_reason_counts': {
                'source_only_no_canonical_station_match': 35981,
            },
            'conflicting_reason_counts': {
                'ambiguous_canonical_station_match': 258,
            },
            'canonical_writes_planned': 0,
            'station_type_writes_planned': 0,
            'identity_rows_written': 0,
        },
        'planned_rows': rows,
        'artifact_integrity': {
            'hash_algorithm': 'sha256',
            'canonical_json_sha256': 'internal-integrity-sha',
        },
    }


def write_load_plan(tmp_path: Path, artifact: dict[str, object]) -> tuple[Path, str]:
    path = tmp_path / 'load-plan.json'
    payload = json.dumps(artifact, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    path.write_text(payload + '\n', encoding='utf-8')
    return path, hashlib.sha256((payload + '\n').encode('utf-8')).hexdigest()


def test_review_packet_verifies_source_artifact_sha(tmp_path):
    path, expected_sha = write_load_plan(tmp_path, load_plan_artifact([planned_row(1)]))

    artifact = review_packet.build_review_packet_from_file(path, expected_load_plan_sha256=expected_sha)

    assert artifact['schema_version'] == 'station_external_identity_review_packet/v1'
    assert artifact['source_artifact']['sha256'] == expected_sha
    assert artifact['source_artifact']['basename'] == 'load-plan.json'
    assert artifact['source_artifact']['artifact_integrity_sha256'] == 'internal-integrity-sha'


def test_checksum_mismatch_fails(tmp_path):
    path, _expected_sha = write_load_plan(tmp_path, load_plan_artifact([planned_row(1)]))

    with pytest.raises(review_packet.IdentityReviewPacketError, match='checksum mismatch'):
        review_packet.build_review_packet_from_file(path, expected_load_plan_sha256='0' * 64)


def test_missing_artifact_fails(tmp_path):
    missing_path = tmp_path / 'missing.json'

    with pytest.raises(review_packet.IdentityReviewPacketError, match='missing'):
        review_packet.build_review_packet_from_file(missing_path, expected_load_plan_sha256='0' * 64)


def test_max_planned_rows_over_20_fails():
    with pytest.raises(SystemExit):
        review_packet.parse_args([
            '--load-plan-artifact',
            'load-plan.json',
            '--expected-load-plan-sha256',
            '0' * 64,
            '--max-planned-rows',
            '21',
        ])


def test_dsn_is_rejected():
    with pytest.raises(SystemExit):
        review_packet.parse_args([
            '--load-plan-artifact',
            'load-plan.json',
            '--expected-load-plan-sha256',
            '0' * 64,
            '--dsn',
            'not-accepted',
        ])


@pytest.mark.parametrize('flag', ['--apply', '--write', '--write-staging', '--load', '--commit'])
def test_write_apply_load_commit_flags_are_rejected(flag):
    with pytest.raises(SystemExit):
        review_packet.parse_args([
            '--load-plan-artifact',
            'load-plan.json',
            '--expected-load-plan-sha256',
            '0' * 64,
            flag,
        ])


def test_planned_rows_are_capped(tmp_path):
    rows = [planned_row(1), planned_row(2), planned_row(3)]
    path, expected_sha = write_load_plan(tmp_path, load_plan_artifact(rows))

    artifact = review_packet.build_review_packet_from_file(
        path,
        expected_load_plan_sha256=expected_sha,
        max_planned_rows=2,
    )

    assert artifact['identity_rows_planned'] == 2
    assert artifact['summary']['planned_rows_available'] == 3
    assert artifact['summary']['planned_rows_included'] == 2
    assert artifact['summary']['planned_rows_capped'] is True
    assert [row['plan_row_id'] for row in artifact['planned_rows']] == ['plan-row-1', 'plan-row-2']
    assert len(artifact['manual_review_items']) == 2


def test_review_items_default_to_needs_manual_review(tmp_path):
    rows = [planned_row(1), planned_row(2)]
    path, expected_sha = write_load_plan(tmp_path, load_plan_artifact(rows))

    artifact = review_packet.build_review_packet_from_file(path, expected_load_plan_sha256=expected_sha)

    assert artifact['summary']['manual_review_status_counts'] == {'needs_manual_review': 2}
    for item in artifact['manual_review_items']:
        assert item['review_status'] == 'needs_manual_review'
        assert item['reviewer_notes'] is None


def test_each_manual_review_item_embeds_planned_row_and_checks(tmp_path):
    path, expected_sha = write_load_plan(tmp_path, load_plan_artifact([planned_row(1)]))

    artifact = review_packet.build_review_packet_from_file(path, expected_load_plan_sha256=expected_sha)
    review_item = artifact['manual_review_items'][0]

    assert review_item['planned_row_index'] == 1
    assert review_item['planned_row']
    assert review_item['planned_row'] == artifact['planned_rows'][0]
    assert review_item['checks']
    assert set(review_item['checks']) == REQUIRED_CHECK_FIELDS
    assert all(isinstance(value, bool) for value in review_item['checks'].values())


def test_planned_row_embedded_in_review_item_contains_reviewable_identity_fields(tmp_path):
    path, expected_sha = write_load_plan(tmp_path, load_plan_artifact([planned_row(1)]))

    artifact = review_packet.build_review_packet_from_file(path, expected_load_plan_sha256=expected_sha)
    row = artifact['manual_review_items'][0]['planned_row']

    assert REQUIRED_PLANNED_ROW_FIELDS <= set(row)
    assert row['canonical_station_id'] == 2001
    assert row['system_id64'] == 420001
    assert row['station_name'] == 'Test Port 1'
    assert row['source'] == 'edsm_nightly_stations'
    assert row['edsm_station_id'] == 1001
    assert row['source_run_key'] == 'run-key'
    assert row['source_file_key'] == 'file-key'
    assert row['source_record_hash'] == 'source-hash-1'
    assert row['confidence'] == 'source_station_snapshot'
    assert row['freshness_class'] == 'source_updated_at'
    assert row['identity_status'] == 'confirmed'
    assert row['conflict_reason'] is None


def test_review_checks_are_populated_correctly(tmp_path):
    path, expected_sha = write_load_plan(tmp_path, load_plan_artifact([planned_row(1)]))

    artifact = review_packet.build_review_packet_from_file(path, expected_load_plan_sha256=expected_sha)
    checks = artifact['manual_review_items'][0]['checks']

    assert checks == {
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


def test_top_level_planned_rows_match_embedded_manual_review_rows(tmp_path):
    rows = [planned_row(1), planned_row(2)]
    path, expected_sha = write_load_plan(tmp_path, load_plan_artifact(rows))

    artifact = review_packet.build_review_packet_from_file(path, expected_load_plan_sha256=expected_sha)
    embedded_rows = [item['planned_row'] for item in artifact['manual_review_items']]

    assert len(artifact['planned_rows']) == len(artifact['manual_review_items'])
    assert artifact['summary']['planned_rows_count'] == 2
    assert embedded_rows == artifact['planned_rows']


def test_safety_fields_remain_zero_or_false(tmp_path):
    path, expected_sha = write_load_plan(tmp_path, load_plan_artifact([planned_row(1)]))

    artifact = review_packet.build_review_packet_from_file(path, expected_load_plan_sha256=expected_sha)

    assert artifact['canonical_writes_planned'] == 0
    assert artifact['station_type_writes_planned'] == 0
    assert artifact['identity_rows_written'] == 0
    assert artifact['approval_record_created'] is False
    assert artifact['summary']['canonical_writes_planned'] == 0
    assert artifact['summary']['station_type_writes_planned'] == 0
    assert artifact['summary']['identity_rows_written'] == 0
    assert artifact['summary']['approval_record_created'] is False
    assert artifact['safety_boundaries']['db_connections_allowed'] is False
    assert artifact['safety_boundaries']['canonical_apply_allowed'] is False


def test_deterministic_json_output(tmp_path):
    path, expected_sha = write_load_plan(tmp_path, load_plan_artifact([planned_row(1)]))

    first = review_packet.build_review_packet_from_file(path, expected_load_plan_sha256=expected_sha)
    second = review_packet.build_review_packet_from_file(path, expected_load_plan_sha256=expected_sha)
    first_json = review_packet.json_dumps_artifact(first)
    second_json = review_packet.json_dumps_artifact(second)

    assert first_json == second_json
    assert json.loads(first_json) == first
    assert '\n' not in first_json
    assert first['artifact_integrity']['canonical_json_sha256']
