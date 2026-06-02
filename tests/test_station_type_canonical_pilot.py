import json
import os
import sys
import hashlib
import subprocess
from pathlib import Path

import pytest


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', '/dev/null')

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import station_type_canonical_pilot as pilot  # noqa: E402
from enrichment_reconciliation import station_body_association_candidates  # noqa: E402


def report_with(*candidates):
    return {
        'schema_version': 'enrichment_staging_reconciliation/v1',
        'dry_run': True,
        'filters': {
            'source_run_key': 'run-1',
            'source_file_key': 'file-1',
            'source': 'edsm_nightly_stations',
        },
        'summary': {
            'canonical_writes_planned': 0,
        },
        'station_candidates': list(candidates),
    }


def station_candidate(**overrides):
    candidate = {
        'entity': 'station',
        'candidate_action': 'candidate_update',
        'source': {
            'source_run_key': 'run-1',
            'source_file_key': 'file-1',
            'source_record_key': 'record-1',
            'source_record_hash': 'hash-1',
            'system_id64': 424242,
            'system_name': 'Test System',
            'market_id': 1001,
            'edsm_station_id': None,
            'station_name': 'Harper Plant',
            'source': 'edsm_nightly_stations',
            'source_class': 'semi-stable',
            'confidence': 'source_station_snapshot',
            'freshness_class': 'source_updated_at',
            'source_updated_at': '2026-05-31T12:00:00Z',
        },
        'canonical': {
            'system_id64': 424242,
            'system_name': 'Test System',
            'station_id': 900001,
            'market_id': 1001,
            'edsm_station_id': None,
            'station_name': 'Harper Plant',
            'station_type': 'Unknown',
        },
        'canonical_matches': [
            {
                'system_id64': 424242,
                'system_name': 'Test System',
                'station_id': 900001,
                'market_id': 1001,
                'edsm_station_id': None,
                'station_name': 'Harper Plant',
                'station_type': 'Unknown',
            }
        ],
        'differences': [
            {
                'field': 'station_type',
                'staged': 'Orbis Starport',
                'canonical': 'Unknown',
            }
        ],
        'warnings': [],
        'confidence': 'high',
        'risk_class': 'clear',
        'risk_flags': [],
        'review_classifications': [],
        'reconciliation_state': 'confirmed',
        'source_freshness': {
            'freshness_class': 'source_updated_at',
            'source_updated_at': '2026-05-31T12:00:00Z',
            'freshness_impact': 'timestamped_source',
        },
        'report_only': True,
        'canonical_writes_planned': 0,
    }
    _deep_update(candidate, overrides)
    return candidate


def test_dry_run_builds_deterministic_station_type_artifact():
    report = report_with(station_candidate())

    first = pilot.build_station_type_pilot_dry_run(
        report,
        generated_at='2026-06-01T00:00:00Z',
        git_commit='abc123',
    )
    second = pilot.build_station_type_pilot_dry_run(
        report,
        generated_at='2026-06-01T00:00:00Z',
        git_commit='abc123',
    )

    assert first == second
    assert first['schema_version'] == 'station_type_canonical_pilot_dry_run/v1'
    assert first['dry_run'] is True
    assert first['pilot_scope']['canonical_table'] == 'stations'
    assert first['pilot_scope']['canonical_field'] == 'station_type'
    assert first['pilot_scope']['apply_requires_separate_guarded_mode'] is True
    assert first['summary']['total_candidates_seen'] == 1
    assert first['summary']['eligible_station_type_updates'] == 1
    assert first['summary']['canonical_writes_planned'] == 0
    assert first['summary']['dry_run_only'] is True
    assert first['summary']['apply_run'] is False
    assert first['summary']['approval_record_created'] is False
    candidate = first['eligible_candidates'][0]
    assert candidate['canonical_table'] == 'stations'
    assert candidate['field'] == 'station_type'
    assert candidate['old_value'] == 'Unknown'
    assert candidate['new_value'] == 'Orbis'
    assert candidate['match_proof']['identifier_match_type'] == 'market_id'
    assert candidate['rollback_pre_image']['pre_image_value'] == 'Unknown'
    assert first['artifact_integrity']['canonical_json_sha256'] == pilot.artifact_sha256(first)


def test_blocks_name_only_or_missing_stable_station_identifier():
    report = report_with(station_candidate(source={'market_id': None, 'edsm_station_id': None}))

    artifact = pilot.build_station_type_pilot_dry_run(report, generated_at='2026-06-01T00:00:00Z')

    assert artifact['summary']['eligible_candidates'] == 0
    assert artifact['summary']['rejected_missing_external_identity'] == 1
    assert artifact['summary']['rejection_reason_counts']['rejected_missing_external_identity'] == 1


def test_blocks_internal_station_pk_match_without_canonical_external_identity():
    candidate = station_candidate(
        source={'market_id': 900001, 'edsm_station_id': None},
        canonical={'market_id': None, 'edsm_station_id': None},
        canonical_matches=[{
            'system_id64': 424242,
            'system_name': 'Test System',
            'station_id': 900001,
            'station_name': 'Harper Plant',
            'station_type': 'Unknown',
        }],
    )

    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(candidate),
        generated_at='2026-06-01T00:00:00Z',
    )

    assert artifact['summary']['eligible_candidates'] == 0
    blocked = artifact['blocked_candidates'][0]
    assert 'rejected_missing_external_identity' in blocked['rejection_reasons']
    assert blocked['canonical']['station_id'] == 900001
    assert blocked['canonical']['market_id'] is None
    assert blocked['match_proof']['source_market_id'] == 900001
    assert blocked['match_proof']['canonical_market_id'] is None


def test_blocks_internal_station_pk_match_when_canonical_external_identity_differs():
    candidate = station_candidate(
        source={'market_id': 900001, 'edsm_station_id': None},
        canonical={'station_id': 900001, 'market_id': 1001, 'edsm_station_id': None},
        canonical_matches=[{
            'system_id64': 424242,
            'system_name': 'Test System',
            'station_id': 900001,
            'market_id': 1001,
            'edsm_station_id': None,
            'station_name': 'Harper Plant',
            'station_type': 'Unknown',
        }],
    )

    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(candidate),
        generated_at='2026-06-01T00:00:00Z',
    )

    assert artifact['summary']['eligible_candidates'] == 0
    blocked = artifact['blocked_candidates'][0]
    assert 'rejected_missing_external_identity' in blocked['rejection_reasons']
    assert blocked['match_proof']['source_market_id'] == 900001
    assert blocked['match_proof']['canonical_market_id'] == 1001


def test_allows_edsm_station_id_external_identity_match():
    candidate = station_candidate(
        source={'market_id': None, 'edsm_station_id': 1001},
        canonical={'market_id': None, 'edsm_station_id': 1001},
        canonical_matches=[{
            'system_id64': 424242,
            'system_name': 'Test System',
            'station_id': 900001,
            'market_id': None,
            'edsm_station_id': 1001,
            'station_name': 'Harper Plant',
            'station_type': 'Unknown',
        }],
    )

    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(candidate),
        generated_at='2026-06-01T00:00:00Z',
    )

    assert artifact['summary']['eligible_candidates'] == 1
    assert artifact['eligible_candidates'][0]['match_proof']['identifier_match_type'] == 'edsm_station_id'


@pytest.mark.parametrize(
    'overrides,reason',
    [
        ({'canonical_matches': []}, 'rejected_ambiguous_identity'),
        ({'canonical_matches': [{'station_id': 1001}, {'station_id': 1002}]}, 'rejected_ambiguous_identity'),
        ({'candidate_action': 'ambiguous_match'}, 'rejected_ambiguous_identity'),
        ({'candidate_action': 'candidate_insert_missing_canonical'}, 'rejected_source_only_insert'),
        ({'source': {'system_id64': 999}}, 'rejected_missing_external_identity'),
        ({'source': {'station_name': 'Wrong Name'}}, 'rejected_missing_external_identity'),
        ({'differences': [{'field': 'station_type', 'staged': 'Fleet Carrier', 'canonical': 'Unknown'}]}, 'rejected_transient_non_slot'),
        ({'differences': [{'field': 'station_type', 'staged': 'MegaShip', 'canonical': 'Unknown'}]}, 'rejected_transient_non_slot'),
        ({'canonical': {'station_type': 'Coriolis'}}, 'rejected_ineligible_canonical_old_value'),
        ({'risk_flags': ['volatile_source_evidence']}, 'rejected_volatile_evidence'),
        ({'source': {'source_class': 'volatile'}}, 'rejected_volatile_evidence'),
        ({'source_freshness': {'freshness_impact': 'undated_source_review'}}, 'rejected_freshness'),
        ({'differences': []}, 'rejected_missing_station_type_delta'),
        ({'differences': [
            {'field': 'station_type', 'staged': 'Orbis Starport', 'canonical': 'Unknown'},
            {'field': 'distance_to_arrival', 'staged': 12.0, 'canonical': None},
        ]}, 'rejected_non_station_type_change'),
    ],
)
def test_blocks_unsafe_candidate_states(overrides, reason):
    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(station_candidate(**overrides)),
        generated_at='2026-06-01T00:00:00Z',
    )

    assert artifact['summary']['eligible_candidates'] == 0
    assert artifact['summary']['blocked_by_reason'][reason] == 1
    assert artifact['blocked_candidates'][0]['rejection_reasons'][0].startswith('rejected_')


def test_missing_station_body_name_does_not_block_external_station_type_update():
    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(station_candidate(
            risk_class='blocked',
            risk_flags=['missing_station_body_name', 'canonical_difference_review'],
            review_classifications=['blocked', 'report_only', 'source_only', 'unknown'],
        )),
        generated_at='2026-06-01T00:00:00Z',
    )

    assert artifact['summary']['eligible_station_type_updates'] == 1
    assert artifact['eligible_candidates'][0]['source_reconciliation']['risk_flags'] == [
        'canonical_difference_review',
        'missing_station_body_name',
    ]
    assert artifact['summary']['canonical_writes_planned'] == 0


def test_missing_station_body_name_remains_station_body_link_blocker():
    association_candidates = station_body_association_candidates([station_candidate()], [])

    assert len(association_candidates) == 1
    candidate = association_candidates[0]
    assert candidate['entity'] == 'station_body_association'
    assert candidate['candidate_action'] == 'station_body_name_missing'
    assert candidate['canonical_link_writes_planned'] == 0
    assert 'missing_station_body_name' in candidate['risk_flags']
    assert 'blocked' in candidate['review_classifications']


def test_requires_explicit_max_row_bound():
    with pytest.raises(pilot.Stage18JPlanError, match='max-row bound'):
        pilot.build_station_type_pilot_dry_run(
            report_with(station_candidate()),
            limit=None,
            generated_at='2026-06-01T00:00:00Z',
        )


def test_summary_contains_strict_rejection_reason_counts():
    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(
            station_candidate(source={'market_id': None, 'edsm_station_id': None}),
            station_candidate(candidate_action='candidate_insert_missing_canonical'),
            station_candidate(risk_flags=['volatile_source_evidence']),
        ),
        generated_at='2026-06-01T00:00:00Z',
    )

    assert artifact['summary']['total_candidates_seen'] == 3
    assert artifact['summary']['eligible_station_type_updates'] == 0
    assert artifact['summary']['canonical_writes_planned'] == 0
    assert artifact['summary']['rejected_missing_external_identity'] == 1
    assert artifact['summary']['rejected_source_only_insert'] == 1
    assert artifact['summary']['rejected_volatile_evidence'] == 1
    assert artifact['summary']['rejection_reason_counts']['rejected_missing_external_identity'] == 1


def test_compact_mode_caps_blocked_samples_but_keeps_full_counts():
    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(
            station_candidate(source={'source_record_key': 'record-eligible', 'source_record_hash': 'hash-eligible'}),
            station_candidate(source={'source_record_key': 'record-missing-id', 'source_record_hash': 'hash-missing-id', 'market_id': None, 'edsm_station_id': None}),
            station_candidate(source={'source_record_key': 'record-volatile', 'source_record_hash': 'hash-volatile'}, risk_flags=['volatile_source_evidence']),
            station_candidate(source={'source_record_key': 'record-source-only', 'source_record_hash': 'hash-source-only'}, candidate_action='candidate_insert_missing_canonical'),
        ),
        limit=1,
        blocked_candidate_sample_limit=2,
        reconciliation_artifact_sha256='source-sha',
        reconciliation_artifact_basename='reconciliation.json',
        reconciliation_artifact_size_bytes=123,
        generated_at='2026-06-01T00:00:00Z',
    )

    assert artifact['summary']['total_candidates_seen'] == 4
    assert artifact['summary']['eligible_station_type_updates'] == 1
    assert artifact['summary']['eligible_candidates'] == 1
    assert len(artifact['eligible_candidates']) == 1
    assert artifact['summary']['blocked_candidates'] == 3
    assert artifact['summary']['blocked_candidate_samples_included'] == 2
    assert artifact['summary']['blocked_candidate_sample_limit'] == 2
    assert artifact['summary']['blocked_candidate_samples_omitted'] == 1
    assert len(artifact['blocked_candidates']) == 2
    assert artifact['summary']['rejected_missing_external_identity'] == 1
    assert artifact['summary']['rejected_volatile_evidence'] == 1
    assert artifact['summary']['rejected_source_only_insert'] == 1
    assert artifact['source_scope']['input_artifact_sha256'] == 'source-sha'
    assert artifact['source_scope']['input_artifact_basename'] == 'reconciliation.json'
    assert artifact['source_scope']['input_artifact_size_bytes'] == 123


def test_blocked_candidate_sample_limit_zero_keeps_counts_without_samples():
    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(
            station_candidate(source={'market_id': None, 'edsm_station_id': None}),
            station_candidate(risk_flags=['volatile_source_evidence']),
        ),
        limit=1,
        blocked_candidate_sample_limit=0,
        generated_at='2026-06-01T00:00:00Z',
    )

    assert artifact['summary']['blocked_candidates'] == 2
    assert artifact['summary']['blocked_candidate_samples_included'] == 0
    assert artifact['summary']['blocked_candidate_samples_omitted'] == 2
    assert artifact['blocked_candidates'] == []
    assert artifact['summary']['rejected_missing_external_identity'] == 1
    assert artifact['summary']['rejected_volatile_evidence'] == 1


def test_blocked_candidate_sample_limit_must_be_non_negative():
    with pytest.raises(pilot.Stage18JPlanError, match='sample limit'):
        pilot.build_station_type_pilot_dry_run(
            report_with(station_candidate(source={'market_id': None, 'edsm_station_id': None})),
            blocked_candidate_sample_limit=-1,
            generated_at='2026-06-01T00:00:00Z',
        )


def test_limit_exclusion_is_reported_as_rejection_reason():
    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(
            station_candidate(source={'source_record_key': 'record-1', 'source_record_hash': 'hash-1'}),
            station_candidate(source={'source_record_key': 'record-2', 'source_record_hash': 'hash-2'}),
        ),
        limit=1,
        generated_at='2026-06-01T00:00:00Z',
    )

    assert artifact['summary']['eligible_station_type_updates'] == 1
    assert artifact['summary']['rejected_by_max_row_bound'] == 1
    assert artifact['blocked_candidates'][0]['eligible_if_limit_allows'] is True


def test_cli_rejects_unsupported_write_commit_flags():
    for flag in ('--write', '--commit'):
        with pytest.raises(SystemExit):
            pilot.parse_args([
                '--reconciliation-report',
                'report.json',
                flag,
            ])


def test_cli_apply_requires_full_explicit_approval_contract():
    with pytest.raises(SystemExit):
        pilot.parse_args(['--apply', '--artifact', 'artifact.json'])

    args = pilot.parse_args([
        '--apply',
        '--artifact',
        'artifact.json',
        '--artifact-sha256',
        'abc',
        '--expected-candidate-count',
        '1',
        '--approved-table',
        'stations',
        '--approved-field',
        'station_type',
        '--approved-source-run',
        'run-1',
        '--approval-id',
        'approval-1',
        '--max-rows',
        '1',
        '--dsn',
        'postgresql://apply/test',
        '--confirm-station-type-canonical-pilot',
    ])
    assert args.apply is True
    assert args.confirm_station_type_canonical_pilot is True


def test_cli_writes_dry_run_json_artifact(tmp_path):
    report_path = tmp_path / 'reconciliation.json'
    output_path = tmp_path / 'stage18j.json'
    report_path.write_text(json.dumps(report_with(station_candidate())), encoding='utf-8')

    result = pilot.main([
        '--reconciliation-report',
        str(report_path),
        '--output',
        str(output_path),
        '--limit',
        '1',
    ])

    assert result == 0
    payload = json.loads(output_path.read_text(encoding='utf-8'))
    assert payload['schema_version'] == 'station_type_canonical_pilot_dry_run/v1'
    assert payload['summary']['eligible_candidates'] == 1
    assert payload['summary']['canonical_writes_planned'] == 0
    assert payload['summary']['blocked_candidate_sample_limit'] == 100
    assert payload['source_scope']['input_artifact_basename'] == 'reconciliation.json'
    assert payload['source_scope']['input_artifact_sha256'] == _file_sha256(report_path)
    assert payload['source_scope']['input_artifact_size_bytes'] == report_path.stat().st_size


def test_cli_quiet_writes_without_stdout_and_respects_blocked_sample_limit(tmp_path, capsys):
    report_path = tmp_path / 'reconciliation.json'
    output_path = tmp_path / 'stage18j.json'
    report_path.write_text(json.dumps(report_with(
        station_candidate(source={'market_id': None, 'edsm_station_id': None}),
        station_candidate(risk_flags=['volatile_source_evidence']),
    )), encoding='utf-8')

    result = pilot.main([
        '--reconciliation-report',
        str(report_path),
        '--output',
        str(output_path),
        '--limit',
        '1',
        '--blocked-candidate-sample-limit',
        '1',
        '--quiet',
    ])

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding='utf-8'))
    assert result == 0
    assert captured.out == ''
    assert payload['summary']['blocked_candidates'] == 2
    assert payload['summary']['blocked_candidate_samples_included'] == 1
    assert len(payload['blocked_candidates']) == 1


def test_cli_dry_run_rejects_dsn_and_does_not_invoke_apply(tmp_path, monkeypatch):
    report_path = tmp_path / 'reconciliation.json'
    output_path = tmp_path / 'stage18j.json'
    report_path.write_text(json.dumps(report_with(station_candidate())), encoding='utf-8')

    def fail_apply(*_args, **_kwargs):
        raise AssertionError('apply path must not be invoked during dry-run')

    monkeypatch.setattr(pilot, 'apply_station_type_pilot', fail_apply)

    assert pilot.main([
        '--reconciliation-report',
        str(report_path),
        '--output',
        str(output_path),
        '--limit',
        '1',
    ]) == 0
    with pytest.raises(SystemExit):
        pilot.parse_args([
            '--reconciliation-report',
            str(report_path),
            '--dsn',
            'postgresql://dry-run/test',
        ])


def test_operator_station_type_dry_run_script_is_syntax_valid_and_guarded():
    script = ROOT / 'scripts' / 'operator' / 'stage18j_run_station_type_dry_run.sh'

    subprocess.run(['bash', '-n', str(script)], check=True)
    text = script.read_text(encoding='utf-8')
    assert 'scripts/operator/require_hetzner_operator_env.sh' in text
    assert '--apply' not in text
    assert '--dsn' not in text
    assert '--limit "$MAX_ROWS"' in text
    assert '--blocked-candidate-sample-limit "$BLOCKED_CANDIDATE_SAMPLE_LIMIT"' in text
    assert 'MAX_ROWS > 20' in text
    assert '[[ ! -s "$RECON_ARTIFACT" ]]' in text
    assert 'checksum mismatch' in text
    assert 'canonical_writes_planned_zero' in text
    assert 'approval_record_created_false' in text


def test_validate_apply_request_fails_closed_on_mismatched_approval_parameters():
    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(station_candidate()),
        generated_at='2026-06-01T00:00:00Z',
    )
    checksum = pilot.artifact_sha256(artifact)

    with pytest.raises(pilot.Stage18JPlanError, match='confirmation'):
        pilot.validate_apply_request(
            artifact,
            artifact_sha256_expected=checksum,
            expected_candidate_count=1,
            approved_table='stations',
            approved_field='station_type',
            approved_source_run='run-1',
            approval_id='approval-1',
            confirmation=False,
        )
    with pytest.raises(pilot.Stage18JPlanError, match='checksum'):
        pilot.validate_apply_request(
            artifact,
            artifact_sha256_expected='bad-sha',
            expected_candidate_count=1,
            approved_table='stations',
            approved_field='station_type',
            approved_source_run='run-1',
            approval_id='approval-1',
            confirmation=True,
        )
    with pytest.raises(pilot.Stage18JPlanError, match='approved field'):
        pilot.validate_apply_request(
            artifact,
            artifact_sha256_expected=checksum,
            expected_candidate_count=1,
            approved_table='stations',
            approved_field='body_name',
            approved_source_run='run-1',
            approval_id='approval-1',
            confirmation=True,
        )
    with pytest.raises(pilot.Stage18JPlanError, match='max rows'):
        pilot.validate_apply_request(
            artifact,
            artifact_sha256_expected=checksum,
            expected_candidate_count=1,
            approved_table='stations',
            approved_field='station_type',
            approved_source_run='run-1',
            approval_id='approval-1',
            confirmation=True,
        )


def test_guarded_apply_updates_only_station_type_and_emits_audit_rollback_and_verification():
    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(station_candidate()),
        generated_at='2026-06-01T00:00:00Z',
    )
    checksum = pilot.artifact_sha256(artifact)
    conn = FakeApplyConn({(900001, 424242): {'id': 900001, 'system_id64': 424242, 'name': 'Harper Plant', 'station_type': 'Unknown'}})

    audit = pilot.apply_station_type_pilot(
        conn,
        artifact,
        artifact_sha256_expected=checksum,
        expected_candidate_count=1,
        approved_table='stations',
        approved_field='station_type',
        approved_source_run='run-1',
        approved_source_file='file-1',
        approval_id='approval-1',
        confirmation=True,
        max_rows=1,
        apply_run_id='apply-1',
        generated_at='2026-06-01T00:00:00Z',
    )

    assert conn.rows[(900001, 424242)]['station_type'] == 'Orbis'
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert audit['schema_version'] == 'station_type_canonical_pilot_apply/v1'
    assert audit['summary']['applied'] == 1
    assert audit['rows'][0]['field'] == 'station_type'
    assert audit['rollback_preimage']['schema_version'] == 'station_type_canonical_pilot_rollback_preimage/v1'
    assert audit['rollback_preimage']['rows'][0]['pre_image_value'] == 'Unknown'
    assert audit['post_apply_verification']['schema_version'] == 'station_type_canonical_pilot_verification/v1'
    assert audit['post_apply_verification']['summary']['ok'] is True
    sql_text = '\n'.join(sql for sql, _params in conn.statements)
    assert 'UPDATE stations' in sql_text
    assert 'SET station_type' in sql_text
    assert 'distance_from_star' not in sql_text
    assert 'station_body_links' not in sql_text


def test_guarded_apply_rolls_back_when_preimage_changed():
    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(station_candidate()),
        generated_at='2026-06-01T00:00:00Z',
    )
    checksum = pilot.artifact_sha256(artifact)
    conn = FakeApplyConn({(900001, 424242): {'id': 900001, 'system_id64': 424242, 'name': 'Harper Plant', 'station_type': 'Coriolis'}})

    with pytest.raises(pilot.Stage18JPlanError, match='pre-image mismatch'):
        pilot.apply_station_type_pilot(
            conn,
            artifact,
            artifact_sha256_expected=checksum,
            expected_candidate_count=1,
            approved_table='stations',
            approved_field='station_type',
            approved_source_run='run-1',
            approval_id='approval-1',
            confirmation=True,
            max_rows=1,
        )

    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert conn.rows[(900001, 424242)]['station_type'] == 'Coriolis'


def test_guarded_apply_rolls_back_when_identity_preimage_changed():
    artifact = pilot.build_station_type_pilot_dry_run(
        report_with(station_candidate()),
        generated_at='2026-06-01T00:00:00Z',
    )
    checksum = pilot.artifact_sha256(artifact)
    conn = FakeApplyConn({(900001, 424242): {'id': 900001, 'system_id64': 424242, 'name': 'Renamed Plant', 'station_type': 'Unknown'}})

    with pytest.raises(pilot.Stage18JPlanError, match='identity pre-image mismatch'):
        pilot.apply_station_type_pilot(
            conn,
            artifact,
            artifact_sha256_expected=checksum,
            expected_candidate_count=1,
            approved_table='stations',
            approved_field='station_type',
            approved_source_run='run-1',
            approval_id='approval-1',
            confirmation=True,
            max_rows=1,
        )

    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert conn.rows[(900001, 424242)]['station_type'] == 'Unknown'


class FakeApplyConn:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeApplyCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeApplyCursor:
    description = None

    def __init__(self, conn):
        self.conn = conn
        self.last_row = None
        self.closed = False

    def execute(self, sql, params=None):
        self.conn.statements.append((sql, params or ()))
        sql_lower = ' '.join(sql.lower().split())
        if sql_lower.startswith('select id, system_id64'):
            station_id, system_id64 = params
            self.last_row = dict(self.conn.rows.get((station_id, system_id64))) if (station_id, system_id64) in self.conn.rows else None
            return
        if sql_lower.startswith('update stations'):
            new_value, station_id, system_id64, old_value = params
            row = self.conn.rows.get((station_id, system_id64))
            if row is None or row.get('station_type') != old_value:
                self.last_row = None
                return
            row['station_type'] = new_value
            self.last_row = dict(row)
            return
        raise AssertionError(f'unexpected SQL: {sql}')

    def fetchone(self):
        return self.last_row

    def close(self):
        self.closed = True


def _deep_update(target, overrides):
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
