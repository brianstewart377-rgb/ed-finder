from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE18H2_PATH = DOCS / 'stage-18h2-readonly-backend-warehouse-evidence-endpoint.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'
API_SRC = ROOT / 'apps' / 'api' / 'src'

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')

import warehouse_planner_evidence as backend  # noqa: E402


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


@pytest.mark.unit
def test_stage18h2_authority_records_readonly_endpoint_scaffold():
    authority = _json(AUTHORITY_PATH)
    stage18h1 = authority['stage18h1']
    stage18h2 = authority['stage18h2']

    assert STAGE18H2_PATH.exists()
    assert authority['stage21']['next_checkpoint'] is None

    assert stage18h1['status'] == 'completed'
    assert stage18h1['implementation_started'] is True
    assert stage18h1['implementation_authorized'] is True

    assert stage18h2['status'] == 'completed'
    assert stage18h2['checkpoint_type'] == 'backend_endpoint_scaffold'
    assert stage18h2['document'] == 'docs/colonisation-redesign/stage-18h2-readonly-backend-warehouse-evidence-endpoint.md'
    assert stage18h2['route'] == '/api/colony-planner/system/{id64}/warehouse-planner-evidence'
    assert stage18h2['response_schema_version'] == 'warehouse_planner_evidence/v1'
    assert stage18h2['read_only'] is True
    assert stage18h2['fixture_backed_safe_examples'] is True
    assert stage18h2['artifact_freshness_fallback_supported'] is True
    assert stage18h2['openapi_included'] is False
    assert stage18h2['live_endpoint_added'] is True
    assert stage18h2['planner_fetch_added'] is False
    assert stage18h2['planner_ui_changed'] is False
    assert stage18h2['db_writes_authorized'] is False
    assert stage18h2['production_like_db_execution_authorized'] is False


@pytest.mark.unit
def test_stage18h2_backend_builder_returns_report_only_and_safe_unavailable_states(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        backend,
        'read_warehouse_status_snapshot',
        lambda _path: {
            'available': True,
            'message': 'Warehouse status artifact loaded.',
            'artifact': {'file_name': 'warehouse-status.json', 'updated_at': '2026-06-17T14:00:00+00:00'},
            'latest_reconciliation_run': {'report_file_name': 'run-20260617.json'},
            'evidence_health': {'stale_records': 0},
            'warnings': [],
        },
    )

    available = backend.build_warehouse_planner_evidence(12866676218109)
    stale = backend.build_warehouse_planner_evidence(9466842275401)
    fallback = backend.build_warehouse_planner_evidence(42)

    assert available.schema_version == 'warehouse_planner_evidence/v1'
    assert available.system_id64 == 12866676218109
    assert available.freshness.status == 'fresh'
    assert available.source_run.source_name == 'warehouse_reconciliation'
    assert available.source_run.run_key == 'warehouse/run-20260617.json'
    assert available.evidence_summary.availability == 'report_only'
    assert available.evidence_summary.report_only is True
    assert available.evidence_summary.manual_review_required is False
    assert available.evidence_summary.items

    assert stale.evidence_summary.availability == 'report_only'
    assert stale.evidence_summary.manual_review_required is True
    assert stale.freshness.status == 'stale'
    assert any(item.label == 'stale' for item in stale.evidence_summary.items)

    assert fallback.evidence_summary.availability == 'unavailable'
    assert fallback.evidence_summary.report_only is True
    assert fallback.evidence_summary.items == []
    assert any('fallback' in warning.lower() for warning in fallback.warnings)


@pytest.mark.unit
def test_stage18h2_docs_and_ci_parity_register_the_endpoint_scaffold():
    document = _read(STAGE18H2_PATH)
    readme = _read(README_PATH)
    parity = _read(LOCAL_CI_PARITY)

    for fragment in (
        'GET /api/colony-planner/system/{id64}/warehouse-planner-evidence',
        'warehouse_planner_evidence/v1',
        'hidden from OpenAPI',
        'unavailable',
        'planner-safe backend endpoint scaffold',
    ):
        assert fragment in document

    assert 'stage-18h2-readonly-backend-warehouse-evidence-endpoint.md' in readme
    assert 'tests/test_stage18h2_warehouse_planner_evidence_endpoint.py' in parity
