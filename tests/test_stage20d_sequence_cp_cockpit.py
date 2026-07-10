import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
STAGE20D_DOC_PATH = DOCS / 'stage-20d-planner-sequence-cp-curve-cockpit.md'
README_PATH = DOCS / 'README.md'
ROADMAP_PATH = DOCS / 'stage-20-roadmap.md'
WORKSPACE_TABS_PATH = ROOT / 'frontend' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'WorkspaceModeTabs.tsx'
PREVIEW_PATH = ROOT / 'frontend' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'SimulationPreview.tsx'
SEQUENCE_VIEW_PATH = ROOT / 'frontend' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'SequenceCockpitWorkspaceView.tsx'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


@pytest.mark.unit
def test_stage20d_authority_records_sequence_cp_cockpit_without_auto_preview_or_write_lanes():
    authority = _json(AUTHORITY_PATH)
    stage20 = authority['stage20']
    stage20d = authority['stage20d_sequence_cp_cockpit']

    assert STAGE20D_DOC_PATH.exists()
    assert stage20['status'] in {'sequence_cp_cockpit_completed', 'completed'}
    assert stage20['current_checkpoint'] in {
        'Stage 20D - Planner sequence and CP curve cockpit',
        'Stage 20E - Export/operator pack and closeout readiness',
    }
    assert stage20['next_checkpoint'] in {
        'Stage 20E - Export/operator pack and closeout readiness',
        None,
    }
    assert stage20['stage20d_sequence_cp_cockpit_completed'] is True

    assert stage20d['status'] == 'completed'
    assert stage20d['frontend_only'] is True
    assert stage20d['workspace_mode'] == 'sequence'
    assert stage20d['manual_preview_only'] is True
    assert stage20d['auto_preview_enabled'] is False
    assert stage20d['build_plan_mutation_from_sequence_review'] is False
    assert stage20d['stage19_remains_paused'] is True
    assert stage20d['next_stage19_write_lane_authorized'] is False
    assert stage20d['canonical_apply_complete'] is False
    assert stage20d['rebaseline_complete'] is False
    assert stage20d['scheduler_enabled'] is False
    assert stage20d['db_writes_authorized'] is False
    assert stage20d['stage19_operator_commands_authorized'] is False
    assert stage20d['production_like_db_execution_authorized'] is False


@pytest.mark.unit
def test_stage20d_docs_and_frontend_files_expose_sequence_mode_and_manual_preview_boundary():
    document = _read(STAGE20D_DOC_PATH)
    roadmap = _read(ROADMAP_PATH)
    readme = _read(README_PATH)
    tabs = _read(WORKSPACE_TABS_PATH)
    preview = _read(PREVIEW_PATH)
    sequence_view = _read(SEQUENCE_VIEW_PATH)

    assert '`Sequence` workspace mode' in document
    assert 'manual Run Preview' in document or 'manual Preview' in document
    assert 'stage-20d-planner-sequence-cp-curve-cockpit.md' in roadmap
    assert 'stage-20d-planner-sequence-cp-curve-cockpit.md' in readme

    assert "'sequence'" in tabs
    assert 'CP tradeoffs' in tabs
    assert 'SequenceCockpitWorkspaceView' in preview
    assert 'Planner sequence cockpit' in sequence_view
    assert 'Run Preview' in sequence_view
    assert 'CpSummary' in sequence_view
    assert 'CpTimelinePanel' in sequence_view
    assert 'CpRepairPanel' in sequence_view


@pytest.mark.unit
def test_stage20d_local_ci_parity_registration_remains_static_and_safe():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage20d_sequence_cp_cockpit.py' in parity
    assert '--commit' not in parity
    assert 'psql' not in parity
