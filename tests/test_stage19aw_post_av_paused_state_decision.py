import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
ROADMAP_PATH = ROOT / 'docs' / 'ROADMAP.md'
AV_DOC_PATH = DOCS / 'stage-19av-expanded-source-run-staging-pilot.md'
AW_DOC_PATH = DOCS / 'stage-19aw-post-av-paused-state-decision.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage19aw_records_post_av_decision_checkpoint_without_unpausing_stage19():
    authority = json.loads(_read(AUTHORITY_PATH))
    av_checkpoint = authority['stage19av_completed_checkpoint']
    aw_checkpoint = authority['stage19aw_decision_checkpoint']

    assert authority['stage19'] == {
        'status': 'paused',
        'stage19as_au_status': 'completed',
    }
    assert av_checkpoint['status'] == 'completed'
    assert av_checkpoint['source_run_key'] == 'stage19av-expanded-source-run-staging-pilot-48688d9d46067867'
    assert av_checkpoint['bridge_key'] == 'source_runs:stage19av-expanded-source-run-staging-pilot-48688d9d46067867'
    assert av_checkpoint['artifact'] == '09652a1c6e6ad661415f535a713432b0d3a76aef5b8c931c0b1874e1c52604f4'
    assert av_checkpoint['rows_read'] == 250
    assert av_checkpoint['rows_staged'] == 250
    assert av_checkpoint['rows_rejected'] == 0
    assert av_checkpoint['rows_skipped'] == 0
    assert av_checkpoint['canonical_writes_performed'] is False
    assert av_checkpoint['approved_stage19ar_baseline_preserved'] is True
    assert av_checkpoint['stage19as_au_checkpoint_preserved'] is True
    assert av_checkpoint['stage19au_verification_preserved'] is True
    assert av_checkpoint['stage19_remains_paused'] is True

    assert aw_checkpoint == {
        'status': 'recorded',
        'checkpoint_type': 'post_av_paused_state_decision',
        'recorded_at': '2026-06-15',
        'docs_static_only': True,
        'stage19av_checkpoint_preserved': True,
        'stage19_remains_paused': True,
        'next_execution_lane_authorized': False,
        'read_only_db_verification_authorized': False,
        'bounded_write_preparation_authorized': False,
        'bounded_write_execution_authorized': False,
        'scheduler_service_authorized': False,
        'canonical_apply_authorized': False,
        'rebaseline_authorized': False,
        'stage19_closeout_authorized': False,
        'test_environment_closeout_authorized': False,
        'db_work_recorded': False,
        'source_acquisition_recorded': False,
        'stage19_operator_commands_recorded': False,
        'runtime_source_files_are_authority': False,
        'operator_artifact_json_committed_as_authority': False,
    }


@pytest.mark.unit
def test_stage19aw_doc_and_roadmap_require_explicit_operator_decision_for_next_lane():
    aw_doc = _squash(_read(AW_DOC_PATH))
    av_doc = _squash(_read(AV_DOC_PATH))
    roadmap = _squash(_read(ROADMAP_PATH))

    for fragment in (
        'Stage 19AW - Post-AV Paused-State Decision',
        'Stage 19AW records the paused-state decision checkpoint after Stage 19AV.',
        'Stage 19AV expanded source-run staging pilot is complete and recorded.',
        'Stage 19 remains paused.',
        'No canonical apply is complete.',
        'No rebaseline is complete.',
        'Scheduler and wider service work remain unauthorized.',
        'no next execution lane is authorized yet',
        'must be selected by a separate explicit operator decision',
        'read-only DB verification lane',
        'bounded write preparation lane',
        'bounded write execution lane',
        'scheduler/service lane',
        'canonical apply lane',
        'rebaseline lane',
        'Stage 19 closeout lane',
        'test environment closeout lane',
    ):
        assert fragment in aw_doc

    assert 'Stage 19AV was run on `2026-06-15T06:21:02Z`' in av_doc
    assert 'Stage 19AW is the post-AV paused-state decision checkpoint.' in roadmap
    assert 'docs/static coverage only' in roadmap
    assert 'The next lane must be selected by a separate explicit operator decision.' in roadmap


@pytest.mark.unit
def test_stage19aw_blocks_db_operator_canonical_rebaseline_scheduler_and_runtime_authority():
    aw_doc = _squash(_read(AW_DOC_PATH))

    for fragment in (
        'does not run Stage 19 operator commands',
        'connect to a database',
        'acquire source input',
        'run a staging loader',
        'write staging rows',
        'write canonical tables',
        'run canonical apply',
        'run rebaseline',
        'enable scheduler/service work',
        'read-only DB verification',
        'bounded write preparation',
        'bounded write execution',
        'Stage 19 operator commands',
        'Stage 19AR with `--commit`',
        'Stage 19AS-AU with `--commit`',
        'Stage 19AV with `--commit`',
        'source acquisition',
        'staging loader execution',
        'full source batch execution',
        'database mutation',
        'scheduler, timer, or service-manager work',
        'production-like database targets',
        'host `5432` as a direct Stage 19 target',
        'secrets access or printing',
        'runtime source JSON or operator artifact JSON commits',
    ):
        assert fragment in aw_doc

    assert 'canonical apply is complete.' not in aw_doc.replace('No canonical apply is complete.', '')
    assert 'rebaseline is complete.' not in aw_doc.replace('No rebaseline is complete.', '')


@pytest.mark.unit
def test_stage19aw_local_ci_parity_registration_is_static_only():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage19aw_post_av_paused_state_decision.py' in parity
    assert 'scripts/operator/stage19' not in parity
    assert '--commit' not in parity

