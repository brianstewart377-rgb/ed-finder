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
    assert 'Stage 23 remains the active product/evidence roadmap' in document
    assert 'stage-19-bounded-production-staging-activation.md' in readme
    assert 'stage-19-bounded-production-staging-activation.md' in stage17p
    assert 'Stage 19BA dependency' in stage19_roadmap
    assert 'stage19ba_bounded_production_staging_activation.py' in operator_readme
    assert 'tests/test_stage19ba_bounded_production_staging_activation.py' in parity


@pytest.mark.unit
def test_stage19ba_wrapper_requires_strict_source_target_and_limit_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    args = stage19ba.parse_args(
        [
            '--source-batch-label',
            'edsm-nightly-20260618',
            '--source-uri',
            'https://example.invalid/edsm/stations-20260618.json.gz',
            '--source-sha256',
            'a' * 64,
            '--limit',
            '100',
            '--timeout-seconds',
            '900',
            '--artifact-dir',
            str(tmp_path),
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
    )
    plan = stage19ba.build_activation_plan(args)

    assert plan['execution_authorized'] is False
    assert plan['mode'] == 'dry_run'
    assert plan['source']['name'] == 'edsm'
    assert plan['limits']['requested_rows'] == 100
    assert plan['limits']['requested_runtime_seconds'] == 900
    assert 'schema_drift_fail_closed' in plan['required_checks']
    assert 'canonical_apply_disabled' in plan['required_checks']

    with pytest.raises(SystemExit):
        stage19ba.parse_args(
            [
                '--source-batch-label',
                'edsm-nightly',
                '--source-uri',
                'https://example.invalid/source.json.gz',
                '--source-sha256',
                'not-a-sha',
                '--limit',
                '101',
                '--timeout-seconds',
                '901',
                '--artifact-dir',
                str(tmp_path),
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
        )


@pytest.mark.unit
def test_stage19ba_wrapper_fails_closed_on_unsafe_targets_and_commit_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    local_args = stage19ba.parse_args(
        [
            '--source-batch-label',
            'edsm-nightly',
            '--source-uri',
            'https://example.invalid/source.json.gz',
            '--source-sha256',
            'b' * 64,
            '--limit',
            '100',
            '--timeout-seconds',
            '900',
            '--artifact-dir',
            str(tmp_path),
            '--target-label',
            'production_staging_only',
            '--db-host',
            '127.0.0.1',
            '--db-port',
            '55432',
            '--db-name',
            'warehouse_stage19',
            '--db-user',
            'stage19_loader',
        ]
    )
    with pytest.raises(stage19ba.Stage19BaActivationError):
        stage19ba.build_activation_plan(local_args)

    commit_args = stage19ba.parse_args(
        [
            '--source-batch-label',
            'edsm-nightly',
            '--source-uri',
            'https://example.invalid/source.json.gz',
            '--source-sha256',
            'c' * 64,
            '--limit',
            '100',
            '--timeout-seconds',
            '900',
            '--artifact-dir',
            str(tmp_path),
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
            '--commit',
            '--confirm-stage19ba',
        ]
    )
    with pytest.raises(stage19ba.Stage19BaActivationError):
        stage19ba.ensure_execution_still_unauthorized(commit_args)
