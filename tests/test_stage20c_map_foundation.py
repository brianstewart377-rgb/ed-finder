import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
STAGE20C_DOC_PATH = DOCS / 'stage-20c-map-planning-surface-foundation.md'
README_PATH = DOCS / 'README.md'
ROADMAP_PATH = DOCS / 'stage-20-roadmap.md'
WORKSPACE_TABS_PATH = ROOT / 'frontend' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'WorkspaceModeTabs.tsx'
PREVIEW_PATH = ROOT / 'frontend' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'SimulationPreview.tsx'
MAP_VIEW_PATH = ROOT / 'frontend' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'MapFoundationWorkspaceView.tsx'
MAP_TAB_PATH = ROOT / 'frontend' / 'src' / 'features' / 'map' / 'MapTab.tsx'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


@pytest.mark.unit
def test_stage20c_authority_records_map_foundation_without_relaxing_guardrails():
    authority = _json(AUTHORITY_PATH)
    stage20 = authority['stage20']
    stage20c = authority['stage20c_map_foundation']

    assert STAGE20C_DOC_PATH.exists()
    assert stage20['status'] in {'map_foundation_completed', 'sequence_cp_cockpit_completed', 'completed'}
    assert stage20['current_checkpoint'] in {
        'Stage 20C - Map planning surface foundation',
        'Stage 20D - Planner sequence and CP curve cockpit',
        'Stage 20E - Export/operator pack and closeout readiness',
    }
    assert stage20['next_checkpoint'] in {
        'Stage 20D - Planner sequence and CP curve cockpit',
        'Stage 20E - Export/operator pack and closeout readiness',
        None,
    }
    assert stage20['stage20c_map_foundation_completed'] is True

    assert stage20c['status'] == 'completed'
    assert stage20c['frontend_only'] is True
    assert stage20c['workspace_mode'] == 'map'
    assert stage20c['timeline_layer_enabled'] is True
    assert stage20c['timeline_supported_buckets'] == ['month', 'quarter', 'year']
    assert stage20c['stage19_remains_paused'] is True
    assert stage20c['stage19_production_activation_complete'] is False
    assert stage20c['next_stage19_write_lane_authorized'] is False
    assert stage20c['canonical_apply_complete'] is False
    assert stage20c['rebaseline_complete'] is False
    assert stage20c['scheduler_enabled'] is False
    assert stage20c['db_writes_authorized'] is False
    assert stage20c['stage19_operator_commands_authorized'] is False
    assert stage20c['production_like_db_execution_authorized'] is False


@pytest.mark.unit
def test_stage20c_docs_and_frontend_files_expose_map_mode_and_timeline_foundation():
    document = _read(STAGE20C_DOC_PATH)
    roadmap = _read(ROADMAP_PATH)
    readme = _read(README_PATH)
    tabs = _read(WORKSPACE_TABS_PATH)
    preview = _read(PREVIEW_PATH)
    map_view = _read(MAP_VIEW_PATH)
    map_tab = _read(MAP_TAB_PATH)

    assert 'Map workspace mode' in document or '`Map` workspace mode' in document
    assert 'timeline-layer ownership' in document
    assert 'read-only' in document
    assert 'stage-20c-map-planning-surface-foundation.md' in roadmap
    assert 'stage-20c-map-planning-surface-foundation.md' in readme

    assert "'map'" in tabs
    assert 'Spatial context' in tabs
    assert 'MapFoundationWorkspaceView' in preview
    assert 'MapFoundationWorkspaceView' in map_view
    assert 'map-timeline-toggle' in map_tab
    assert 'map-timeline-summary' in map_tab


@pytest.mark.unit
def test_stage20c_local_ci_parity_registration_remains_static_and_safe():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage20c_map_foundation.py' in parity
    assert '--commit' not in parity
    assert 'psql' not in parity
