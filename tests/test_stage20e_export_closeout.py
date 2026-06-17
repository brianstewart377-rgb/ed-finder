import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
STAGE20E_DOC_PATH = DOCS / 'stage-20e-export-operator-pack-closeout-readiness.md'
README_PATH = DOCS / 'README.md'
ROADMAP_PATH = DOCS / 'stage-20-roadmap.md'
WORKSPACE_TABS_PATH = ROOT / 'frontend-v2' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'WorkspaceModeTabs.tsx'
PREVIEW_PATH = ROOT / 'frontend-v2' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'SimulationPreview.tsx'
EXPORT_VIEW_PATH = ROOT / 'frontend-v2' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'ExportReadinessWorkspaceView.tsx'
EXPORT_ARTIFACTS_PATH = ROOT / 'frontend-v2' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'exportArtifacts.ts'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


@pytest.mark.unit
def test_stage20e_authority_records_export_closeout_and_stage_completion():
    authority = _json(AUTHORITY_PATH)
    stage20 = authority['stage20']
    stage20e = authority['stage20e_export_closeout']

    assert STAGE20E_DOC_PATH.exists()
    assert stage20['status'] == 'completed'
    assert stage20['current_checkpoint'] == 'Stage 20E - Export/operator pack and closeout readiness'
    assert stage20['next_checkpoint'] is None
    assert stage20['stage20e_export_closeout_completed'] is True
    assert stage20['closeout_ready'] is True

    assert stage20e['status'] == 'completed'
    assert stage20e['workspace_mode'] == 'export'
    assert stage20e['exports_markdown'] is True
    assert stage20e['exports_json'] is True
    assert stage20e['exports_csv'] is True
    assert stage20e['closeout_ready'] is True
    assert stage20e['stage20_complete'] is True
    assert stage20e['stage19_remains_paused'] is True
    assert stage20e['stage19_production_activation_complete'] is False
    assert stage20e['next_stage19_write_lane_authorized'] is False
    assert stage20e['canonical_apply_complete'] is False
    assert stage20e['rebaseline_complete'] is False
    assert stage20e['scheduler_enabled'] is False
    assert stage20e['db_writes_authorized'] is False
    assert stage20e['stage19_operator_commands_authorized'] is False
    assert stage20e['production_like_db_execution_authorized'] is False


@pytest.mark.unit
def test_stage20e_docs_and_frontend_files_expose_export_mode_and_artifact_builder():
    document = _read(STAGE20E_DOC_PATH)
    roadmap = _read(ROADMAP_PATH)
    readme = _read(README_PATH)
    tabs = _read(WORKSPACE_TABS_PATH)
    preview = _read(PREVIEW_PATH)
    export_view = _read(EXPORT_VIEW_PATH)
    export_artifacts = _read(EXPORT_ARTIFACTS_PATH)

    assert '`Export` workspace mode' in document
    assert 'Markdown, JSON, and CSV' in document
    assert 'Stage 20 is complete' in document
    assert 'stage-20e-export-operator-pack-closeout-readiness.md' in roadmap
    assert 'stage-20e-export-operator-pack-closeout-readiness.md' in readme

    assert "'export'" in tabs
    assert 'Review packs' in tabs
    assert 'ExportReadinessWorkspaceView' in preview
    assert 'Export mode' in export_view
    assert 'export-markdown' in export_view
    assert 'export-json' in export_view
    assert 'export-csv' in export_view
    assert 'planned' in export_artifacts
    assert 'projected' in export_artifacts
    assert 'observed' in export_artifacts
    assert 'inferred' in export_artifacts
    assert 'warehouse' in export_artifacts


@pytest.mark.unit
def test_stage20e_local_ci_parity_registration_remains_static_and_safe():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage20e_export_closeout.py' in parity
    assert '--commit' not in parity
    assert 'psql' not in parity
