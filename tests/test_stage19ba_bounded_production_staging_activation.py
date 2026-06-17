from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE17P_PATH = DOCS / 'stage-17p-current-state-forward-plan.md'
STAGE19_ROADMAP_PATH = DOCS / 'stage-19-data-warehouse-utopia-roadmap.md'
STAGE19BA_PATH = DOCS / 'stage-19-bounded-production-staging-activation.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'
WRAPPER_PATH = ROOT / 'scripts' / 'operator' / 'stage19ba_bounded_production_staging_activation.py'
OPERATOR_README_PATH = ROOT / 'scripts' / 'operator' / 'README.md'

if str(WRAPPER_PATH.parent) not in sys.path:
    sys.path.insert(0, str(WRAPPER_PATH.parent))

import stage19ba_bounded_production_staging_activation as stage19ba  # noqa: E402


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def _valid_argv(tmp_path: Path) -> list[str]:
    return [
        '--source-batch-label',
        'edsm-nightly-20260618',
        '--source-uri',
        'https://example.invalid/edsm/stations-20260618.json.gz?token=secret#fragment',
        '--source-sha256',
        'a' * 64,
        '--limit',
        '100',
        '--timeout-seconds',
        '900',
        '--artifact-dir',
        str(tmp_path / 'artifacts'),
        '--target-label',
        'production_staging_only',
        '--db-host',
        'staging-db.internal',
        '--db-port',
        '6432',
        '--db-name',
        'warehouse_stage19',
        '--db-user',
        'stage19_loader',
    ]


@pytest.mark.unit
def test_stage19ba_authority_prepares_a_bounded_non_executing_staging_activation_baseline():
    authority = _json(AUTHORITY_PATH)
    stage19 = authority['stage19']
    stage19ba_authority = authority['stage19ba_bounded_production_staging_activation']
    stage23 = authority['stage23']

    assert stage19['status'] == 'paused'
    assert stage19ba_authority['status'] == 'prepared'
    assert stage19ba_authority['checkpoint_type'] == 'bounded_production_staging_activation_control_baseline'
    assert stage19ba_authority['document'] == 'docs/colonisation-redesign/stage-19-bounded-production-staging-activation.md'
    assert stage19ba_authority['operator_wrapper'] == 'scripts/operator/stage19ba_bounded_production_staging_activation.py'
    assert stage19ba_authority['stage19_remains_paused'] is True
    assert stage19ba_authority['stage23a_merged_to_main'] is True
    assert stage23['stage23a_live_provider_completed'] is True
    assert stage19ba_authority['source_name'] == 'edsm'
    assert stage19ba_authority['manual_operator_invocation_only'] is True
    assert stage19ba_authority['source_identity_required'] is True
    assert stage19ba_authority['source_hash_required'] is True
    assert stage19ba_authority['permitted_tables'] == [
        'source_runs',
        'enrichment_source_runs',
        'staging_edsm_stations',
    ]
    assert stage19ba_authority['initial_row_cap'] == 100
    assert stage19ba_authority['hard_max_rows'] == 100
    assert stage19ba_authority['max_runtime_seconds'] == 900
    assert stage19ba_authority['malformed_row_threshold'] == 0
    assert stage19ba_authority['overlap_protection_required'] is True
    assert stage19ba_authority['schema_drift_fail_closed'] is True
    assert stage19ba_authority['audit_artifact_required'] is True
    assert stage19ba_authority['default_mode_dry_run'] is True
    assert stage19ba_authority['dry_run_filesystem_non_mutating'] is True
    assert stage19ba_authority['commit_refusal_filesystem_non_mutating'] is True
    assert stage19ba_authority['source_uri_display_sanitized'] is True
    assert stage19ba_authority['source_uri_userinfo_forbidden'] is True
    assert stage19ba_authority['query_and_fragment_logging_forbidden'] is True
    assert stage19ba_authority['exact_target_identity_approval_required'] is True
    assert stage19ba_authority['exact_execution_target_approved'] is False
    assert stage19ba_authority['write_execution_authorized'] is False
    assert stage19ba_authority['canonical_apply_authorized'] is False
    assert stage19ba_authority['rebaseline_authorized'] is False
    assert stage19ba_authority['scheduler_service_authorized'] is False
    assert stage19ba_authority['production_like_db_execution_authorized'] is False


@pytest.mark.unit
def test_stage19ba_docs_indexes_and_roadmaps_record_the_separate_dependency():
    document = ' '.join(_read(STAGE19BA_PATH).split())
    readme = _read(README_PATH)
    stage17p = _read(STAGE17P_PATH)
    stage19_roadmap = _read(STAGE19_ROADMAP_PATH)
    parity = _read(LOCAL_CI_PARITY)
    operator_readme = _read(OPERATOR_README_PATH)

    assert STAGE19BA_PATH.exists()
    assert 'bounded production-staging activation contract for a future manual EDSM staging run without authorizing execution in this checkpoint' in document
    assert '`source_runs`' in document
    assert '`enrichment_source_runs`' in document
    assert '`staging_edsm_stations`' in document
    assert '`100` row cap' in document
    assert '`900` seconds' in document
    assert 'runtime' in document
    assert 'filesystem-non-mutating' in document
    assert 'sanitized for display' in document
    assert 'credentials are forbidden' in document
    assert 'query strings/fragments are never logged' in document
    assert 'exact production target approval remains a later gate' in document
    assert 'Stage 23 remains the active product/evidence roadmap' in document
    assert 'stage-19-bounded-production-staging-activation.md' in readme
    assert 'stage-19-bounded-production-staging-activation.md' in stage17p
    assert 'Stage 19BA dependency' in stage19_roadmap
    assert 'stage19ba_bounded_production_staging_activation.py' in operator_readme
    assert 'tests/test_stage19ba_bounded_production_staging_activation.py' in parity


@pytest.mark.unit
def test_stage19ba_build_plan_is_side_effect_free_and_sanitizes_source_uri(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    artifact_dir = tmp_path / 'artifacts'
    args = stage19ba.parse_args(_valid_argv(tmp_path))
    stage19ba.ensure_execution_still_unauthorized(args)
    stage19ba.assert_safe_stage19ba_target(args)
    stage19ba.validate_source_uri(args.source_uri)
    plan = stage19ba.build_activation_plan(
        args,
        sanitized_source_uri=stage19ba.sanitize_source_uri_for_display(args.source_uri),
        artifact_dir_reference=stage19ba.validate_artifact_directory_reference(args.artifact_dir),
    )

    assert plan['execution_authorized'] is False
    assert plan['mode'] == 'dry_run'
    assert plan['source']['name'] == 'edsm'
    assert plan['source']['uri'] == 'https://example.invalid/edsm/stations-20260618.json.gz'
    assert 'token=' not in plan['source']['uri']
    assert '#fragment' not in plan['source']['uri']
    assert plan['limits']['requested_rows'] == 100
    assert plan['limits']['requested_runtime_seconds'] == 900
    assert plan['limits']['hard_max_rows'] == 100
    assert plan['limits']['max_runtime_seconds'] == 900
    assert plan['writes']['permitted_tables'] == [
        'source_runs',
        'enrichment_source_runs',
        'staging_edsm_stations',
    ]
    assert 'schema_drift_fail_closed' in plan['required_checks']
    assert 'canonical_apply_disabled' in plan['required_checks']
    assert 'rebaseline_disabled' in plan['required_checks']
    assert 'scheduler_disabled' in plan['required_checks']
    assert not artifact_dir.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
def test_stage19ba_main_dry_run_json_and_commit_refusal_never_print_password_or_mutate_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('PGPASSWORD', 'ULTRA_SECRET_STAGE19_PASSWORD')
    artifact_dir = tmp_path / 'artifacts'

    dry_run_exit = stage19ba.main(_valid_argv(tmp_path))
    dry_run = capsys.readouterr()
    dry_run_payload = json.loads(dry_run.out)

    assert dry_run_exit == 0
    assert dry_run_payload['execution_authorized'] is False
    assert dry_run_payload['mode'] == 'dry_run'
    assert dry_run_payload['source']['uri'] == 'https://example.invalid/edsm/stations-20260618.json.gz'
    assert 'token=' not in dry_run.out
    assert '#fragment' not in dry_run.out
    assert 'ULTRA_SECRET_STAGE19_PASSWORD' not in dry_run.out
    assert 'ULTRA_SECRET_STAGE19_PASSWORD' not in dry_run.err
    assert not artifact_dir.exists()
    assert list(tmp_path.iterdir()) == []

    commit_exit = stage19ba.main(_valid_argv(tmp_path) + ['--commit', '--confirm-stage19ba'])
    commit_refusal = capsys.readouterr()

    assert commit_exit == 2
    assert 'execution remains unauthorized' in commit_refusal.err
    assert 'ULTRA_SECRET_STAGE19_PASSWORD' not in commit_refusal.out
    assert 'ULTRA_SECRET_STAGE19_PASSWORD' not in commit_refusal.err
    assert not artifact_dir.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
def test_stage19ba_parse_rejects_malformed_sha_source_name_and_bad_limit_shapes(tmp_path: Path):
    bad_sha_argv = _valid_argv(tmp_path)
    bad_sha_argv[bad_sha_argv.index('--source-sha256') + 1] = 'not-a-sha'
    with pytest.raises(SystemExit):
        stage19ba.parse_args(bad_sha_argv)

    bad_source_name_argv = _valid_argv(tmp_path)
    bad_source_name_argv[bad_source_name_argv.index('--source-name') + 1 if '--source-name' in bad_source_name_argv else 0:0] = [
        '--source-name',
        'spansh',
    ]
    with pytest.raises(SystemExit):
        stage19ba.parse_args(bad_source_name_argv)

    bad_limit_argv = _valid_argv(tmp_path)
    bad_limit_argv[bad_limit_argv.index('--limit') + 1] = '101'
    with pytest.raises(SystemExit):
        stage19ba.parse_args(bad_limit_argv)

    bad_timeout_argv = _valid_argv(tmp_path)
    bad_timeout_argv[bad_timeout_argv.index('--timeout-seconds') + 1] = '901'
    with pytest.raises(SystemExit):
        stage19ba.parse_args(bad_timeout_argv)


@pytest.mark.unit
def test_stage19ba_source_uri_validation_rejects_malformed_unsupported_and_userinfo_shapes():
    with pytest.raises(stage19ba.Stage19BaActivationError):
        stage19ba.validate_source_uri('not a uri')

    with pytest.raises(stage19ba.Stage19BaActivationError):
        stage19ba.validate_source_uri('ftp://example.invalid/source.json.gz')

    with pytest.raises(stage19ba.Stage19BaActivationError):
        stage19ba.validate_source_uri('https://user@example.invalid/source.json.gz')

    with pytest.raises(stage19ba.Stage19BaActivationError):
        stage19ba.validate_source_uri('https://user:password@example.invalid/source.json.gz')

    with pytest.raises(stage19ba.Stage19BaActivationError):
        stage19ba.validate_source_uri('file:///')

    stage19ba.validate_source_uri('file:///var/lib/ed-finder/source.json.gz?token=secret#fragment')
    assert (
        stage19ba.sanitize_source_uri_for_display(
            'file:///var/lib/ed-finder/source.json.gz?token=secret#fragment'
        )
        == 'file://<redacted>/source.json.gz'
    )


@pytest.mark.unit
def test_stage19ba_target_validation_fails_closed_for_database_url_label_ports_hosts_and_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv('DATABASE_URL', raising=False)

    args = stage19ba.parse_args(_valid_argv(tmp_path))
    monkeypatch.setenv('DATABASE_URL', 'postgresql://should-not-be-used')
    with pytest.raises(stage19ba.Stage19BaActivationError):
        stage19ba.assert_safe_stage19ba_target(args)
    monkeypatch.delenv('DATABASE_URL', raising=False)

    wrong_label = stage19ba.parse_args(_valid_argv(tmp_path))
    wrong_label.target_label = 'wrong'
    with pytest.raises(stage19ba.Stage19BaActivationError):
        stage19ba.assert_safe_stage19ba_target(wrong_label)

    remote_5432 = stage19ba.parse_args(_valid_argv(tmp_path))
    remote_5432.db_port = '5432'
    with pytest.raises(stage19ba.Stage19BaActivationError):
        stage19ba.assert_safe_stage19ba_target(remote_5432)

    localhost_nonstandard = stage19ba.parse_args(_valid_argv(tmp_path))
    localhost_nonstandard.db_host = 'localhost'
    localhost_nonstandard.db_port = '6432'
    with pytest.raises(stage19ba.Stage19BaActivationError):
        stage19ba.assert_safe_stage19ba_target(localhost_nonstandard)

    incomplete_identity = stage19ba.parse_args(_valid_argv(tmp_path))
    incomplete_identity.db_user = '   '
    with pytest.raises(stage19ba.Stage19BaActivationError):
        stage19ba.assert_safe_stage19ba_target(incomplete_identity)
