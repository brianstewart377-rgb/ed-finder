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
AX_DOC_PATH = DOCS / 'stage-19ax-readonly-av-safety-gate.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage19ax_records_readonly_av_gate_without_unpausing_stage19():
    authority = json.loads(_read(AUTHORITY_PATH))
    av_checkpoint = authority['stage19av_completed_checkpoint']
    aw_checkpoint = authority['stage19aw_decision_checkpoint']
    ax_checkpoint = authority['stage19ax_readonly_av_safety_gate']

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

    assert aw_checkpoint['status'] == 'recorded'
    assert aw_checkpoint['checkpoint_type'] == 'post_av_paused_state_decision'
    assert aw_checkpoint['stage19_remains_paused'] is True
    assert aw_checkpoint['next_execution_lane_authorized'] is False
    assert aw_checkpoint['read_only_db_verification_authorized'] is False
    assert aw_checkpoint['canonical_apply_authorized'] is False
    assert aw_checkpoint['rebaseline_authorized'] is False
    assert aw_checkpoint['scheduler_service_authorized'] is False

    assert ax_checkpoint == {
        'status': 'completed',
        'checkpoint_type': 'read_only_av_safety_gate',
        'completed_at': '2026-06-16T16:17:31Z',
        'safe_db_target': '127.0.0.1:55432',
        'read_only_db_verification_attempted': True,
        'read_only_db_verification_passed': True,
        'artifact_checksum_verification_attempted': True,
        'artifact_checksum_verification_passed': True,
        'source_run_key': 'stage19av-expanded-source-run-staging-pilot-48688d9d46067867',
        'bridge_key': 'source_runs:stage19av-expanded-source-run-staging-pilot-48688d9d46067867',
        'artifact': '09652a1c6e6ad661415f535a713432b0d3a76aef5b8c931c0b1874e1c52604f4',
        'artifact_path': (
            '/home/brian/.local/share/ed-finder/operator-artifacts/stage-19av/'
            'stage19av_edsm_import_20260615T062102Z.json'
        ),
        'rows_read': 250,
        'rows_staged': 250,
        'rows_rejected': 0,
        'rows_skipped': 0,
        'staging_prerequisite_source_run_key': (
            '7fe4382fbde60752e026b576d92e0352c01d85799613884d2b2e7ee57cd3f5f3'
        ),
        'stage19ar_baseline_preserved': True,
        'stage19as_au_checkpoint_preserved': True,
        'stage19au_verification_preserved': True,
        'stage19aw_paused_decision_preserved': True,
        'stage19_remains_paused': True,
        'next_write_lane_authorized': False,
        'canonical_apply_complete': False,
        'rebaseline_complete': False,
        'scheduler_enabled': False,
        'db_mutation_performed': False,
        'stage19_operator_write_commands_run': False,
        'source_acquisition_run': False,
        'staging_loader_run': False,
        'canonical_apply_run': False,
        'rebaseline_run': False,
        'scheduler_service_enabled': False,
        'runtime_source_files_are_authority': False,
        'operator_artifact_json_committed_as_authority': False,
    }


@pytest.mark.unit
def test_stage19ax_doc_and_roadmap_record_passed_readonly_evidence():
    ax_doc = _squash(_read(AX_DOC_PATH))
    av_doc = _squash(_read(AV_DOC_PATH))
    aw_doc = _squash(_read(AW_DOC_PATH))
    roadmap = _squash(_read(ROADMAP_PATH))

    for fragment in (
        'Stage 19AX - Read-Only AV Safety Gate',
        'Stage 19AX records the read-only post-AV safety-gate verification selected after Stage 19AW.',
        'safe DB target: `127.0.0.1:55432`',
        'query mode: SELECT-only/read-only verification',
        'AV source run: `stage19av-expanded-source-run-staging-pilot-48688d9d46067867`',
        'AV bridge: `source_runs:stage19av-expanded-source-run-staging-pilot-48688d9d46067867`',
        'AV artifact checksum: `09652a1c6e6ad661415f535a713432b0d3a76aef5b8c931c0b1874e1c52604f4`',
        'artifact checksum verification: `passed`',
        'rows read: `250`',
        'rows staged: `250`',
        'rows rejected: `0`',
        'rows skipped: `0`',
        'staging prerequisite source run found: `7fe4382fbde60752e026b576d92e0352c01d85799613884d2b2e7ee57cd3f5f3`',
        'Stage 19AR baseline preserved: `true`',
        'Stage 19AS-AU checkpoint preserved: `true`',
        'Stage 19AU read-only verification preserved: `true`',
        'Stage 19AW paused-state decision preserved: `true`',
        'Stage 19 remains paused: `true`',
    ):
        assert fragment in ax_doc

    assert 'Stage 19AV was run on `2026-06-15T06:21:02Z`' in av_doc
    assert 'Stage 19AW records the paused-state decision checkpoint after Stage 19AV.' in aw_doc
    assert 'Stage 19AX is the completed read-only AV safety-gate verification selected after Stage 19AW.' in roadmap
    assert 'does not authorize any next write lane' in roadmap


@pytest.mark.unit
def test_stage19ax_blocks_write_lanes_runtime_authority_and_forbidden_work():
    ax_doc = _squash(_read(AX_DOC_PATH))

    for fragment in (
        'Stage 19AX is read-only verification only.',
        'database mutation',
        'source acquisition',
        'staging loader execution',
        'Stage 19 operator write commands',
        'canonical apply',
        'rebaseline',
        'scheduler/service enablement',
        'next write lane authorized: `false`',
        'canonical apply complete: `false`',
        'rebaseline complete: `false`',
        'scheduler/service enabled: `false`',
        'canonical writes performed: `false`',
        'runtime source files committed as authority: `false`',
        'operator artifact JSON committed as authority: `false`',
        'Runtime source files and operator artifact JSON files remain evidence only',
    ):
        assert fragment in ax_doc

    assert 'next write lane authorized: `true`' not in ax_doc
    assert 'canonical apply complete: `true`' not in ax_doc
    assert 'rebaseline complete: `true`' not in ax_doc
    assert 'scheduler/service enabled: `true`' not in ax_doc


@pytest.mark.unit
def test_stage19ax_local_ci_parity_registration_is_static_only():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage19ax_readonly_av_safety_gate.py' in parity
    assert 'scripts/operator/stage19' not in parity
    assert '--commit' not in parity

