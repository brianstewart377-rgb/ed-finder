from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE22D_PATH = DOCS / 'stage-22d-export-and-documentation-governance-consolidation.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'
EXPORT_BUILDER_PATH = ROOT / 'frontend' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'exportArtifacts.ts'
EXPORT_VIEW_PATH = ROOT / 'frontend' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'ExportReadinessWorkspaceView.tsx'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def test_stage22d_authority_records_export_governance_completion():
    authority = _json(AUTHORITY_PATH)
    stage22 = authority['stage22']
    stage22d = authority['stage22d']

    assert stage22['current_checkpoint'] == 'Stage 22E - Deferred Stage 19 decision gate and closeout'
    assert stage22['next_checkpoint'] is None
    assert stage22['stage22d_export_governance_consolidation_completed'] is True

    assert stage22d['status'] == 'completed'
    assert stage22d['checkpoint_type'] == 'export_documentation_governance'
    assert stage22d['document'] == 'docs/colonisation-redesign/stage-22d-export-and-documentation-governance-consolidation.md'
    assert stage22d['export_governance_panel_present'] is True
    assert stage22d['governance_json_section_present'] is True
    assert stage22d['governance_markdown_section_present'] is True
    assert stage22d['authority_scope_visible'] is True
    assert stage22d['documentation_reference_list_present'] is True
    assert stage22d['exclusions_visible'] is True
    assert stage22d['historical_context_visible'] is True
    assert stage22d['export_pack_not_authority'] is True
    assert stage22d['private_paths_excluded'] is True
    assert stage22d['runtime_source_files_excluded'] is True
    assert stage22d['operator_artifact_json_not_authority'] is True
    assert stage22d['db_writes_authorized'] is False
    assert stage22d['stage19_operator_commands_authorized'] is False
    assert stage22d['production_like_db_execution_authorized'] is False


def test_stage22d_docs_frontend_sources_and_ci_parity_are_aligned():
    document = _read(STAGE22D_PATH)
    readme = _read(README_PATH)
    parity = _read(LOCAL_CI_PARITY)
    builder = _read(EXPORT_BUILDER_PATH)
    view = _read(EXPORT_VIEW_PATH)

    assert STAGE22D_PATH.exists()
    assert 'governance section in Markdown and JSON exports' in document
    assert 'Export packs are review artifacts, not planner authority.' in document
    assert 'stage-22d-export-and-documentation-governance-consolidation.md' in readme
    assert 'tests/test_stage22d_export_documentation_governance.py' in parity

    assert 'governance =' in builder
    assert 'Review/export artifact only. This pack is not planner authority' in builder
    assert 'Documentation governance' in view
    assert 'export-governance-scope' in view
    assert 'export-governance-exclusions' in view
    assert 'export-governance-references' in view
