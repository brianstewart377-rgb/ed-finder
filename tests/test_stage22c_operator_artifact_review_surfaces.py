from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE22C_PATH = DOCS / 'stage-22c-operator-artifact-review-and-audit-surfaces.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'
EXPORT_BUILDER_PATH = ROOT / 'frontend' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'exportArtifacts.ts'
EXPORT_VIEW_PATH = ROOT / 'frontend' / 'src' / 'features' / 'system-detail' / 'simulation-preview' / 'ExportReadinessWorkspaceView.tsx'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def test_stage22c_authority_records_operator_review_surface_completion():
    authority = _json(AUTHORITY_PATH)
    stage22 = authority['stage22']
    stage22c = authority['stage22c']

    assert stage22['current_checkpoint'] == 'Stage 22E - Deferred Stage 19 decision gate and closeout'
    assert stage22['next_checkpoint'] is None
    assert stage22['stage22c_operator_review_surfaces_completed'] is True

    assert stage22c['status'] == 'completed'
    assert stage22c['checkpoint_type'] == 'operator_artifact_review_surfaces'
    assert stage22c['document'] == 'docs/colonisation-redesign/stage-22c-operator-artifact-review-and-audit-surfaces.md'
    assert stage22c['export_workspace_audit_surface_present'] is True
    assert stage22c['operator_review_focus_items_present'] is True
    assert stage22c['sanitized_references_present'] is True
    assert stage22c['export_safeguards_present'] is True
    assert stage22c['section_coverage_checks_present'] is True
    assert stage22c['operator_review_json_section_present'] is True
    assert stage22c['operator_review_markdown_section_present'] is True
    assert stage22c['private_paths_excluded'] is True
    assert stage22c['runtime_artifacts_authority'] is False
    assert stage22c['db_writes_authorized'] is False
    assert stage22c['stage19_operator_commands_authorized'] is False
    assert stage22c['production_like_db_execution_authorized'] is False


def test_stage22c_docs_frontend_sources_and_ci_parity_are_aligned():
    document = ' '.join(_read(STAGE22C_PATH).split())
    readme = _read(README_PATH)
    parity = _read(LOCAL_CI_PARITY)
    builder = _read(EXPORT_BUILDER_PATH)
    view = _read(EXPORT_VIEW_PATH)

    assert STAGE22C_PATH.exists()
    assert 'operator-review and audit section' in document
    assert 'source-run key, artifact basename, and warehouse posture' in document
    assert 'Read-only only.' in document
    assert 'stage-22c-operator-artifact-review-and-audit-surfaces.md' in readme
    assert 'tests/test_stage22c_operator_artifact_review_surfaces.py' in parity

    assert 'operator_review' in builder
    assert 'Source run references are informational review aids only and do not become planner authority.' in builder
    assert 'Operator review and audit' in view
    assert 'operator-review-focus' in view
    assert 'operator-review-references' in view
    assert 'operator-review-sections' in view
