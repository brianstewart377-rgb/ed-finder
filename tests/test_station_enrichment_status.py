import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
API_SRC = ROOT / 'apps' / 'api' / 'src'
FIXTURES = ROOT / 'tests' / 'fixtures'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

import station_enrichment_status as status  # noqa: E402
from enrichment_operator_status import (  # noqa: E402
    read_enrichment_status_snapshot,
    read_warehouse_status_snapshot,
)
from shared_contracts.enrichment_artifact_contracts import validate_warehouse_status_artifact  # noqa: E402


def write_checkpoint(path: Path, ids: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'processed_system_id64s': sorted(ids),
        'last_system_id64': max(ids) if ids else None,
    }
    path.write_text(json.dumps(payload), encoding='utf-8')


def write_report(
    path: Path,
    *,
    systems: list[dict] | None = None,
    metadata_updates: list[dict] | None = None,
    confirmed_links: list[dict] | None = None,
    conflicts: list[dict] | None = None,
    skipped: list[dict] | None = None,
    fetch_errors: list[dict] | None = None,
    systems_fetch_failed: list[dict] | None = None,
    suppressed_station_writes: list[dict] | None = None,
    ignored_transient_non_slot: list[dict] | None = None,
    dirty_planned: int = 0,
    dirty_marked: int = 0,
) -> None:
    systems = systems if systems is not None else [{'id64': 1, 'name': 'Alpha'}]
    metadata_updates = metadata_updates or []
    confirmed_links = confirmed_links or []
    conflicts = conflicts or []
    skipped = skipped or []
    fetch_errors = fetch_errors or []
    systems_fetch_failed = systems_fetch_failed or []
    suppressed_station_writes = suppressed_station_writes or []
    ignored_transient_non_slot = ignored_transient_non_slot or []
    payload = {
        'stations': {
            'systems': systems,
            'metadata_updates_planned': metadata_updates,
            'confirmed_link_updates_planned': confirmed_links,
            'conflicts': conflicts,
            'skipped': skipped,
            'fetch_errors': fetch_errors,
            'systems_fetch_failed': systems_fetch_failed,
            'counts': {},
            'station_writes_suppressed': suppressed_station_writes,
            'ignored_transient_non_slot': ignored_transient_non_slot,
        },
        'summary': {
            'systems_processed': len(systems),
            'stations': {
                'conflicts': len(conflicts),
                'skipped': len(skipped),
                'fetch_errors': len(fetch_errors),
                'systems_fetch_failed': len(systems_fetch_failed),
            },
            'dirty_systems_planned': dirty_planned,
            'dirty_systems_marked': dirty_marked,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')


def write_log(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def set_mtime(path: Path, value: float) -> None:
    os.utime(path, (value, value))


def test_status_reports_checkpoint_and_latest_run(tmp_path):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [10, 20, 30])

    output_root = tmp_path / 'runs'
    run_dir = output_root / '20260530-181500-all-records'
    batch_dir = run_dir / 'batch-0001'
    batch_dir.mkdir(parents=True)
    write_report(batch_dir / '01_initial_dryrun.json')

    args = status.parse_args([
        '--checkpoint-file', str(checkpoint),
        '--output-root', str(output_root),
        '--system-id64', '20',
    ])
    payload = status.build_status(args)

    assert payload['checkpoint']['exists'] is True
    assert payload['checkpoint']['valid'] is True
    assert payload['checkpoint']['processed_count'] == 3
    assert payload['checkpoint']['last_system_id64'] == 30
    assert payload['latest_run']['latest_all_records_output_dir'] == str(run_dir)
    assert payload['latest_batch']['path'] == str(batch_dir)
    assert payload['latest_batch']['number'] == 1
    assert payload['latest_report_summary']['systems_processed'] == 1
    assert payload['system_query']['is_checkpointed'] is True
    assert payload['system_query']['index'] == 1
    assert payload['system_query']['position'] == 2


def test_status_handles_missing_checkpoint(tmp_path):
    args = status.parse_args([
        '--checkpoint-file', str(tmp_path / 'missing.json'),
        '--root', str(tmp_path / 'no-runs'),
    ])
    payload = status.build_status(args)

    assert payload['checkpoint']['exists'] is False
    assert payload['checkpoint']['valid'] is False
    assert payload['checkpoint']['processed_count'] == 0
    assert payload['latest_run']['output_dir'] is None
    assert 'WARNING: checkpoint file missing' in payload['warnings']


def test_status_handles_invalid_checkpoint(tmp_path):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text('{not json', encoding='utf-8')

    args = status.parse_args([
        '--checkpoint-file', str(checkpoint),
        '--root', str(tmp_path / 'no-runs'),
    ])
    payload = status.build_status(args)

    assert payload['checkpoint']['exists'] is True
    assert payload['checkpoint']['valid'] is False
    assert 'invalid JSON' in payload['checkpoint']['error']
    assert 'WARNING: checkpoint file invalid' in payload['warnings']


def test_latest_all_record_run_and_batch_detection(tmp_path):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [1])
    output_root = tmp_path / 'runs'
    limit_run = output_root / '20260530-190000-limit-10'
    all_run_old = output_root / '20260530-180000-all-records'
    all_run_new = output_root / '20260530-200000-all-records'
    for run in (limit_run, all_run_old, all_run_new):
        run.mkdir(parents=True)
    batch_1 = all_run_new / 'batch-0001'
    batch_2 = all_run_new / 'batch-0002'
    batch_1.mkdir()
    batch_2.mkdir()
    write_report(batch_1 / '01_initial_dryrun.json')
    write_report(batch_2 / 'final_dryrun.json', systems=[{'id64': 1, 'name': 'Done'}])
    set_mtime(limit_run, 300)
    set_mtime(all_run_old, 100)
    set_mtime(all_run_new, 200)

    args = status.parse_args([
        '--checkpoint-file', str(checkpoint),
        '--root', str(output_root),
    ])
    payload = status.build_status(args)

    assert payload['latest_run']['latest_any_output_dir'] == str(limit_run)
    assert payload['latest_run']['latest_all_records_output_dir'] == str(all_run_new)
    assert payload['latest_run']['output_dir'] == str(all_run_new)
    assert payload['latest_batch']['path'] == str(batch_2)
    assert payload['latest_batch']['number'] == 2
    assert payload['latest_batch']['latest_phase_name'] == 'final dry-run'


def test_compact_report_summary_parsing(tmp_path):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [1])
    batch_dir = tmp_path / 'runs' / '20260530-181500-all-records' / 'batch-0001'
    report_path = batch_dir / '02_metadata_apply_1.json'
    write_report(
        report_path,
        systems=[{'id64': 1, 'name': 'Alpha'}, {'id64': 2, 'name': 'Beta'}],
        metadata_updates=[{'station_id': 1}],
        confirmed_links=[{'station_id': 2}],
        conflicts=[{'type': 'x'}],
        skipped=[{'reason': 'y'}],
        fetch_errors=[{'system': {'id64': 2, 'name': 'Beta'}}],
        systems_fetch_failed=[{'id64': 2, 'name': 'Beta'}],
        suppressed_station_writes=[{'station_id': 3}],
        ignored_transient_non_slot=[{'station': 'Carrier'}],
        dirty_planned=3,
        dirty_marked=2,
    )

    args = status.parse_args([
        '--checkpoint-file', str(checkpoint),
        '--root', str(tmp_path / 'runs'),
    ])
    payload = status.build_status(args)
    summary = payload['latest_report_summary']

    assert summary['systems_processed'] == 2
    assert summary['metadata_updates'] == 1
    assert summary['confirmed_links'] == 1
    assert summary['conflicts'] == 1
    assert summary['skipped'] == 1
    assert summary['fetch_errors'] == 1
    assert summary['systems_fetch_failed'] == 1
    assert summary['suppressed_station_writes'] == 1
    assert summary['ignored_transient_non_slot'] == 1
    assert summary['dirty_marked_planned'] == '2/3'
    assert 'WARNING: latest batch has fetch failures' in payload['warnings']


def test_progress_line_parsing_from_log(tmp_path):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [1])
    batch_dir = tmp_path / 'runs' / '20260530-181500-all-records' / 'batch-0001'
    write_report(batch_dir / '01_initial_dryrun.json', systems=[{'id64': 1, 'name': 'Alpha'}])
    log_file = tmp_path / 'station-enrichment.log'
    write_log(log_file, [
        '=== all-records batch 1 ===',
        'Station enrichment progress 1236/2000',
        "Station enrichment 1237/2000: system='Sol' id64=10477373803",
        'initial dry-run: systems_processed=1237 metadata_updates=0 confirmed_links=0 '
        'conflicts=0 skipped=0 fetch_errors=2 systems_fetch_failed=1 '
        'suppressed_station_writes=0 ignored_transient_non_slot=0 dirty_marked/planned=0/0 file=x',
    ])

    args = status.parse_args([
        '--checkpoint-file', str(checkpoint),
        '--root', str(tmp_path / 'runs'),
        '--log-file', str(log_file),
    ])
    payload = status.build_status(args)
    progress = payload['latest_progress']

    assert progress['latest_progress_counter_line'] == "Station enrichment 1237/2000: system='Sol' id64=10477373803"
    assert progress['counter'] == {'current': 1237, 'total': 2000}
    assert progress['batch_progress_percent'] == 61.9
    assert progress['latest_system_name'] == 'Sol'
    assert progress['latest_system_id64'] == 10477373803
    assert progress['fetch_errors'] == 2
    assert progress['systems_fetch_failed'] == 1


def test_429_retry_line_parsing_and_warning(tmp_path):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [1])
    batch_dir = tmp_path / 'runs' / '20260530-181500-all-records' / 'batch-0001'
    write_report(batch_dir / '01_initial_dryrun.json')
    log_file = tmp_path / 'station-enrichment.log'
    write_log(log_file, [
        "EDSM rate limit retry system='Achenar' id64=123 endpoint=stations "
        "next_attempt=2/5 reason=HTTP 429 Too Many Requests retry_after='2.5' backoff_seconds=5",
        "EDSM rate limit retry system='Achenar' id64=123 endpoint=stations "
        "next_attempt=3/5 reason=HTTP 429 Too Many Requests backoff_seconds=60",
        "EDSM rate limit retry system='Sol' id64=456 endpoint=stations "
        "next_attempt=4/5 reason=HTTP 429 Too Many Requests retry_after='120' backoff_seconds=120",
    ])

    args = status.parse_args([
        '--checkpoint-file', str(checkpoint),
        '--root', str(tmp_path / 'runs'),
        '--log-file', str(log_file),
    ])
    payload = status.build_status(args)
    rate = payload['rate_limit_summary']

    assert rate['recent_429_lines'] == 3
    assert rate['repeated_429_detected'] is True
    assert rate['most_recent_429_system'] == 'Sol'
    assert rate['most_recent_429_system_id64'] == 456
    assert rate['most_recent_retry_after'] == '120'
    assert rate['most_recent_backoff_seconds'] == 120.0
    assert 'WARNING: repeated EDSM 429 rate limits detected' in payload['warnings']


def test_interrupted_batch_detection(tmp_path):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [])
    batch_dir = tmp_path / 'runs' / '20260530-181500-all-records' / 'batch-0001'
    write_report(batch_dir / 'final_dryrun.json', systems=[{'id64': 99, 'name': 'Needs checkpoint'}])

    args = status.parse_args([
        '--checkpoint-file', str(checkpoint),
        '--root', str(tmp_path / 'runs'),
    ])
    payload = status.build_status(args)

    assert payload['latest_batch']['state'] == 'interrupted'
    assert 'WARNING: latest run appears interrupted before checkpoint update' in payload['warnings']
    assert 'WARNING: no checkpoint progress detected' in payload['warnings']


def test_completed_zero_successful_batch_warning(tmp_path):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [1])
    failed_system = {'id64': 2, 'name': 'Limited'}
    fetch_error = {'system': failed_system, 'message': 'HTTP 429 Too Many Requests', 'rate_limited': True}
    batch_dir = tmp_path / 'runs' / '20260530-181500-all-records' / 'batch-0001'
    write_report(
        batch_dir / '01_initial_dryrun.json',
        systems=[],
        fetch_errors=[fetch_error],
        systems_fetch_failed=[failed_system],
    )
    log_file = tmp_path / 'station-enrichment.log'
    write_log(log_file, [
        'all-records batch 1: checkpoint_added=0 checkpoint_total=1 fetch_failed_this_batch=1',
        'all-records aborted: every system in this batch hit a fetch/rate-limit error.',
    ])

    args = status.parse_args([
        '--checkpoint-file', str(checkpoint),
        '--root', str(tmp_path / 'runs'),
        '--log-file', str(log_file),
    ])
    payload = status.build_status(args)

    assert payload['latest_batch']['state'] == 'failed'
    assert 'WARNING: latest batch completed with zero successful systems' in payload['warnings']


def test_system_id64_not_checkpointed_returns_false(tmp_path):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [1, 2])
    args = status.parse_args([
        '--checkpoint-file', str(checkpoint),
        '--root', str(tmp_path),
        '--system-id64', '99',
    ])
    payload = status.build_status(args)

    assert payload['system_query']['is_checkpointed'] is False
    assert payload['system_query']['index'] is None
    assert 'may still be pending' in payload['system_query']['note']


@pytest.mark.parametrize('flag', [['--json'], []])
def test_status_main_emits_output(flag, tmp_path, capsys):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [42])
    rc = status.main([
        '--checkpoint-file', str(checkpoint),
        '--root', str(tmp_path / 'no-runs'),
        *flag,
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert '42' in out


def test_json_output_shape(tmp_path, capsys):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [42])
    batch_dir = tmp_path / 'runs' / '20260530-181500-all-records' / 'batch-0001'
    write_report(batch_dir / '01_initial_dryrun.json', systems=[{'id64': 42, 'name': 'Alpha'}])

    rc = status.main([
        '--checkpoint-file', str(checkpoint),
        '--root', str(tmp_path / 'runs'),
        '--system-id64', '42',
        '--json',
    ])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert set(payload) >= {
        'checkpoint',
        'latest_run',
        'latest_batch',
        'latest_report_summary',
        'latest_progress',
        'rate_limit_summary',
        'warnings',
        'system_query',
    }
    assert payload['system_query']['is_checkpointed'] is True


def test_operator_status_snapshot_sanitizes_paths_and_reports_counts(tmp_path):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [10, 20])
    failed_system = {'id64': 30, 'name': 'Limited'}
    fetch_error = {'system': failed_system, 'message': 'HTTP 429 Too Many Requests', 'rate_limited': True}
    batch_dir = tmp_path / 'runs' / '20260530-181500-all-records' / 'batch-0003'
    write_report(
        batch_dir / 'final_dryrun.json',
        systems=[{'id64': 20, 'name': 'Alpha'}],
        fetch_errors=[fetch_error],
        systems_fetch_failed=[failed_system],
        conflicts=[{'type': 'station_economy_mismatch'}],
    )
    log_file = tmp_path / 'station-enrichment.log'
    write_log(log_file, [
        '=== all-records batch 3 ===',
        "Station enrichment 7/10: system='Alpha' id64=20",
        "EDSM rate limit retry system='Limited' id64=30 endpoint=stations "
        "next_attempt=2/5 reason=HTTP 429 Too Many Requests backoff_seconds=60",
    ])
    args = status.parse_args([
        '--checkpoint-file', str(checkpoint),
        '--root', str(tmp_path / 'runs'),
        '--log-file', str(log_file),
        '--json',
    ])
    artifact = tmp_path / 'shared' / 'station-status.json'
    artifact.parent.mkdir()
    artifact.write_text(json.dumps(status.build_status(args)), encoding='utf-8')

    payload = read_enrichment_status_snapshot(str(artifact))
    rendered = json.dumps(payload, sort_keys=True)

    assert payload['available'] is True
    assert payload['checkpoint']['processed_count'] == 2
    assert payload['latest_batch']['number'] == 3
    assert payload['latest_report']['systems_processed'] == 1
    assert payload['latest_report']['systems_fetch_failed'] == 1
    assert payload['latest_report']['fetch_errors'] == 1
    assert payload['latest_report']['conflicts'] == 1
    assert payload['rate_limit']['recent_429_lines'] == 1
    assert payload['artifact']['file_name'] == 'station-status.json'
    assert payload['latest_batch']['latest_report_file_name'] == 'final_dryrun.json'
    assert str(tmp_path) not in rendered
    assert '/tmp/' not in rendered


def test_operator_status_snapshot_missing_or_invalid_keeps_unknown_values(tmp_path):
    not_configured = read_enrichment_status_snapshot(None)
    assert not_configured['available'] is False
    assert not_configured['state'] == 'not_configured'
    assert not_configured['checkpoint'] is None

    missing = read_enrichment_status_snapshot(str(tmp_path / 'missing.json'))
    assert missing['available'] is False
    assert missing['state'] == 'missing'
    assert missing['latest_report'] is None

    invalid = tmp_path / 'invalid.json'
    invalid.write_text('{not json', encoding='utf-8')
    invalid_payload = read_enrichment_status_snapshot(str(invalid))
    assert invalid_payload['available'] is False
    assert invalid_payload['state'] == 'invalid_json'
    assert invalid_payload['artifact']['file_name'] == 'invalid.json'
    assert str(tmp_path) not in json.dumps(invalid_payload)

    unsafe = tmp_path / 'unsafe.json'
    unsafe.write_text(json.dumps({
        'checkpoint': {
            'exists': True,
            'valid': False,
            'error': f'{tmp_path}/checkpoint.json',
        },
        'latest_report_summary': {
            'valid': False,
            'error': 'DATABASE_URL=postgresql://user:secret@example/db',
        },
        'warnings': [f'WARNING: checkpoint at {tmp_path}/checkpoint.json'],
    }), encoding='utf-8')
    unsafe_payload = read_enrichment_status_snapshot(str(unsafe))
    rendered_unsafe = json.dumps(unsafe_payload)
    assert unsafe_payload['available'] is True
    assert unsafe_payload['checkpoint']['error'] == 'unavailable'
    assert unsafe_payload['latest_report']['error'] == 'unavailable'
    assert unsafe_payload['warnings'] == ['unavailable']
    assert str(tmp_path) not in rendered_unsafe
    assert 'postgresql://' not in rendered_unsafe


def test_warehouse_status_snapshot_sanitizes_report_and_preserves_review_counts(tmp_path):
    artifact = tmp_path / 'shared' / 'warehouse-status.json'
    artifact.parent.mkdir()
    artifact.write_text(json.dumps({
        'schema_version': 'enrichment_staging_reconciliation/v1',
        'dry_run': True,
        'filters': {
            'source_run_key': 'run-warehouse',
            'source_file_key': 'file-warehouse',
            'source': 'edsm_nightly_stations',
            'limit': 1000,
        },
        'summary': {
            'staged_station_rows_considered': 12,
            'staged_body_rows_considered': 8,
            'staged_ring_rows_considered': 3,
            'canonical_matches_found': 10,
            'canonical_misses': 2,
            'ambiguous_matches': 1,
            'insufficient_evidence': 1,
            'warnings': 2,
            'errors': 0,
            'canonical_writes_planned': 0,
        },
        'source_coverage_summary': {
            'entities': {
                'station': {'candidates': 12},
                'body': {'candidates': 8},
                'ring': {'candidates': 3},
            },
            'ring_evidence': {
                'staged_ring_candidates': 3,
                'trusted_local_matched_ring_candidates': 1,
            },
        },
        'warehouse_coverage_report': {
            'schema_version': 'enrichment_warehouse_coverage_report/v1',
            'dry_run': True,
            'report_only': True,
            'canonical_writes_planned': 0,
            'summary': {
                'systems_with_station_evidence': 4,
                'systems_missing_station_evidence': 2,
                'trusted_ring_evidence_bodies': 1,
                'unknown_ring_evidence_bodies': 3,
                'explicit_no_ring_evidence_bodies': 1,
                'unresolved_stations': 5,
                'source_files_considered': 2,
                'malformed_or_skipped_source_rows': 6,
                'source_identity_conflicts': 2,
                'high_value_systems_needing_better_evidence': 3,
                'canonical_writes_planned': 0,
            },
            'operator_review': {
                'needs_attention_buckets': {
                    'stale_or_undated_sources': 7,
                    'duplicate_source_records': 4,
                    'source_identity_conflicts': 2,
                    'skipped_or_malformed_raw_records': 6,
                    'high_value_systems_needing_better_evidence': 3,
                },
            },
            'source_freshness': {
                'stale_or_undated_evidence': {
                    'records_without_source_updated_at': 7,
                    'file_snapshot_candidate_records': 2,
                },
            },
            'source_quality': {
                'malformed_or_skipped_source_rows': {'count': 6},
                'duplicate_source_records': {'duplicate_records': 4},
                'source_identity_conflicts': {'count': 2},
            },
            'source_formats': {
                'source_type_distribution': {'edsm_nightly_stations': 1},
                'source_format_distribution': {'json': 1},
            },
        },
        'confidence_risk_summary': {
            'risk_class_distribution': {
                'blocked': 2,
                'risky': 3,
                'stale': 4,
                'volatile': 1,
            },
        },
        'warnings': [
            {'reason': 'volatile_source_evidence_not_canonical_update'},
            f'{tmp_path}/unsafe-warning',
        ],
        'errors': [],
    }), encoding='utf-8')

    payload = read_warehouse_status_snapshot(str(artifact))
    rendered = json.dumps(payload, sort_keys=True)

    assert payload['available'] is True
    assert payload['state'] == 'blocked'
    assert payload['source'] == 'warehouse_reconciliation_status_json'
    assert payload['artifact']['file_name'] == 'warehouse-status.json'
    assert payload['latest_snapshot_load']['source_run_key'] == 'run-warehouse'
    assert payload['latest_reconciliation_run']['schema_version'] == 'enrichment_staging_reconciliation/v1'
    assert payload['latest_reconciliation_run']['coverage_schema_version'] == 'enrichment_warehouse_coverage_report/v1'
    assert payload['latest_reconciliation_run']['canonical_writes_planned'] == 0
    assert payload['source_coverage']['systems_with_station_evidence'] == 4
    assert payload['source_coverage']['systems_missing_station_evidence'] == 2
    assert payload['source_coverage']['trusted_ring_evidence_bodies'] == 1
    assert payload['evidence_health']['unresolved_stations'] == 5
    assert payload['evidence_health']['blocked_conflicts'] == 2
    assert payload['evidence_health']['risky_conflicts'] == 3
    assert payload['evidence_health']['stale_or_undated_source_records'] == 7
    assert payload['evidence_health']['duplicate_source_records'] == 4
    assert payload['evidence_health']['source_identity_conflicts'] == 2
    assert payload['canonical_safety'] == {
        'canonical_tables_untouched': True,
        'canonical_writes_planned': 0,
        'dry_run': True,
        'report_only': True,
    }
    assert payload['warnings'] == ['volatile_source_evidence_not_canonical_update', 'unavailable']
    assert str(tmp_path) not in rendered


def test_warehouse_status_snapshot_missing_invalid_and_unsafe_states(tmp_path):
    not_configured = read_warehouse_status_snapshot(None)
    assert not_configured['available'] is False
    assert not_configured['state'] == 'not_configured'
    assert not_configured['source_coverage'] is None

    missing = read_warehouse_status_snapshot(str(tmp_path / 'missing.json'))
    assert missing['available'] is False
    assert missing['state'] == 'missing'
    assert missing['latest_reconciliation_run'] is None

    invalid = tmp_path / 'invalid-warehouse.json'
    invalid.write_text('[1, 2, 3]', encoding='utf-8')
    invalid_payload = read_warehouse_status_snapshot(str(invalid))
    assert invalid_payload['available'] is False
    assert invalid_payload['state'] == 'invalid_json'
    assert invalid_payload['artifact']['file_name'] == 'invalid-warehouse.json'

    unsafe = tmp_path / 'unsafe-warehouse.json'
    unsafe.write_text(json.dumps({
        'schema_version': 'enrichment_staging_reconciliation/v1',
        'dry_run': True,
        'summary': {'canonical_writes_planned': 1},
        'source_coverage_summary': {},
        'warehouse_coverage_report': {},
        'confidence_risk_summary': {},
        'warnings': ['ok'],
        'errors': [],
    }), encoding='utf-8')
    unsafe_payload = read_warehouse_status_snapshot(str(unsafe))
    assert unsafe_payload['available'] is True
    assert unsafe_payload['state'] == 'unsafe'
    assert unsafe_payload['canonical_safety']['canonical_tables_untouched'] is False


def test_warehouse_status_shared_fixture_matches_contract_and_sanitizes(tmp_path):
    payload = json.loads(
        (FIXTURES / 'enrichment_staging_reconciliation_fixture.json').read_text(encoding='utf-8')
    )
    validate_warehouse_status_artifact(payload)

    artifact = tmp_path / 'shared' / 'warehouse-contract.json'
    artifact.parent.mkdir()
    artifact.write_text(json.dumps(payload), encoding='utf-8')

    sanitized = read_warehouse_status_snapshot(str(artifact))

    assert sanitized['available'] is True
    assert sanitized['latest_reconciliation_run']['schema_version'] == 'enrichment_staging_reconciliation/v1'
    assert sanitized['canonical_safety']['canonical_tables_untouched'] is True


def test_warehouse_status_contract_invalid_payload_is_rejected(tmp_path):
    artifact = tmp_path / 'shared' / 'warehouse-contract-invalid.json'
    artifact.parent.mkdir()
    artifact.write_text(json.dumps({'schema_version': 'enrichment_staging_reconciliation/v1'}), encoding='utf-8')

    payload = read_warehouse_status_snapshot(str(artifact))

    assert payload['available'] is False
    assert payload['state'] == 'invalid'
