from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE19BA_PATH = DOCS / 'stage-19-bounded-production-staging-activation.md'
STAGE19BB_PATH = DOCS / 'stage-19bb-first-production-staging-activation.md'
STAGE19BB_CLOSEOUT_PATH = DOCS / 'stage-19bb-production-staging-execution-closeout.md'
STAGE19_ROADMAP_PATH = DOCS / 'stage-19-data-warehouse-utopia-roadmap.md'
STAGE23_PATH = DOCS / 'stage-23-roadmap.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'
WRAPPER_PATH = ROOT / 'scripts' / 'operator' / 'stage19bb_first_production_staging_activation.py'
OPERATOR_README_PATH = ROOT / 'scripts' / 'operator' / 'README.md'

if str(WRAPPER_PATH.parent) not in sys.path:
    sys.path.insert(0, str(WRAPPER_PATH.parent))

import stage19bb_first_production_staging_activation as stage19bb  # noqa: E402


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def _approved_preview(limit: int) -> dict[str, object]:
    return {
        'snapshot_basename': stage19bb.APPROVED_SOURCE_BASENAME,
        'source_sha256': stage19bb.APPROVED_SOURCE_SHA256,
        'file_size_bytes': stage19bb.APPROVED_SOURCE_SIZE_BYTES,
        'file_format': {
            'source_format': stage19bb.APPROVED_SOURCE_FORMAT,
            'record_stream_shape': stage19bb.APPROVED_SOURCE_RECORD_STREAM_SHAPE,
        },
        'compression': stage19bb.APPROVED_SOURCE_COMPRESSION,
        'plan': {
            'rows_read': limit,
            'rows_staged': limit,
            'rows_rejected': 0,
            'rows_skipped': 0,
            'raw_records': [],
            'staged_rows': [],
            'warning_reason_counts': {},
            'rejection_reason_counts': {},
            'skipped_reason_counts': {},
        },
    }


def _approved_preflight() -> dict[str, object]:
    return {
        'identity': {
            'host': stage19bb.APPROVED_TARGET_HOST,
            'port': stage19bb.APPROVED_TARGET_PORT,
            'database': stage19bb.APPROVED_TARGET_DATABASE,
            'role': stage19bb.APPROVED_TARGET_ROLE,
        },
        'tables_present': list(stage19bb.PERMITTED_TABLES),
        'columns': dict(stage19bb.EXPECTED_COLUMNS),
        'indexes': dict(stage19bb.EXPECTED_INDEXES),
        'constraints': dict(stage19bb.EXPECTED_CONSTRAINTS),
        'canonical_tables_absent': True,
        'blocking_runs': 0,
        'loader_caps': {
            'rolcreatedb': 'false',
            'rolcreaterole': 'false',
            'rolsuper': 'false',
            'schema_create': 'false',
            'database_create': 'false',
        },
        'restricted_loader': True,
        'recomputed_target_fingerprint': stage19bb.APPROVED_TARGET_FINGERPRINT,
    }


@pytest.mark.unit
def test_stage19bb_authority_docs_and_indexes_record_exact_authorized_after_merge_boundary():
    authority = _json(AUTHORITY_PATH)
    checkpoint = authority['stage19bb_first_production_staging_activation']
    closeout = authority['stage19bb_execution_closeout']
    stage19ba = authority['stage19ba_bounded_production_staging_activation']
    readme = _read(README_PATH)
    operator_readme = _read(OPERATOR_README_PATH)
    stage19ba_doc = _read(STAGE19BA_PATH)
    stage19bb_doc = _read(STAGE19BB_PATH)
    stage19bb_closeout = _read(STAGE19BB_CLOSEOUT_PATH)
    stage19_roadmap = _read(STAGE19_ROADMAP_PATH)
    stage23 = _read(STAGE23_PATH)
    parity = _read(LOCAL_CI_PARITY)

    assert checkpoint['status'] == 'authorized_after_merge'
    assert checkpoint['approved_source_sha256'] == stage19bb.APPROVED_SOURCE_SHA256
    assert checkpoint['approved_source_size_bytes'] == stage19bb.APPROVED_SOURCE_SIZE_BYTES
    assert checkpoint['approved_eligible_source_rows'] == stage19bb.APPROVED_ELIGIBLE_SOURCE_ROWS
    assert checkpoint['previous_approved_source_sha256'] == '09225e43323464e332a792f8716a6e4264ef5999ce1544f1157bfc60f406f4a2'
    assert checkpoint['previous_approved_source_size_bytes'] == 2614426684
    assert checkpoint['source_refresh_reason'] == 'live EDSM dump rotated after PR #243 authorization'
    assert checkpoint['source_refresh_pr_required_before_execution'] is True
    assert checkpoint['approved_target_fingerprint'] == stage19bb.APPROVED_TARGET_FINGERPRINT
    assert checkpoint['target_type'] == stage19bb.APPROVED_TARGET_TYPE
    assert checkpoint['permitted_tables'] == stage19bb.PERMITTED_TABLES
    assert checkpoint['canonical_tables_absent'] is True
    assert checkpoint['restricted_loader_verified'] is True
    assert checkpoint['authorization_pr_contains_execution_evidence'] is False
    assert checkpoint['stage19_execution_performed'] is True
    assert checkpoint['staging_import_performed'] is True
    assert checkpoint['runtime_source_run_created'] is True
    assert checkpoint['runtime_artifact_created'] is True
    assert checkpoint['execution_closeout_prepared'] is True
    assert checkpoint['execution_closeout_document'] == str(STAGE19BB_CLOSEOUT_PATH.relative_to(ROOT))
    assert checkpoint['canonical_apply_authorized'] is False
    assert checkpoint['rebaseline_authorized'] is False
    assert checkpoint['scheduler_service_authorized'] is False

    assert closeout['status'] == 'completed'
    assert closeout['approved_source_sha256'] == stage19bb.APPROVED_SOURCE_SHA256
    assert closeout['approved_target_fingerprint'] == stage19bb.APPROVED_TARGET_FINGERPRINT
    assert closeout['permitted_tables'] == stage19bb.PERMITTED_TABLES
    assert [run['limit'] for run in closeout['runs']] == [100, 1000, 10000]
    assert all(run['rows_rejected'] == 0 for run in closeout['runs'])
    assert all(run['rows_skipped'] == 0 for run in closeout['runs'])
    assert all(run['verification_passed'] is True for run in closeout['runs'])
    assert closeout['only_permitted_tables_changed'] is True
    assert closeout['canonical_tables_absent_after_runs'] is True
    assert closeout['canonical_apply_performed'] is False
    assert closeout['rebaseline_performed'] is False
    assert closeout['scheduler_enabled'] is False
    assert closeout['production_automation_complete'] is False
    assert closeout['stage23b_dependency_satisfied'] is True
    assert closeout['stage23b_may_proceed_if_final_run_evidence_sufficient'] is True

    assert stage19ba['permitted_tables'] == [
        'source_runs',
        'enrichment_source_runs',
        'staging_edsm_stations',
    ]
    assert stage19ba['loader_support_tables_identified'] == [
        'enrichment_source_files',
        'enrichment_raw_records',
    ]
    assert stage19ba['historical_stage19ba_execution_authorized_for_five_tables'] is False

    assert 'stage-19bb-first-production-staging-activation.md' in readme
    assert 'stage-19bb-production-staging-execution-closeout.md' in readme
    assert 'stage19bb_first_production_staging_activation.py' in operator_readme
    assert 'stage-19bb-production-staging-execution-closeout.md' in operator_readme
    assert 'five-table' in stage19ba_doc
    assert 'authorized_after_merge' in stage19bb_doc
    assert stage19bb.APPROVED_SOURCE_SHA256 in stage19bb_doc
    assert 'live EDSM dump rotated after PR `#243`' in stage19bb_doc
    assert 'bounded production staging execution is complete' in stage19bb_closeout
    assert 'stage19bb-edsm-10000-row-bounded-staging-20260619T200018Z' in stage19bb_closeout
    assert stage19bb.APPROVED_TARGET_FINGERPRINT in stage19bb_doc
    assert 'formula mismatch' in stage19bb_doc
    assert 'Stage 19BB authorization dependency' in stage19_roadmap
    assert 'Stage 19BB bounded execution closeout' in stage19_roadmap
    assert 'source refresh reason' in stage19_roadmap
    assert 'Stage 19BB authorization' in stage23
    assert 'dependency is now' in stage23
    assert 'satisfied' in stage23
    assert 'tests/test_stage19bb_first_production_staging_activation.py' in parity


@pytest.mark.unit
def test_stage19bb_parse_requires_approved_limits_and_commit_confirmation():
    args = stage19bb.parse_args(['--limit', '100'])
    assert args.limit == 100
    assert args.commit is False
    assert args.confirm_stage19bb is False

    with pytest.raises(SystemExit):
        stage19bb.parse_args(['--limit', '250'])

    with pytest.raises(SystemExit):
        stage19bb.parse_args(['--limit', '100', '--commit'])


@pytest.mark.unit
def test_stage19bb_runtime_inputs_require_snapshot_dsn_and_external_artifact_dir(tmp_path: Path):
    snapshot = tmp_path / 'stations.json.gz'
    snapshot.write_bytes(b'{}')
    external_artifacts = tmp_path / 'external-artifacts'
    env = {
        'EDSM_STATION_SNAPSHOT': str(snapshot),
        'EDFINDER_STAGING_DSN': 'dsn-redacted',
        'SAFE_ARTIFACT_DIR': str(external_artifacts),
    }

    args = stage19bb.parse_args(['--limit', '100'])
    resolved = stage19bb.resolve_runtime_inputs(args, env=env)

    assert resolved['snapshot_display_name'] == 'stations.json.gz'
    assert resolved['artifact_dir'] == external_artifacts.resolve()

    with pytest.raises(stage19bb.Stage19BbActivationError):
        stage19bb.resolve_runtime_inputs(args, env={'EDFINDER_STAGING_DSN': 'dsn-redacted'})

    with pytest.raises(stage19bb.Stage19BbActivationError):
        stage19bb.resolve_runtime_inputs(
            stage19bb.parse_args(['--limit', '100', '--artifact-dir', str(ROOT / 'artifacts')]),
            env=env,
        )


@pytest.mark.unit
def test_stage19bb_source_preview_requires_exact_hash_format_and_no_malformed_rows():
    stage19bb.assert_source_preview_ok(_approved_preview(100), limit=100)

    bad_hash = _approved_preview(100)
    bad_hash['source_sha256'] = 'b' * 64
    with pytest.raises(stage19bb.Stage19BbActivationError, match='SHA-256 mismatch'):
        stage19bb.assert_source_preview_ok(bad_hash, limit=100)

    malformed = _approved_preview(100)
    malformed['plan']['rejection_reason_counts'] = {'invalid_station_snapshot_record': 1}
    with pytest.raises(stage19bb.Stage19BbActivationError, match='malformed rows'):
        stage19bb.assert_source_preview_ok(malformed, limit=100)


@pytest.mark.unit
def test_stage19bb_target_preflight_allows_only_exact_fingerprinted_localhost_target():
    approved = _approved_preflight()
    stage19bb.assert_target_preflight_ok(approved)

    mismatched = _approved_preflight()
    mismatched['recomputed_target_fingerprint'] = '0' * 64
    with pytest.raises(stage19bb.Stage19BbActivationError, match='arbitrary localhost targets|fingerprint mismatch'):
        stage19bb.assert_target_preflight_ok(mismatched)

    canonical_present = _approved_preflight()
    canonical_present['canonical_tables_absent'] = False
    with pytest.raises(stage19bb.Stage19BbActivationError, match='canonical application tables'):
        stage19bb.assert_target_preflight_ok(canonical_present)

    broad_loader = _approved_preflight()
    broad_loader['restricted_loader'] = False
    with pytest.raises(stage19bb.Stage19BbActivationError, match='restricted loader role'):
        stage19bb.assert_target_preflight_ok(broad_loader)

    schema_create = _approved_preflight()
    schema_create['loader_caps'] = {
        'rolcreatedb': 'false',
        'rolcreaterole': 'false',
        'rolsuper': 'false',
        'schema_create': 'true',
        'database_create': 'false',
    }
    with pytest.raises(stage19bb.Stage19BbActivationError, match='create schemas or tables'):
        stage19bb.assert_target_preflight_ok(schema_create)

    overlap = _approved_preflight()
    overlap['blocking_runs'] = 1
    with pytest.raises(stage19bb.Stage19BbActivationError, match='blocking Stage 19 source runs'):
        stage19bb.assert_target_preflight_ok(overlap)


@pytest.mark.unit
def test_stage19bb_execution_requires_merged_authority(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(stage19bb, 'load_authority', lambda: {
        'stage19bb_first_production_staging_activation': {
            'status': 'authorized_after_merge',
            'approved_source_sha256': stage19bb.APPROVED_SOURCE_SHA256,
            'approved_target_fingerprint': stage19bb.APPROVED_TARGET_FINGERPRINT,
        }
    })
    monkeypatch.setattr(stage19bb, 'verify_stage19bb_merged_to_origin_main', lambda: False)

    with pytest.raises(stage19bb.Stage19BbActivationError, match='merged authority'):
        stage19bb.ensure_execution_authorized_after_merge()


@pytest.mark.unit
def test_stage19bb_main_dry_run_keeps_output_sanitized_and_secret_free(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    args = stage19bb.parse_args(['--limit', '100'])
    runtime_inputs = {
        'snapshot_path': Path('/private/stage19/stations.json.gz'),
        'staging_dsn': 'REDACTED_STAGING_DSN_VALUE',
        'artifact_dir': Path('/private/artifacts'),
        'snapshot_display_name': 'stations.json.gz',
        'artifact_dir_display_name': 'artifacts',
    }
    preview = _approved_preview(100)
    preflight = _approved_preflight()

    monkeypatch.setattr(stage19bb, 'parse_args', lambda _argv=None: args)
    monkeypatch.setattr(stage19bb, 'resolve_runtime_inputs', lambda _args: runtime_inputs)
    monkeypatch.setattr(stage19bb, 'build_source_preview', lambda *_args, **_kwargs: preview)
    monkeypatch.setattr(stage19bb, 'assert_source_preview_ok', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stage19bb, 'run_target_preflight', lambda _dsn: preflight)
    monkeypatch.setattr(stage19bb, 'assert_target_preflight_ok', lambda _preflight: None)

    exit_code = stage19bb.main([])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload['mode'] == 'dry_run'
    assert payload['source']['reference'] == stage19bb.APPROVED_SOURCE_REFERENCE
    assert payload['source']['basename'] == stage19bb.APPROVED_SOURCE_BASENAME
    assert 'REDACTED_STAGING_DSN_VALUE' not in captured.out
    assert '/private/stage19' not in captured.out
    assert '/private/artifacts' not in captured.out
    assert captured.err == ''


@pytest.mark.unit
def test_stage19bb_script_source_blocks_scheduler_service_and_canonical_apply_paths():
    source = _read(WRAPPER_PATH)

    assert 'systemctl' not in source.lower()
    assert '.timer' not in source
    assert '.service' not in source
    assert 'scheduler_service_authorized' in source
    assert 'canonical_apply_authorized' in source
    assert 'rebaseline_authorized' in source
    assert "['git', 'merge-base', '--is-ancestor'" in source
