import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
ROADMAP_PATH = DOCS / 'stage-19-data-warehouse-utopia-roadmap.md'
AY_DOC_PATH = DOCS / 'stage-19ay-test-environment-closeout.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'

AV_SOURCE_RUN_KEY = 'stage19av-expanded-source-run-staging-pilot-48688d9d46067867'
AV_BRIDGE_KEY = f'source_runs:{AV_SOURCE_RUN_KEY}'
AV_ARTIFACT = '09652a1c6e6ad661415f535a713432b0d3a76aef5b8c931c0b1874e1c52604f4'
AV_ARTIFACT_PATH = (
    '/home/brian/.local/share/ed-finder/operator-artifacts/stage-19av/'
    'stage19av_edsm_import_20260615T062102Z.json'
)
AV_PREREQ = '7fe4382fbde60752e026b576d92e0352c01d85799613884d2b2e7ee57cd3f5f3'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage19ay_authority_records_closeout_without_unpausing_stage19():
    authority = json.loads(_read(AUTHORITY_PATH))
    ay = authority['stage19ay_test_environment_closeout']

    assert authority['stage19'] == {
        'status': 'paused',
        'stage19as_au_status': 'completed',
    }
    assert ay['status'] == 'completed'
    assert ay['checkpoint_type'] == 'test_environment_safety_programme_closeout_preparation'
    assert ay['docs_static_only'] is True
    assert ay['closeout_classification'] == 'stage20_planning_ready'
    assert ay['test_environment_safety_programme_complete'] is True
    assert ay['stage19_production_activation_complete'] is False
    assert ay['stage20_planning_ready'] is True
    assert ay['stage19_remains_paused'] is True
    assert ay['next_write_lane_authorized'] is False
    assert ay['canonical_apply_complete'] is False
    assert ay['canonical_apply_authorized'] is False
    assert ay['rebaseline_complete'] is False
    assert ay['rebaseline_authorized'] is False
    assert ay['scheduler_enabled'] is False
    assert ay['scheduler_service_authorized'] is False
    assert ay['production_activation_deferred'] is True
    assert ay['unresolved_blockers'] == []


@pytest.mark.unit
def test_stage19ay_preserves_completed_evidence_chain_and_av_ax_identity():
    authority = json.loads(_read(AUTHORITY_PATH))
    ay = authority['stage19ay_test_environment_closeout']
    av = authority['stage19av_completed_checkpoint']
    ax = authority['stage19ax_readonly_av_safety_gate']

    assert ay['preserved_checkpoints'] == {
        'stage19ar_baseline': True,
        'stage19as_au_checkpoint': True,
        'stage19au_verification': True,
        'stage19av_checkpoint': True,
        'stage19aw_paused_decision': True,
        'stage19ax_verification': True,
    }
    assert av['source_run_key'] == AV_SOURCE_RUN_KEY
    assert av['bridge_key'] == AV_BRIDGE_KEY
    assert av['artifact'] == AV_ARTIFACT
    assert av['artifact_path'] == AV_ARTIFACT_PATH
    assert (av['rows_read'], av['rows_staged'], av['rows_rejected'], av['rows_skipped']) == (250, 250, 0, 0)
    assert av['staging_prerequisite_source_run_key'] == AV_PREREQ
    assert av['canonical_writes_performed'] is False

    assert ax['status'] == 'completed'
    assert ax['read_only_db_verification_passed'] is True
    assert ax['artifact_checksum_verification_passed'] is True
    assert ax['source_run_key'] == AV_SOURCE_RUN_KEY
    assert ax['bridge_key'] == AV_BRIDGE_KEY
    assert ax['artifact'] == AV_ARTIFACT
    assert (ax['rows_read'], ax['rows_staged'], ax['rows_rejected'], ax['rows_skipped']) == (250, 250, 0, 0)

    assert ay['stage19av_proof'] == {
        'source_run_key': AV_SOURCE_RUN_KEY,
        'bridge_key': AV_BRIDGE_KEY,
        'artifact': AV_ARTIFACT,
        'artifact_path': AV_ARTIFACT_PATH,
        'rows_read': 250,
        'rows_staged': 250,
        'rows_rejected': 0,
        'rows_skipped': 0,
        'staging_prerequisite_source_run_key': AV_PREREQ,
        'canonical_writes_performed': False,
    }


@pytest.mark.unit
def test_stage19ay_evidence_matrix_classifies_complete_deferred_and_no_blockers():
    authority = json.loads(_read(AUTHORITY_PATH))
    matrix = authority['stage19ay_test_environment_closeout']['evidence_matrix']

    for key in (
        'project_state_resolver',
        'db_isolation_guardrails',
        'test_fortress_aq1_recovery',
        'operator_script_contract',
        'safe_target_enforcement',
        'bounded_staging_only_loader_path',
        'stage19ar_baseline',
        'stage19as_au_100_row_expansion',
        'stage19au_readonly_verification',
        'stage19av_250_row_expansion',
        'stage19ax_readonly_verification',
        'runtime_source_exclusion',
        'operator_artifact_exclusion',
        'secret_handling',
        'local_ci_parity',
    ):
        assert matrix[key] == 'complete_and_verified'

    assert matrix['disposable_postgresql_constraint_coverage'] == 'complete_static_only'
    for key in (
        'canonical_apply',
        'rebaseline',
        'scheduler_service_activation',
        'production_like_db_execution',
    ):
        assert matrix[key] == 'deliberately_deferred'

    assert 'unresolved_blocker' not in set(matrix.values())


@pytest.mark.unit
def test_stage19ay_doc_and_roadmap_keep_production_activation_deferred():
    ay_doc = _squash(_read(AY_DOC_PATH))
    roadmap = _squash(_read(ROADMAP_PATH))

    for fragment in (
        'Stage 19AY - Test-Environment Safety Programme Closeout',
        'Stage 19 test-environment/safety programme complete: `true`',
        'Stage 19 production activation complete: `false`',
        'closeout classification: `stage20_planning_ready`',
        'Stage 20 planning may begin independently of deferred Stage 19 production activation.',
        'Production activation, canonical apply, rebaseline, scheduler/service work, and any future write lane remain separately gated',
        'canonical apply complete: `false`',
        'rebaseline complete: `false`',
        'scheduler/service enabled: `false`',
        'No capability is classified as `unresolved_blocker` for Stage 19AY.',
        'Deferred production/canonical work is not a closeout blocker for Stage 19AY',
    ):
        assert fragment in ay_doc

    assert 'Stage 19AY is the completed docs/static test-environment and safety-programme closeout-preparation checkpoint.' in roadmap
    assert '`stage20_planning_ready`' in roadmap
    assert 'Stage 19 remains paused.' in roadmap
    assert 'No DB commands, read-only DB queries, artifact checksum commands' in roadmap


@pytest.mark.unit
def test_stage19ay_did_not_record_db_operator_or_runtime_artifact_work():
    authority = json.loads(_read(AUTHORITY_PATH))
    ay = authority['stage19ay_test_environment_closeout']
    ay_doc = _squash(_read(AY_DOC_PATH))

    for key in (
        'db_commands_run',
        'read_only_db_verification_run',
        'artifact_checksum_rerun',
        'stage19_operator_commands_run',
        'source_acquisition_run',
        'staging_loader_run',
        'db_mutation_performed',
        'production_like_db_execution',
        'direct_host_5432_target_used',
        'runtime_source_files_are_authority',
        'operator_artifact_json_committed_as_authority',
    ):
        assert ay[key] is False

    for fragment in (
        'Stage 19AY did not run database commands',
        'read-only database queries',
        'checksum commands',
        'Stage 19 operator commands',
        'source acquisition',
        'staging loaders',
        'canonical apply',
        'rebaseline',
        'scheduler/timer/service work',
    ):
        assert fragment in ay_doc


@pytest.mark.unit
def test_stage19ay_local_ci_parity_registration_is_static_only():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage19ay_test_environment_closeout.py' in parity
    assert 'scripts/operator/stage19' not in parity
    assert '--commit' not in parity
